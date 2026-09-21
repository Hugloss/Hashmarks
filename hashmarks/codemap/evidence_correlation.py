from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from hashmarks.paths import normalize_relative_path

from .decision_session import decision_scoped

if TYPE_CHECKING:
    from .engine import CodeMap

_MAX_BUNDLES = 64
_MAX_ANCHORS_PER_BUNDLE = 256
_MAX_TOTAL_ANCHORS = 256
_MAX_PATH_MAPPINGS = 64
_MAX_METADATA_BYTES_PER_ANCHOR = 8_192
_MAX_TOTAL_METADATA_BYTES = 262_144
_MAX_SYMBOL_CANDIDATES = 32
_MAX_MODULE_CANDIDATES = 20
CORRELATION_REQUEST_MAX_BYTES = 1_048_576
CORRELATION_PACKET_MAX_BYTES = 1_048_576
_MAX_ID_CHARS = 512
_MAX_SYMBOL_CHARS = 1_024
_MAX_EXTERNAL_PATH_CHARS = 8_192
_COMPLETENESS = frozenset({"complete", "incomplete", "unknown"})
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:/")


@dataclass(frozen=True, slots=True)
class _AnchorClaims:
    anchor_id: str
    path: str | None
    line: int | None
    symbol: str | None
    module: str | None
    metadata: dict[str, object]
    metadata_bytes: int
    member_revision: str | None
    span_identity: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            **({"path": self.path} if self.path is not None else {}),
            **({"line": self.line} if self.line is not None else {}),
            **({"symbol": self.symbol} if self.symbol is not None else {}),
            **({"module": self.module} if self.module is not None else {}),
            **(
                {"member_revision": self.member_revision}
                if self.member_revision is not None
                else {}
            ),
            **(
                {"span_identity": self.span_identity}
                if self.span_identity is not None
                else {}
            ),
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class _Resolution:
    state: str
    reason: str
    path_origin: str
    repository_path: str | None = None
    symbol: Mapping[str, object] | None = None
    candidates: tuple[Mapping[str, object], ...] = ()
    module_candidates: tuple[str, ...] = ()
    candidates_truncated: bool = False


@dataclass(frozen=True, slots=True)
class _PreparedBundle:
    packet: dict[str, object]
    bindings: tuple[dict[str, object], ...]
    metadata_bytes: int
    anchor_count: int


def _json_size(value: object, *, label: str) -> int:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must contain JSON-compatible values") from exc
    return len(encoded)


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


