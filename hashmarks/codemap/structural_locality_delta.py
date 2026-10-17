"""Pure comparison of caller-supplied structural-locality observations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hashmarks.operation_contract import operation_response

from .structural_locality_model import (
    LOCALITY_DELTA_SCHEMA,
    LOCALITY_SCHEMA,
    locality_identity,
)


def _packet_identity_valid(packet: Mapping[str, object]) -> bool:
    identity = packet.get("evidence_identity")
    if not isinstance(identity, str) or not identity:
        return False
    semantic = {
        str(key): value for key, value in packet.items() if key != "evidence_identity"
    }
    return identity == locality_identity(semantic)


def _delta_incomparability_reasons(
    before: Mapping[str, object], after: Mapping[str, object]
) -> list[str]:
    checks = (
        ("before-schema", before.get("schema") == LOCALITY_SCHEMA),
        ("after-schema", after.get("schema") == LOCALITY_SCHEMA),
        ("before-provider", before.get("provider") == "hashmarks"),
        ("after-provider", after.get("provider") == "hashmarks"),
        (
            "provider-version",
            before.get("provider_version") == after.get("provider_version"),
        ),
        (
            "provider-implementation",
            before.get("provider_implementation_identity")
            == after.get("provider_implementation_identity"),
        ),
        ("before-evidence-identity", _packet_identity_valid(before)),
        ("after-evidence-identity", _packet_identity_valid(after)),
        ("target", before.get("target") == after.get("target")),
        (
            "measurement-configuration",
            before.get("measurement_configuration_identity")
            == after.get("measurement_configuration_identity"),
        ),
        (
            "repository-state-not-distinct",
            before.get("repository_identity") != after.get("repository_identity"),
        ),
    )
    issues = [label for label, valid in checks if not valid]
    for label, packet in (("before", before), ("after", after)):
        freshness = packet.get("freshness")
        if not isinstance(freshness, Mapping) or freshness.get("state") != "current":
            issues.append(f"{label}-freshness")
        if not isinstance(packet.get("evidence_identity"), str):
            issues.append(f"{label}-identity")
    return issues


def _delta_nodes(packet: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    rows = packet.get("nodes", [])
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        return {}
    return {
        str(row.get("symbol_id")): row
        for row in rows
        if isinstance(row, Mapping) and row.get("symbol_id")
    }


def _integer_dimension_delta(
    before: object, after: object
) -> tuple[dict[str, int], bool]:
    if not isinstance(before, Mapping) or not isinstance(after, Mapping):
        return {}, False
    delta: dict[str, int] = {}
    for key in sorted(set(before) & set(after)):
        left, right = before.get(key), after.get(key)
        if (
            isinstance(left, int)
            and not isinstance(left, bool)
            and isinstance(right, int)
            and not isinstance(right, bool)
        ):
            delta[str(key)] = right - left
    return delta, True


def _native_relation_evidence(
    packet: Mapping[str, object],
) -> tuple[set[str], set[tuple[str, str, str, str, str]], bool]:
    raw = packet.get("native_semantic_relationships")
    if not isinstance(raw, Mapping) or raw.get("truncated") is not False:
        return set(), set(), False
    producers = raw.get("producer_bindings")
    rows = raw.get("relationships")
    if not isinstance(producers, list) or not isinstance(rows, list):
        return set(), set(), False
    keys: set[tuple[str, str, str, str, str]] = set()
    for row in rows:
        if not isinstance(row, Mapping) or any(
            not isinstance(row.get(key), (str, int)) or isinstance(row.get(key), bool)
            for key in ("producer", "source_symbol", "kind", "target_symbol", "line")
        ):
            return set(), set(), False
        keys.add(
            (
                str(row["producer"]),
                str(row["source_symbol"]),
                str(row["kind"]),
                str(row["target_symbol"]),
                str(row["line"]),
            )
        )
    return {str(value) for value in producers}, keys, True


def _string_set(packet: Mapping[str, object], key: str) -> set[str]:
    values = packet.get(key, [])
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        return set()
    return {str(value) for value in values if value}


def _native_relationship_delta(
    before: Mapping[str, object],
    after: Mapping[str, object],
    endpoint_issues: Sequence[str],
) -> dict[str, object]:
    before_producers, before_relations, before_valid = _native_relation_evidence(before)
    after_producers, after_relations, after_valid = _native_relation_evidence(after)
    reasons = []
    if endpoint_issues:
        reasons.append("structural-endpoints-incomparable")
    if not before_valid:
        reasons.append("before-relationship-observation-incomplete")
    if not after_valid:
        reasons.append("after-relationship-observation-incomplete")
    if not before_producers or before_producers != after_producers:
        reasons.append("producer-bindings-differ-or-unobserved")
    comparable = not reasons
    return {
        "native_relationships_comparable": comparable,
        "native_relationships_incomparability_reasons": sorted(set(reasons)),
        "native_relationships_added": sorted(after_relations - before_relations)
        if comparable
        else [],
        "native_relationships_removed": sorted(before_relations - after_relations)
        if comparable
        else [],
    }


@operation_response("structural_locality_delta")
def structural_locality_delta(
    before: Mapping[str, object], after: Mapping[str, object]
) -> dict[str, object]:
    """Compare two structural-locality packets without interpreting the tradeoff."""
    issues = _delta_incomparability_reasons(before, after)
    before_nodes, after_nodes = _delta_nodes(before), _delta_nodes(after)
    dimension_delta, dimensions_valid = _integer_dimension_delta(
        before.get("dimensions"), after.get("dimensions")
    )
    if not dimensions_valid:
        issues.append("dimensions")
    before_verifiers = _string_set(before, "verification_paths")
    after_verifiers = _string_set(after, "verification_paths")
    native_delta = _native_relationship_delta(before, after, issues)
    # No comparable producer at either endpoint means no absence claim.
    semantic = {
        "schema": LOCALITY_DELTA_SCHEMA,
        "target": before.get("target"),
        "before_evidence_identity": before.get("evidence_identity"),
        "after_evidence_identity": after.get("evidence_identity"),
        "before_repository_identity": before.get("repository_identity"),
        "after_repository_identity": after.get("repository_identity"),
        "measurement_configuration_identity": before.get(
            "measurement_configuration_identity"
        ),
        "comparable": not issues,
        "incomparability_reasons": sorted(set(issues)),
        "introduced_symbol_ids": sorted(set(after_nodes) - set(before_nodes)),
        "removed_symbol_ids": sorted(set(before_nodes) - set(after_nodes)),
        "dimension_delta": dimension_delta,
        "verification_paths_added": sorted(after_verifiers - before_verifiers),
        "verification_paths_removed": sorted(before_verifiers - after_verifiers),
        **native_delta,
        "claims": {
            "architectural_improvement": False,
            "refactor_recommendation": False,
            "consumer_policy_applied": False,
        },
    }
    return {**semantic, "evidence_identity": locality_identity(semantic)}
