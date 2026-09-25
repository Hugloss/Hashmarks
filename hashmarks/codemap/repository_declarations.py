from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

from .repository_declaration_contract import (
    MAX_DECLARATIONS,
    MAX_EXPECTED_PER_GROUP,
    MAX_GROUPS,
    absence,
    comparison,
    json_value,
    mapping,
    normalize_correspondence,
    normalize_coverage,
    normalize_declaration,
    normalize_request,
    reject_unknown,
    required_text,
    GROUP_KEYS,
)
from .repository_declaration_delta import declaration_delta

if TYPE_CHECKING:
    from .engine import CodeMap

_SCHEMA = "hashmarks.repository-declarations.v1"


class RepositoryDeclarationsMixin:
    """Project cross-artifact declarations without choosing a winning value."""

    def _declaration_group(
        self,
        raw: object,
        binding_rows: Mapping[str, Mapping[str, object]],
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        group = mapping(raw, name="declaration group")
        reject_unknown(group, allowed=GROUP_KEYS, name="declaration group")
        group_id = required_text(group.get("group_id"), name="group_id")
        concept = json_value(group.get("concept"), name="concept")
        scope = json_value(group.get("scope", {}), name="scope")
        if not isinstance(concept, dict) or not isinstance(scope, dict):
            raise ValueError("concept and scope must be objects")
        correspondence = normalize_correspondence(group.get("correspondence", {}))
        coverage = normalize_coverage(group.get("coverage", {}))

        raw_declarations = group.get("declarations")
        if not isinstance(raw_declarations, Sequence) or isinstance(
            raw_declarations, (str, bytes)
        ):
            raise ValueError("declarations must be a list")

        declarations: list[dict[str, object]] = []
        seen: set[str] = set()
        for raw_declaration in raw_declarations:
            normalized, _binding = normalize_declaration(
                raw_declaration, group_id=group_id
            )
            declaration_id = str(normalized["declaration_id"])
            if declaration_id in seen:
                raise ValueError(
                    f"duplicate declaration_id in group {group_id}: {declaration_id}"
                )
            seen.add(declaration_id)
            binding = binding_rows[str(normalized["binding_id"])]
            definition = {
                "group_id": group_id,
                "concept": concept,
                "scope": scope,
                "declaration_id": declaration_id,
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
                "binding_observation_identity": binding[
                    "binding_observation_identity"
                ],
            }
            declarations.append(
                {
                    **normalized,
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
            )

        declarations.sort(key=lambda row: str(row["declaration_id"]))
        definition_payload = {
            "group_id": group_id,
            "concept": concept,
            "scope": scope,
            "expected_declaration_ids": coverage["expected_declaration_ids"],
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

    def _validate_previous_declarations(
        self, previous: Mapping[str, object]
    ) -> None:
        if previous.get("schema") != _SCHEMA:
            raise ValueError(f"previous observation must use schema {_SCHEMA}")
        identity = previous.get("observation_identity")
        if not isinstance(identity, str) or identity != self._declaration_packet_identity(
            previous
        ):
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
            self._declaration_group(raw, binding_rows) for raw in normalized_groups
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
            },
            "storage": "derived-not-persisted",
            "authority": "repository-intelligence-only",
            "semantic_value_authority": "provider-claimed",
            "correspondence_authority": "provider-claimed",
            "interpretation_authority": "consumer-owned",
            "winner": "not-selected",
        }
        packet["observation_identity"] = self._declaration_packet_identity(packet)
        if previous_observation is not None:
            if not isinstance(previous_observation, Mapping):
                raise ValueError("previous_observation must be an object")
            self._validate_previous_declarations(previous_observation)
            packet["delta_from_previous"] = declaration_delta(
                previous_observation, packet
            )
        return packet
