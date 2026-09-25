from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

from .repository_declaration_contract import (
    MAX_DECLARATIONS,
    MAX_EXPECTED_PER_GROUP,
    MAX_GROUPS,
    MAX_PACKET_BYTES,
    MAX_REQUEST_BYTES,
    absence,
    comparison,
    encoded_json_bytes,
    normalize_request,
)
from .repository_declaration_delta import declaration_delta

if TYPE_CHECKING:
    from .engine import CodeMap

_SCHEMA = "hashmarks.repository-declarations.v1"


class RepositoryDeclarationsMixin:
    """Project cross-artifact declarations without choosing a winning value."""

    @staticmethod
    def _binding_evidence_state(binding: Mapping[str, object]) -> str:
        evidence = binding.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            return "unknown"
        states = {
            str(row.get("state") or "unknown")
            for row in evidence
            if isinstance(row, Mapping)
        }
        if states == {"known-present"}:
            return "known-present"
        if "unsupported" in states:
            return "unsupported"
        if "known-absent" in states:
            return "known-absent"
        return "unknown"

    def _project_declaration(
        self,
        normalized: Mapping[str, object],
        group_id: str,
        concept: Mapping[str, object],
        scope: Mapping[str, object],
        binding_rows: Mapping[str, Mapping[str, object]],
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        declaration_id = str(normalized["declaration_id"])
        binding = binding_rows[str(normalized["binding_id"])]
        evidence_state = self._binding_evidence_state(binding)
        definition = {
            "group_id": group_id,
            "concept": concept,
            "scope": scope,
            "declaration_id": declaration_id,
            "binding_definition_identity": binding["binding_definition_identity"],
        }
        observation = {
            **definition,
            "value_state": normalized["value_state"],
            **({"value": normalized["value"]} if "value" in normalized else {}),
            **(
                {"candidate_values": normalized["candidate_values"]}
                if "candidate_values" in normalized
                else {}
            ),
            "producer": normalized["producer"],
            "evidence_state": evidence_state,
            "binding_observation_identity": binding["binding_observation_identity"],
        }
        return {
            **normalized,
            "evidence_state": evidence_state,
            "declaration_definition_identity": "sha256:"
            + self._packet_digest(
                "hashmarks.repository-declaration-definition.v1",
                definition,
            ),
            "declaration_observation_identity": "sha256:"
            + self._packet_digest(
                "hashmarks.repository-declaration-observation.v1",
                observation,
            ),
        }

    def _declaration_group(
        self,
        group: Mapping[str, object],
        binding_rows: Mapping[str, Mapping[str, object]],
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        group_id = str(group["group_id"])
        concept = cast("Mapping[str, object]", group["concept"])
        scope = cast("Mapping[str, object]", group["scope"])
        correspondence = cast("Mapping[str, object]", group["correspondence"])
        coverage = cast("Mapping[str, object]", group["coverage"])
        raw_declarations = cast(
            "Sequence[Mapping[str, object]]",
            group["declarations"],
        )
        declarations = [
            self._project_declaration(
                normalized,
                group_id,
                concept,
                scope,
                binding_rows,
            )
            for normalized in raw_declarations
        ]
        declarations.sort(key=lambda row: str(row["declaration_id"]))

        definition_payload = {
            "group_id": group_id,
            "concept": concept,
            "scope": scope,
            "coverage_scope": coverage["scope"],
            "expected_declaration_ids": coverage["expected_declaration_ids"],
            "declaration_definition_identities": [
                {
                    "declaration_id": row["declaration_id"],
                    "identity": row["declaration_definition_identity"],
                }
                for row in declarations
            ],
        }
        observation_payload = {
            **definition_payload,
            "correspondence": correspondence,
            "coverage": coverage,
            "declarations": declarations,
            "comparison": comparison(declarations, correspondence),
            "absence": absence(declarations, coverage),
        }
        return {
            **observation_payload,
            "group_definition_identity": "sha256:"
            + self._packet_digest(
                "hashmarks.repository-declaration-group-definition.v1",
                definition_payload,
            ),
            "group_observation_identity": "sha256:"
            + self._packet_digest(
                "hashmarks.repository-declaration-group-observation.v1",
                observation_payload,
            ),
        }

    def _declaration_packet_identity(self, packet: Mapping[str, object]) -> str:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        payload = {
            key: value
            for key, value in packet.items()
            if key not in {"observation_identity", "delta_from_previous"}
        }
        return "sha256:" + self._packet_digest(_SCHEMA, payload)

    def _validate_previous_declarations(self, previous: Mapping[str, object]) -> None:
        if previous.get("schema") != _SCHEMA:
            raise ValueError(f"previous observation must use schema {_SCHEMA}")
        identity = previous.get("observation_identity")
        if not isinstance(
            identity, str
        ) or identity != self._declaration_packet_identity(previous):
            raise ValueError("previous declaration observation identity mismatch")

    def repository_declarations(
        self,
        groups: Sequence[Mapping[str, object]],
        *,
        previous_observation: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        """Qualify declaration correspondence against exact repository evidence.

        Semantic extraction, normalization, grouping, and correspondence are
        provider claims. Hashmarks binds those claims to current repository
        evidence, preserves ambiguity, compares only normalized values inside an
        explicitly scoped group, and admits absence only under complete,
        untruncated declared coverage.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        normalized_groups, bindings = normalize_request(groups)
        evidence_packet = self.repository_evidence_bindings(
            bindings, include_relationships=False
        )
        binding_rows = {
            str(row["binding_id"]): row for row in evidence_packet["bindings"]
        }
        projected = [
            self._declaration_group(group, binding_rows) for group in normalized_groups
        ]
        projected.sort(key=lambda row: str(row["group_id"]))

        packet: dict[str, object] = {
            "schema": _SCHEMA,
            "observer": evidence_packet["observer"],
            "repository": evidence_packet["repository"],
            "groups": projected,
            "repository_evidence": evidence_packet,
            "bounds": {
                "max_groups": MAX_GROUPS,
                "max_declarations": MAX_DECLARATIONS,
                "max_expected_declarations_per_group": MAX_EXPECTED_PER_GROUP,
                "max_request_bytes": MAX_REQUEST_BYTES,
                "max_packet_bytes": MAX_PACKET_BYTES,
            },
            "storage": "derived-not-persisted",
            "authority": "repository-intelligence-only",
            "semantic_value_authority": "provider-claimed",
            "correspondence_authority": "provider-claimed",
            "interpretation_authority": "consumer-owned",
            "winner": "not-selected",
        }
        packet["observation_identity"] = self._declaration_packet_identity(packet)
        if encoded_json_bytes(packet, name="declaration packet") > MAX_PACKET_BYTES:
            raise ValueError(
                f"declaration packet exceeds {MAX_PACKET_BYTES} encoded bytes"
            )
        if previous_observation is not None:
            if not isinstance(previous_observation, Mapping):
                raise ValueError("previous_observation must be an object")
            if (
                encoded_json_bytes(
                    previous_observation,
                    name="previous_observation",
                )
                > MAX_PACKET_BYTES
            ):
                raise ValueError(
                    f"previous_observation exceeds {MAX_PACKET_BYTES} encoded bytes"
                )
            self._validate_previous_declarations(previous_observation)
            previous_repository_evidence = previous_observation.get(
                "repository_evidence"
            )
            if not isinstance(previous_repository_evidence, Mapping):
                raise ValueError(
                    "previous_observation.repository_evidence must be an object"
                )
            repository_evidence_delta = self.repository_evidence_binding_delta(
                previous_repository_evidence,
                evidence_packet,
            )
            packet["delta_from_previous"] = declaration_delta(
                previous_observation,
                packet,
                repository_evidence_delta=repository_evidence_delta,
            )
            if encoded_json_bytes(packet, name="declaration packet") > MAX_PACKET_BYTES:
                raise ValueError(
                    f"declaration packet exceeds {MAX_PACKET_BYTES} encoded bytes"
                )
        return packet
