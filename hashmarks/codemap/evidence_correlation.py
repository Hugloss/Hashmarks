from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

from hashmarks.paths import normalize_relative_path

from .decision_session import decision_scoped
from .model import EvidenceVisibility

if TYPE_CHECKING:
    from .engine import CodeMap

_MAX_BUNDLES = 64
_MAX_ANCHORS_PER_BUNDLE = 256
_MAX_TOTAL_ANCHORS = 256
_MAX_PATH_MAPPINGS = 64
_MAX_METADATA_BYTES_PER_ANCHOR = 8_192
_MAX_TOTAL_METADATA_BYTES = 262_144
_MAX_SYMBOL_CANDIDATES = 32
_MAX_ID_CHARS = 512
_MAX_SYMBOL_CHARS = 1_024
_MAX_EXTERNAL_PATH_CHARS = 8_192
_COMPLETENESS = frozenset({"complete", "incomplete", "unknown"})
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:/")


def _json_size(value: object, *, label: str) -> int:
    try:
        return len(
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must contain JSON-compatible values") from exc


def _bounded_identifier(value: object, *, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} must not be empty")
    if len(text) > _MAX_ID_CHARS:
        raise ValueError(f"{label} exceeds {_MAX_ID_CHARS} characters")
    return text


def _bounded_symbol(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > _MAX_SYMBOL_CHARS:
        raise ValueError(f"symbol exceeds {_MAX_SYMBOL_CHARS} characters")
    return text


def _external_path(value: object) -> str:
    raw = str(value or "")
    if not raw:
        raise ValueError("path must not be empty")
    if len(raw) > _MAX_EXTERNAL_PATH_CHARS:
        raise ValueError(f"path exceeds {_MAX_EXTERNAL_PATH_CHARS} characters")
    if "\x00" in raw:
        raise ValueError("path contains NUL byte")
    normalized = raw.replace("\\", "/")
    if re.fullmatch(r"[A-Za-z]:/", normalized):
        return normalized
    parts = normalized.split("/")
    if ".." in parts:
        raise ValueError("external path must not contain '..'")
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    if normalized != "/":
        normalized = normalized.rstrip("/")
    if not normalized:
        raise ValueError("path must not be empty")
    return normalized


def _is_absolute_external_path(path: str) -> bool:
    return path.startswith("/") or bool(_WINDOWS_DRIVE.match(path))


def _path_mapping_definition(raw: Mapping[str, object]) -> dict[str, str]:
    external_prefix = _external_path(raw.get("external_prefix"))
    if not _is_absolute_external_path(external_prefix):
        raise ValueError("external_prefix must be an absolute external path")
    repository_prefix_raw = str(raw.get("repository_prefix") or "")
    repository_prefix = normalize_relative_path(repository_prefix_raw, allow_root=True)
    return {
        "external_prefix": external_prefix,
        "repository_prefix": repository_prefix,
    }


def _member_revision(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not _HEX64.fullmatch(text):
        raise ValueError(
            "member_revision must be a lowercase 64-character sha256 hex digest"
        )
    return text


def _span_identity(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not _SHA256.fullmatch(text):
        raise ValueError(
            "span_identity must use sha256:<64 lowercase hex characters>"
        )
    return text


class EvidenceCorrelationMixin:
    """Correlate bounded external claims to canonical repository evidence.

    External claims remain claims. This mixin resolves them into existing
    repository-evidence bindings and never promotes correlation into causation,
    diagnosis, recommendation, workflow, or execution authority.
    """

    @staticmethod
    def _correlation_path_mappings(
        raw_mappings: Sequence[Mapping[str, object]] | None,
    ) -> list[dict[str, str]]:
        if raw_mappings is None:
            return []
        if not isinstance(raw_mappings, Sequence) or isinstance(
            raw_mappings, (str, bytes, bytearray)
        ):
            raise ValueError("path_mappings must be a sequence")
        if len(raw_mappings) > _MAX_PATH_MAPPINGS:
            raise ValueError(f"path_mappings exceeds {_MAX_PATH_MAPPINGS} entries")
        mappings: list[dict[str, str]] = []
        seen: set[str] = set()
        for raw in raw_mappings:
            if not isinstance(raw, Mapping):
                raise ValueError("each path mapping must be an object")
            mapping = _path_mapping_definition(raw)
            prefix = mapping["external_prefix"]
            if prefix in seen:
                raise ValueError(f"duplicate external_prefix: {prefix}")
            seen.add(prefix)
            mappings.append(mapping)
        mappings.sort(
            key=lambda row: (-len(row["external_prefix"]), row["external_prefix"])
        )
        return mappings

    @staticmethod
    def _map_external_path(
        claimed_path: str, mappings: Sequence[Mapping[str, str]]
    ) -> tuple[str | None, str]:
        if not _is_absolute_external_path(claimed_path):
            return (
                normalize_relative_path(claimed_path, allow_root=False),
                "repository-relative",
            )

        for mapping in mappings:
            prefix = str(mapping["external_prefix"])
            root_prefix = prefix == "/" or bool(
                re.fullmatch(r"[A-Za-z]:/", prefix)
            )
            matches = (
                claimed_path.startswith(prefix)
                if root_prefix
                else claimed_path == prefix
                or claimed_path.startswith(prefix + "/")
            )
            if not matches:
                continue
            suffix = claimed_path[len(prefix) :].lstrip("/")
            repository_prefix = str(mapping["repository_prefix"])
            combined = "/".join(
                part for part in (repository_prefix, suffix) if part
            )
            if not combined:
                return None, "mapping-resolves-repository-root"
            return (
                normalize_relative_path(combined, allow_root=False),
                "explicit-path-mapping",
            )
        return None, "external-path-mapping-required"

    @staticmethod
    def _visible_symbol(row: Mapping[str, object]) -> bool:
        visibility = row.get("evidence_visibility")
        if visibility is None:
            return True
        return (
            EvidenceVisibility(str(visibility))
            is not EvidenceVisibility.DENY
        )

    def _symbols_for_path(self, path: str) -> list[dict[str, object]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._ensure_path_current(path)
        return [
            dict(row)
            for row in self.store.symbols_for_paths_complete([path])
            if self._visible_symbol(row)
        ]

    @staticmethod
    def _symbol_matches(
        row: Mapping[str, object], claimed_symbol: str
    ) -> bool:
        return claimed_symbol in {
            str(row.get("name") or ""),
            str(row.get("qualname") or ""),
            f"{row.get('path')}::{row.get('qualname')}",
        }

    @staticmethod
    def _symbol_projection(
        row: Mapping[str, object],
    ) -> dict[str, object]:
        return {
            "path": str(row.get("path") or ""),
            "name": str(row.get("name") or ""),
            "qualname": str(row.get("qualname") or ""),
            "kind": str(row.get("kind") or ""),
            "start_line": int(row.get("start_line") or 0),
            "end_line": int(row.get("end_line") or 0),
        }

    def _resolve_anchor(  # noqa: PLR0914
        self,
        raw_anchor: Mapping[str, object],
        *,
        mappings: Sequence[Mapping[str, str]],
    ) -> tuple[dict[str, object], list[dict[str, object]]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)

        anchor_id = _bounded_identifier(
            raw_anchor.get("anchor_id"), label="anchor_id"
        )
        claimed_path = (
            _external_path(raw_anchor.get("path"))
            if raw_anchor.get("path") is not None
            else None
        )
        claimed_symbol = _bounded_symbol(raw_anchor.get("symbol"))
        raw_line = raw_anchor.get("line")
        line: int | None = None
        if raw_line is not None:
            if isinstance(raw_line, bool):
                raise ValueError("line must be a positive integer")
            try:
                line = int(raw_line)
            except (TypeError, ValueError) as exc:
                raise ValueError("line must be a positive integer") from exc
            if line < 1:
                raise ValueError("line must be a positive integer")
        if claimed_path is None and claimed_symbol is None:
            raise ValueError("each anchor requires path and/or symbol")
        if line is not None and claimed_path is None:
            raise ValueError("line requires path")

        metadata = raw_anchor.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise ValueError("anchor metadata must be an object")
        metadata = dict(metadata)
        metadata_bytes = _json_size(metadata, label="anchor metadata")
        if metadata_bytes > _MAX_METADATA_BYTES_PER_ANCHOR:
            raise ValueError(
                "anchor metadata exceeds "
                f"{_MAX_METADATA_BYTES_PER_ANCHOR} encoded bytes"
            )

        claimed_member_revision = _member_revision(
            raw_anchor.get("member_revision")
        )
        claimed_span_identity = _span_identity(
            raw_anchor.get("span_identity")
        )

        resolved_path: str | None = None
        path_origin = "not-supplied"
        if claimed_path is not None:
            resolved_path, path_origin = self._map_external_path(
                claimed_path, mappings
            )

        candidates: list[dict[str, object]] = []
        candidates_truncated = False
        selected: dict[str, object] | None = None
        state = "unresolved"
        reason = "no-repository-match"

        if resolved_path is None and claimed_path is not None:
            reason = path_origin
        elif resolved_path is not None:
            symbols = self._symbols_for_path(resolved_path)
            if line is not None:
                containing = [
                    row
                    for row in symbols
                    if int(row.get("start_line") or 0)
                    <= line
                    <= int(row.get("end_line") or 0)
                ]
                if claimed_symbol is not None:
                    matching = [
                        row
                        for row in containing
                        if self._symbol_matches(row, claimed_symbol)
                    ]
                    if len(matching) == 1:
                        selected = matching[0]
                        candidates = matching
                        state = "resolved-unique"
                        reason = "path-line-symbol"
                    elif len(matching) > 1:
                        candidates = matching
                        state = "resolved-ambiguous"
                        reason = (
                            "multiple-containing-symbols-match-claim"
                        )
                    elif containing:
                        candidates = containing
                        state = "claim-conflict"
                        reason = (
                            "symbol-does-not-match-containing-repository-symbol"
                        )
                    else:
                        matching_anywhere = [
                            row
                            for row in symbols
                            if self._symbol_matches(row, claimed_symbol)
                        ]
                        candidates = matching_anywhere
                        state = (
                            "claim-conflict"
                            if matching_anywhere
                            else "resolved-unique"
                        )
                        reason = (
                            "symbol-does-not-contain-claimed-line"
                            if matching_anywhere
                            else "path-line-no-containing-symbol"
                        )
                elif containing:
                    min_span = min(
                        int(row.get("end_line") or 0)
                        - int(row.get("start_line") or 0)
                        for row in containing
                    )
                    most_specific = [
                        row
                        for row in containing
                        if int(row.get("end_line") or 0)
                        - int(row.get("start_line") or 0)
                        == min_span
                    ]
                    candidates = most_specific
                    if len(most_specific) == 1:
                        selected = most_specific[0]
                        state = "resolved-unique"
                        reason = "path-line"
                    else:
                        state = "resolved-ambiguous"
                        reason = (
                            "multiple-most-specific-containing-symbols"
                        )
                else:
                    state = "resolved-unique"
                    reason = "path-line-no-containing-symbol"
            elif claimed_symbol is not None:
                matching = [
                    row
                    for row in symbols
                    if self._symbol_matches(row, claimed_symbol)
                ]
                candidates = matching
                if len(matching) == 1:
                    selected = matching[0]
                    state = "resolved-unique"
                    reason = "path-symbol"
                elif len(matching) > 1:
                    state = "resolved-ambiguous"
                    reason = "multiple-symbols-match-path-claim"
                else:
                    state = "claim-conflict"
                    reason = "symbol-not-found-at-resolved-path"
            else:
                state = "resolved-unique"
                reason = "path-member"
        else:
            assert claimed_symbol is not None
            rows = [
                row
                for row in self.store.symbol(claimed_symbol)
                if self._visible_symbol(row)
            ]
            candidates_truncated = len(rows) > _MAX_SYMBOL_CANDIDATES
            candidates = [
                dict(row) for row in rows[:_MAX_SYMBOL_CANDIDATES]
            ]
            if len(rows) == 1:
                selected = dict(rows[0])
                resolved_path = str(rows[0]["path"])
                state = "resolved-unique"
                reason = "symbol-only"
            elif rows:
                state = "resolved-ambiguous"
                reason = "symbol-matches-multiple-repository-symbols"
            else:
                reason = "symbol-not-found"

        evidence: list[dict[str, object]] = []
        if resolved_path is not None:
            if line is not None:
                evidence.append(
                    {
                        "path": resolved_path,
                        "start_line": line,
                        "end_line": line,
                    }
                )
            elif selected is not None:
                evidence.append(
                    {
                        "path": resolved_path,
                        "start_line": int(selected["start_line"]),
                        "end_line": int(selected["end_line"]),
                    }
                )
            elif state == "resolved-ambiguous" and candidates:
                for row in candidates:
                    evidence.append(
                        {
                            "path": str(row["path"]),
                            "start_line": int(row["start_line"]),
                            "end_line": int(row["end_line"]),
                        }
                    )
            else:
                evidence.append(
                    {"scope": "member", "path": resolved_path}
                )
        elif candidates:
            for row in candidates:
                evidence.append(
                    {
                        "path": str(row["path"]),
                        "start_line": int(row["start_line"]),
                        "end_line": int(row["end_line"]),
                    }
                )

        result: dict[str, object] = {
            "anchor_id": anchor_id,
            "claims": {
                **(
                    {"path": claimed_path}
                    if claimed_path is not None
                    else {}
                ),
                **({"line": line} if line is not None else {}),
                **(
                    {"symbol": claimed_symbol}
                    if claimed_symbol is not None
                    else {}
                ),
                **(
                    {"member_revision": claimed_member_revision}
                    if claimed_member_revision is not None
                    else {}
                ),
                **(
                    {"span_identity": claimed_span_identity}
                    if claimed_span_identity is not None
                    else {}
                ),
                "metadata": metadata,
            },
            "resolution": {
                "state": state,
                "reason": reason,
                "path_origin": path_origin,
                **(
                    {"repository_path": resolved_path}
                    if resolved_path is not None
                    else {}
                ),
                **(
                    {"symbol": self._symbol_projection(selected)}
                    if selected is not None
                    else {}
                ),
                "candidates": [
                    self._symbol_projection(row) for row in candidates
                ],
                "candidate_completeness": (
                    "bounded"
                    if candidates_truncated
                    else "complete"
                ),
            },
            "source_equivalence": {"state": "unknown", "basis": []},
            "metadata_bytes": metadata_bytes,
        }
        return result, evidence

    @staticmethod
    def _equivalence(
        anchor: Mapping[str, object], binding: Mapping[str, object]
    ) -> dict[str, object]:
        claims = anchor.get("claims")
        if not isinstance(claims, Mapping):
            return {"state": "unknown", "basis": []}
        claimed_member = claims.get("member_revision")
        claimed_span = claims.get("span_identity")
        evidence = binding.get("evidence")
        if not isinstance(evidence, Sequence) or isinstance(
            evidence, (str, bytes)
        ):
            return {"state": "unknown", "basis": []}
        comparable = [
            row for row in evidence if isinstance(row, Mapping)
        ]
        if len(comparable) != 1:
            return {"state": "unknown", "basis": []}
        observed = comparable[0]
        basis: list[dict[str, object]] = []
        mismatched = False
        if (
            claimed_member is not None
            and observed.get("member_revision") is not None
        ):
            matched = str(claimed_member) == str(
                observed["member_revision"]
            )
            mismatched = mismatched or not matched
            basis.append(
                {"kind": "member-revision", "matched": matched}
            )
        if (
            claimed_span is not None
            and observed.get("span_identity") is not None
        ):
            matched = str(claimed_span) == str(
                observed["span_identity"]
            )
            mismatched = mismatched or not matched
            basis.append(
                {"kind": "span-identity", "matched": matched}
            )
        if not basis:
            return {"state": "unknown", "basis": []}
        return {
            "state": "mismatch" if mismatched else "proven",
            "basis": basis,
        }

    @decision_scoped
    def correlate_evidence(  # noqa: PLR0914
        self,
        bundles: Sequence[Mapping[str, object]],
        *,
        path_mappings: Sequence[Mapping[str, object]] | None = None,
        relationship_limit_per_path: int = 100,
        include_relationships: bool = True,
        previous_correlation: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        """Correlate bounded evidence bundles with current repository truth."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if not isinstance(bundles, Sequence) or isinstance(
            bundles, (str, bytes, bytearray)
        ):
            raise ValueError("bundles must be a sequence")
        if len(bundles) > _MAX_BUNDLES:
            raise ValueError(f"bundles exceeds {_MAX_BUNDLES} entries")
        if any(not isinstance(bundle, Mapping) for bundle in bundles):
            raise ValueError("each bundle must be an object")

        mappings = self._correlation_path_mappings(path_mappings)
        seen_bundles: set[str] = set()
        binding_definitions: list[dict[str, object]] = []
        prepared: list[dict[str, object]] = []
        total_metadata_bytes = 0

        for bundle_index, raw_bundle in enumerate(bundles):
            assert isinstance(raw_bundle, Mapping)
            bundle_id = _bounded_identifier(
                raw_bundle.get("bundle_id"), label="bundle_id"
            )
            if bundle_id in seen_bundles:
                raise ValueError(f"duplicate bundle_id: {bundle_id}")
            seen_bundles.add(bundle_id)
            completeness = str(
                raw_bundle.get("completeness") or "unknown"
            ).strip()
            if completeness not in _COMPLETENESS:
                raise ValueError(
                    "bundle completeness must be complete, "
                    "incomplete, or unknown"
                )
            producer = raw_bundle.get("producer", {})
            if not isinstance(producer, Mapping):
                raise ValueError("bundle producer must be an object")
            producer = dict(producer)
            producer_bytes = _json_size(
                producer, label="bundle producer"
            )
            if producer_bytes > _MAX_METADATA_BYTES_PER_ANCHOR:
                raise ValueError(
                    "bundle producer exceeds "
                    f"{_MAX_METADATA_BYTES_PER_ANCHOR} encoded bytes"
                )
            raw_anchors = raw_bundle.get("anchors")
            if not isinstance(raw_anchors, Sequence) or isinstance(
                raw_anchors, (str, bytes, bytearray)
            ):
                raise ValueError("bundle anchors must be a sequence")
            if len(raw_anchors) > _MAX_ANCHORS_PER_BUNDLE:
                raise ValueError(
                    "bundle anchors exceeds "
                    f"{_MAX_ANCHORS_PER_BUNDLE} entries"
                )
            if any(
                not isinstance(anchor, Mapping)
                for anchor in raw_anchors
            ):
                raise ValueError("each anchor must be an object")

            seen_anchors: set[str] = set()
            anchors: list[dict[str, object]] = []
            for anchor_index, raw_anchor in enumerate(raw_anchors):
                assert isinstance(raw_anchor, Mapping)
                anchor, evidence = self._resolve_anchor(
                    raw_anchor, mappings=mappings
                )
                anchor_id = str(anchor["anchor_id"])
                if anchor_id in seen_anchors:
                    raise ValueError(
                        "duplicate anchor_id in bundle "
                        f"{bundle_id}: {anchor_id}"
                    )
                seen_anchors.add(anchor_id)
                total_metadata_bytes += int(
                    anchor["metadata_bytes"]
                )
                if total_metadata_bytes > _MAX_TOTAL_METADATA_BYTES:
                    raise ValueError(
                        "evidence metadata exceeds "
                        f"{_MAX_TOTAL_METADATA_BYTES} encoded bytes"
                    )
                binding_id = (
                    f"external-evidence:{bundle_index}:{anchor_index}"
                )
                anchor["repository_evidence_binding_id"] = binding_id
                binding_definitions.append(
                    {"binding_id": binding_id, "evidence": evidence}
                )
                if (
                    len(binding_definitions)
                    > _MAX_TOTAL_ANCHORS
                ):
                    raise ValueError(
                        "evidence request exceeds "
                        f"{_MAX_TOTAL_ANCHORS} total anchors"
                    )
                anchors.append(anchor)
            prepared.append(
                {
                    "bundle_id": bundle_id,
                    "producer": producer,
                    "completeness": completeness,
                    "anchors": anchors,
                }
            )

        repository_evidence = self.repository_evidence_bindings(
            binding_definitions,
            relationship_limit_per_path=relationship_limit_per_path,
            include_relationships=include_relationships,
        )
        binding_rows = {
            str(row["binding_id"]): row
            for row in repository_evidence.get("bindings", [])
            if isinstance(row, Mapping)
            and row.get("binding_id") is not None
        }
        for bundle in prepared:
            anchors = bundle["anchors"]
            assert isinstance(anchors, list)
            for anchor in anchors:
                assert isinstance(anchor, dict)
                binding_id = str(
                    anchor["repository_evidence_binding_id"]
                )
                binding = binding_rows.get(binding_id)
                if binding is not None:
                    anchor["source_equivalence"] = self._equivalence(
                        anchor, binding
                    )
                    anchor["repository_evidence"] = {
                        "binding_definition_identity": binding.get(
                            "binding_definition_identity"
                        ),
                        "binding_observation_identity": binding.get(
                            "binding_observation_identity"
                        ),
                        "evidence": binding.get("evidence", []),
                        "relationships": binding.get(
                            "relationships", {}
                        ),
                    }
                anchor.pop("metadata_bytes", None)

        declaration = {
            "path_mappings": mappings,
            "bundles": [
                {
                    "bundle_id": bundle["bundle_id"],
                    "producer": bundle["producer"],
                    "completeness": bundle["completeness"],
                    "anchors": [
                        anchor["claims"]
                        for anchor in bundle["anchors"]
                        if isinstance(anchor, Mapping)
                    ],
                }
                for bundle in prepared
            ],
            "include_relationships": include_relationships,
            "relationship_limit_per_path": (
                relationship_limit_per_path
                if include_relationships
                else None
            ),
        }
        states = [
            str(bundle["completeness"]) for bundle in prepared
        ]
        packet: dict[str, object] = {
            "schema": "hashmarks.evidence-correlation.v1",
            "evidence_definition_identity": "sha256:"
            + self._packet_digest(
                "hashmarks.evidence-correlation-definition.v1",
                declaration,
            ),
            "path_mappings": mappings,
            "bundles": prepared,
            "repository_evidence": repository_evidence,
            "completeness": {
                "state": (
                    "complete"
                    if states
                    and all(state == "complete" for state in states)
                    else "incomplete"
                    if "incomplete" in states
                    else "unknown"
                ),
                "scope": "caller-declared-external-observations",
            },
            "storage": "request-scoped-not-persisted",
            "authority": "repository-intelligence-only",
            "external_claims_authority": (
                "untrusted-unless-correlated"
            ),
            "interpretation_authority": "consumer-owned",
            "causation": "not-inferred",
            "execution_effect": "none",
        }
        packet["correlation_identity"] = (
            "sha256:"
            + self._packet_digest(
                "hashmarks.evidence-correlation.v1", packet
            )
        )
        if previous_correlation is not None:
            packet[
                "delta_from_previous"
            ] = self.evidence_correlation_delta(
                previous_correlation, packet
            )
        return packet

    def evidence_correlation_delta(
        self,
        before: Mapping[str, object],
        after: Mapping[str, object],
    ) -> dict[str, object]:
        """Compare two correlation packets without inferring causal meaning."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if (
            before.get("schema")
            != "hashmarks.evidence-correlation.v1"
        ):
            raise ValueError(
                "before must be a "
                "hashmarks.evidence-correlation.v1 packet"
            )
        if (
            after.get("schema")
            != "hashmarks.evidence-correlation.v1"
        ):
            raise ValueError(
                "after must be a "
                "hashmarks.evidence-correlation.v1 packet"
            )
        before_repository = before.get("repository_evidence")
        after_repository = after.get("repository_evidence")
        if not isinstance(
            before_repository, Mapping
        ) or not isinstance(after_repository, Mapping):
            raise ValueError(
                "correlation packets must contain repository_evidence"
            )

        repository_delta = (
            self.repository_evidence_binding_delta(
                before_repository, after_repository
            )
        )
        definition_state = (
            "preserved"
            if before.get("evidence_definition_identity")
            == after.get("evidence_definition_identity")
            else "changed"
        )
        payload: dict[str, object] = {
            "schema": "hashmarks.evidence-correlation-delta.v1",
            "definition": {
                "state": definition_state,
                "before": before.get(
                    "evidence_definition_identity"
                ),
                "after": after.get(
                    "evidence_definition_identity"
                ),
            },
            "repository_evidence_delta": repository_delta,
            "before_correlation_identity": before.get(
                "correlation_identity"
            ),
            "after_correlation_identity": after.get(
                "correlation_identity"
            ),
            "authority": "repository-intelligence-only",
            "interpretation_authority": "consumer-owned",
            "causation": "not-inferred",
            "execution_effect": "none",
        }
        payload["delta_identity"] = (
            "sha256:"
            + self._packet_digest(
                "hashmarks.evidence-correlation-delta.v1",
                payload,
            )
        )
        return payload
