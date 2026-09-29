from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from .engine import CodeMap

_MAX_TOTAL_ANCHORS = 256
CORRELATION_REQUEST_MAX_BYTES = 1_048_576
CORRELATION_PACKET_MAX_BYTES = 1_048_576
_CORRELATION_SCHEMA = "hashmarks.evidence-correlation.v2"
_DEFINITION_DOMAIN = "hashmarks.evidence-correlation-definition.v2"
_DELTA_SCHEMA = "hashmarks.evidence-correlation-delta.v2"
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


def _json_equal(left: object, right: object) -> bool:
    return json.dumps(
        left, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ) == json.dumps(right, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class EvidenceCorrelationReplayMixin:
    def _validate_correlation_packet(
        self,
        packet: Mapping[str, object],
        *,
        label: str,
    ) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if packet.get("schema") != _CORRELATION_SCHEMA:
            raise ValueError(f"{label} must be a {_CORRELATION_SCHEMA} packet")
        repository_evidence = packet.get("repository_evidence")
        if not isinstance(repository_evidence, Mapping):
            raise ValueError("correlation packets must contain repository_evidence")
        repository = repository_evidence.get("repository")
        repository_identity = (
            str(repository.get("repository_identity") or "")
            if isinstance(repository, Mapping)
            else ""
        )
        if repository_identity != self._repository_packet_identity():
            raise ValueError(f"{label} correlation repository-mismatch")
        self._validate_binding_delta_input(
            repository_evidence, name=f"{label} repository"
        )
        supplied_identity = packet.get("correlation_identity")
        if not isinstance(supplied_identity, str) or not _SHA256.fullmatch(
            supplied_identity
        ):
            raise ValueError(
                f"{label} correlation_identity must use sha256:<64 lowercase hex characters>"
            )
        identity_payload = dict(packet)
        identity_payload.pop("correlation_identity", None)
        identity_payload.pop("delta_from_previous", None)
        expected_identity = "sha256:" + self._packet_digest(
            _CORRELATION_SCHEMA,
            identity_payload,
        )
        if supplied_identity != expected_identity:
            raise ValueError(
                f"{label} correlation_identity does not match packet content"
            )

        self._validate_correlation_projections(packet, label=label)

    def _validate_correlation_projections(
        self, packet: Mapping[str, object], *, label: str
    ) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._validate_correlation_contract(packet, label=label)
        bundles = packet.get("bundles")
        mappings = packet.get("path_mappings")
        if not isinstance(bundles, list) or any(
            not isinstance(bundle, Mapping) for bundle in bundles
        ):
            raise ValueError(f"{label} correlation bundles are invalid")
        if not isinstance(mappings, list) or any(
            not isinstance(mapping, Mapping) for mapping in mappings
        ):
            raise ValueError(f"{label} correlation path mappings are invalid")
        bundles = cast("list[Mapping[str, object]]", bundles)
        mappings = cast("list[Mapping[str, str]]", mappings)
        include, limit = self._validated_correlation_options(packet, label=label)
        definition = self._definition(
            bundles,
            mappings=mappings,
            include_relationships=include,
            relationship_limit_per_path=limit or 100,
        )
        expected_definition = "sha256:" + self._packet_digest(
            _DEFINITION_DOMAIN, definition
        )
        if packet.get("evidence_definition_identity") != expected_definition:
            raise ValueError(f"{label} evidence_definition_identity mismatch")
        if not _json_equal(
            packet.get("completeness"), self._overall_completeness(bundles)
        ):
            raise ValueError(f"{label} correlation completeness mismatch")
        repository_evidence = packet["repository_evidence"]
        assert isinstance(repository_evidence, Mapping)
        self._validate_correlation_anchors(
            bundles, repository_evidence, include=include, limit=limit, label=label
        )
        if not _json_equal(
            packet.get("correspondence"), self._cross_bundle_correspondence(bundles)
        ):
            raise ValueError(f"{label} correlation correspondence mismatch")

    @staticmethod
    def _validate_correlation_contract(
        packet: Mapping[str, object], *, label: str
    ) -> None:
        expected_fields = {
            "schema",
            "evidence_definition_identity",
            "definition_options",
            "path_mappings",
            "bundles",
            "repository_evidence",
            "completeness",
            "storage",
            "authority",
            "external_claims_authority",
            "interpretation_authority",
            "causation",
            "execution_effect",
            "bounds",
            "correspondence",
            "correlation_identity",
        }
        if set(packet) - {"delta_from_previous"} != expected_fields:
            raise ValueError(f"{label} correlation fields mismatch")
        fixed = {
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
        if any(not _json_equal(packet.get(key), value) for key, value in fixed.items()):
            raise ValueError(f"{label} correlation authority or bounds mismatch")

    @staticmethod
    def _validated_correlation_options(
        packet: Mapping[str, object], *, label: str
    ) -> tuple[bool, int | None]:
        options = packet.get("definition_options")
        if not isinstance(options, Mapping):
            raise ValueError(f"{label} correlation definition inputs are invalid")
        if set(options) != {"include_relationships", "relationship_limit_per_path"}:
            raise ValueError(f"{label} correlation definition inputs are invalid")
        include = options["include_relationships"]
        limit = options["relationship_limit_per_path"]
        if type(include) is not bool:
            raise ValueError(f"{label} correlation definition options are invalid")
        if include and (type(limit) is not int or not 1 <= limit <= 1000):
            raise ValueError(f"{label} correlation definition options are invalid")
        if not include and limit is not None:
            raise ValueError(f"{label} correlation definition options are invalid")
        return cast("bool", include), cast("int | None", limit)

    def _validate_correlation_anchors(
        self,
        bundles: Sequence[Mapping[str, object]],
        repository_evidence: Mapping[str, object],
        *,
        include: bool,
        limit: int | None,
        label: str,
    ) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        rows = self._correlation_binding_rows(repository_evidence)
        referenced: set[str] = set()
        for bundle in bundles:
            anchors = bundle.get("anchors")
            if not isinstance(anchors, list) or any(
                not isinstance(anchor, Mapping) for anchor in anchors
            ):
                raise ValueError(f"{label} correlation anchors are invalid")
            for anchor in anchors:
                assert isinstance(anchor, Mapping)
                binding_id = self._validate_correlation_anchor(
                    anchor, rows, include=include, limit=limit, label=label
                )
                referenced.add(binding_id)
        if referenced != set(rows):
            raise ValueError(f"{label} correlation binding set mismatch")

    def _validate_correlation_anchor(
        self,
        anchor: Mapping[str, object],
        rows: Mapping[str, Mapping[str, object]],
        *,
        include: bool,
        limit: int | None,
        label: str,
    ) -> str:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        binding_id = anchor.get("repository_evidence_binding_id")
        if not isinstance(binding_id, str) or binding_id not in rows:
            raise ValueError(f"{label} correlation anchor binding mismatch")
        binding = rows[binding_id]
        expected_reference = {
            "binding_id": binding_id,
            "binding_definition_identity": binding.get("binding_definition_identity"),
            "binding_observation_identity": binding.get("binding_observation_identity"),
        }
        if not _json_equal(anchor.get("repository_evidence"), expected_reference):
            raise ValueError(f"{label} correlation anchor evidence mismatch")
        self._validate_anchor_references(anchor, binding, label=label)
        if not _json_equal(
            anchor.get("source_equivalence"),
            self._equivalence(anchor, binding),
        ):
            raise ValueError(f"{label} correlation source equivalence mismatch")
        self._validate_correlation_relationships(
            binding, include=include, limit=limit, label=label
        )
        return binding_id

    @staticmethod
    def _validate_anchor_references(
        anchor: Mapping[str, object],
        binding: Mapping[str, object],
        *,
        label: str,
    ) -> None:
        claims = anchor.get("claims")
        resolution = anchor.get("resolution")
        evidence = binding.get("evidence")
        if not isinstance(claims, Mapping) or not isinstance(resolution, Mapping):
            raise ValueError(f"{label} correlation anchor resolution is invalid")
        if not isinstance(evidence, list) or any(
            not isinstance(row, Mapping) for row in evidence
        ):
            raise ValueError(f"{label} correlation binding evidence is invalid")
        expected = EvidenceCorrelationReplayMixin._anchor_reference_definitions(
            claims, resolution, label=label
        )
        actual = [
            {
                key: row[key]
                for key in ("scope", "path", "start_line", "end_line")
                if key in row
            }
            for row in evidence
        ]
        if not _json_equal(actual, expected):
            raise ValueError(f"{label} correlation anchor binding references mismatch")

    @staticmethod
    def _anchor_reference_definitions(
        claims: Mapping[str, object],
        resolution: Mapping[str, object],
        *,
        label: str,
    ) -> list[dict[str, object]]:
        path, line = EvidenceCorrelationReplayMixin._anchor_path_line(
            claims, resolution, label=label
        )
        if path is not None and line is not None:
            return [
                {"scope": "lines", "path": path, "start_line": line, "end_line": line}
            ]
        symbol = resolution.get("symbol")
        candidates = resolution.get("candidates")
        modules = resolution.get("module_candidates")
        if path is not None and isinstance(symbol, Mapping):
            return [
                EvidenceCorrelationReplayMixin._symbol_reference_definition(
                    symbol, label=label
                )
            ]
        if isinstance(candidates, list) and candidates:
            return [
                EvidenceCorrelationReplayMixin._symbol_reference_definition(
                    row, label=label
                )
                for row in candidates
            ]
        if isinstance(modules, list) and modules:
            if any(not isinstance(module, str) for module in modules):
                raise ValueError(f"{label} correlation module candidates are invalid")
            return [{"scope": "member", "path": module} for module in modules]
        if path is not None:
            return [{"scope": "member", "path": path}]
        return []

    @staticmethod
    def _anchor_path_line(
        claims: Mapping[str, object],
        resolution: Mapping[str, object],
        *,
        label: str,
    ) -> tuple[str | None, int | None]:
        path = resolution.get("repository_path")
        line = claims.get("line")
        if path is not None and not isinstance(path, str):
            raise ValueError(f"{label} correlation anchor path is invalid")
        if line is not None and (type(line) is not int or line < 1):
            raise ValueError(f"{label} correlation anchor line is invalid")
        return path, cast("int | None", line)

    @staticmethod
    def _symbol_reference_definition(row: object, *, label: str) -> dict[str, object]:
        if not isinstance(row, Mapping):
            raise ValueError(f"{label} correlation symbol reference is invalid")
        path = row.get("path")
        start = row.get("start_line")
        end = row.get("end_line")
        if not isinstance(path, str) or not path:
            raise ValueError(f"{label} correlation symbol reference is invalid")
        if type(start) is not int or type(end) is not int:
            raise ValueError(f"{label} correlation symbol reference is invalid")
        return {"scope": "lines", "path": path, "start_line": start, "end_line": end}

    @staticmethod
    def _validate_correlation_relationships(
        binding: Mapping[str, object],
        *,
        include: bool,
        limit: int | None,
        label: str,
    ) -> None:
        relationships = binding.get("relationships")
        if not isinstance(relationships, Mapping):
            raise ValueError(f"{label} correlation relationships are invalid")
        if include:
            bounds = relationships.get("bounds")
            if not isinstance(bounds, Mapping) or not _json_equal(
                bounds.get("limit_per_path"), limit
            ):
                raise ValueError(f"{label} correlation relationship limit mismatch")
            if relationships.get("state") == "not-requested":
                raise ValueError(f"{label} correlation relationship mode mismatch")
        elif relationships.get("state") != "not-requested":
            raise ValueError(f"{label} correlation relationship mode mismatch")
