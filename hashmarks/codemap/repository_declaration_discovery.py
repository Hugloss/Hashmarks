from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import islice
from typing import TYPE_CHECKING, cast

from .decision_session import decision_scoped
from .repository_declaration_contract import encoded_json_bytes
from .repository_declaration_provider import (
    MAX_DECLARATION_PROVIDERS,
    MAX_DISCOVERY_PACKET_BYTES,
    MAX_PROVIDER_ENUMERATED_PATHS,
    MAX_PROVIDER_ENUMERATIONS,
    MAX_PROVIDER_INPUTS,
    RepositoryDeclarationProvider,
    collect_repository_declaration_providers,
    validate_repository_declaration_provider_inputs,
)

if TYPE_CHECKING:
    from .engine import CodeMap

_SCHEMA = "hashmarks.repository-declaration-discovery.v1"
_DELTA_SCHEMA = "hashmarks.repository-declaration-discovery-delta.v1"


def _provider_rows(value: object) -> dict[str, Mapping[str, object]]:
    if not isinstance(value, list):
        raise ValueError("declaration discovery providers must be a list")
    rows: dict[str, Mapping[str, object]] = {}
    for row in value:
        if not isinstance(row, Mapping):
            raise ValueError("declaration discovery provider rows must be objects")
        name = row.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("declaration discovery provider name is malformed")
        if name in rows:
            raise ValueError("declaration discovery provider names are duplicated")
        rows[name] = row
    return rows


def _provider_delta(
    previous: Mapping[str, object],
    current: Mapping[str, object],
) -> dict[str, object]:
    before = _provider_rows(previous.get("providers"))
    after = _provider_rows(current.get("providers"))
    return {
        "added": sorted(set(after) - set(before)),
        "removed": sorted(set(before) - set(after)),
        "changed": sorted(
            name for name in set(before) & set(after) if before[name] != after[name]
        ),
    }


def _qualified_declaration_indexes(
    declarations: Mapping[str, object],
) -> tuple[
    dict[str, Mapping[str, object]],
    dict[str, Mapping[str, object]],
]:
    groups_raw = declarations.get("groups")
    evidence_packet = declarations.get("repository_evidence")
    if not isinstance(groups_raw, list) or not isinstance(evidence_packet, Mapping):
        raise ValueError("declaration discovery nested evidence is malformed")
    bindings_raw = evidence_packet.get("bindings")
    if not isinstance(bindings_raw, list):
        raise ValueError("declaration discovery nested bindings are malformed")
    groups = {
        str(row.get("group_id") or ""): row
        for row in groups_raw
        if isinstance(row, Mapping)
    }
    bindings = {
        str(row.get("binding_id") or ""): row
        for row in bindings_raw
        if isinstance(row, Mapping)
    }
    return groups, bindings


def _provider_group_ids_and_inputs(
    provider: Mapping[str, object],
) -> tuple[list[str], dict[str, Mapping[str, object]]]:
    inputs_raw = provider.get("inputs")
    group_ids = provider.get("group_ids")
    if not isinstance(inputs_raw, list) or not isinstance(group_ids, list):
        raise ValueError("declaration discovery provider evidence is malformed")
    inputs = {
        str(row.get("path") or ""): row
        for row in inputs_raw
        if isinstance(row, Mapping)
    }
    return [str(group_id) for group_id in group_ids], inputs


def _declaration_evidence_rows(
    declaration: Mapping[str, object],
    bindings: Mapping[str, Mapping[str, object]],
) -> list[Mapping[str, object]]:
    binding = bindings.get(str(declaration.get("binding_id") or ""))
    if not isinstance(binding, Mapping):
        raise ValueError("declaration discovery binding missing")
    evidence = binding.get("evidence")
    if not isinstance(evidence, list) or any(
        not isinstance(row, Mapping) for row in evidence
    ):
        raise ValueError("declaration discovery binding evidence malformed")
    return [row for row in evidence if isinstance(row, Mapping)]


def _validate_evidence_revisions(
    evidence: Sequence[Mapping[str, object]],
    inputs: Mapping[str, Mapping[str, object]],
) -> None:
    for row in evidence:
        path = str(row.get("path") or "")
        provider_input = inputs.get(path)
        if not isinstance(provider_input, Mapping):
            raise ValueError(f"declaration discovery provider input missing for {path}")
        if provider_input.get("state") != "known-present" or row.get(
            "member_revision"
        ) != provider_input.get("member_revision"):
            raise ValueError(f"declaration provider evidence revision changed: {path}")


def _validate_group_evidence_revisions(
    group: Mapping[str, object],
    bindings: Mapping[str, Mapping[str, object]],
    inputs: Mapping[str, Mapping[str, object]],
) -> None:
    declarations = group.get("declarations")
    if not isinstance(declarations, list) or any(
        not isinstance(row, Mapping) for row in declarations
    ):
        raise ValueError("declaration discovery group declarations malformed")
    for declaration in declarations:
        assert isinstance(declaration, Mapping)
        evidence = _declaration_evidence_rows(declaration, bindings)
        _validate_evidence_revisions(evidence, inputs)


def _validate_provider_evidence_revisions(
    provider_observations: Sequence[Mapping[str, object]],
    declarations: Mapping[str, object],
) -> None:
    groups, bindings = _qualified_declaration_indexes(declarations)
    for provider in provider_observations:
        if provider.get("state") != "collected":
            continue
        group_ids, inputs = _provider_group_ids_and_inputs(provider)
        for group_id in group_ids:
            group = groups.get(group_id)
            if not isinstance(group, Mapping):
                raise ValueError(
                    "declaration discovery group missing after qualification: "
                    f"{group_id}"
                )
            _validate_group_evidence_revisions(group, bindings, inputs)


