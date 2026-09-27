from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from .engine import CodeMap

_DERIVATION_SCHEMA = "hashmarks.repository-declaration-derivation.v1"
_EXPLAIN_SCHEMA = "hashmarks.repository-declaration-explain.v1"


class RepositoryDeclarationDerivationMixin:
    """Explain declaration authority without reinterpreting provider semantics."""

    def repository_declaration_derivation_authority(
        self,
        observation: Mapping[str, object],
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._validate_declaration_observation(
            observation,
            name="declaration observation",
        )

        repository_evidence = cast(
            "Mapping[str, object]",
            observation["repository_evidence"],
        )
        raw_bindings = cast("list[Mapping[str, object]]", repository_evidence["bindings"])
        binding_rows = {str(row["binding_id"]): row for row in raw_bindings}

        group_authorities: list[dict[str, object]] = []
        for group in cast("list[Mapping[str, object]]", observation["groups"]):
            declaration_authorities: list[dict[str, object]] = []
            for declaration in cast(
                "list[Mapping[str, object]]",
                group["declarations"],
            ):
                binding_id = str(declaration["binding_id"])
                binding = binding_rows[binding_id]
                declaration_authorities.append(
                    {
                        "declaration_id": declaration["declaration_id"],
                        "declaration_definition_identity": declaration[
                            "declaration_definition_identity"
                        ],
                        "declaration_observation_identity": declaration[
                            "declaration_observation_identity"
                        ],
                        "binding_id": binding_id,
                        "binding_definition_identity": binding[
                            "binding_definition_identity"
                        ],
                        "binding_observation_identity": binding[
                            "binding_observation_identity"
                        ],
                        "producer": deepcopy(declaration["producer"]),
                        "evidence_state": declaration["evidence_state"],
                        "repository_evidence": deepcopy(binding["evidence"]),
                    }
                )
            group_authorities.append(
                {
                    "group_id": group["group_id"],
                    "group_definition_identity": group["group_definition_identity"],
                    "group_observation_identity": group["group_observation_identity"],
                    "correspondence": deepcopy(group["correspondence"]),
                    "coverage": deepcopy(group["coverage"]),
                    "declarations": declaration_authorities,
                }
            )

        identity_payload = {
            "observation_identity": observation["observation_identity"],
            "repository_evidence_identity": repository_evidence["bindings_identity"],
            "groups": group_authorities,
        }
        return {
            "schema": _DERIVATION_SCHEMA,
            "authority": observation["authority"],
            "semantic_value_authority": observation["semantic_value_authority"],
            "correspondence_authority": observation["correspondence_authority"],
            "interpretation_authority": observation["interpretation_authority"],
            "observation_identity": observation["observation_identity"],
            "derivation_identity": "sha256:"
            + self._packet_digest(_DERIVATION_SCHEMA, identity_payload),
            "repository": deepcopy(observation["repository"]),
            "observer": deepcopy(observation["observer"]),
            "repository_evidence_identity": repository_evidence["bindings_identity"],
            "groups": group_authorities,
        }

    def repository_declaration_explain(
        self,
        observation: Mapping[str, object],
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        derivation = self.repository_declaration_derivation_authority(observation)
        groups = cast("list[Mapping[str, object]]", observation["groups"])
        declaration_count = sum(
            len(cast("list[object]", group["declarations"])) for group in groups
        )
        semantic_groups = [
            {
                "group_id": group["group_id"],
                "group_definition_identity": group["group_definition_identity"],
                "group_observation_identity": group["group_observation_identity"],
                "comparison": deepcopy(group["comparison"]),
                "absence": deepcopy(group["absence"]),
                "declaration_count": len(
                    cast("list[object]", group["declarations"])
                ),
            }
            for group in groups
        ]
        return {
            "schema": _EXPLAIN_SCHEMA,
            "authority": observation["authority"],
            "semantic_value_authority": observation["semantic_value_authority"],
            "correspondence_authority": observation["correspondence_authority"],
            "interpretation_authority": observation["interpretation_authority"],
            "semantic_result": {
                "observation_identity": observation["observation_identity"],
                "group_count": len(groups),
                "declaration_count": declaration_count,
                "groups": semantic_groups,
            },
            "derivation": derivation,
        }
