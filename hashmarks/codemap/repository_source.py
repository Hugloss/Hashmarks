from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict, Unpack, cast

from hashmarks.digest import Digest
from hashmarks.file_store import UnstableFileError
from hashmarks.freshness import freshness_state
from hashmarks.operation_contract import operation_response, operation_schema
from hashmarks.paths import normalize_relative_path

from .decision_session import (
    DecisionRefreshRequired,
    DecisionScope,
    ReadScopeOwner,
    decision_scoped,
)
from .model import EvidenceVisibility
from .python_ast import estimate_tokens
from .query_primitives import _WORD_RE
from .repository_observation import evidence_identity, packet_digest
from .scoped_source_literals import ScopedSourceLiteralsMixin
from .source_line_correspondence import (
    source_line_anchors,
    source_shape,
    validated_source_lines,
)
from .source_range_receipt import (
    SOURCE_RANGE_RECEIPT_SCHEMA,
    source_range_evidence,
    validate_source_range,
)

if TYPE_CHECKING:
    from .indexing_lifecycle import RepositoryIndex


def _instruction_scope(authority: str) -> str:
    parent = Path(authority).parent.as_posix()
    return "." if parent in {"", "."} else parent


def _instruction_applies(authority: str, target: str) -> bool:
    scope = _instruction_scope(authority)
    return scope == "." or target == scope or target.startswith(scope + "/")


def _instruction_specificity(authority: str) -> int:
    scope = _instruction_scope(authority)
    return 0 if scope == "." else len(Path(scope).parts)


class _SourceObservationLineOptions(TypedDict, total=False):
    """Typed optional line selectors; public keywords remain backward compatible."""

    lines: Sequence[int]
    context_lines: int
    anchor_context_lines: int


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
    context_lines: int = 0
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
        if observed and isinstance(count, int):
            self.match_count += count
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