def _bounded_module(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().strip(".")
    if not text:
        return None
    if len(text) > _MAX_SYMBOL_CHARS:
        raise ValueError(f"module exceeds {_MAX_SYMBOL_CHARS} characters")
    if any(char.isspace() for char in text) or "/" in text or "\\" in text:
        raise ValueError("module must be an exact dotted module identity")
    if any(not part for part in text.split(".")):
        raise ValueError("module must be an exact dotted module identity")
    return text


def _positive_line(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("line must be a positive integer")
    try:
        line = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("line must be a positive integer") from exc
    if line < 1:
        raise ValueError("line must be a positive integer")
    return line


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
    if ".." in normalized.split("/"):
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
    repository_prefix = normalize_relative_path(
        str(raw.get("repository_prefix") or ""),
        allow_root=True,
    )
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


def _binding_id(evidence: Sequence[Mapping[str, object]]) -> str:
    encoded = json.dumps(
        list(evidence),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    digest = hashlib.sha256(
        b"hashmarks.external-evidence-binding.v2\0" + encoded
    ).hexdigest()
    return "external-evidence:" + digest


class EvidenceCorrelationMixin:
    """Correlate bounded external claims to canonical repository evidence.

    External claims remain claims. The implementation resolves them into the
    existing repository-evidence binding authority and never promotes
    correlation into causation, diagnosis, recommendation, workflow, or
    execution authority.
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
        mappings = EvidenceCorrelationMixin._validated_mappings(raw_mappings)
        mappings.sort(
            key=lambda row: (-len(row["external_prefix"]), row["external_prefix"])
        )
        return mappings

    @staticmethod
    def _validated_mappings(
        raw_mappings: Sequence[Mapping[str, object]],
    ) -> list[dict[str, str]]:
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
        return mappings

    @staticmethod
    def _map_external_path(
        claimed_path: str,
        mappings: Sequence[Mapping[str, str]],
    ) -> tuple[str | None, str]:
        if not _is_absolute_external_path(claimed_path):
            return (
                normalize_relative_path(claimed_path, allow_root=False),
                "repository-relative",
            )
        for mapping in mappings:
            mapped = EvidenceCorrelationMixin._apply_path_mapping(
                claimed_path, mapping
            )
            if mapped is not None:
                return mapped
        return None, "external-path-mapping-required"

    @staticmethod
    def _apply_path_mapping(
        claimed_path: str,
        mapping: Mapping[str, str],
    ) -> tuple[str | None, str] | None:
        prefix = str(mapping["external_prefix"])
        root_prefix = prefix == "/" or bool(re.fullmatch(r"[A-Za-z]:/", prefix))
        matches = (
            claimed_path.startswith(prefix)
            if root_prefix
            else claimed_path == prefix or claimed_path.startswith(prefix + "/")
        )
        if not matches:
            return None
        suffix = claimed_path[len(prefix) :].lstrip("/")
        repository_prefix = str(mapping["repository_prefix"])
        combined = "/".join(part for part in (repository_prefix, suffix) if part)
        if not combined:
            return None, "mapping-resolves-repository-root"
        return (
            normalize_relative_path(combined, allow_root=False),
            "explicit-path-mapping",
        )

    @staticmethod
    def _anchor_claims(raw_anchor: Mapping[str, object]) -> _AnchorClaims:
        claimed_path = (
            _external_path(raw_anchor.get("path"))
            if raw_anchor.get("path") is not None
            else None
        )
        line = _positive_line(raw_anchor.get("line"))
        symbol = _bounded_symbol(raw_anchor.get("symbol"))
        module = _bounded_module(raw_anchor.get("module"))
        if claimed_path is None and symbol is None and module is None:
            raise ValueError("each anchor requires path, symbol, and/or module")
        if line is not None and claimed_path is None and module is None:
            raise ValueError("line requires path or module")
        metadata = raw_anchor.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise ValueError("anchor metadata must be an object")
        metadata_dict = dict(metadata)
        metadata_bytes = _json_size(metadata_dict, label="anchor metadata")
        if metadata_bytes > _MAX_METADATA_BYTES_PER_ANCHOR:
            raise ValueError(
                "anchor metadata exceeds "
                f"{_MAX_METADATA_BYTES_PER_ANCHOR} encoded bytes"
            )
        return _AnchorClaims(
            anchor_id=_bounded_identifier(
                raw_anchor.get("anchor_id"), label="anchor_id"
            ),
            path=claimed_path,
            line=line,
            symbol=symbol,
            module=module,
            metadata=metadata_dict,
            metadata_bytes=metadata_bytes,
            member_revision=_member_revision(raw_anchor.get("member_revision")),
            span_identity=_span_identity(raw_anchor.get("span_identity")),
        )

    def _resolve_anchor(
        self,
        claims: _AnchorClaims,
        *,
        mappings: Sequence[Mapping[str, str]],
    ) -> _Resolution:
        if claims.path is None:
            if claims.module is not None:
                module_resolution = self._resolve_module_only(claims.module)
                if module_resolution.state != "resolved-unique":
                    return module_resolution
                assert module_resolution.repository_path is not None
                if claims.symbol is not None:
                    return self._resolve_symbol_at_path(
                        module_resolution.repository_path,
                        claims.symbol,
                        line=claims.line,
                        path_origin="module",
                    )
                if claims.line is not None:
                    return self._resolve_line_at_path(
                        module_resolution.repository_path,
                        claims.line,
                        path_origin="module",
                    )
                return module_resolution
            assert claims.symbol is not None
            return self._resolve_symbol_only(claims.symbol)
        repository_path, path_origin = self._map_external_path(
            claims.path, mappings
        )
        if repository_path is None:
            return _Resolution(
                "unresolved",
                path_origin,
                path_origin,
            )
        member, _raw = self._repository_member_observation(repository_path)
        if member.get("state") != "known-present":
            return _Resolution(
                "unresolved",
                str(member.get("reason") or member.get("state") or "unknown"),
                path_origin,
                repository_path,
            )
        if claims.module is not None:
            module_conflict = self._module_path_conflict(
                repository_path, claims.module, path_origin=path_origin
            )
            if module_conflict is not None:
                return module_conflict
        if claims.symbol is not None:
            return self._resolve_symbol_at_path(
                repository_path,
                claims.symbol,
                line=claims.line,
                path_origin=path_origin,
            )
        if claims.line is not None:
            return self._resolve_line_at_path(
                repository_path,
                claims.line,
                path_origin=path_origin,
            )
        return _Resolution(
            "resolved-unique",
            "path-member",
            path_origin,
            repository_path,
        )

    def _resolve_module_only(self, module: str) -> _Resolution:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        rows = self.store.visible_module_paths(
            module, limit=_MAX_MODULE_CANDIDATES + 1
        )
        admitted: list[str] = []
        for path in rows:
            member, _raw = self._repository_member_observation(path)
            if member.get("state") == "known-present":
                admitted.append(path)
        candidates = tuple(admitted[:_MAX_MODULE_CANDIDATES])
        truncated = len(admitted) > _MAX_MODULE_CANDIDATES
        if len(admitted) == 1:
            return _Resolution(
                "resolved-unique",
                "module-only",
                "module",
                admitted[0],
                module_candidates=candidates,
            )
        if admitted:
            return _Resolution(
                "resolved-ambiguous",
                (
                    "module-match-bound-exhausted"
                    if truncated
                    else "module-matches-multiple-repository-members"
                ),
                "module",
                module_candidates=candidates,
                candidates_truncated=truncated,
            )
        return _Resolution(
            "unresolved",
            "module-not-found",
            "module",
        )

    def _module_path_conflict(
        self,
        path: str,
        module: str,
        *,
        path_origin: str,
    ) -> _Resolution | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        row = self._session_file_row(path)
        observed = "" if row is None else str(row.get("module_name") or "")
        if observed == module:
            return None
        return _Resolution(
            "claim-conflict",
            (
                "module-does-not-match-resolved-path"
                if observed
                else "module-not-proven-for-resolved-path"
            ),
            path_origin,
            path,
        )

    def _resolve_symbol_only(self, symbol: str) -> _Resolution:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        rows = self.store.visible_symbol_candidates(
            symbol,
            limit=_MAX_SYMBOL_CANDIDATES + 1,
        )
        candidates = tuple(rows[:_MAX_SYMBOL_CANDIDATES])
        truncated = len(rows) > _MAX_SYMBOL_CANDIDATES
        if len(rows) == 1:
            selected = rows[0]
            return _Resolution(
                "resolved-unique",
                "symbol-only",
                "not-supplied",
                str(selected["path"]),
                selected,
                candidates,
            )
        if rows:
            return _Resolution(
                "resolved-ambiguous",
                "symbol-matches-multiple-repository-symbols",
                "not-supplied",
                candidates=candidates,
                candidates_truncated=truncated,
            )
        return _Resolution(
            "unresolved",
            "symbol-not-found",
            "not-supplied",
        )

    def _resolve_symbol_at_path(
        self,
        path: str,
        symbol: str,
        *,
        line: int | None,
        path_origin: str,
    ) -> _Resolution:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        rows = self.store.symbol_candidates_at_path(
            path,
            symbol,
            limit=_MAX_SYMBOL_CANDIDATES + 1,
        )
        candidates = tuple(rows[:_MAX_SYMBOL_CANDIDATES])
        truncated = len(rows) > _MAX_SYMBOL_CANDIDATES
        if truncated:
            return _Resolution(
                "resolved-ambiguous",
                "symbol-match-bound-exhausted",
                path_origin,
                path,
                candidates=candidates,
                candidates_truncated=True,
            )
        if not rows:
            return _Resolution(
                "claim-conflict",
                "symbol-not-found-at-resolved-path",
                path_origin,
                path,
            )
        return self._resolve_symbol_rows(
            path,
            rows,
            line=line,
            path_origin=path_origin,
        )

    @staticmethod
    def _resolve_symbol_rows(
        path: str,
        rows: Sequence[Mapping[str, object]],
        *,
        line: int | None,
        path_origin: str,
    ) -> _Resolution:
        candidates = tuple(rows)
        if line is None:
            if len(rows) == 1:
                return _Resolution(
                    "resolved-unique",
                    "path-symbol",
                    path_origin,
                    path,
                    rows[0],
                    candidates,
                )
            return _Resolution(
                "resolved-ambiguous",
                "multiple-symbols-match-path-claim",
                path_origin,
                path,
                candidates=candidates,
            )
        containing = tuple(
            row
            for row in rows
            if int(row.get("start_line") or 0)
            <= line
            <= int(row.get("end_line") or 0)
        )
        if len(containing) == 1:
            return _Resolution(
                "resolved-unique",
                "path-line-symbol",
                path_origin,
                path,
                containing[0],
                containing,
            )
        if len(containing) > 1:
            return _Resolution(
                "resolved-ambiguous",
                "multiple-containing-symbols-match-claim",
                path_origin,
                path,
                candidates=containing,
            )
        return _Resolution(
            "claim-conflict",
            "symbol-does-not-contain-claimed-line",
            path_origin,
            path,
            candidates=candidates,
        )

    def _resolve_line_at_path(
        self,
        path: str,
        line: int,
        *,
        path_origin: str,
    ) -> _Resolution:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        rows = self.store.symbols_containing_line(
            path,
            line,
            limit=_MAX_SYMBOL_CANDIDATES + 1,
        )
        candidates = tuple(rows[:_MAX_SYMBOL_CANDIDATES])
        if len(rows) > _MAX_SYMBOL_CANDIDATES:
            return _Resolution(
                "resolved-ambiguous",
                "containing-symbol-bound-exhausted",
                path_origin,
                path,
                candidates=candidates,
                candidates_truncated=True,
            )
        if not rows:
            return _Resolution(
                "resolved-unique",
                "path-line-no-containing-symbol",
                path_origin,
                path,
            )
        smallest = min(
            int(row.get("end_line") or 0)
            - int(row.get("start_line") or 0)
            for row in rows
        )
        most_specific = tuple(
            row
            for row in rows
            if int(row.get("end_line") or 0)
            - int(row.get("start_line") or 0)
            == smallest
        )
        if len(most_specific) == 1:
            return _Resolution(
                "resolved-unique",
                "path-line",
                path_origin,
                path,
                most_specific[0],
                most_specific,
            )
        return _Resolution(
            "resolved-ambiguous",
            "multiple-most-specific-containing-symbols",
            path_origin,
            path,
            candidates=most_specific,
        )

    @staticmethod
    def _symbol_projection(row: Mapping[str, object]) -> dict[str, object]:
        return {
            "path": str(row.get("path") or ""),
            "name": str(row.get("name") or ""),
            "qualname": str(row.get("qualname") or ""),
            "kind": str(row.get("kind") or ""),
            "start_line": int(row.get("start_line") or 0),
            "end_line": int(row.get("end_line") or 0),
        }

    @staticmethod
    def _resolution_packet(resolution: _Resolution) -> dict[str, object]:
        return {
            "state": resolution.state,
            "reason": resolution.reason,
            "path_origin": resolution.path_origin,
            **(
                {"repository_path": resolution.repository_path}
                if resolution.repository_path is not None
                else {}
            ),
            **(
                {"symbol": EvidenceCorrelationMixin._symbol_projection(resolution.symbol)}
                if resolution.symbol is not None
                else {}
            ),
            "candidates": [
                EvidenceCorrelationMixin._symbol_projection(row)
                for row in resolution.candidates
            ],
            "module_candidates": list(resolution.module_candidates),
            "candidate_completeness": (
                "bounded" if resolution.candidates_truncated else "complete"
            ),
        }

    @staticmethod
    def _repository_references(
        claims: _AnchorClaims,
        resolution: _Resolution,
    ) -> list[dict[str, object]]:
        path = resolution.repository_path
        if path is not None and claims.line is not None:
            return [
                {
                    "path": path,
                    "start_line": claims.line,
                    "end_line": claims.line,
                }
            ]
        if path is not None and resolution.symbol is not None:
            return [
                EvidenceCorrelationMixin._symbol_reference(resolution.symbol)
            ]
        if resolution.candidates:
            return [
                EvidenceCorrelationMixin._symbol_reference(row)
                for row in resolution.candidates
            ]
        if resolution.module_candidates:
            return [
                {"scope": "member", "path": candidate}
                for candidate in resolution.module_candidates
            ]
        if path is not None:
            return [{"scope": "member", "path": path}]
        return []

    @staticmethod
    def _symbol_reference(row: Mapping[str, object]) -> dict[str, object]:
        return {
            "path": str(row["path"]),
            "start_line": int(row["start_line"]),
            "end_line": int(row["end_line"]),
        }

    def _prepare_anchor(
        self,
        raw_anchor: Mapping[str, object],
        *,
        mappings: Sequence[Mapping[str, str]],
        resolution_cache: dict[
            tuple[str | None, int | None, str | None, str | None],
            _Resolution,
        ],
    ) -> tuple[dict[str, object], dict[str, object], int]:
        claims = self._anchor_claims(raw_anchor)
        resolution_key = (
            claims.path,
            claims.line,
            claims.symbol,
            claims.module,
        )
        resolution = resolution_cache.get(resolution_key)
        if resolution is None:
            resolution = self._resolve_anchor(claims, mappings=mappings)
            resolution_cache[resolution_key] = resolution
        references = self._repository_references(claims, resolution)
        binding_id = _binding_id(references)
        packet = {
            "anchor_id": claims.anchor_id,
            "claims": claims.as_dict(),
            "resolution": self._resolution_packet(resolution),
            "source_equivalence": {"state": "unknown", "basis": []},
            "repository_evidence_binding_id": binding_id,
        }
        binding = {
            "binding_id": binding_id,
            "evidence": references,
        }
        return packet, binding, claims.metadata_bytes

    def _prepare_bundle(
        self,
        raw_bundle: Mapping[str, object],
        *,
        mappings: Sequence[Mapping[str, str]],
        resolution_cache: dict[
            tuple[str | None, int | None, str | None, str | None],
            _Resolution,
        ],
    ) -> _PreparedBundle:
        bundle_id = _bounded_identifier(
            raw_bundle.get("bundle_id"),
            label="bundle_id",
        )
        completeness = str(raw_bundle.get("completeness") or "unknown").strip()
        if completeness not in _COMPLETENESS:
            raise ValueError(
                "bundle completeness must be complete, incomplete, or unknown"
            )
        producer = self._bundle_producer(raw_bundle)
        raw_anchors = raw_bundle.get("anchors")
        self._validate_raw_anchors(raw_anchors)
        assert isinstance(raw_anchors, Sequence)
        return self._prepare_bundle_anchors(
            bundle_id,
            producer,
            completeness,
            raw_anchors,
            mappings=mappings,
            resolution_cache=resolution_cache,
        )

    @staticmethod
    def _bundle_producer(
        raw_bundle: Mapping[str, object],
    ) -> dict[str, object]:
        producer = raw_bundle.get("producer", {})
        if not isinstance(producer, Mapping):
            raise ValueError("bundle producer must be an object")
        packet = dict(producer)
        if _json_size(packet, label="bundle producer") > _MAX_METADATA_BYTES_PER_ANCHOR:
            raise ValueError(
                "bundle producer exceeds "
                f"{_MAX_METADATA_BYTES_PER_ANCHOR} encoded bytes"
            )
        return packet

    @staticmethod
    def _validate_raw_anchors(raw_anchors: object) -> None:
        if not isinstance(raw_anchors, Sequence) or isinstance(
            raw_anchors, (str, bytes, bytearray)
        ):
            raise ValueError("bundle anchors must be a sequence")
        if len(raw_anchors) > _MAX_ANCHORS_PER_BUNDLE:
            raise ValueError(
                f"bundle anchors exceeds {_MAX_ANCHORS_PER_BUNDLE} entries"
            )
        if any(not isinstance(anchor, Mapping) for anchor in raw_anchors):
            raise ValueError("each anchor must be an object")

    def _prepare_bundle_anchors(
        self,
        bundle_id: str,
        producer: dict[str, object],
        completeness: str,
        raw_anchors: Sequence[object],
        *,
        mappings: Sequence[Mapping[str, str]],
        resolution_cache: dict[
            tuple[str | None, int | None, str | None, str | None],
            _Resolution,
        ],
    ) -> _PreparedBundle:
        anchors: list[dict[str, object]] = []
        bindings: list[dict[str, object]] = []
        seen: set[str] = set()
        metadata_bytes = 0
        for raw_anchor in raw_anchors:
            assert isinstance(raw_anchor, Mapping)
            anchor, binding, anchor_metadata_bytes = self._prepare_anchor(
                raw_anchor,
                mappings=mappings,
                resolution_cache=resolution_cache,
            )
            anchor_id = str(anchor["anchor_id"])
            if anchor_id in seen:
                raise ValueError(
                    f"duplicate anchor_id in bundle {bundle_id}: {anchor_id}"
                )
            seen.add(anchor_id)
            metadata_bytes += anchor_metadata_bytes
            anchors.append(anchor)
            bindings.append(binding)
        return _PreparedBundle(
            packet={
                "bundle_id": bundle_id,
                "producer": producer,
                "completeness": completeness,
                "anchors": anchors,
            },
            bindings=tuple(bindings),
            metadata_bytes=metadata_bytes,
            anchor_count=len(anchors),
        )

    def _prepare_bundles(
        self,
        bundles: Sequence[Mapping[str, object]],
        *,
        mappings: Sequence[Mapping[str, str]],
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        prepared: list[dict[str, object]] = []
        bindings_by_id: dict[str, dict[str, object]] = {}
        seen: set[str] = set()
        total_metadata = 0
        total_anchors = 0
        resolution_cache: dict[
            tuple[str | None, int | None, str | None, str | None],
            _Resolution,
        ] = {}
        for raw_bundle in bundles:
            result = self._prepare_bundle(
                raw_bundle,
                mappings=mappings,
                resolution_cache=resolution_cache,
            )
            bundle_id = str(result.packet["bundle_id"])
            if bundle_id in seen:
                raise ValueError(f"duplicate bundle_id: {bundle_id}")
            seen.add(bundle_id)
            total_metadata += result.metadata_bytes
            total_anchors += result.anchor_count
            self._validate_request_totals(total_metadata, total_anchors)
            prepared.append(result.packet)
            for binding in result.bindings:
                bindings_by_id[str(binding["binding_id"])] = binding
        prepared.sort(key=lambda row: str(row["bundle_id"]))
        bindings = [bindings_by_id[key] for key in sorted(bindings_by_id)]
        return prepared, bindings

    @staticmethod
    def _validate_request_totals(metadata_bytes: int, anchor_count: int) -> None:
        if metadata_bytes > _MAX_TOTAL_METADATA_BYTES:
            raise ValueError(
                "evidence metadata exceeds "
                f"{_MAX_TOTAL_METADATA_BYTES} encoded bytes"
            )
        if anchor_count > _MAX_TOTAL_ANCHORS:
            raise ValueError(
                f"evidence request exceeds {_MAX_TOTAL_ANCHORS} total anchors"
            )

    @staticmethod
    def _equivalence(
        anchor: Mapping[str, object],
        binding: Mapping[str, object],
    ) -> dict[str, object]:
        claims = anchor.get("claims")
        evidence = binding.get("evidence")
        if not isinstance(claims, Mapping):
            return {"state": "unknown", "basis": []}
        if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)):
            return {"state": "unknown", "basis": []}
        rows = [row for row in evidence if isinstance(row, Mapping)]
        if len(rows) != 1:
            return {"state": "unknown", "basis": []}
        return EvidenceCorrelationMixin._equivalence_for_row(claims, rows[0])

    @staticmethod
    def _equivalence_for_row(
        claims: Mapping[str, object],
        observed: Mapping[str, object],
    ) -> dict[str, object]:
        basis: list[dict[str, object]] = []
        for claim_key, observed_key, kind in (
            ("member_revision", "member_revision", "member-revision"),
            ("span_identity", "span_identity", "span-identity"),
        ):
            if claims.get(claim_key) is None or observed.get(observed_key) is None:
                continue
            basis.append(
                {
                    "kind": kind,
                    "matched": str(claims[claim_key]) == str(observed[observed_key]),
                }
            )
        if not basis:
            return {"state": "unknown", "basis": []}
        state = (
            "proven"
            if all(bool(row["matched"]) for row in basis)
            else "mismatch"
        )
        return {"state": state, "basis": basis}

    @staticmethod
    def _correlation_binding_rows(
        repository_evidence: Mapping[str, object],
    ) -> dict[str, Mapping[str, object]]:
        rows = repository_evidence.get("bindings", [])
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            return {}
        return {
            str(row["binding_id"]): row
            for row in rows
            if isinstance(row, Mapping) and row.get("binding_id") is not None
        }

    @staticmethod
    def _attach_repository_evidence(
        bundles: Sequence[dict[str, object]],
        repository_evidence: Mapping[str, object],
    ) -> None:
        binding_rows = EvidenceCorrelationMixin._correlation_binding_rows(repository_evidence)
        for bundle in bundles:
            anchors = bundle.get("anchors", [])
            if not isinstance(anchors, list):
                continue
            for anchor in anchors:
                if isinstance(anchor, dict):
                    EvidenceCorrelationMixin._attach_anchor_evidence(
                        anchor, binding_rows
                    )

    @staticmethod
    def _attach_anchor_evidence(
        anchor: dict[str, object],
        binding_rows: Mapping[str, Mapping[str, object]],
    ) -> None:
        binding_id = str(anchor["repository_evidence_binding_id"])
        binding = binding_rows.get(binding_id)
        if binding is None:
            return
        anchor["source_equivalence"] = EvidenceCorrelationMixin._equivalence(
            anchor, binding
        )
        anchor["repository_evidence"] = {
            "binding_id": binding_id,
            "binding_definition_identity": binding.get(
                "binding_definition_identity"
            ),
            "binding_observation_identity": binding.get(
                "binding_observation_identity"
            ),
        }

    @staticmethod
    def _definition(
        bundles: Sequence[Mapping[str, object]],
        *,
        mappings: Sequence[Mapping[str, str]],
        include_relationships: bool,
        relationship_limit_per_path: int,
    ) -> dict[str, object]:
        declarations = [
            EvidenceCorrelationMixin._bundle_definition(bundle)
            for bundle in bundles
        ]
        declarations.sort(key=lambda row: str(row["bundle_id"]))
        return {
            "path_mappings": list(mappings),
            "bundles": declarations,
            "include_relationships": include_relationships,
            "relationship_limit_per_path": (
                relationship_limit_per_path if include_relationships else None
            ),
        }

    @staticmethod
    def _bundle_definition(
        bundle: Mapping[str, object],
    ) -> dict[str, object]:
        anchors = bundle.get("anchors", [])
        return {
            "bundle_id": bundle.get("bundle_id"),
            "producer": bundle.get("producer", {}),
            "completeness": bundle.get("completeness"),
            "anchors": [
                {
                    "anchor_id": anchor.get("anchor_id"),
                    "claims": anchor.get("claims", {}),
                }
                for anchor in anchors
                if isinstance(anchor, Mapping)
            ],
        }

    @staticmethod
    def _overall_completeness(
        bundles: Sequence[Mapping[str, object]],
    ) -> dict[str, str]:
        states = [str(bundle.get("completeness") or "unknown") for bundle in bundles]
        if states and all(state == "complete" for state in states):
            state = "complete"
        elif "incomplete" in states:
            state = "incomplete"
        else:
            state = "unknown"
        return {
            "state": state,
            "scope": "caller-declared-external-observations",
        }

    @decision_scoped
    def correlate_evidence(
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
        self._validate_request_size(bundles, path_mappings)
        if previous_correlation is not None:
            self._validate_previous_correlation_size(previous_correlation)
        self._validate_bundles(bundles)
        mappings = self._correlation_path_mappings(path_mappings)
        prepared, bindings = self._prepare_bundles(bundles, mappings=mappings)
        repository_evidence = self.repository_evidence_bindings(
            bindings,
            relationship_limit_per_path=relationship_limit_per_path,
            include_relationships=include_relationships,
        )
        self._attach_repository_evidence(prepared, repository_evidence)
        definition = self._definition(
            prepared,
            mappings=mappings,
            include_relationships=include_relationships,
            relationship_limit_per_path=relationship_limit_per_path,
        )
        packet = self._correlation_packet(
            prepared,
            repository_evidence,
            definition,
            mappings=mappings,
        )
        if previous_correlation is not None:
            packet["delta_from_previous"] = self.evidence_correlation_delta(
                previous_correlation, packet
            )
        self._validate_packet_size(packet)
        return packet

    @staticmethod
    def _validate_request_size(
        bundles: object,
        path_mappings: object,
    ) -> None:
        size = _json_size(
            {"bundles": bundles, "path_mappings": path_mappings or []},
            label="evidence correlation request",
        )
        if size > CORRELATION_REQUEST_MAX_BYTES:
            raise ValueError(
                "evidence correlation request exceeds "
                f"{CORRELATION_REQUEST_MAX_BYTES} encoded bytes"
            )

    @staticmethod
    def _validate_previous_correlation_size(packet: Mapping[str, object]) -> None:
        size = _json_size(packet, label="previous correlation")
        if size > CORRELATION_PACKET_MAX_BYTES:
            raise ValueError(
                "previous correlation exceeds "
                f"{CORRELATION_PACKET_MAX_BYTES} encoded bytes"
            )

    @staticmethod
    def _validate_packet_size(packet: Mapping[str, object]) -> None:
        size = _json_size(packet, label="evidence correlation packet")
        if size > CORRELATION_PACKET_MAX_BYTES:
            raise ValueError(
                "evidence correlation packet exceeds "
                f"{CORRELATION_PACKET_MAX_BYTES} encoded bytes; "
                "reduce anchors or relationship_limit_per_path and split the evidence set"
            )

    @staticmethod
    def _validate_bundles(
        bundles: Sequence[Mapping[str, object]],
    ) -> None:
        if not isinstance(bundles, Sequence) or isinstance(
            bundles, (str, bytes, bytearray)
        ):
            raise ValueError("bundles must be a sequence")
        if len(bundles) > _MAX_BUNDLES:
            raise ValueError(f"bundles exceeds {_MAX_BUNDLES} entries")
        if any(not isinstance(bundle, Mapping) for bundle in bundles):
            raise ValueError("each bundle must be an object")

    def _correlation_packet(
        self,
        bundles: list[dict[str, object]],
        repository_evidence: dict[str, object],
        definition: dict[str, object],
        *,
        mappings: Sequence[Mapping[str, str]],
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        packet: dict[str, object] = {
            "schema": "hashmarks.evidence-correlation.v1",
            "evidence_definition_identity": "sha256:"
            + self._packet_digest(
                "hashmarks.evidence-correlation-definition.v1",
                definition,
            ),
            "path_mappings": list(mappings),
            "bundles": bundles,
            "repository_evidence": repository_evidence,
            "completeness": self._overall_completeness(bundles),
            "storage": "request-scoped-not-persisted",
            "authority": "repository-intelligence-only",
            "external_claims_authority": "untrusted-unless-correlated",
            "interpretation_authority": "consumer-owned",
            "causation": "not-inferred",
            "execution_effect": "none",
            "bounds": {
                "request_max_bytes": CORRELATION_REQUEST_MAX_BYTES,
                "packet_max_bytes": CORRELATION_PACKET_MAX_BYTES,
                "max_anchors": _MAX_TOTAL_ANCHORS,
            },
        }
        packet["correlation_identity"] = "sha256:" + self._packet_digest(
            "hashmarks.evidence-correlation.v1",
            packet,
        )
        return packet

    def evidence_correlation_delta(
        self,
        before: Mapping[str, object],
        after: Mapping[str, object],
    ) -> dict[str, object]:
        """Compare correlation packets without inferring causal meaning."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._validate_correlation_packet(before, label="before")
        self._validate_correlation_packet(after, label="after")
        before_repository = before["repository_evidence"]
        after_repository = after["repository_evidence"]
        assert isinstance(before_repository, Mapping)
        assert isinstance(after_repository, Mapping)
        repository_delta = self.repository_evidence_binding_delta(
            before_repository,
            after_repository,
        )
        payload = self._correlation_delta_packet(
            before,
            after,
            repository_delta,
        )
        payload["delta_identity"] = "sha256:" + self._packet_digest(
            "hashmarks.evidence-correlation-delta.v1",
            payload,
        )
        return payload

    @staticmethod
    def _validate_correlation_packet(
        packet: Mapping[str, object],
        *,
        label: str,
    ) -> None:
        if packet.get("schema") != "hashmarks.evidence-correlation.v1":
            raise ValueError(
                f"{label} must be a hashmarks.evidence-correlation.v1 packet"
            )
        if not isinstance(packet.get("repository_evidence"), Mapping):
            raise ValueError(
                "correlation packets must contain repository_evidence"
            )

    @staticmethod
    def _correlation_delta_packet(
        before: Mapping[str, object],
        after: Mapping[str, object],
        repository_delta: dict[str, object],
    ) -> dict[str, object]:
        definition_state = (
            "preserved"
            if before.get("evidence_definition_identity")
            == after.get("evidence_definition_identity")
            else "changed"
        )
        return {
            "schema": "hashmarks.evidence-correlation-delta.v1",
            "definition": {
                "state": definition_state,
                "before": before.get("evidence_definition_identity"),
                "after": after.get("evidence_definition_identity"),
            },
            "repository_evidence_delta": repository_delta,
            "before_correlation_identity": before.get("correlation_identity"),
            "after_correlation_identity": after.get("correlation_identity"),
            "authority": "repository-intelligence-only",
            "interpretation_authority": "consumer-owned",
            "causation": "not-inferred",
            "execution_effect": "none",
        }
