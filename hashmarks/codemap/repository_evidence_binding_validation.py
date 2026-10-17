"""Pure identity and shape validation of supplied repository-binding packets."""

from __future__ import annotations

from collections.abc import Mapping

from hashmarks.operation_contract import operation_schema

from .repository_observation import packet_digest


def _retained_binding_definition_identity(
    row: Mapping[str, object],
) -> str:
    evidence = row.get("evidence")
    dependencies = row.get("dependencies")
    relationships = row.get("relationships")
    if not isinstance(evidence, list) or not isinstance(dependencies, list):
        raise ValueError("retained binding definition inputs malformed")
    relationship_state = (
        relationships.get("state") if isinstance(relationships, Mapping) else None
    )
    relationship_bounds = (
        relationships.get("bounds") if isinstance(relationships, Mapping) else None
    )
    include_relationships = relationship_state != "not-requested"
    definition_payload = {
        "binding_id": row.get("binding_id"),
        "evidence": [
            {
                key: item.get(key)
                for key in ("scope", "path", "start_line", "end_line")
                if key in item
            }
            for item in evidence
            if isinstance(item, Mapping)
        ],
        "dependencies": [
            str(item.get("path") or "")
            for item in dependencies
            if isinstance(item, Mapping)
        ],
        "include_relationships": include_relationships,
        "relationship_limit_per_path": (
            relationship_bounds.get("limit_per_path")
            if include_relationships and isinstance(relationship_bounds, Mapping)
            else None
        ),
    }
    return "sha256:" + packet_digest(
        "hashmarks.repository-evidence-binding-definition.v1",
        definition_payload,
    )


def _validate_retained_binding_row(
    row: Mapping[str, object],
    *,
    name: str,
) -> None:
    binding_payload = {
        key: row.get(key)
        for key in ("binding_id", "evidence", "dependencies", "relationships")
    }
    expected_observation_identity = "sha256:" + packet_digest(
        "hashmarks.repository-evidence-binding-observation.v1",
        binding_payload,
    )
    if row.get("binding_observation_identity") != expected_observation_identity:
        raise ValueError(f"{name} binding observation identity mismatch")
    expected_definition_identity = _retained_binding_definition_identity(row)
    if row.get("binding_definition_identity") != expected_definition_identity:
        raise ValueError(f"{name} binding definition identity mismatch")


def validate_bindings_packet(
    packet: Mapping[str, object],
    *,
    name: str,
) -> None:
    if packet.get("schema") != operation_schema("repository_evidence", "observation"):
        raise ValueError(f"{name} must be a repository evidence bindings packet")
    identity = packet.get("bindings_identity")
    expected_identity = "sha256:" + packet_digest(
        operation_schema("repository_evidence", "observation"),
        {key: value for key, value in packet.items() if key != "bindings_identity"},
    )
    if not isinstance(identity, str) or identity != expected_identity:
        raise ValueError(f"{name} bindings identity mismatch")
    rows = packet.get("bindings")
    if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
        raise ValueError(f"{name} bindings must be a list of objects")
    binding_ids = [str(row.get("binding_id") or "") for row in rows]
    if any(not binding_id for binding_id in binding_ids):
        raise ValueError(f"{name} binding_id must not be empty")
    if len(set(binding_ids)) != len(binding_ids):
        raise ValueError(f"{name} contains duplicate binding_id")
    expected_contract = {
        "completeness": {
            "state": "complete",
            "scope": "explicit-declared-evidence",
        },
        "storage": "derived-not-persisted",
        "authority": "repository-intelligence-only",
        "execution_effect": "none",
    }
    mismatched = [
        field
        for field, expected in expected_contract.items()
        if packet.get(field) != expected
    ]
    if mismatched:
        raise ValueError(f"{name} {mismatched[0]} contract mismatch")
    for row in rows:
        _validate_retained_binding_row(row, name=name)