class RepositorySource(ScopedSourceLiteralsMixin, ReadScopeOwner):
    """Own admitted member bytes, revisions, ranges and source disclosure.

    Index reconciles before a read scope; drift inside a scope stays explicit.
    This owner has no task retrieval, ownership or verification dependency.
    """

    def __init__(
        self,
        index: RepositoryIndex,
        reads: DecisionScope,
    ) -> None:
        if reads.index is not index:
            raise ValueError(
                "Source Index and read scope must share one repository authority"
            )
        self.files = index.files
        self.index = index
        self._reads = reads
        self.store = index.store
        self.file_store = index.file_store
        self.workspace = index.workspace

    @property
    def reads(self) -> DecisionScope:
        return self._reads

    @staticmethod
    def _physical_lines(raw: bytes) -> list[bytes]:
        """Split physical repository lines only on LF while preserving exact bytes."""
        if not raw:
            return []
        parts = raw.split(b"\n")
        lines = [part + b"\n" for part in parts[:-1]]
        if parts[-1]:
            lines.append(parts[-1])
        return lines

    def _repository_member_source(
        self, relpath: str
    ) -> _RepositoryMemberSource | dict[str, object]:
        rel = normalize_relative_path(relpath, allow_root=False)
        decision = self.files.decide(rel)
        if not decision.index or decision.evidence_visibility.value == "deny":
            return {
                "path": rel,
                "state": "unsupported",
                "reason": "repository-evidence-denied",
            }
        if not self.files.is_admitted(rel):
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
        row = self.reads.file_row(rel)
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

    def member(
        self,
        relpath: str,
        *,
        include_bytes: bool = False,
    ) -> tuple[dict[str, object], bytes | None]:
        """Observe one repository member through canonical policy/revision authority."""
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
    def _source_symbol_ranges(
        symbols: Sequence[Mapping[str, object]],
    ) -> list[tuple[Mapping[str, object], int, int]]:
        """Bind each indexed declaration to its numeric source span once."""
        ranges: list[tuple[Mapping[str, object], int, int]] = []
        for row in symbols:
            start, end = row.get("start_line"), row.get("end_line")
            if start is None or end is None:
                continue
            if not isinstance(
                start, (int, str, float, bytes, bytearray)
            ) or not isinstance(end, (int, str, float, bytes, bytearray)):
                raise TypeError("indexed symbol ranges must be numeric")
            ranges.append((row, int(start), int(end)))
        return ranges

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
        ranges = RepositorySource._source_symbol_ranges(symbols)
        count = 0
        for line_number, line in enumerate(text.split("\n"), 1):
            column = 0
            while (column := line.find(literal, column)) >= 0:
                count += 1
                if len(hits) < limit:
                    owners = [
                        span for span in ranges if span[1] <= line_number <= span[2]
                    ]
                    owner_span = min(
                        owners,
                        key=lambda span: (
                            span[2] - span[1],
                            str(span[0].get("qualname") or ""),
                        ),
                        default=None,
                    )
                    owner = None if owner_span is None else owner_span[0]
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
    def _source_context_excerpt(
        lines: Sequence[str],
        *,
        line: int,
        column: int,
        literal_length: int,
        anchor_role: str = "match",
    ) -> list[dict[str, object]]:
        """Bounded display-only context from the same admitted UTF-8 byte capture.

        Column coordinates and occurrence identities continue to refer to the
        original source. Never read again to construct context.
        """
        excerpt: list[dict[str, object]] = []
        for number in range(max(1, line - 1), min(len(lines), line + 1) + 1):
            source = lines[number - 1]
            if source.endswith("\r"):
                source = source[:-1]
            # Reserve room for the entire <=256-character literal and nearby
            # source even when the match is deep in a very long physical line.
            start = max(0, column - 1 - 32) if number == line else 0
            if number == line and start + 320 < column - 1 + literal_length:
                start = column - 1 + literal_length - 320
            excerpt.append(
                {
                    "line": number,
                    "role": anchor_role if number == line else "context",
                    "start_column": start + 1,
                    "text": source[start : start + 320],
                    "truncated_left": start > 0,
                    "truncated_right": start + 320 < len(source),
                }
            )
        return excerpt

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
        member, raw = self.member(relpath, include_bytes=True)
        if raw is not None and len(raw) > max_bytes:
            return {
                "path": member["path"],
                "state": "unknown",
                "reason": "source-size-bound",
            }, None
        return member, raw

    def _source_evidenced_hits(
        self,
        hits: list[dict[str, object]],
        *,
        text: str,
        literal: str,
        context_lines: int,
    ) -> None:
        """Attach stable location IDs before optional display-only excerpts."""
        source_lines = text.split("\n") if context_lines else []
        if source_lines and text.endswith("\n"):
            source_lines.pop()
        for hit in hits:
            hit["evidence_identity"] = evidence_identity(
                "hashmarks.source-occurrence.v1", hit
            )
            if context_lines:
                hit["context_excerpt"] = self._source_context_excerpt(
                    source_lines,
                    line=cast("int", hit["line"]),
                    column=cast("int", hit["column"]),
                    literal_length=len(literal),
                )

    def _attach_source_anchor_context(
        self, packet: dict[str, object], text: str
    ) -> None:
        """Attach preview text only to qualified anchors from stable source bytes."""
        if not cast("dict[str, int]", packet["limits"]).get("anchor_context_lines", 0):
            return
        source_lines = text.split("\n")
        if text.endswith("\n"):
            source_lines.pop()
        for anchor in cast("list[dict[str, object]]", packet["line_anchors"]):
            if anchor["state"] != "observed":
                continue
            anchor["context_excerpt"] = self._source_context_excerpt(
                source_lines,
                line=cast("int", anchor["line"]),
                column=1,
                literal_length=0,
                anchor_role="anchor",
            )

    @staticmethod
    def _validate_anchor_context_lines(value: object, requested: Sequence[int]) -> None:
        """Reject malformed and unbounded line-preview requests before source work."""
        if type(value) is not int or value not in (0, 1):
            raise ValueError("anchor_context_lines must be 0 or 1")
        if value and not 1 <= len(requested) <= 8:
            raise ValueError("anchor_context_lines requires 1 to 8 explicit lines")

    @staticmethod
    def _record_source_context_limits(
        packet: dict[str, object], match_lines: int, anchor_lines: int
    ) -> None:
        """Keep absent optional preview limits absent from legacy packets."""
        limits = cast("dict[str, int]", packet["limits"])
        if match_lines:
            limits["context_lines"] = match_lines
        if anchor_lines:
            limits["anchor_context_lines"] = anchor_lines

    def _source_observation_from_bytes(
        self, packet: dict[str, object], raw: bytes
    ) -> None:
        """Complete a qualified single-member observation from the same byte capture."""
        limit = cast("dict[str, int]", packet["limits"])["results"]
        member = cast("dict[str, object]", packet["member"])
        literal = cast("str | None", packet["literal_query"])
        packet["source_shape"] = source_shape(
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
            self._attach_source_anchor_context(packet, text)
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
        context_lines = cast("dict[str, int]", packet["limits"]).get("context_lines", 0)
        self._source_evidenced_hits(
            hits, text=text, literal=literal, context_lines=context_lines
        )
        packet["occurrences"] = hits
        packet["observed_match_count"] = count
        packet["truncation"] = "truncated" if count > limit else "complete"
        packet["completeness"] = "incomplete" if count > limit else "complete"
        if count == 0 and packet["freshness"] == "current":
            packet["negative_evidence"] = "admissible-within-exact-member"

    def observe(
        self,
        relpath: str,
        *,
        literal: str | None = None,
        limit: int = 50,
        max_bytes: int = 1_048_576,
        long_line_threshold: int = 2_000,
        **line_options: Unpack[_SourceObservationLineOptions],
    ) -> dict[str, object]:
        """Describe one stable source member, with no repository-wide absence claim."""
        unexpected = set(line_options) - {
            "lines",
            "context_lines",
            "anchor_context_lines",
        }
        if unexpected:
            raise TypeError(f"unexpected source observation keyword: {min(unexpected)}")
        lines = line_options.get("lines", ())
        context_lines = line_options.get("context_lines", 0)
        anchor_context_lines = line_options.get("anchor_context_lines", 0)
        self._validate_source_observation(
            literal, limit, max_bytes, long_line_threshold
        )
        if type(context_lines) is not int or context_lines not in (0, 1):
            raise ValueError("context_lines must be 0 or 1")
        if context_lines and literal is None:
            raise ValueError("context_lines requires a literal")
        requested = validated_source_lines(lines)
        self._validate_anchor_context_lines(anchor_context_lines, requested)
        generation_before = self.store.generation()
        member, raw = self._bounded_source_observation(relpath, max_bytes)
        generation, identity_generation, stale = self.reads.generation_status()
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
        self._record_source_context_limits(packet, context_lines, anchor_context_lines)
        if raw is None:
            return packet
        self._source_observation_from_bytes(packet, raw)
        if packet["availability"] != "observed":
            return packet
        packet["observation_identity"] = evidence_identity(
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

    def range_receipt(
        self,
        relpath: str,
        *,
        start_byte: int,
        end_byte: int,
        max_bytes: int = 1_048_576,
    ) -> dict[str, object]:
        """Return original bytes for [start_byte, end_byte) from one stable read.

        Coordinates are zero-based byte offsets, independent of text encoding.
        The observation identity binds the range to the full member revision.
        Completeness describes only the requested range; canonical freshness
        remains separate. Unavailable members never return content or identity.
        """
        validate_source_range(start_byte, end_byte, max_bytes)
        generation_before = self.store.generation()
        member, raw = self._bounded_source_observation(relpath, max_bytes)
        generation, identity_generation, stale = self.reads.generation_status()
        packet: dict[str, object] = {
            "schema": SOURCE_RANGE_RECEIPT_SCHEMA,
            "member": member,
            "generation": generation,
            "identity_generation": identity_generation,
            "freshness": (
                "stale" if generation != generation_before else freshness_state(stale)
            ),
            "observation_scope": "exact-admitted-member-byte-range",
            "range": {
                "coordinate_system": "zero-based-half-open-bytes",
                "start_byte": start_byte,
                "end_byte": end_byte,
            },
            "limits": {"max_bytes": max_bytes},
            "availability": "unavailable",
            "completeness": "unknown",
            "truncation": "unknown",
            "source_byte_count": None,
            "content": None,
            "observation_identity": None,
            "negative_evidence": "not-admissible",
            "authority": "repository-evidence-only",
            "execution_effect": "none",
        }
        if raw is not None:
            packet.update(source_range_evidence(raw, member, start_byte, end_byte))
        return packet

    def _scoped_source_member(
        self,
        path: str,
        literal: str,
        limit: int,
        available_bytes: int,
        member_max_bytes: int,
        context_lines: int,
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
        return self.observe(
            path,
            literal=literal,
            limit=limit,
            max_bytes=min(available_bytes, member_max_bytes),
            context_lines=context_lines,
        )

    def _scoped_source_result(
        self, batch: _ScopedSourceAggregation
    ) -> dict[str, object]:
        """Project request-local scan facts using the canonical generation owner."""
        generation, identity_generation, stale = self.reads.generation_status()
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
        limits = {
            "returned_occurrences": batch.limit,
            "max_total_bytes": batch.max_total_bytes,
            "max_member_bytes": batch.max_member_bytes,
        }
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
            "limits": limits,
            "observed_source_bytes": batch.consumed_bytes,
            "authority": "repository-evidence-only",
            "execution_effect": "none",
        }
        if batch.context_lines:
            limits["context_lines"] = batch.context_lines
        result["observation_identity"] = evidence_identity(
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

    def scoped_occurrences(
        self,
        paths: Sequence[str],
        literal: str,
        *,
        limit: int = 100,
        max_total_bytes: int = 4_194_304,
        max_member_bytes: int = 1_048_576,
        context_lines: int = 0,
    ) -> dict[str, object]:
        """Observe an explicit member set; never imply repository-wide absence."""
        if isinstance(paths, (str, bytes)) or not 1 <= len(paths) <= 32:
            raise ValueError("scope must contain between 1 and 32 explicit paths")
        if not 1 <= max_total_bytes <= 8_388_608:
            raise ValueError("max_total_bytes must be between 1 and 8388608")
        self._validate_source_observation(literal, limit, max_member_bytes, 2_000)
        if type(context_lines) is not int or context_lines not in (0, 1):
            raise ValueError("context_lines must be 0 or 1")
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
            context_lines=context_lines,
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
                    context_lines,
                ),
            )
        return self._scoped_source_result(batch)

    def _grep_candidate_match(
        self,
        candidate: dict[str, object],
        *,
        lowered: str,
        tokens: list[str],
        context_lines: int,
    ) -> dict[str, object] | None:
        path = str(candidate["path"])
        visibility = EvidenceVisibility(str(candidate["evidence_visibility"]))
        if visibility is not EvidenceVisibility.SOURCE:
            return None
        self.ensure_current(path)
        _observation, raw = self.member(path, include_bytes=True)
        if raw is None:
            return None
        lines = raw.decode("utf-8", errors="replace").splitlines()
        line_value = candidate["line"]
        assert isinstance(line_value, int)
        line_no = line_value
        if line_no < 1 or line_no > len(lines):
            return None
        line = lines[line_no - 1]
        if lowered not in line.lower() and not all(
            token in line.lower() for token in tokens
        ):
            return None
        start = max(1, line_no - max(0, context_lines))
        end = min(len(lines), line_no + max(0, context_lines))
        return {
            "path": path,
            "line": line_no,
            "range": [start, end],
            "content": "\n".join(lines[start - 1 : end]),
            "evidence_visibility": visibility.value,
        }

    @operation_response("grep")
    @decision_scoped
    def grep(
        self, query: str, *, limit: int = 50, context_lines: int = 0
    ) -> dict[str, object]:
        self.reads.ready()
        raw = query.strip()
        if not raw:
            raise ValueError("query must not be empty")
        tokens = [token.lower() for token in _WORD_RE.findall(raw) if len(token) >= 2]
        candidates = self.store.lexical_candidates(tokens, limit=max(limit * 10, 100))
        matches: list[dict[str, object]] = []
        lowered = raw.lower()
        for candidate in candidates:
            match = self._grep_candidate_match(
                dict(candidate),
                lowered=lowered,
                tokens=tokens,
                context_lines=context_lines,
            )
            if match is None:
                continue
            matches.append(match)
            if len(matches) >= limit:
                break
        generation, identity_generation, stale = self.reads.generation_status()
        return {
            "schema": operation_schema("grep"),
            "query": query,
            "generation": generation,
            "identity_generation": identity_generation,
            "stale": stale,
            "matches": matches,
        }

    @operation_response("symbol")
    @decision_scoped
    def symbol(self, query: str) -> dict[str, object]:
        self.reads.ready()
        matches = self.store.symbol(query)
        if not matches:
            raise KeyError(f"symbol not found: {query}")
        visible = [
            row
            for row in matches
            if EvidenceVisibility(str(row["evidence_visibility"]))
            is not EvidenceVisibility.DENY
        ]
        if not visible:
            raise PermissionError(f"symbol exists but agent context is denied: {query}")
        return {
            "schema": operation_schema("symbol"),
            "query": query,
            **self.reads.freshness_fields(),
            "matches": visible,
        }

    def _source_visible_matches(
        self,
        query: str,
    ) -> list[dict[str, object]]:
        if "::" in query:
            raw_path, qualname = query.split("::", 1)
            path = normalize_relative_path(raw_path, allow_root=False)
            self.ensure_current(path)
            match = self.store.symbol_at(path, qualname)
            matches = [] if match is None else [match]
        else:
            matches = self.store.symbol(query)
        visible = [
            dict(row)
            for row in matches
            if EvidenceVisibility(str(row["evidence_visibility"]))
            is not EvidenceVisibility.DENY
        ]
        if not visible:
            raise KeyError(f"symbol not found: {query}")
        return visible

    def _source_current_content(
        self,
        query: str,
        row: dict[str, object],
    ) -> tuple[str, str, dict[str, object], str]:
        path = str(row["path"])
        qualname = str(row["qualname"])
        self.ensure_current(path)
        current_row = self.store.symbol_at(path, qualname)
        if current_row is None:
            raise KeyError(f"symbol changed or disappeared during refresh: {query}")
        current = dict(current_row)
        visibility = EvidenceVisibility(str(current["evidence_visibility"]))
        if visibility is not EvidenceVisibility.SOURCE:
            raise PermissionError(f"source body is not agent-visible: {path}")
        content = self.slice(
            path,
            int(current["start_line"]),
            int(current["end_line"]),
            qualname=qualname,
        )
        return path, qualname, current, content

    @operation_response("source")
    @decision_scoped
    def read(self, query: str, *, token_budget: int = 4000) -> dict[str, object]:
        self.reads.ready()
        if token_budget < 16:
            raise ValueError("token budget must be at least 16")
        visible = self._source_visible_matches(query)
        if len(visible) > 1 and "::" not in query:
            return {
                "schema": operation_schema("source"),
                "query": query,
                "ambiguous": True,
                "matches": [
                    {
                        "symbol_id": f"{row['path']}::{row['qualname']}",
                        "path": row["path"],
                        "qualname": row["qualname"],
                        "signature": row["signature"],
                    }
                    for row in visible[:20]
                ],
            }

        path, qualname, current, body = self._source_current_content(query, visible[0])
        tokens = estimate_tokens(body)
        if tokens > token_budget:
            return {
                "schema": operation_schema("source"),
                "query": query,
                "symbol_id": f"{path}::{qualname}",
                "path": path,
                "qualname": qualname,
                "signature": current["signature"],
                "lines": [current["start_line"], current["end_line"]],
                "estimated_tokens": tokens,
                "budget": token_budget,
                "too_large": True,
                "guidance": "Use outline/deps or raise the explicit source budget.",
            }
        return {
            "schema": operation_schema("source"),
            "query": query,
            "symbol_id": f"{path}::{qualname}",
            "path": path,
            "qualname": qualname,
            "signature": current["signature"],
            "lines": [current["start_line"], current["end_line"]],
            "estimated_tokens": tokens,
            "budget": token_budget,
            "too_large": False,
            "content": body,
        }

    @staticmethod
    def _instruction_authority_projection(
        seed_paths: list[str],
        indexed_authority: dict[str, dict[str, object]],
        authority_paths: set[str],
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        chains: list[dict[str, object]] = []
        merged: dict[str, dict[str, object]] = {}
        for seed in seed_paths:
            applicable = [
                path for path in authority_paths if _instruction_applies(path, seed)
            ]
            applicable.sort(
                key=lambda path: (
                    _instruction_specificity(path),
                    0 if Path(path).name == "AGENTS.md" else 1,
                    path,
                )
            )
            chain: list[dict[str, object]] = []
            for order, path in enumerate(applicable):
                row = indexed_authority[path]
                entry: dict[str, object] = {
                    "path": path,
                    "scope": _instruction_scope(path),
                    "specificity": _instruction_specificity(path),
                    "kind": (
                        "override"
                        if Path(path).name == "AGENTS.override.md"
                        else "agents"
                    ),
                    "precedence": order,
                    "evidence_visibility": str(row.get("evidence_visibility") or ""),
                }
                chain.append(entry)
                previous = merged.get(path)
                if previous is None:
                    merged[path] = {**entry, "applies_to": [seed]}
                    continue
                applies_to = previous["applies_to"]
                if isinstance(applies_to, list) and seed not in applies_to:
                    applies_to.append(seed)
            chains.append({"path": seed, "authority": chain})

        ordered = sorted(
            merged.values(),
            key=lambda row: (
                cast(int, row["specificity"]),
                0 if row["kind"] == "agents" else 1,
                str(row["path"]),
            ),
        )
        return chains, ordered

    def ensure_current(self, relpath: str) -> None:
        rel = normalize_relative_path(relpath, allow_root=False)
        if self.index.needs_reconcile(rel):
            if self.reads.depth > 0:
                raise DecisionRefreshRequired(rel)
            self.index.reconcile_path(rel)

    def reconcile_contributors(self, paths: Sequence[str]) -> None:
        """Reconcile caller-observed drift before opening another read scope."""
        if not paths:
            return
        normalized = tuple(
            normalize_relative_path(path, allow_root=False) for path in paths
        )
        if self.reads.depth > 0:
            for path in normalized:
                self.ensure_current(path)
            return
        if any(not (self.workspace / path).exists() for path in normalized):
            self.index.sync()
        else:
            self.index.sync(normalized)

    def restored_contributors(self, paths: Sequence[str]) -> tuple[str, ...]:
        """Observe admitted regular files that have returned under a stale binding."""
        return tuple(
            sorted(
                path
                for path in paths
                if self.files.is_admitted(path)
                and (self.workspace / path).is_file()
                and not (self.workspace / path).is_symlink()
                and not self.index.is_current(path)
            )
        )

    @operation_response("outline")
    @decision_scoped
    def outline(self, relpath: str) -> dict[str, object]:
        self.reads.ready()
        rel = normalize_relative_path(relpath, allow_root=False)
        self.ensure_current(rel)
        row = self.store.outline(rel)
        if row is None:
            raise FileNotFoundError(f"not indexed: {rel}")
        visibility = EvidenceVisibility(str(row["evidence_visibility"]))
        if visibility is EvidenceVisibility.DENY:
            raise PermissionError(
                f"repository evidence denied by context policy: {rel}"
            )
        generation, identity_generation, stale = self.reads.generation_status()
        return {
            "schema": operation_schema("outline"),
            "path": rel,
            "language": row["language"],
            "file_digest": row["file_digest"],
            "full_tokens": row["full_tokens"],
            "outline_tokens": estimate_tokens(str(row["outline"])),
            "outline": row["outline"],
            "symbols": deepcopy(self.reads.symbols_for_path(rel)),
            "parse_error": row["parse_error"],
            "evidence_visibility": visibility.value,
            "generation": generation,
            "identity_generation": identity_generation,
            "stale": stale,
        }

    def slice(
        self, path: str, start: int, end: int, *, qualname: str | None = None
    ) -> str:
        self.ensure_current(path)
        row = self.reads.file_row(path)
        if row is None:
            raise FileNotFoundError(path)
        visibility = EvidenceVisibility(str(row["evidence_visibility"]))
        if visibility is not EvidenceVisibility.SOURCE:
            raise PermissionError(
                f"source body is not visible under the evidence policy: {path}"
            )
        if qualname is not None:
            current = self.store.symbol_at(path, qualname)
            if current is not None:
                start = int(current["start_line"])
                end = int(current["end_line"])
        observation, raw = self.member(path, include_bytes=True)
        if raw is None:
            if observation.get("reason") == "member-revision-mismatch":
                raise DecisionRefreshRequired(path)
            raise OSError(
                f"source observation unavailable for {path}: {observation['state']}"
            )
        lines = raw.decode("utf-8", errors="replace").splitlines()
        return "\n".join(lines[start - 1 : end])

    def packet_identity(
        self,
        *,
        generation: int,
        identity_generation: int | None,
        stale: bool | None,
    ) -> str:
        digest = packet_digest(
            "hashmarks.source-identity.v1",
            {
                "repository_identity": self.reads.repository_identity(),
                "codemap_generation": generation,
                "identity_generation": identity_generation,
                "stale": stale is not False,
            },
        )
        return f"sha256:{digest}"

    @decision_scoped
    def instruction_scope(
        self,
        paths: str | Sequence[str],
        *,
        query: str = "",
        scope_source: str = "explicit-path",
    ) -> dict[str, object]:
        """Observe indexed instruction scope for explicit caller-selected paths."""
        self.reads.ready()
        raw_paths = [paths] if isinstance(paths, str) else paths
        seed_paths = list(
            dict.fromkeys(
                normalize_relative_path(path, allow_root=False) for path in raw_paths
            )
        )
        rows = self.store.repository_instruction_file_rows()
        indexed_authority = {str(row["path"]): dict(row) for row in rows}
        authority_paths = {
            path
            for path in indexed_authority
            if Path(path).name in {"AGENTS.md", "AGENTS.override.md"}
        }
        chains, ordered = self._instruction_authority_projection(
            seed_paths, indexed_authority, authority_paths
        )
        return {
            "schema": "hashmarks.codemap-scoped-authority.v1",
            "query": query,
            **self.reads.freshness_fields(),
            "scope_source": scope_source,
            "seed_paths": seed_paths,
            "authority": ordered,
            "chains": chains,
            "precedence": "deeper scope wins; AGENTS.override.md wins over AGENTS.md at the same scope",
            "evidence": "indexed repository path hierarchy only; no semantic authority inference",
            "ranking_effect": "none",
        }
