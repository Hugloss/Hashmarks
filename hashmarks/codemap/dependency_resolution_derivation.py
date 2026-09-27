from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import cast

from . import dependency_resolution_contract as _contract
from .dependency_resolution_evidence import (
    _MAX_INVENTORY,
    _canonical,
    _identifier,
    _identity,
    _objects,
)


class DependencyResolutionDerivationMixin:
    """Project derivation authority from an already-qualified dependency packet.

    This mixin owns projection shape only. Qualification, normalization, identity,
    repository binding, and source authority remain owned by dependency evidence.
    """

    def dependency_resolution_derivation_authority(
        self,
        observation: Mapping[str, object],
    ) -> dict[str, object]:
        self._require_qualified_dependency_observation_v3(observation)

        producer = cast("Mapping[str, object]", observation["producer"])
        adapter_semantics = _identifier(
            producer.get("adapter_semantics"),
            label="adapter semantics",
        )
        evidence_sources = cast(
            "list[dict[str, object]]",
            json.loads(_canonical(observation["evidence_sources"])),
        )
        repository_inputs = cast(
            "list[dict[str, object]]",
            json.loads(_canonical(observation["repository_inputs"])),
        )
        repository_binding = cast(
            "dict[str, object]",
            json.loads(_canonical(observation["repository_binding"])),
        )

        contributing_source_ids: set[str] = set()
        for field in (
            "root_evidence",
            "selections",
            "inventory",
            "relationships",
            "module_ownership",
            "coverage",
        ):
            for row in _objects(
                observation[field],
                label=field,
                limit=_MAX_INVENTORY,
            ):
                refs = row.get("evidence_sources", ())
                if isinstance(refs, Sequence) and not isinstance(
                    refs, (str, bytes, bytearray)
                ):
                    contributing_source_ids.update(str(ref) for ref in refs)

        contributing_sources = [
            row
            for row in evidence_sources
            if str(row["source_id"]) in contributing_source_ids
        ]
        semantic_authorities = sorted(
            {
                str(authority)
                for row in contributing_sources
                for authority in cast("Sequence[object]", row["authorities"])
            }
        )
        qualification_semantics = _contract.QUALIFICATION_SEMANTICS_V3
        identity_payload = {
            "observation_identity": observation["observation_identity"],
            "adapter_semantics": adapter_semantics,
            "qualification_semantics": qualification_semantics,
            "repository_binding": repository_binding,
            "repository_inputs": repository_inputs,
            "contributing_source_ids": sorted(contributing_source_ids),
        }
        return {
            "schema": _contract.DERIVATION_SCHEMA_V1,
            "authority": observation["authority"],
            "producer_authority": observation["producer_authority"],
            "definition_identity": observation["definition_identity"],
            "resolution_identity": observation["resolution_identity"],
            "observation_identity": observation["observation_identity"],
            "derivation_identity": _identity(
                _contract.DERIVATION_SCHEMA_V1,
                identity_payload,
            ),
            "repository_binding": repository_binding,
            "repository_inputs": repository_inputs,
            "producer": dict(producer),
            "adapter_semantics": adapter_semantics,
            "qualification_semantics": qualification_semantics,
            "semantic_authorities": semantic_authorities,
            "contributing_source_ids": sorted(contributing_source_ids),
            "evidence_sources": evidence_sources,
        }
