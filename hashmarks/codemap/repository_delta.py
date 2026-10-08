from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from hashmarks.digest import Digest
from hashmarks.file_store import UnstableFileError
from hashmarks.freshness import freshness_state
from hashmarks.operation_contract import operation_schema
from hashmarks.paths import normalize_relative_path

from .change_impact import ChangeImpactOptions
from .decision_session import diagnostic_producer
from .freshness_map import FreshnessMapOptions
from .source_line_correspondence import (
    diagnostic_line_correspondence,
    source_line_anchors,
    source_shape,
)

if TYPE_CHECKING:
    from pathlib import Path

    from .engine import CodeMap


@dataclass(frozen=True, slots=True)
class RepositoryGenerationBinding:
    repository_identity: str
    codemap_generation: int


@dataclass(frozen=True, slots=True)
class _RepositoryMemberSource:
    rel: str
    path: Path
    row: Mapping[str, object] | None
    visibility: str
    indexed_revision: str


@dataclass(frozen=True, slots=True)
class _RepositoryMemberRead:
    raw: bytes | None
    digest: Digest | None


@dataclass(slots=True)
class _ScopedSourceAggregation:
    """Ephemeral request-only accumulator; not a source or index authority."""

    paths: list[str]
    literal: str
    limit: int
    max_total_bytes: int
    max_member_bytes: int
    start_generation: int
    members: list[dict[str, object]] = field(default_factory=list)
    occurrences: list[dict[str, object]] = field(default_factory=list)
    match_count: int = 0
    consumed_bytes: int = 0
    complete: bool = True
    members_fresh: bool = True

    def add(self, path: str, packet: Mapping[str, object]) -> None:
        """Accumulate only actually scanned bytes and emitted match locations."""
        shape = packet.get("source_shape")
        if isinstance(shape, Mapping):
            self.consumed_bytes += cast("int", shape.get("bytes") or 0)
        count = packet.get("observed_match_count")
        observed = packet.get("availability") == "observed" and isinstance(count, int)
        self.complete = self.complete and observed
        self.members_fresh = self.members_fresh and packet.get("freshness") == "current"
        source_rows = cast("list[dict[str, object]]", packet["occurrences"])
        selected = (
            deepcopy(source_rows[: max(0, self.limit - len(self.occurrences))])
            if observed
            else []
        )
        if observed:
            self.match_count += cast("int", count)
            self.occurrences.extend(selected)
        member = cast("Mapping[str, object]", packet["member"])
        self.members.append(
            {
                "path": path,
                "state": member["state"],
                "reason": member.get("reason"),
                "member_revision": member.get("member_revision"),
                "availability": packet["availability"],
                "observed_match_count": count,
                "returned_occurrence_count": len(selected),
            }
        )


def _observer_descriptor() -> dict[str, object]:
    """Describe the observer capability separately from repository identity."""
    return {
        "producer": "hashmarks",
        "surface": "repository-intelligence",
        "schema": "hashmarks.repository-observer.v1",
        "capabilities": [
            "affected",
            "dependencies",
            "evidence-bindings",
            "freshness",
            "ownership",
            "symbols",
            "verification",
        ],
    }


REPOSITORY_SNAPSHOT_SCHEMA = "hashmarks.repository-intelligence-snapshot.v1"
REPOSITORY_DELTA_SCHEMA = "hashmarks.repository-intelligence-delta.v1"
DIAGNOSTIC_DELTA_SCHEMA = "hashmarks.diagnostic-observation-delta.v1"


