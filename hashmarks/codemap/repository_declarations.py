from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

from hashmarks.operation_contract import (
    operation_schema,
    require_operation_mode,
    validate_operation_response,
)

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

_SCHEMA = operation_schema("repository_declarations", "observation")


class RepositoryDeclarationsMixin:
    """Project cross-artifact declarations without choosing a winning value."""

    def _semantic_subject_identity(
        self,
        *,
        semantic_namespace: str,
        concept: Mapping[str, object],
        scope: Mapping[str, object],
    ) -> str:
        """Identify the provider-declared semantic subject independently of location."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        return "sha256:" + self._packet_digest(
            "hashmarks.repository-declaration-semantic-subject.v1",
            {
                "semantic_namespace": semantic_namespace,
                "concept": concept,
                "scope": scope,
            },
        )

    def _semantic_declaration_identity(
        self,
        *,
        semantic_subject_identity: str,
        semantic_role: Mapping[str, object],
    ) -> str:
        """Identify one provider-declared semantic role inside a subject."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        return "sha256:" + self._packet_digest(
            "hashmarks.repository-declaration-semantic-role.v1",
            {
                "semantic_subject_identity": semantic_subject_identity,
                "semantic_role": semantic_role,
            },
        )

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

    @staticmethod
    def _declaration_identity_payloads(
        declaration: Mapping[str, object],
        *,
        group_id: str,
        semantic_subject_identity: str,
        binding: Mapping[str, object],
    ) -> tuple[dict[str, object], dict[str, object]]:
        definition = {
            "group_id": group_id,
            "semantic_subject_identity": semantic_subject_identity,
            **(
                {
                    "semantic_declaration_identity": declaration[
                        "semantic_declaration_identity"
                    ]
                }
                if "semantic_declaration_identity" in declaration
                else {}
            ),
            "declaration_id": declaration["declaration_id"],
            "binding_definition_identity": binding["binding_definition_identity"],
        }
        observation = {
            **definition,
            "value_state": declaration["value_state"],
            **({"value": declaration["value"]} if "value" in declaration else {}),
            **(
                {"candidate_values": declaration["candidate_values"]}
                if "candidate_values" in declaration
                else {}
            ),
            "producer": declaration["producer"],
            "evidence_state": declaration["evidence_state"],
            "binding_observation_identity": binding["binding_observation_identity"],
        }
        return definition, observation

    def _project_declaration(
        self,
        normalized: Mapping[str, object],
        group_id: str,
        semantic_subject_identity: str,
        binding_rows: Mapping[str, Mapping[str, object]],
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        binding = binding_rows[str(normalized["binding_id"])]
        semantic_role = normalized.get("semantic_role")
        semantic_declaration_identity = (
            self._semantic_declaration_identity(
                semantic_subject_identity=semantic_subject_identity,
                semantic_role=cast("Mapping[str, object]", semantic_role),
            )
            if isinstance(semantic_role, Mapping)
            else None
        )
        projected = {
            **normalized,
            "semantic_subject_identity": semantic_subject_identity,
            **(
                {"semantic_declaration_identity": semantic_declaration_identity}
                if semantic_declaration_identity is not None
                else {}
            ),
            "evidence_state": self._binding_evidence_state(binding),
        }
        definition, observation = self._declaration_identity_payloads(
            projected,
            group_id=group_id,
            semantic_subject_identity=semantic_subject_identity,
            binding=binding,
        )
        return {
            **projected,
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

    @staticmethod
    def _group_identity_payloads(
        *,
        group_id: str,
        semantic_subject: Mapping[str, object],
        correspondence: Mapping[str, object],
        coverage: Mapping[str, object],
        declarations: Sequence[Mapping[str, object]],
    ) -> tuple[dict[str, object], dict[str, object]]:
        definition_payload = {
            "group_id": group_id,
            "semantic_subject_identity": semantic_subject["semantic_subject_identity"],
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
            **semantic_subject,
            "correspondence": correspondence,
            "coverage": coverage,
            "declarations": list(declarations),
            "comparison": comparison(declarations, correspondence),
            "absence": absence(declarations, coverage),
        }
        return definition_payload, observation_payload

    def _declaration_group(
        self,
        group: Mapping[str, object],
        binding_rows: Mapping[str, Mapping[str, object]],
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        group_id = str(group["group_id"])
        semantic_namespace = str(group["semantic_namespace"])
        concept = cast("Mapping[str, object]", group["concept"])
        scope = cast("Mapping[str, object]", group["scope"])
        correspondence = cast("Mapping[str, object]", group["correspondence"])
        coverage = cast("Mapping[str, object]", group["coverage"])
        semantic_subject_identity = self._semantic_subject_identity(
            semantic_namespace=semantic_namespace,
            concept=concept,
            scope=scope,
        )
        semantic_subject = {
            "semantic_namespace": semantic_namespace,
            "concept": concept,
            "scope": scope,
            "semantic_subject_identity": semantic_subject_identity,
        }
        raw_declarations = cast(
            "Sequence[Mapping[str, object]]",
            group["declarations"],
        )
        declarations = [
            self._project_declaration(
                normalized,
                group_id,
                semantic_subject_identity,
                binding_rows,
            )
            for normalized in raw_declarations
        ]
        declarations.sort(key=lambda row: str(row["declaration_id"]))

        definition_payload, observation_payload = self._group_identity_payloads(
            group_id=group_id,
            semantic_subject=semantic_subject,
            correspondence=correspondence,
            coverage=coverage,
            declarations=declarations,
        )
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

    def _validate_declaration_packet_contract(
        self,
        packet: Mapping[str, object],
        *,
        name: str,
    ) -> None:
        if packet.get("schema") != _SCHEMA:
            raise ValueError(f"{name} must use schema {_SCHEMA}")
        identity = packet.get("observation_identity")
        if not isinstance(
            identity, str
        ) or identity != self._declaration_packet_identity(packet):
            raise ValueError(f"{name} identity mismatch")

        expected_contract = {
            "storage": "derived-not-persisted",
            "authority": "repository-intelligence-only",
            "semantic_value_authority": "provider-claimed",
            "correspondence_authority": "provider-claimed",
            "interpretation_authority": "consumer-owned",
            "winner": "not-selected",
        }
        mismatched = [
            field
            for field, expected in expected_contract.items()
            if packet.get(field) != expected
        ]
        if mismatched:
            raise ValueError(f"{name} {mismatched[0]} contract mismatch")

        expected_bounds = {
            "max_groups": MAX_GROUPS,
            "max_declarations": MAX_DECLARATIONS,
            "max_expected_declarations_per_group": MAX_EXPECTED_PER_GROUP,
            "max_request_bytes": MAX_REQUEST_BYTES,
            "max_packet_bytes": MAX_PACKET_BYTES,
        }
        if packet.get("bounds") != expected_bounds:
            raise ValueError(f"{name} bounds contract mismatch")

    def _declaration_repository_evidence(
        self,
        packet: Mapping[str, object],
        *,
        name: str,
    ) -> Mapping[str, object]:
        repository = packet.get("repository")
        if not isinstance(repository, Mapping):
            raise ValueError(f"{name} repository must be an object")
        repository_identity = str(repository.get("repository_identity") or "")
        if not repository_identity:
            raise ValueError(f"{name} repository identity missing")

        repository_evidence = packet.get("repository_evidence")
        if not isinstance(repository_evidence, Mapping):
            raise ValueError(f"{name} repository_evidence must be an object")
        self._validate_binding_delta_input(
            repository_evidence,
            name=f"{name} repository evidence",
        )

        evidence_repository = repository_evidence.get("repository")
        if not isinstance(evidence_repository, Mapping):
            raise ValueError(f"{name} evidence repository must be an object")
        if str(evidence_repository.get("repository_identity") or "") != (
            repository_identity
        ):
            raise ValueError(f"{name} evidence repository-mismatch")
        if repository != evidence_repository:
            raise ValueError(f"{name} repository projection mismatch")
        if packet.get("observer") != repository_evidence.get("observer"):
            raise ValueError(f"{name} observer projection mismatch")
        return repository_evidence

    @staticmethod
    def _declaration_packet_collections(
        packet: Mapping[str, object],
        repository_evidence: Mapping[str, object],
        *,
        name: str,
    ) -> tuple[dict[str, Mapping[str, object]], list[Mapping[str, object]]]:
        raw_bindings = repository_evidence.get("bindings")
        if not isinstance(raw_bindings, list) or any(
            not isinstance(row, Mapping) for row in raw_bindings
        ):
            raise ValueError(f"{name} repository evidence bindings malformed")
        binding_ids = [str(row["binding_id"]) for row in raw_bindings]
        if binding_ids != sorted(binding_ids):
            raise ValueError(f"{name} repository evidence bindings are not canonical")
        binding_rows = {
            str(row["binding_id"]): cast("Mapping[str, object]", row)
            for row in raw_bindings
        }

        raw_groups = packet.get("groups")
        if not isinstance(raw_groups, list) or any(
            not isinstance(group, Mapping) for group in raw_groups
        ):
            raise ValueError(f"{name} groups must be a list of objects")
        groups = cast("list[Mapping[str, object]]", raw_groups)
        group_ids = [str(group.get("group_id") or "") for group in groups]
        if group_ids != sorted(group_ids):
            raise ValueError(f"{name} groups are not canonical")
        if len(set(group_ids)) != len(group_ids):
            raise ValueError(f"{name} contains duplicate group_id")
        return binding_rows, groups

    def _validate_semantic_declaration_identity(
        self,
        declaration: Mapping[str, object],
        *,
        semantic_subject_identity: str,
        name: str,
    ) -> None:
        role = declaration.get("semantic_role")
        identity = declaration.get("semantic_declaration_identity")
        if role is None:
            if "semantic_declaration_identity" in declaration:
                raise ValueError(
                    f"{name} semantic declaration identity without semantic_role"
                )
            return
        if not isinstance(role, Mapping) or not role:
            raise ValueError(f"{name} semantic_role must be a non-empty object")
        expected = self._semantic_declaration_identity(
            semantic_subject_identity=semantic_subject_identity,
            semantic_role=role,
        )
        if identity != expected:
            raise ValueError(f"{name} semantic declaration identity mismatch")

    def _validate_projected_declaration(
        self,
        declaration: Mapping[str, object],
        *,
        group_id: str,
        semantic_subject_identity: str,
        binding_rows: Mapping[str, Mapping[str, object]],
        name: str,
    ) -> str:
        declaration_id = str(declaration.get("declaration_id") or "")
        if not declaration_id:
            raise ValueError(f"{name} declaration_id must not be empty")
        binding_id = str(declaration.get("binding_id") or "")
        binding = binding_rows.get(binding_id)
        if binding is None:
            raise ValueError(f"{name} declaration binding missing: {binding_id}")
        if declaration.get("evidence_state") != self._binding_evidence_state(binding):
            raise ValueError(f"{name} declaration evidence state mismatch")
        self._validate_semantic_declaration_identity(
            declaration,
            semantic_subject_identity=semantic_subject_identity,
            name=name,
        )

        definition, observation = self._declaration_identity_payloads(
            declaration,
            group_id=group_id,
            semantic_subject_identity=semantic_subject_identity,
            binding=binding,
        )
        expected_definition = "sha256:" + self._packet_digest(
            "hashmarks.repository-declaration-definition.v1",
            definition,
        )
        expected_observation = "sha256:" + self._packet_digest(
            "hashmarks.repository-declaration-observation.v1",
            observation,
        )
        if declaration.get("declaration_definition_identity") != expected_definition:
            raise ValueError(f"{name} declaration definition identity mismatch")
        if declaration.get("declaration_observation_identity") != expected_observation:
            raise ValueError(f"{name} declaration observation identity mismatch")
        return binding_id

    @staticmethod
    def _projected_group_contract(
        raw_group: Mapping[str, object],
        *,
        name: str,
    ) -> tuple[
        str,
        str,
        Mapping[str, object],
        Mapping[str, object],
        Mapping[str, object],
        Mapping[str, object],
        list[Mapping[str, object]],
    ]:
        group_id = str(raw_group.get("group_id") or "")
        if not group_id:
            raise ValueError(f"{name} group_id must not be empty")
        semantic_namespace = str(raw_group.get("semantic_namespace") or "")
        if not semantic_namespace:
            raise ValueError(f"{name} semantic_namespace must not be empty")

        concept = raw_group.get("concept")
        scope = raw_group.get("scope")
        correspondence = raw_group.get("correspondence")
        coverage = raw_group.get("coverage")
        if not all(
            isinstance(value, Mapping)
            for value in (concept, scope, correspondence, coverage)
        ):
            raise ValueError(f"{name} group contract malformed")

        declarations = raw_group.get("declarations")
        if not isinstance(declarations, list) or any(
            not isinstance(row, Mapping) for row in declarations
        ):
            raise ValueError(f"{name} declarations must be a list of objects")
        projected_rows = cast("list[Mapping[str, object]]", declarations)
        declaration_ids = [
            str(row.get("declaration_id") or "") for row in projected_rows
        ]
        if declaration_ids != sorted(declaration_ids):
            raise ValueError(f"{name} declarations are not canonical")
        if len(set(declaration_ids)) != len(declaration_ids):
            raise ValueError(f"{name} contains duplicate declaration_id")

        return (
            group_id,
            semantic_namespace,
            cast("Mapping[str, object]", concept),
            cast("Mapping[str, object]", scope),
            cast("Mapping[str, object]", correspondence),
            cast("Mapping[str, object]", coverage),
            projected_rows,
        )

    def _validate_projected_group_result(
        self,
        raw_group: Mapping[str, object],
        contract: tuple[
            str,
            str,
            Mapping[str, object],
            Mapping[str, object],
            Mapping[str, object],
            Mapping[str, object],
            list[Mapping[str, object]],
        ],
        *,
        name: str,
    ) -> None:
        (
            group_id,
            semantic_namespace,
            concept,
            scope,
            correspondence,
            coverage,
            declarations,
        ) = contract
        semantic_subject = {
            "semantic_namespace": semantic_namespace,
            "concept": concept,
            "scope": scope,
            "semantic_subject_identity": raw_group.get("semantic_subject_identity"),
        }
        definition_payload, observation_payload = self._group_identity_payloads(
            group_id=group_id,
            semantic_subject=semantic_subject,
            correspondence=correspondence,
            coverage=coverage,
            declarations=declarations,
        )
        if raw_group.get("comparison") != observation_payload["comparison"]:
            raise ValueError(f"{name} declaration comparison mismatch")
        if raw_group.get("absence") != observation_payload["absence"]:
            raise ValueError(f"{name} declaration absence mismatch")

        expected_definition = "sha256:" + self._packet_digest(
            "hashmarks.repository-declaration-group-definition.v1",
            definition_payload,
        )
        expected_observation = "sha256:" + self._packet_digest(
            "hashmarks.repository-declaration-group-observation.v1",
            observation_payload,
        )
        if raw_group.get("group_definition_identity") != expected_definition:
            raise ValueError(f"{name} group definition identity mismatch")
        if raw_group.get("group_observation_identity") != expected_observation:
            raise ValueError(f"{name} group observation identity mismatch")

    def _validate_projected_group(
        self,
        raw_group: Mapping[str, object],
        *,
        binding_rows: Mapping[str, Mapping[str, object]],
        name: str,
    ) -> set[str]:
        (
            group_id,
            semantic_namespace,
            concept,
            scope,
            correspondence,
            coverage,
            projected_rows,
        ) = self._projected_group_contract(raw_group, name=name)

        semantic_subject_identity = self._semantic_subject_identity(
            semantic_namespace=semantic_namespace,
            concept=concept,
            scope=scope,
        )
        if raw_group.get("semantic_subject_identity") != semantic_subject_identity:
            raise ValueError(f"{name} semantic subject identity mismatch")
        for declaration in projected_rows:
            if (
                declaration.get("semantic_subject_identity")
                != semantic_subject_identity
            ):
                raise ValueError(
                    f"{name} declaration semantic subject identity mismatch"
                )

        referenced = {
            self._validate_projected_declaration(
                declaration,
                group_id=group_id,
                semantic_subject_identity=semantic_subject_identity,
                binding_rows=binding_rows,
                name=name,
            )
            for declaration in projected_rows
        }
        self._validate_projected_group_result(
            raw_group,
            (
                group_id,
                semantic_namespace,
                concept,
                scope,
                correspondence,
                coverage,
                projected_rows,
            ),
            name=name,
        )
        return referenced

    def _validate_declaration_observation(
        self,
        packet: Mapping[str, object],
        *,
        name: str,
    ) -> None:
        self._validate_declaration_packet_contract(packet, name=name)
        repository_evidence = self._declaration_repository_evidence(
            packet,
            name=name,
        )
        binding_rows, groups = self._declaration_packet_collections(
            packet,
            repository_evidence,
            name=name,
        )
        referenced_binding_ids: set[str] = set()
        for group in groups:
            referenced_binding_ids.update(
                self._validate_projected_group(
                    group,
                    binding_rows=binding_rows,
                    name=name,
                )
            )
        if referenced_binding_ids != set(binding_rows):
            raise ValueError(f"{name} repository evidence binding set mismatch")

    def _validate_previous_declarations(self, previous: Mapping[str, object]) -> None:
        self._validate_declaration_observation(
            previous,
            name="previous declaration observation",
        )
        repository = cast("Mapping[str, object]", previous["repository"])
        if repository.get("repository_identity") != self._repository_packet_identity():
            raise ValueError("previous declaration observation repository-mismatch")

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

    def repository_declarations_operation(
        self,
        groups: Sequence[Mapping[str, object]],
        *,
        previous_observation: Mapping[str, object] | None = None,
        result_mode: str = "observation",
    ) -> dict[str, object]:
        """Execute one canonical declaration operation independent of transport."""
        mode = require_operation_mode("repository_declarations", result_mode)
        if mode == "explain" and previous_observation is not None:
            raise ValueError("previous_observation requires result_mode=observation")
        packet = self.repository_declarations(
            groups,
            previous_observation=previous_observation,
        )
        result = (
            self.repository_declaration_explain(packet)
            if mode == "explain"
            else packet
        )
        return validate_operation_response(
            "repository_declarations",
            result,
            mode=mode,
        )
