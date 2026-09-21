from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

SCHEMA = "hashmarks.repository-quality-case.v1"
REPORT_SCHEMA = "hashmarks.repository-quality-report.v1"
METRIC_POLICY = "hashmarks.lexicographic-quality.v1"

SEMANTIC_TRUTH = {
    "unique-owner",
    "true-ambiguity",
    "insufficient-owner-evidence",
    "non-edit",
    "explicit-test-edit",
    "multi-edit",
}
EVIDENCE_TRUTH = {"sufficient", "insufficient", "contradictory"}
REPORTED_STATE = {
    "resolved",
    "ambiguous",
    "unresolved",
    "no-edit-authority",
    "explicit-test-target",
}

HARD_ZERO_METRICS = (
    "false_owner",
    "false_unique",
    "sufficient_unique_reported_ambiguous",
    "sufficient_unique_reported_unresolved",
    "true_ambiguity_collapsed",
    "non_edit_promoted_to_edit",
    "explicit_test_laundered_to_implementation_owner",
    "denied_evidence_authority_leak",
    "external_evidence_authority_leak",
    "stale_or_unknown_promoted_to_current",
    "mixed_generation_authority",
    "owner_projection_drift",
    "ambiguity_projection_drift",
    "freshness_projection_drift",
    "candidate_promoted_during_projection",
    "false_verification_authority",
    "fabricated_verification_command_authority",
)


@dataclass(frozen=True)
class QualityTruth:
    semantic_truth: str
    admitted_evidence_truth: str
    expected_owner: str | None = None


def _choice(value: object, allowed: set[str], field: str) -> str:
    text = str(value or "")
    if text not in allowed:
        raise ValueError(f"{field} must be one of {sorted(allowed)}")
    return text


def validate_case(case: Mapping[str, Any]) -> QualityTruth:
    if case.get("schema") != SCHEMA:
        raise ValueError("unsupported repository quality case schema")
    for field in ("case_id", "repository_identity", "source_identity", "ground_truth_basis"):
        if not isinstance(case.get(field), str) or not str(case[field]).strip():
            raise ValueError(f"{field} must be a non-empty string")
    semantic = _choice(case.get("semantic_truth"), SEMANTIC_TRUTH, "semantic_truth")
    evidence = _choice(
        case.get("admitted_evidence_truth"), EVIDENCE_TRUTH, "admitted_evidence_truth"
    )
    owner = case.get("expected_owner")
    if semantic == "unique-owner" and (not isinstance(owner, str) or not owner):
        raise ValueError("unique-owner cases require expected_owner")
    if semantic != "unique-owner" and owner is not None:
        raise ValueError("expected_owner is only valid for unique-owner cases")
    return QualityTruth(semantic, evidence, owner if isinstance(owner, str) else None)


def _hard_zero_counts() -> Counter[str]:
    return Counter({name: 0 for name in HARD_ZERO_METRICS})


def evaluate_case(case: Mapping[str, Any], observed: Mapping[str, Any]) -> dict[str, Any]:
    truth = validate_case(case)
    state = _choice(observed.get("state"), REPORTED_STATE, "observed state")
    owner = observed.get("owner")
    counts = _hard_zero_counts()

    if state == "resolved":
        if truth.semantic_truth == "unique-owner":
            if truth.admitted_evidence_truth != "sufficient":
                counts["false_unique"] += 1
            elif owner != truth.expected_owner:
                counts["false_owner"] += 1
        elif truth.semantic_truth in {"true-ambiguity", "multi-edit"}:
            counts["true_ambiguity_collapsed"] += 1
            counts["false_unique"] += 1
        elif truth.semantic_truth == "non-edit":
            counts["non_edit_promoted_to_edit"] += 1
        elif truth.semantic_truth == "explicit-test-edit":
            counts["explicit_test_laundered_to_implementation_owner"] += 1

    if truth.semantic_truth == "unique-owner" and truth.admitted_evidence_truth == "sufficient":
        if state == "ambiguous":
            counts["sufficient_unique_reported_ambiguous"] += 1
        elif state == "unresolved":
            counts["sufficient_unique_reported_unresolved"] += 1

    for metric in HARD_ZERO_METRICS:
        if metric in {
            "false_owner",
            "false_unique",
            "sufficient_unique_reported_ambiguous",
            "sufficient_unique_reported_unresolved",
            "true_ambiguity_collapsed",
            "non_edit_promoted_to_edit",
            "explicit_test_laundered_to_implementation_owner",
        }:
            continue
        if observed.get(metric) is True:
            counts[metric] += 1

    correct_resolution = (
        truth.semantic_truth == "unique-owner"
        and truth.admitted_evidence_truth == "sufficient"
        and state == "resolved"
        and owner == truth.expected_owner
    )
    return {
        "case_id": case["case_id"],
        "semantic_truth": truth.semantic_truth,
        "admitted_evidence_truth": truth.admitted_evidence_truth,
        "reported_state": state,
        "hard_zero": dict(counts),
        "correct_resolution": correct_resolution,
    }


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    totals = _hard_zero_counts()
    sufficient_unique = 0
    correct_unique = 0
    resolved = 0
    incorrect_resolved = 0
    semantic_counts: Counter[str] = Counter()
    for row in rows:
        semantic_counts[str(row["semantic_truth"])] += 1
        for name, count in row["hard_zero"].items():
            totals[name] += int(count)
        if (
            row["semantic_truth"] == "unique-owner"
            and row["admitted_evidence_truth"] == "sufficient"
        ):
            sufficient_unique += 1
            correct_unique += int(bool(row["correct_resolution"]))
        if row["reported_state"] == "resolved":
            resolved += 1
            unsafe = (
                int(row["hard_zero"]["false_owner"])
                + int(row["hard_zero"]["false_unique"])
                + int(row["hard_zero"]["true_ambiguity_collapsed"])
                + int(row["hard_zero"]["non_edit_promoted_to_edit"])
                + int(row["hard_zero"]["explicit_test_laundered_to_implementation_owner"])
            )
            incorrect_resolved += int(unsafe > 0)

    violations = sum(totals.values())
    return {
        "schema": REPORT_SCHEMA,
        "metric_policy": METRIC_POLICY,
        "qualification": "qualified" if violations == 0 else "not-qualified",
        "hard_zero": dict(totals),
        "selective_quality": {
            "resolved_cases": resolved,
            "incorrect_resolved_cases": incorrect_resolved,
            "selective_owner_risk": (
                incorrect_resolved / resolved if resolved else None
            ),
            "sufficient_unique_cases": sufficient_unique,
            "correctly_resolved_unique_cases": correct_unique,
            "resolvable_owner_coverage": (
                correct_unique / sufficient_unique if sufficient_unique else None
            ),
        },
        "corpus": {
            "cases": len(rows),
            "semantic_slices": dict(sorted(semantic_counts.items())),
        },
        "lexicographic_order": [
            "benchmark-integrity",
            "authority-safety",
            "evidence-sufficiency-and-overclaim",
            "abstention-correctness",
            "useful-resolution-coverage",
            "projection-generation-provenance",
            "retrieval-verification-evidence-quality",
            "metamorphic-semantic-stability",
            "economics",
        ],
        "missing_metric_policy": "unknown-not-zero",
    }