class RepositoryDeltaMixin:
    """Bounded semantic snapshots and deltas over repository intelligence.

    F3 owns no historical repository store.  A caller retains the earlier
    producer snapshot and supplies it back after a later repository state has
    been admitted.  Hashmarks derives the current snapshot from existing
    ownership/impact/verification/freshness authority and emits only changed
    facts plus compact semantic summaries.
    """

    def _repository_observer_packet(self) -> dict[str, object]:
        """Return the canonical observer capability descriptor with stable identity."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        observer = _observer_descriptor()
        return {
            **observer,
            "identity": "sha256:"
            + self._packet_digest("hashmarks.repository-observer.v1", observer),
        }

    @staticmethod
    def _evidence_identity(schema: str, value: Mapping[str, object]) -> str:
        """Return a deterministic domain-separated identity for observer evidence."""
        import hashlib
        import json

        raw = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        digest = hashlib.sha256(schema.encode("utf-8") + b"\0" + raw).hexdigest()
        return f"sha256:{digest}"

    @staticmethod
    def _delta_mapping(value: object, *, field: str) -> Mapping[str, object]:
        if not isinstance(value, Mapping):
            raise ValueError(f"{field} must be an object")
        return value

    def _repository_member_source(
        self, relpath: str
    ) -> _RepositoryMemberSource | dict[str, object]:
        self = cast("CodeMap", self)
        rel = normalize_relative_path(relpath, allow_root=False)
        decision = self.policy.decide(rel)
        if not decision.index or decision.evidence_visibility.value == "deny":
            return {
                "path": rel,
                "state": "unsupported",
                "reason": "repository-evidence-denied",
            }
        if not self._path_admitted_for_analysis(rel):
            return {
                "path": rel,
                "state": "unsupported",
                "reason": "repository-evidence-not-admitted",
            }
        path = self.workspace / rel
        cursor = self.workspace
        for part in rel.split("/"):
            cursor = cursor / part
            if cursor.is_symlink():
                return {
                    "path": rel,
                    "state": "unsupported",
                    "reason": "symlink-evidence-not-observed",
                }
        if not path.is_file():
            return {
                "path": rel,
                "state": "known-absent",
                "reason": "member-not-present",
            }
        row = self._session_file_row(rel)
        visibility = (
            str(row.get("evidence_visibility") or decision.evidence_visibility.value)
            if row is not None
            else decision.evidence_visibility.value
        )
        indexed_revision = str(row.get("file_digest") or "") if row is not None else ""
        return _RepositoryMemberSource(
            rel=rel,
            path=path,
            row=row,
            visibility=visibility,
            indexed_revision=indexed_revision,
        )

    def _read_repository_member_source(
        self,
        source: _RepositoryMemberSource,
        *,
        include_bytes: bool,
    ) -> _RepositoryMemberRead | dict[str, object]:
        self = cast("CodeMap", self)
        try:
            if include_bytes:
                raw, digest = self.file_store.read_bytes_stable(source.path)
            elif source.row is None:
                digest = self.file_store.digest(
                    source.path,
                    workspace=self.workspace,
                    relative_path=source.rel,
                    force=True,
                )
                raw = None
            else:
                digest = None
                raw = None
        except FileNotFoundError:
            return {
                "path": source.rel,
                "state": "known-absent",
                "reason": "member-not-present",
            }
        except (OSError, UnstableFileError):
            return {
                "path": source.rel,
                "state": "unknown",
                "reason": "member-read-unstable-or-unavailable",
                **(
                    {"member_revision": source.indexed_revision}
                    if source.indexed_revision
                    else {}
                ),
                "evidence_visibility": source.visibility,
                "index_state": "indexed" if source.row is not None else "unindexed",
            }
        return _RepositoryMemberRead(raw, digest)

    def _repository_member_observation(
        self,
        relpath: str,
        *,
        include_bytes: bool = False,
    ) -> tuple[dict[str, object], bytes | None]:
        """Observe one repository member through canonical policy/revision authority."""
        self = cast("CodeMap", self)
        source = self._repository_member_source(relpath)
        if isinstance(source, dict):
            return source, None
        base: dict[str, object] = {"path": source.rel}
        row = source.row
        visibility = source.visibility
        indexed_revision = source.indexed_revision

        if include_bytes and visibility != "source":
            return (
                {
                    **base,
                    "state": "unsupported",
                    "reason": "source-evidence-not-visible",
                    **(
                        {"member_revision": indexed_revision}
                        if indexed_revision
                        else {}
                    ),
                    "evidence_visibility": visibility,
                    "index_state": "indexed" if row is not None else "unindexed",
                },
                None,
            )

        read = self._read_repository_member_source(source, include_bytes=include_bytes)
        if isinstance(read, dict):
            return read, None
        raw, digest = read.raw, read.digest

        if row is not None:
            if digest is not None and digest.hash != indexed_revision:
                return (
                    {
                        **base,
                        "state": "unknown",
                        "reason": "member-revision-mismatch",
                        "member_revision": indexed_revision,
                        "evidence_visibility": visibility,
                        "index_state": "indexed",
                    },
                    None,
                )
            revision = indexed_revision
            index_state = "indexed"
        else:
            assert digest is not None
            revision = digest.hash
            index_state = "unindexed"

        return (
            {
                **base,
                "state": "known-present",
                "member_revision": revision,
                "evidence_visibility": visibility,
                "index_state": index_state,
            },
            raw,
        )

    def _snapshot_paths(
        self, changed_paths: Sequence[str | Path]
    ) -> dict[str, dict[str, object]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        paths = tuple(
            dict.fromkeys(
                normalize_relative_path(path, allow_root=False)
                for path in changed_paths
            )
        )
        if not paths:
            raise ValueError(
                "changed_paths must contain at least one repository-relative path"
            )
        symbols_by_path = self.store.symbols_for_paths_many(paths, limit_per_path=32)
        edges_by_path = self._session_edges_for_paths_many(paths, limit_per_path=32)
        rows: dict[str, dict[str, object]] = {}
        for path in paths:
            member, _raw = self._repository_member_observation(path)
            revision = (
                str(member.get("member_revision") or "")
                if member.get("state") == "known-present"
                else None
            )
            symbols = sorted(
                (
                    {
                        **{
                            key: str(symbol[key])
                            for key in ("name", "qualname", "kind")
                            if symbol.get(key) is not None
                            and str(symbol.get(key) or "")
                        },
                        "identity": self._evidence_identity(
                            "hashmarks.symbol-evidence.v1",
                            {
                                "path": path,
                                **{
                                    key: str(symbol[key])
                                    for key in ("name", "qualname", "kind")
                                    if symbol.get(key) is not None
                                    and str(symbol.get(key) or "")
                                },
                            },
                        ),
                        "provenance": {
                            "source": "codemap-symbol-index",
                            "path": path,
                        },
                    }
                    for symbol in symbols_by_path.get(path, ())
                ),
                key=lambda row: (
                    row.get("qualname", ""),
                    row.get("name", ""),
                    row.get("kind", ""),
                ),
            )
            dependencies = sorted(
                (
                    {
                        **{
                            key: str(edge[key])
                            for key in ("source", "kind", "target", "confidence")
                            if edge.get(key) is not None and str(edge.get(key) or "")
                        },
                        "identity": self._evidence_identity(
                            "hashmarks.relationship-evidence.v1",
                            {
                                "path": path,
                                **{
                                    key: str(edge[key])
                                    for key in (
                                        "source",
                                        "kind",
                                        "target",
                                        "confidence",
                                    )
                                    if edge.get(key) is not None
                                    and str(edge.get(key) or "")
                                },
                            },
                        ),
                        "provenance": {
                            "source": "codemap-edge-index",
                            "path": path,
                        },
                    }
                    for edge in edges_by_path.get(path, ())
                    if edge.get("kind") and edge.get("target")
                ),
                key=lambda row: (
                    row.get("kind", ""),
                    row.get("source", ""),
                    row.get("target", ""),
                    row.get("confidence", ""),
                ),
            )
            rows[path] = {
                "member_state": member["state"],
                "revision": revision,
                "symbols": symbols,
                "dependencies": dependencies,
            }
        return rows

    @staticmethod
    def _snapshot_verification(brief: Mapping[str, object]) -> dict[str, object] | None:
        verification = brief.get("verification")
        if not isinstance(verification, Mapping):
            return None
        return {
            key: deepcopy(verification[key])
            for key in ("member", "test_symbol", "reason", "facts")
            if key in verification
        }

    @staticmethod
    def _snapshot_freshness(
        freshness: Mapping[str, object],
    ) -> dict[str, dict[str, object]]:
        entries = freshness.get("entries")
        if not isinstance(entries, list):
            return {}
        rows: dict[str, dict[str, object]] = {}
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            kind = str(entry.get("kind") or "")
            if not kind:
                continue
            member = str(entry.get("member") or "")
            key = kind if not member else f"{kind}:{member}"
            rows[key] = {
                field: deepcopy(entry[field])
                for field in ("state", "evidence_identity", "member", "reason")
                if field in entry
            }
        return rows

    _source_shape = staticmethod(source_shape)

    @staticmethod
    def _python_source_token_kinds(
        text: str, path: str
    ) -> dict[int, list[tuple[int, int, str]]]:
        """Classify exact lexical tokens without guessing semantic ownership."""
        if not path.endswith((".py", ".pyi")):
            return {}
        import io
        import tokenize

        kinds: dict[int, list[tuple[int, int, str]]] = {}
        names = {
            tokenize.NAME: "identifier",
            tokenize.STRING: "string-literal",
            tokenize.COMMENT: "comment",
        }
        try:
            for token in tokenize.generate_tokens(io.StringIO(text).readline):
                kind = names.get(token.type)
                if kind is None or token.start[0] != token.end[0]:
                    continue
                kinds.setdefault(token.start[0], []).append(
                    (token.start[1], token.end[1], kind)
                )
        except (tokenize.TokenError, IndentationError, SyntaxError):
            return {}
        return kinds

    @staticmethod
    def _source_occurrences(
        text: str,
        literal: str,
        *,
        member: Mapping[str, object],
        limit: int,
        symbols: Sequence[Mapping[str, object]],
        token_kinds: Mapping[int, Sequence[tuple[int, int, str]]],
    ) -> tuple[list[dict[str, object]], int]:
        """Bound returned locations, not the count over the admitted member."""
        hits: list[dict[str, object]] = []
        count = 0
        for line_number, line in enumerate(text.split("\n"), 1):
            column = 0
            while (column := line.find(literal, column)) >= 0:
                count += 1
                if len(hits) < limit:
                    owners = [
                        row
                        for row in symbols
                        if row.get("start_line") is not None
                        and row.get("end_line") is not None
                        and int(row["start_line"])
                        <= line_number
                        <= int(row["end_line"])
                    ]
                    owner = min(
                        owners,
                        key=lambda row: (
                            int(row["end_line"]) - int(row["start_line"]),
                            str(row.get("qualname") or ""),
                        ),
                        default=None,
                    )
                    occurrence_kind = next(
                        (
                            kind
                            for start, end, kind in token_kinds.get(line_number, ())
                            if start <= column and column + len(literal) <= end
                        ),
                        "unknown",
                    )
                    fact = {
                        "occurrence_kind": occurrence_kind,
                        "kind_basis": (
                            "python-tokenizer"
                            if occurrence_kind != "unknown"
                            else "unknown"
                        ),
                        "path": member["path"],
                        "member_revision": member["member_revision"],
                        "line": line_number,
                        "column": column + 1,
                        "column_unit": "unicode-codepoint",
                        "literal": literal,
                        "enclosing_symbol": (
                            str(owner.get("qualname") or owner.get("name") or "")
                            if owner is not None
                            else None
                        ),
                        "symbol_basis": (
                            "indexed-containing-range"
                            if owner is not None
                            else "unknown"
                        ),
                    }
                    hits.append(fact)
                column += len(literal)
        return hits, count

    @staticmethod
    def _validate_source_observation(
        literal: str | None,
        limit: int,
        max_bytes: int,
        long_line_threshold: int,
    ) -> None:
        if not 1 <= limit <= 500 or not 1 <= max_bytes <= 8_388_608:
            raise ValueError("source observation bounds are outside supported limits")
        if not 1 <= long_line_threshold <= 1_000_000:
            raise ValueError("long_line_threshold must be between 1 and 1000000")
        if literal is not None and (
            not literal or len(literal) > 256 or "\r" in literal or "\n" in literal
        ):
            raise ValueError(
                "literal must be a nonempty single-line query <=256 characters"
            )

    def _bounded_source_observation(
        self, relpath: str, max_bytes: int
    ) -> tuple[dict[str, object], bytes | None]:
        """Enforce the source budget while reusing canonical member authority."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        candidate = self._repository_member_source(relpath)
        if isinstance(candidate, dict):
            return candidate, None
        try:
            oversized = candidate.path.stat().st_size > max_bytes
        except OSError:
            oversized = False
        if oversized:
            return {
                "path": candidate.rel,
                "state": "unknown",
                "reason": "source-size-bound",
            }, None
        member, raw = self._repository_member_observation(relpath, include_bytes=True)
        if raw is not None and len(raw) > max_bytes:
            return {
                "path": member["path"],
                "state": "unknown",
                "reason": "source-size-bound",
            }, None
        return member, raw

    def _source_observation_from_bytes(
        self, packet: dict[str, object], raw: bytes
    ) -> None:
        """Complete a qualified single-member observation from the same byte capture."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        limit = cast("dict[str, int]", packet["limits"])["results"]
        member = cast("dict[str, object]", packet["member"])
        literal = cast("str | None", packet["literal_query"])
        packet["source_shape"] = self._source_shape(
            raw,
            long_line_threshold=cast("int", packet["long_line_threshold"]),
        )
        if b"\x00" in raw:
            packet["availability"] = "unsupported"
            packet["reason"] = "null-byte-text"
            return
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            packet["availability"] = "unsupported"
            packet["reason"] = "invalid-utf8"
            return

        packet["completeness"] = "complete"
        packet["truncation"] = "complete"
        requested = cast("list[int]", packet["requested_lines"])
        if requested:
            packet["line_anchors"], packet["line_coverage"] = source_line_anchors(
                raw, requested=requested, member=member
            )
        if literal is None:
            return
        symbols = (
            self.store.symbols_for_path(str(member["path"]))
            if member.get("index_state") == "indexed"
            else []
        )
        hits, count = self._source_occurrences(
            text,
            literal,
            member=member,
            limit=limit,
            symbols=symbols,
            token_kinds=self._python_source_token_kinds(text, str(member["path"])),
        )
        for hit in hits:
            hit["evidence_identity"] = self._evidence_identity(
                "hashmarks.source-occurrence.v1", hit
            )
        packet["occurrences"] = hits
        packet["observed_match_count"] = count
        packet["truncation"] = "truncated" if count > limit else "complete"
        packet["completeness"] = "incomplete" if count > limit else "complete"
        if count == 0 and packet["freshness"] == "current":
            packet["negative_evidence"] = "admissible-within-exact-member"

    def source_observation(
        self,
        relpath: str,
        *,
        literal: str | None = None,
        limit: int = 50,
        max_bytes: int = 1_048_576,
        long_line_threshold: int = 2_000,
        lines: Sequence[int] = (),
    ) -> dict[str, object]:
        """Describe one stable source member, with no repository-wide absence claim."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._validate_source_observation(
            literal, limit, max_bytes, long_line_threshold
        )
        if isinstance(lines, (str, bytes)) or len(lines) > 32 or any(
            type(line) is not int or line < 1 for line in lines
        ):
            raise ValueError("lines must be up to 32 positive integers")
        requested = sorted(set(lines))
        generation_before = self.store.generation()
        member, raw = self._bounded_source_observation(relpath, max_bytes)
        generation, identity_generation, stale = self._generation_status()
        packet: dict[str, object] = {
            "schema": operation_schema("source_observation", "member"),
            "member": member,
            "generation": generation,
            "identity_generation": identity_generation,
            "freshness": (
                "stale" if generation != generation_before else freshness_state(stale)
            ),
            "observation_scope": "exact-admitted-repository-member",
            "limits": {"max_bytes": max_bytes, "results": limit},
            "long_line_threshold": long_line_threshold,
            "availability": "observed" if raw is not None else "unavailable",
            "completeness": "unknown",
            "source_shape": None,
            "literal_query": literal,
            "requested_lines": requested,
            "line_anchors": [],
            "line_coverage": "unknown" if requested else "not-requested",
            "occurrences": [],
            "observed_match_count": None,
            "truncation": "unknown",
            "negative_evidence": "not-admissible",
            "authority": "repository-evidence-only",
            "execution_effect": "none",
        }
        if raw is None:
            return packet
        self._source_observation_from_bytes(packet, raw)
        if packet["availability"] != "observed":
            return packet
        packet["observation_identity"] = self._evidence_identity(
            operation_schema("source_observation", "member"),
            {
                "member": member,
                "literal_query": literal,
                "source_shape": packet["source_shape"],
                "requested_lines": requested,
                "line_anchors": packet["line_anchors"],
                "line_coverage": packet["line_coverage"],
                "occurrences": packet["occurrences"],
                "observed_match_count": packet["observed_match_count"],
                "truncation": packet["truncation"],
            },
        )
        return packet

    def _scoped_source_member(
        self,
        path: str,
        literal: str,
        limit: int,
        available_bytes: int,
        member_max_bytes: int,
    ) -> dict[str, object]:
        """Observe one selected member, or record an explicit exhausted budget."""
        if available_bytes < 1:
            return {
                "member": {
                    "path": path,
                    "state": "unknown",
                    "reason": "scope-byte-budget-exhausted",
                },
                "availability": "unavailable",
                "observed_match_count": None,
                "occurrences": [],
                "freshness": "unknown",
                "source_shape": None,
            }
        return self.source_observation(
            path,
            literal=literal,
            limit=limit,
            max_bytes=min(available_bytes, member_max_bytes),
        )

    def _scoped_source_result(
        self, batch: _ScopedSourceAggregation
    ) -> dict[str, object]:
        """Project request-local scan facts using the canonical generation owner."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        generation, identity_generation, stale = self._generation_status()
        generation_matches = generation == batch.start_generation
        coverage_complete = batch.complete and generation_matches
        freshness = (
            freshness_state(stale)
            if generation_matches and batch.members_fresh
            else "stale"
        )
        truncated = batch.match_count > len(batch.occurrences)
        completeness = (
            "unknown"
            if not coverage_complete
            else "incomplete"
            if truncated
            else "complete"
        )
        result: dict[str, object] = {
            "schema": operation_schema("source_observation", "scope"),
            "observation_scope": "explicit-member-set-only",
            "paths": batch.paths,
            "literal": batch.literal,
            "generation": generation,
            "identity_generation": identity_generation,
            "freshness": freshness,
            "member_count": len(batch.paths),
            "member_observations": batch.members,
            "source_coverage": "complete" if coverage_complete else "unknown",
            "observed_match_count": batch.match_count,
            "exact_match_count": batch.match_count if coverage_complete else None,
            "occurrences": batch.occurrences,
            "completeness": completeness,
            "truncation": (
                "truncated"
                if truncated
                else "complete"
                if coverage_complete
                else "unknown"
            ),
            "negative_evidence": (
                "admissible-within-explicit-member-set"
                if coverage_complete
                and batch.match_count == 0
                and freshness == "current"
                else "not-admissible"
            ),
            "limits": {
                "returned_occurrences": batch.limit,
                "max_total_bytes": batch.max_total_bytes,
                "max_member_bytes": batch.max_member_bytes,
            },
            "observed_source_bytes": batch.consumed_bytes,
            "authority": "repository-evidence-only",
            "execution_effect": "none",
        }
        result["observation_identity"] = self._evidence_identity(
            operation_schema("source_observation", "scope"),
            {
                "paths": batch.paths,
                "literal": batch.literal,
                "members": batch.members,
                "matches": batch.occurrences,
                "source_coverage": result["source_coverage"],
                "observed_match_count": batch.match_count,
                "truncation": result["truncation"],
            },
        )
        return result

    def scoped_source_occurrences(
        self,
        paths: Sequence[str],
        literal: str,
        *,
        limit: int = 100,
        max_total_bytes: int = 4_194_304,
        max_member_bytes: int = 1_048_576,
    ) -> dict[str, object]:
        """Observe an explicit member set; never imply repository-wide absence."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if isinstance(paths, (str, bytes)) or not 1 <= len(paths) <= 32:
            raise ValueError("scope must contain between 1 and 32 explicit paths")
        if not 1 <= max_total_bytes <= 8_388_608:
            raise ValueError("max_total_bytes must be between 1 and 8388608")
        self._validate_source_observation(literal, limit, max_member_bytes, 2_000)
        if literal is None:
            raise ValueError("scoped source observations require a literal")
        batch = _ScopedSourceAggregation(
            paths=sorted(
                {normalize_relative_path(path, allow_root=False) for path in paths}
            ),
            literal=literal,
            limit=limit,
            max_total_bytes=max_total_bytes,
            max_member_bytes=max_member_bytes,
            start_generation=self.store.generation(),
        )
        for path in batch.paths:
            batch.add(
                path,
                self._scoped_source_member(
                    path,
                    literal,
                    max(1, limit - len(batch.occurrences)),
                    max_total_bytes - batch.consumed_bytes,
                    max_member_bytes,
                ),
            )
        return self._scoped_source_result(batch)

    @staticmethod
    def _diagnostic_identity(row: Mapping[str, object]) -> str:
        """Canonical diagnostic identity independent of aggregate count/order."""
        import hashlib
        import json

        identity_fields = {
            key: row.get(key)
            for key in ("tool", "rule", "path", "symbol", "line", "column", "message")
            if row.get(key) is not None
        }
        raw = json.dumps(
            identity_fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(raw).hexdigest()

    @staticmethod
    def external_diagnostic_observation(  # noqa: PLR0913 - additive producer fields
        *,
        producer: str,
        binding: RepositoryGenerationBinding,
        diagnostics: Sequence[Mapping[str, object]],
        outcome: str,
        environment_identity: str | None = None,
        scope_paths: Sequence[str] = (),
        collection_state: str | None = None,
    ) -> dict[str, object]:
        """Normalize externally produced diagnostics without executing the tool."""
        allowed_outcomes = {
            "pass",
            "fail",
            "not-run",
            "blocked-environment",
            "blocked-supply",
            "blocked-permission",
            "invalid-baseline",
            "stale",
        }
        if outcome not in allowed_outcomes:
            raise ValueError("unsupported external observation outcome")
        if collection_state is not None and collection_state not in {
            "fresh-complete",
            "fresh-partial",
            "timed-out",
            "unavailable",
            "source-mismatch",
            "unknown",
        }:
            raise ValueError("unsupported diagnostic collection state")
        rows = []
        for raw in diagnostics:
            row = dict(raw)
            row["identity"] = RepositoryDeltaMixin._diagnostic_identity(row)
            rows.append(row)
        rows.sort(key=lambda row: str(row["identity"]))
        return {
            "schema": "hashmarks.external-diagnostic-observation.v1",
            "producer": producer,
            "repository_identity": binding.repository_identity,
            "codemap_generation": int(binding.codemap_generation),
            "environment_identity": environment_identity,
            "scope_paths": sorted({str(path) for path in scope_paths}),
            "outcome": outcome,
            "diagnostics": rows,
            "diagnostic_count": len(rows),
            "collection": (
                {"state": collection_state, "authority": "producer-claimed"}
                if collection_state is not None
                else None
            ),
            "authority": "observation-only",
            "execution_effect": "none",
        }

    def verification_relationship_evidence(
        self,
        *,
        source: str,
        target: str,
        classification: str,
        relation_kind: str,
        provenance: str,
    ) -> dict[str, object]:
        """Describe an objective repository relationship without consumer policy."""
        if classification not in {"direct", "related", "unknown"}:
            raise ValueError("unsupported verification relationship classification")
        if not relation_kind.strip():
            raise ValueError("verification relationship kind must be nonblank")
        payload = {
            "source": source,
            "target": target,
            "classification": classification,
            "relation_kind": relation_kind,
            "provenance": provenance,
        }
        return {
            **payload,
            "evidence_identity": self._evidence_identity(
                "hashmarks.verification-relationship.v1", payload
            ),
            "authority": "repository-relationship-only",
            "execution_effect": "none",
        }

    @staticmethod
    def external_observation_freshness(
        observation: Mapping[str, object],
        *,
        current_repository_identity: str,
        current_generation: int,
        changed_paths: Sequence[str] = (),
        dependency_paths: Sequence[str] = (),
    ) -> dict[str, object]:
        """Evaluate scoped freshness without making every generation globally stale."""
        observed_repository = str(observation.get("repository_identity") or "")
        observed_generation = observation.get("codemap_generation")
        raw_scope = observation.get("scope_paths")
        scope = (
            {str(path) for path in raw_scope} if isinstance(raw_scope, list) else set()
        )
        relevant = scope | {str(path) for path in dependency_paths}
        changed = {str(path) for path in changed_paths}
        intersection = sorted(relevant & changed)
        repository_changed = observed_repository != current_repository_identity
        generation_changed = observed_generation != current_generation

        if not repository_changed and not generation_changed:
            state = "current"
            reason = "repository-and-generation-unchanged"
        elif not relevant:
            state = "stale"
            reason = "repository-changed-without-declared-observation-scope"
        elif intersection:
            state = "stale"
            reason = "relevant-repository-evidence-changed"
        else:
            state = "current"
            reason = "changed-paths-proven-outside-observation-scope"

        return {
            "schema": "hashmarks.external-observation-freshness.v1",
            "state": state,
            "reason": reason,
            "repository_changed": repository_changed,
            "generation_changed": generation_changed,
            "observation_scope": sorted(scope),
            "dependency_scope": sorted({str(path) for path in dependency_paths}),
            "changed_paths": sorted(changed),
            "intersection": intersection,
            "authority": "observation-freshness-only",
            "execution_effect": "none",
        }

    @staticmethod
    def _possible_diagnostic_relocations(
        before: Mapping[str, object],
        after: Mapping[str, object],
        removed: Sequence[Mapping[str, object]],
        added: Sequence[Mapping[str, object]],
    ) -> list[dict[str, object]]:
        """Non-authoritative candidates; never suppress added/removed evidence."""
        if before.get("repository_identity") != after.get(
            "repository_identity"
        ) or before.get("producer") != after.get("producer"):
            return []

        def facts(row: Mapping[str, object]) -> tuple[object, ...]:
            return tuple(
                row.get(field)
                for field in ("tool", "rule", "path", "symbol", "message")
            )

        old: dict[tuple[object, ...], list[Mapping[str, object]]] = {}
        new: dict[tuple[object, ...], list[Mapping[str, object]]] = {}
        for row in removed:
            old.setdefault(facts(row), []).append(row)
        for row in added:
            new.setdefault(facts(row), []).append(row)
        possible: list[dict[str, object]] = []
        for key in sorted(old, key=repr):
            before_rows = old[key]
            after_rows = new.get(key, [])
            if len(before_rows) != 1 or len(after_rows) != 1:
                continue
            prior, subsequent = before_rows[0], after_rows[0]
            if (
                prior.get("line") is None
                or subsequent.get("line") is None
                or (prior.get("line"), prior.get("column"))
                == (subsequent.get("line"), subsequent.get("column"))
            ):
                continue
            possible.append(
                {
                    "before_identity": prior["identity"],
                    "after_identity": subsequent["identity"],
                    "before_line": prior["line"],
                    "after_line": subsequent["line"],
                    "path": prior.get("path"),
                    "basis": "unique-equal-nonlocational-diagnostic-fields",
                    "state": "possible",
                    "identity_authority": False,
                }
            )
        return possible

    @staticmethod
    def _diagnostic_claim_qualification(
        before: Mapping[str, object],
        after: Mapping[str, object],
        added: Sequence[Mapping[str, object]],
        removed: Sequence[Mapping[str, object]],
    ) -> dict[str, object]:
        """Qualify diagnostic absence using declared external collection coverage.

        Raw identity additions/removals are retained; this only marks which
        claims can be drawn from producer-claimed collection completeness.
        """
        prior = before.get("collection")
        current = after.get("collection")
        prior_state = prior.get("state") if isinstance(prior, Mapping) else None
        current_state = current.get("state") if isinstance(current, Mapping) else None
        prior_scope = before.get("scope_paths")
        current_scope = after.get("scope_paths")
        before_paths = set(prior_scope) if isinstance(prior_scope, list) else set()
        after_paths = set(current_scope) if isinstance(current_scope, list) else set()
        same_context = all(
            (
                before.get("producer"),
                before.get("producer") == after.get("producer"),
                before.get("repository_identity"),
                before.get("repository_identity") == after.get("repository_identity"),
                before.get("environment_identity"),
                before.get("environment_identity") == after.get("environment_identity"),
                before.get("outcome") in {"pass", "fail"},
                after.get("outcome") in {"pass", "fail"},
            )
        )
        qualified_added = sorted(
            str(row["identity"])
            for row in added
            if same_context
            and prior_state == "fresh-complete"
            and current_state in {"fresh-complete", "fresh-partial"}
            and row.get("path") in before_paths & after_paths
        )
        qualified_removed = sorted(
            str(row["identity"])
            for row in removed
            if same_context
            and prior_state in {"fresh-complete", "fresh-partial"}
            and current_state == "fresh-complete"
            and row.get("path") in before_paths & after_paths
        )
        return {
            "schema": "hashmarks.diagnostic-delta-qualification.v1",
            "basis": "producer-claimed-collection-and-explicit-path-scope",
            "shared_context": same_context,
            "collection_before": prior_state or "unknown",
            "collection_after": current_state or "unknown",
            "qualified_added_identities": qualified_added,
            "qualified_removed_identities": qualified_removed,
            "unqualified_added_identities": sorted(
                {str(row["identity"]) for row in added} - set(qualified_added)
            ),
            "unqualified_removed_identities": sorted(
                {str(row["identity"]) for row in removed} - set(qualified_removed)
            ),
            "identity_authority": False,
            "execution_effect": "none",
        }

    @staticmethod
    def diagnostic_observation_delta(
        before: Mapping[str, object],
        after: Mapping[str, object],
        *,
        changed_paths: Sequence[str] = (),
        before_source: Mapping[str, object] | None = None,
        after_source: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        """Compare diagnostic identities; counts alone are never delta authority."""

        def indexed(packet: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
            rows = packet.get("diagnostics")
            if not isinstance(rows, list):
                return {}
            return {
                str(row["identity"]): row
                for row in rows
                if isinstance(row, Mapping) and row.get("identity")
            }

        old = indexed(before)
        new = indexed(after)
        old_ids = set(old)
        new_ids = set(new)
        added_ids = sorted(new_ids - old_ids)
        removed_ids = sorted(old_ids - new_ids)
        scope = {str(path) for path in changed_paths}
        added = [deepcopy(new[identity]) for identity in added_ids]
        removed = [deepcopy(old[identity]) for identity in removed_ids]
        added_in_changed_scope = [
            row for row in added if str(row.get("path") or "") in scope
        ]
        possible_relocations = RepositoryDeltaMixin._possible_diagnostic_relocations(
            before, after, removed, added
        )
        if (before_source is None) != (after_source is None):
            raise ValueError("source correspondence requires both endpoint observations")
        source_correspondence = (
            diagnostic_line_correspondence(
                candidates=possible_relocations,
                before_diagnostic=before,
                after_diagnostic=after,
                before_source=before_source,
                after_source=after_source,
            )
            if before_source is not None and after_source is not None
            else None
        )

        return {
            "schema": DIAGNOSTIC_DELTA_SCHEMA,
            "producer": after.get("producer"),
            "repository": {
                "before": before.get("repository_identity"),
                "after": after.get("repository_identity"),
                "changed": before.get("repository_identity")
                != after.get("repository_identity"),
            },
            "generation": {
                "before": before.get("codemap_generation"),
                "after": after.get("codemap_generation"),
            },
            "outcome": {
                "before": before.get("outcome"),
                "after": after.get("outcome"),
            },
            "collection": {
                "before": before.get("collection"),
                "after": after.get("collection"),
            },
            "diagnostics": {
                "before_count": len(old),
                "after_count": len(new),
                "added": added,
                "removed": removed,
                "unchanged_count": len(old_ids & new_ids),
                "added_in_changed_scope": added_in_changed_scope,
                "possible_relocations": possible_relocations,
                "source_correspondence": source_correspondence,
                "qualification": RepositoryDeltaMixin._diagnostic_claim_qualification(
                    before, after, added, removed
                ),
            },
            "authority": "observation-only",
            "execution_effect": "none",
        }

    @diagnostic_producer
    def repository_intelligence_snapshot(
        self,
        task: str,
        changed_paths: Sequence[str | Path],
        *,
        limit: int = 20,
        per_role: int = 3,
        impact_limit_per_surface: int = 4,
        max_depth: int = 3,
    ) -> dict[str, object]:
        """Capture bounded repository meaning for an explicit change set.

        Inside one explicit ``decision_session()``, identical snapshot requests
        reuse the already-derived immutable repository-intelligence composition.
        The cache is generation-bound and disposable; callers always receive a
        deep copy so mutation cannot become shared authority.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        snapshot_key = None
        if self._decision_session_depth > 0:
            generation = int(
                self._decision_session_generation or self.store.generation()
            )
            snapshot_key = (
                generation,
                task,
                tuple(str(path) for path in changed_paths),
                int(limit),
                int(per_role),
                int(impact_limit_per_surface),
                int(max_depth),
            )
            cached = self._decision_snapshot_cache.get(snapshot_key)
            if cached is not None:
                self._decision_session_stats["snapshot_hit"] += 1
                return deepcopy(cached)
            self._decision_session_stats["snapshot_miss"] += 1

        brief = self.change_intelligence_brief(
            task,
            changed_paths,
            limit=limit,
            per_role=per_role,
            impact_limit_per_surface=impact_limit_per_surface,
            max_depth=max_depth,
        )
        freshness = self.evidence_freshness_map(
            task,
            changed_paths,
            options=FreshnessMapOptions(
                limit=limit,
                per_role=per_role,
                impact_limit_per_surface=impact_limit_per_surface,
                max_depth=max_depth,
            ),
        )
        payload: dict[str, object] = {
            "schema": REPOSITORY_SNAPSHOT_SCHEMA,
            "observer": self._repository_observer_packet(),
            "repository": deepcopy(brief["repository"]),
            "task_identity": brief["task_identity"],
            "paths": self._snapshot_paths(changed_paths),
            "affected": deepcopy(brief.get("affected") or {}),
            "ownership": deepcopy(brief.get("ownership")),
            "verification": self._snapshot_verification(brief),
            "freshness": self._snapshot_freshness(freshness),
            "bounds": deepcopy(brief.get("bounds") or {}),
            "completeness": {
                "state": "complete",
                "scope": "bounded-explicit-change-set",
                "dynamic_runtime_relationships": "unknown",
            },
            "storage": "derived-not-persisted",
            "authority": "repository-intelligence-only",
            "execution_effect": "none",
        }
        if "project_impact" in brief:
            payload["project_impact"] = deepcopy(brief["project_impact"])
        payload["snapshot_identity"] = "sha256:" + self._packet_digest(
            REPOSITORY_SNAPSHOT_SCHEMA, payload
        )
        if snapshot_key is not None:
            self._decision_snapshot_cache[snapshot_key] = deepcopy(payload)
        return payload

    def _validate_previous_snapshot(
        self,
        task: str,
        previous_snapshot: Mapping[str, object],
    ) -> tuple[Mapping[str, object], str]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if previous_snapshot.get("schema") != REPOSITORY_SNAPSHOT_SCHEMA:
            raise ValueError(
                "previous_snapshot must be a hashmarks.repository-intelligence-snapshot.v1 packet"
            )
        repository = self._delta_mapping(
            previous_snapshot.get("repository"), field="previous_snapshot.repository"
        )
        repository_identity = str(repository.get("repository_identity") or "")
        if repository_identity != self._repository_packet_identity():
            raise ValueError("previous_snapshot repository-mismatch")
        expected_task = self._packet_digest("hashmarks.task.v1", {"task": task})
        if str(previous_snapshot.get("task_identity") or "") != expected_task:
            raise ValueError("previous_snapshot task-mismatch")
        identity = previous_snapshot.get("snapshot_identity")
        expected_identity = "sha256:" + self._packet_digest(
            REPOSITORY_SNAPSHOT_SCHEMA,
            {
                key: value
                for key, value in previous_snapshot.items()
                if key != "snapshot_identity"
            },
        )
        if not isinstance(identity, str) or identity != expected_identity:
            raise ValueError("previous_snapshot snapshot identity mismatch")
        return repository, repository_identity

    @classmethod
    def _leaf_changes(
        cls,
        previous: object,
        current: object,
        path: tuple[str, ...] = (),
    ) -> list[dict[str, object]]:
        if isinstance(previous, Mapping) and isinstance(current, Mapping):
            changes: list[dict[str, object]] = []
            for key in sorted(set(previous) | set(current)):
                child = (*path, str(key))
                if key not in current:
                    changes.append({"path": list(child), "delete": True})
                elif key not in previous:
                    changes.append(
                        {"path": list(child), "value": deepcopy(current[key])}
                    )
                else:
                    changes.extend(
                        cls._leaf_changes(previous[key], current[key], child)
                    )
            return changes
        if isinstance(previous, list) and isinstance(current, list):
            if previous == current:
                return []
            return [{"path": list(path), "value": deepcopy(current)}]
        if previous != current:
            return [{"path": list(path), "value": deepcopy(current)}]
        return []

    @staticmethod
    def _path_index(snapshot: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
        rows = snapshot.get("paths")
        if not isinstance(rows, Mapping):
            return {}
        return {
            str(path): row for path, row in rows.items() if isinstance(row, Mapping)
        }

    @staticmethod
    def _row_set(
        row: Mapping[str, object] | None, key: str
    ) -> set[tuple[tuple[str, str], ...]]:
        if not isinstance(row, Mapping):
            return set()
        values = row.get(key)
        if not isinstance(values, list):
            return set()
        return {
            tuple(
                sorted(
                    (str(k), str(v))
                    for k, v in item.items()
                    if k not in {"identity", "provenance"}
                )
            )
            for item in values
            if isinstance(item, Mapping)
        }

    @staticmethod
    def _decode_row(value: tuple[tuple[str, str], ...]) -> dict[str, str]:
        return dict(value)

    def _semantic_changes(
        self,
        previous: Mapping[str, object],
        current: Mapping[str, object],
    ) -> dict[str, object]:
        before = self._path_index(previous)
        after = self._path_index(current)
        symbols_added: list[dict[str, object]] = []
        symbols_removed: list[dict[str, object]] = []
        dependencies_added: list[dict[str, object]] = []
        dependencies_removed: list[dict[str, object]] = []
        for path in sorted(set(before) | set(after)):
            old_symbols = self._row_set(before.get(path), "symbols")
            new_symbols = self._row_set(after.get(path), "symbols")
            old_dependencies = self._row_set(before.get(path), "dependencies")
            new_dependencies = self._row_set(after.get(path), "dependencies")
            symbols_added.extend(
                {"path": path, **self._decode_row(value)}
                for value in sorted(new_symbols - old_symbols)
            )
            symbols_removed.extend(
                {"path": path, **self._decode_row(value)}
                for value in sorted(old_symbols - new_symbols)
            )
            dependencies_added.extend(
                {"path": path, **self._decode_row(value)}
                for value in sorted(new_dependencies - old_dependencies)
            )
            dependencies_removed.extend(
                {"path": path, **self._decode_row(value)}
                for value in sorted(old_dependencies - new_dependencies)
            )
        possible_moves: list[dict[str, object]] = []
        removed_by_symbol = {
            (row.get("qualname") or row.get("name"), row.get("kind")): row
            for row in symbols_removed
        }
        for added in symbols_added:
            key = (added.get("qualname") or added.get("name"), added.get("kind"))
            removed = removed_by_symbol.get(key)
            if removed is not None and removed["path"] != added["path"]:
                possible_moves.append(
                    {
                        "name": added.get("qualname") or added.get("name"),
                        "kind": added.get("kind"),
                        "from": removed["path"],
                        "to": added["path"],
                        "state": "possible",
                        "provenance": "same-qualified-name-and-kind",
                        "identity_authority": False,
                    }
                )
        result: dict[str, object] = {}
        for key, rows in (
            ("symbols_added", symbols_added),
            ("symbols_removed", symbols_removed),
            ("possible_symbol_moves", possible_moves),
            ("dependencies_added", dependencies_added),
            ("dependencies_removed", dependencies_removed),
        ):
            if rows:
                result[key] = rows
        for key, changed in (
            (
                "ownership_changed",
                previous.get("ownership") != current.get("ownership"),
            ),
            ("impact_changed", previous.get("affected") != current.get("affected")),
            (
                "verification_changed",
                previous.get("verification") != current.get("verification"),
            ),
            (
                "freshness_changed",
                previous.get("freshness") != current.get("freshness"),
            ),
            (
                "project_provenance_changed",
                previous.get("project_impact") != current.get("project_impact"),
            ),
        ):
            if changed:
                result[key] = True
        return result

    @diagnostic_producer
    def repository_intelligence_delta(
        self,
        task: str,
        changed_paths: Sequence[str | Path],
        *,
        previous_snapshot: Mapping[str, object],
        limit: int = 20,
        per_role: int = 3,
        options: ChangeImpactOptions = ChangeImpactOptions(
            impact_limit_per_surface=4,
            max_depth=3,
        ),
    ) -> dict[str, object]:
        """Return changed repository-intelligence facts between admitted states."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        previous_repository, repository_identity = self._validate_previous_snapshot(
            task, previous_snapshot
        )
        current = self.repository_intelligence_snapshot(
            task,
            changed_paths,
            limit=limit,
            per_role=per_role,
            impact_limit_per_surface=options.impact_limit_per_surface,
            max_depth=options.max_depth,
        )
        current_repository = self._delta_mapping(
            current.get("repository"), field="current.repository"
        )
        changes = self._leaf_changes(previous_snapshot, current)
        changes = [row for row in changes if row.get("path") != ["snapshot_identity"]]
        changed_sections = sorted(
            {
                str(row["path"][0])
                for row in changes
                if isinstance(row.get("path"), list) and row["path"]
            }
        )
        previous_observer = self._delta_mapping(
            previous_snapshot.get("observer"), field="previous_snapshot.observer"
        )
        current_observer = self._delta_mapping(
            current.get("observer"), field="current.observer"
        )
        previous_completeness = self._delta_mapping(
            previous_snapshot.get("completeness"),
            field="previous_snapshot.completeness",
        )
        current_completeness = self._delta_mapping(
            current.get("completeness"), field="current.completeness"
        )
        payload: dict[str, object] = {
            "schema": REPOSITORY_DELTA_SCHEMA,
            "repository_identity": repository_identity,
            "task_identity": current["task_identity"],
            "from": {
                "snapshot_identity": previous_snapshot["snapshot_identity"],
                "codemap_generation": previous_repository.get("codemap_generation"),
            },
            "to": {
                "snapshot_identity": current["snapshot_identity"],
                "codemap_generation": current_repository.get("codemap_generation"),
            },
            "changes": changes,
            "changed_sections": changed_sections,
            "semantic": self._semantic_changes(previous_snapshot, current),
            "observer": {
                "before": previous_observer.get("identity"),
                "after": current_observer.get("identity"),
                "changed": previous_observer.get("identity")
                != current_observer.get("identity"),
            },
            "completeness": {
                "before": deepcopy(previous_completeness),
                "after": deepcopy(current_completeness),
                "changed": previous_completeness != current_completeness,
            },
            "storage": "derived-not-persisted",
            "authority": "repository-intelligence-only",
            "execution_effect": "none",
        }
        payload["delta_identity"] = "sha256:" + self._packet_digest(
            REPOSITORY_DELTA_SCHEMA, payload
        )
        return payload
