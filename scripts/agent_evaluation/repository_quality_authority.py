from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

METAMORPHIC_FAMILIES = {
    "retrieval-limit",
    "pagination",
    "candidate-order",
    "cache-rebuild",
    "irrelevant-file-addition",
    "equivalent-wording",
    "batching",
    "compact-full",
    "cli-mcp",
    "generation-mutation",
}
PRESENTATION_ONLY_FAMILIES = {
    "retrieval-limit",
    "pagination",
    "candidate-order",
    "batching",
    "compact-full",
    "cli-mcp",
}
PROOF_PROFILE_MINIMUMS = {
    "navigation.v1": {"unit": 1},
    "change-support.v1": {"unit": 1, "boundary": 1, "adversarial": 1},
    "release-critical.v1": {
        "unit": 1,
        "boundary": 1,
        "lifecycle": 1,
        "adversarial": 1,
        "mutation": 1,
    },
}


def derived_authority_vetoes(observed: Mapping[str, Any]) -> dict[str, bool]:
    authority = observed.get("authority_observation")
    if not isinstance(authority, Mapping):
        return {}
    resolved = bool(authority.get("owner_resolved"))
    proof_complete = bool(authority.get("proof_complete"))
    candidate = str(authority.get("candidate_owner") or "")
    resolved_owner = str(authority.get("resolved_owner") or "")
    external_only = bool(authority.get("external_evidence_only"))
    stale = bool(authority.get("stale_or_unknown"))
    mixed_generation = bool(authority.get("mixed_generation"))
    return {
        "false_authority": resolved and (not proof_complete or not resolved_owner),
        "external_evidence_authority_leak": external_only and resolved,
        "stale_or_unknown_promoted_to_current": stale and resolved,
        "mixed_generation_authority": mixed_generation and resolved,
        "candidate_promoted_during_projection": (
            bool(candidate) and resolved and candidate != resolved_owner
        ),
    }


def derived_finding_vetoes(observed: Mapping[str, Any]) -> dict[str, bool]:
    finding = observed.get("finding_observation")
    if not isinstance(finding, Mapping):
        return {}
    actionable = bool(finding.get("actionable"))
    admissible = bool(finding.get("admissible_evidence"))
    contradicted = bool(finding.get("contradicted"))
    return {
        "unjustified_actionable_finding": actionable and (not admissible or contradicted),
    }


def metamorphic_observation(observed: Mapping[str, Any]) -> dict[str, Any]:
    value = observed.get("metamorphic_observation")
    if not isinstance(value, Mapping):
        return {}
    family = str(value.get("family") or "")
    if family not in METAMORPHIC_FAMILIES:
        raise ValueError(f"metamorphic family must be one of {sorted(METAMORPHIC_FAMILIES)}")
    baseline = str(value.get("baseline_authority_proof_identity") or "")
    candidate = str(value.get("candidate_authority_proof_identity") or "")
    if not baseline or not candidate:
        raise ValueError("metamorphic observations require baseline and candidate proof identity")
    expected = str(value.get("expected_relation") or "invariant")
    if expected not in {"invariant", "change"}:
        raise ValueError("metamorphic expected_relation must be invariant or change")
    changed = baseline != candidate
    violation = (expected == "invariant" and changed) or (
        expected == "change" and not changed
    )
    return {
        "family": family,
        "expected_relation": expected,
        "proof_changed": changed,
        "violation": violation,
        "presentation_only": family in PRESENTATION_ONLY_FAMILIES,
    }


def proof_profile_health(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for profile, minimums in sorted(PROOF_PROFILE_MINIMUMS.items()):
        profile_rows = [row for row in rows if row["evaluation_profile"] == profile]
        counts = {
            mode: sum(row["proof_mode"] == mode for row in profile_rows)
            for mode in minimums
        }
        missing = {
            mode: minimum - counts[mode]
            for mode, minimum in minimums.items()
            if counts[mode] < minimum
        }
        result[profile] = {
            "cases": len(profile_rows),
            "minimums": dict(minimums),
            "counts": counts,
            "missing": missing,
            "adequate": bool(profile_rows) and not missing,
        }
    return result


def authority_transition(observed: Mapping[str, Any]) -> dict[str, Any] | None:
    value = observed.get("authority_transition")
    if not isinstance(value, Mapping):
        return None
    before = str(value.get("before") or "")
    after = str(value.get("after") or "")
    evidence = str(value.get("admissible_evidence") or "")
    if not before or not after:
        raise ValueError("authority transition requires before and after proof identities")
    changed = before != after
    if changed and not evidence:
        raise ValueError("changed authority transition requires named admissible evidence")
    return {
        "changed": changed,
        "admissible_evidence": evidence or None,
    }