def _previous_declarations(
    previous: Mapping[str, object],
) -> Mapping[str, object]:
    if (
        encoded_json_bytes(
            previous,
            name="previous declaration discovery",
        )
        > MAX_DISCOVERY_PACKET_BYTES
    ):
        raise ValueError(
            "previous declaration discovery exceeds "
            f"{MAX_DISCOVERY_PACKET_BYTES} encoded bytes"
        )
    candidate = previous.get("declarations")
    if not isinstance(candidate, Mapping):
        raise ValueError(
            "previous declaration discovery declarations must be an object"
        )
    return candidate


class RepositoryDeclarationDiscoveryMixin:
    """Run explicit declaration providers and qualify their claims."""

    def _declaration_provider_member_read(
        self,
        path: str,
        include_bytes: bool,
    ) -> tuple[dict[str, object], bytes | None]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        return self._repository_member_observation(
            path,
            include_bytes=include_bytes,
        )

    def _declaration_provider_paths(self, prefix: str) -> tuple[str, ...]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        visible = (
            item.rel
            for item in self._iter_admitted_repository_files(prefix)
            if item.visibility.value != "deny"
        )
        return tuple(islice(visible, MAX_PROVIDER_ENUMERATED_PATHS + 1))

    def _declaration_discovery_identity(
        self,
        packet: Mapping[str, object],
    ) -> str:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        declarations = packet.get("declarations")
        if not isinstance(declarations, Mapping):
            raise ValueError("declaration discovery declarations must be an object")
        declaration_identity = declarations.get("observation_identity")
        if not isinstance(declaration_identity, str):
            raise ValueError(
                "declaration discovery nested observation identity is malformed"
            )
        payload = {
            "schema": packet.get("schema"),
            "repository": packet.get("repository"),
            "providers": packet.get("providers"),
            "declaration_observation_identity": declaration_identity,
            "bounds": packet.get("bounds"),
            "storage": packet.get("storage"),
            "authority": packet.get("authority"),
            "execution_effect": packet.get("execution_effect"),
        }
        return "sha256:" + self._packet_digest(_SCHEMA, payload)

    def _validate_previous_declaration_discovery(
        self,
        previous: Mapping[str, object],
    ) -> None:
        if previous.get("schema") != _SCHEMA:
            raise ValueError(f"previous discovery must use schema {_SCHEMA}")
        identity = previous.get("observation_identity")
        if not isinstance(identity, str) or identity != (
            self._declaration_discovery_identity(previous)
        ):
            raise ValueError("previous declaration discovery identity mismatch")
        _provider_rows(previous.get("providers"))

    def _previous_declaration_packet(
        self,
        previous_observation: Mapping[str, object] | None,
    ) -> Mapping[str, object] | None:
        if previous_observation is None:
            return None
        if not isinstance(previous_observation, Mapping):
            raise ValueError("previous_observation must be an object")
        self._validate_previous_declaration_discovery(previous_observation)
        return _previous_declarations(previous_observation)

    def _declaration_discovery_packet(
        self,
        providers: list[dict[str, object]],
        declarations: Mapping[str, object],
    ) -> dict[str, object]:
        packet: dict[str, object] = {
            "schema": _SCHEMA,
            "repository": declarations["repository"],
            "providers": providers,
            "declarations": declarations,
            "bounds": {
                "max_providers": MAX_DECLARATION_PROVIDERS,
                "max_inputs_per_provider": MAX_PROVIDER_INPUTS,
                "max_path_enumerations_per_provider": MAX_PROVIDER_ENUMERATIONS,
                "max_enumerated_paths_per_provider": MAX_PROVIDER_ENUMERATED_PATHS,
                "max_packet_bytes": MAX_DISCOVERY_PACKET_BYTES,
            },
            "storage": "derived-not-persisted",
            "authority": "repository-intelligence-only",
            "execution_effect": {
                "hashmarks": "none",
                "provider_contract": "read-only",
                "provider_sandboxed": False,
            },
        }
        packet["observation_identity"] = self._declaration_discovery_identity(packet)
        return packet

    @decision_scoped
    def discover_repository_declarations(
        self,
        providers: Sequence[RepositoryDeclarationProvider],
        *,
        previous_observation: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        """Run caller-selected declaration providers and qualify their output."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)

        previous_declarations = self._previous_declaration_packet(previous_observation)
        groups, provider_observations = collect_repository_declaration_providers(
            self._declaration_provider_member_read,
            self._declaration_provider_paths,
            providers,
        )
        validate_repository_declaration_provider_inputs(
            self._declaration_provider_member_read,
            self._declaration_provider_paths,
            provider_observations,
        )
        declarations = self.repository_declarations(
            groups,
            previous_observation=previous_declarations,
        )
        validate_repository_declaration_provider_inputs(
            self._declaration_provider_member_read,
            self._declaration_provider_paths,
            provider_observations,
        )
        _validate_provider_evidence_revisions(
            provider_observations,
            declarations,
        )

        packet = self._declaration_discovery_packet(
            provider_observations,
            declarations,
        )
        if previous_observation is not None:
            packet["delta_from_previous"] = {
                "schema": _DELTA_SCHEMA,
                "providers": _provider_delta(previous_observation, packet),
                "declarations": declarations.get("delta_from_previous"),
                "interpretation": "factual-only",
            }
        if (
            encoded_json_bytes(packet, name="declaration discovery packet")
            > MAX_DISCOVERY_PACKET_BYTES
        ):
            raise ValueError(
                "declaration discovery packet exceeds "
                f"{MAX_DISCOVERY_PACKET_BYTES} encoded bytes"
            )
        return packet
