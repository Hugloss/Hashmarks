"""Pure endpoint deltas over retained direct claims and their qualifications."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .semantic_relationship_model import (
    AUTHORITY,
    DELTA_SCHEMA,
    content_identity,
    validate_relationship_observation,
)


def _observations(packet: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for row in packet["observations"]:
        key = content_identity({"producer": row["producer"], "scope": row["scope"]})
        result.setdefault(key, []).append(row)
    return result


def _reasons(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    reasons = []
    if before["target"] != after["target"]:
        reasons.append("subjects-differ")
    for key in ("scope_identity", "observer_identity"):
        if before["repository"].get(key) != after["repository"].get(key):
            reasons.append(f"repository-{key}-differs")
    if before["bounds"] != after["bounds"]:
        reasons.append("observation-bounds-differ")
    for endpoint, value in (("before", before), ("after", after)):
        if value["coverage"]["omitted_observations"]:
            reasons.append(f"{endpoint}-observations-omitted")
    return reasons


def _producer_reasons(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    reasons = []
    if (
        before["configuration_identity"] is None
        or before["configuration_identity"] != after["configuration_identity"]
    ):
        reasons.append("producer-configuration-unbound-or-different")
    for endpoint, row in (("before", before), ("after", after)):
        if (
            row["collection_state"] != "fresh-complete"
            or row["truncated"]
            or row["accounting"].get("denied_or_unadmitted", 0)
        ):
            reasons.append(f"{endpoint}-claim-collection-incomplete")
        if row["freshness"] != "current":
            reasons.append(f"{endpoint}-producer-freshness-unproven")
        bindings = [
            *row["source_bindings"],
            *(
                claim[end].get("source_binding", {"state": "unknown"})
                for claim in row["claims"]
                for end in ("source", "target")
                if "source_binding" in claim[end]
                or "resolution" not in claim[end]
                or not claim[end]["resolution"].get("candidates")
            ),
        ]
        if not bindings or any(binding["state"] != "matching" for binding in bindings):
            reasons.append(f"{endpoint}-source-correspondence-unproven")
    return reasons


def _axis(before: object, after: object) -> dict[str, Any]:
    return {
        "before": deepcopy(before),
        "after": deepcopy(after),
        "changed": before != after,
    }


def _claim_evidence(claims: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    evidence: dict[str, list[dict[str, Any]]] = {}
    for claim in claims:
        evidence.setdefault(claim["identity"], []).append(claim)
    return evidence


def _producer_delta(
    before: Mapping[str, Any], after: Mapping[str, Any], endpoint_reasons: list[str]
) -> dict[str, Any]:
    reasons = [*endpoint_reasons, *_producer_reasons(before, after)]
    old = {claim["identity"]: claim for claim in before["claims"]}
    new = {claim["identity"]: claim for claim in after["claims"]}
    old_evidence, new_evidence = (
        _claim_evidence(before["claims"]),
        _claim_evidence(after["claims"]),
    )
    added, removed = (
        [new[key] for key in sorted(new.keys() - old.keys())],
        [old[key] for key in sorted(old.keys() - new.keys())],
    )
    locator_changes = [
        {
            "identity": key,
            **_axis(
                {end: old[key][end].get("locator") for end in ("source", "target")},
                {end: new[key][end].get("locator") for end in ("source", "target")},
            ),
        }
        for key in sorted(old.keys() & new.keys())
        if any(
            old[key][end].get("locator") != new[key][end].get("locator")
            for end in ("source", "target")
        )
    ]
    return {
        "producer": before["producer"],
        "scope": before["scope"],
        "comparable": not reasons,
        "incomparability_reasons": sorted(set(reasons)),
        "facts": {
            "added": added if not reasons else [],
            "removed": removed if not reasons else [],
            "unchanged_count": len(old.keys() & new.keys()) if not reasons else None,
            "authority": "qualified-producer-claim-set-comparison-only",
        },
        "observed_claim_set_changes": {
            "added": added,
            "removed": removed,
            "authority": "delivered-subset-comparison-only",
            "repository_absence_inferred": False,
        },
        "locators": locator_changes,
        "claim_evidence_changes": [
            {"identity": key, **_axis(old_evidence[key], new_evidence[key])}
            for key in sorted(old.keys() & new.keys())
            if old_evidence[key] != new_evidence[key]
        ],
        "capture": _axis(before["capture_identity"], after["capture_identity"]),
        "source_bindings": _axis(before["source_bindings"], after["source_bindings"]),
        "capability": _axis(before["capability"], after["capability"]),
        "configuration": _axis(
            before["configuration_identity"], after["configuration_identity"]
        ),
        "collection": _axis(
            {
                key: before[key]
                for key in ("collection_state", "freshness", "truncated", "accounting")
            },
            {
                key: after[key]
                for key in ("collection_state", "freshness", "truncated", "accounting")
            },
        ),
        "resolution_changes": [
            {
                "identity": key,
                **_axis(
                    {
                        end: old[key][end].get("resolution")
                        for end in ("source", "target")
                    },
                    {
                        end: new[key][end].get("resolution")
                        for end in ("source", "target")
                    },
                ),
            }
            for key in sorted(old.keys() & new.keys())
            if any(
                old[key][end].get("resolution") != new[key][end].get("resolution")
                for end in ("source", "target")
            )
        ],
    }


def semantic_relationship_delta(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> dict[str, Any]:
    old, new = (
        validate_relationship_observation(before),
        validate_relationship_observation(after),
    )
    reasons = _reasons(old, new)
    left, right = _observations(old), _observations(new)
    if not left or not right:
        reasons.append("producer-observations-unavailable")
    if left.keys() != right.keys():
        reasons.append("producer-observation-scopes-differ")
    if any(len(rows) != 1 for rows in [*left.values(), *right.values()]):
        reasons.append("ambiguous-producer-observations")
    deltas = []
    for key in sorted(left.keys() & right.keys()):
        if len(left[key]) != 1 or len(right[key]) != 1:
            continue
        deltas.append(_producer_delta(left[key][0], right[key][0], reasons))
    value = {
        "schema": DELTA_SCHEMA,
        "target": old["target"],
        "authority": AUTHORITY,
        "execution_effect": "none",
        "negative_evidence_admissible": False,
        "before": old,
        "after": new,
        "comparable": bool(deltas)
        and not reasons
        and all(row["comparable"] for row in deltas),
        "incomparability_reasons": sorted(
            set(reasons).union(*(row["incomparability_reasons"] for row in deltas))
        ),
        "producer_deltas": deltas,
        "observation_changes": _axis(
            old["evidence_identity"], new["evidence_identity"]
        ),
    }
    return {**value, "evidence_identity": content_identity(value)}


def validate_relationship_delta(payload: Mapping[str, Any]) -> dict[str, Any]:
    if payload.get("schema") != DELTA_SCHEMA:
        raise ValueError("unsupported semantic relationship delta schema")
    expected = semantic_relationship_delta(payload["before"], payload["after"])
    if dict(payload) != expected:
        raise ValueError("relationship delta contradicts retained endpoints")
    return expected
