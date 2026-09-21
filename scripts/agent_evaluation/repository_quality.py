from __future__ import annotations

import hashlib
import json
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
DERIVED_METRICS = {
    "false_owner",
    "false_unique",
    "sufficient_unique_reported_ambiguous",
    "sufficient_unique_reported_unresolved",
    "true_ambiguity_collapsed",
    "non_edit_promoted_to_edit",
    "explicit_test_laundered_to_implementation_owner",
}
HARD_ZERO_METRICS = (
    *sorted(DERIVED_METRICS),
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


def case_identity(case: Mapping[str, Any]) -> str:
    validate_case(case)
    payload = json.dumps(case, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _choice(value: object, allowed: set[str], field: str) -> str:
    text = str(value or "")
    if text not in allowed:
        raise ValueError(f"{field} must be one of {sorted(allowed)}")
    return text


def validate_case(case: Mapping[str, Any]) -> QualityTruth:
    if case.get("schema") != SCHEMA:
        raise ValueError("unsupported repository quality case schema")
    for field in (
        "case_id",
        "repository_identity",
        "source_identity",
        "ground_truth_basis",
    ):
        if not isinstance(case.get(field), str) or not str(case[field]).strip():
            raise ValueError(f"{field} must be a non-empty string")
    semantic = _choice(case.get("semantic_truth"), SEMANTIC_TRUTH, "semantic_truth")
    evidence = _choice(
        case.get("admitted_evidence_truth"),
        EVIDENCE_TRUTH,
        "admitted_evidence_truth",
    )
    owner = case.get("expected_owner")
    if semantic == "unique-owner" and (not isinstance(owner, str) or not owner):
        raise ValueError("unique-owner cases require expected_owner")
    if semantic != "unique-owner" and owner is not None:
        raise ValueError("expected_owner is only valid for unique-owner cases")
    return QualityTruth(semantic, evidence, owner if isinstance(owner, str) else None)


def _hard_zero_counts() -> Counter[str]:
    return Counter({name: 0 for name in HARD_ZERO_METRICS})


def _grade_resolved(
    truth: QualityTruth,
    owner: object,
    counts: Counter[str],
) -> None:
    if truth.semantic_truth == "unique-owner":
        if truth.admitted_evidence_truth != "sufficient":
            counts["false_unique"] += 1
        elif owner != truth.expected_owner:
            counts["false_owner"] += 1
        return
    if truth.semantic_truth in {"true-ambiguity", "multi-edit"}:
        counts["true_ambiguity_collapsed"] += 1
        counts["false_unique"] += 1
    elif truth.semantic_truth == "non-edit":
        counts["non_edit_promoted_to_edit"] += 1
    elif truth.semantic_truth == "explicit-test-edit":
        counts["explicit_test_laundered_to_implementation_owner"] += 1


def _grade_abstention(
    truth: QualityTruth,
    state: str,
    counts: Counter[str],
) -> None:
    if (
        truth.semantic_truth != "unique-owner"
        or truth.admitted_evidence_truth != "sufficient"
    ):
        return
    if state == "ambiguous":
        counts["sufficient_unique_reported_ambiguous"] += 1
    elif state == "unresolved":
        counts["sufficient_unique_reported_unresolved"] += 1


def _grade_observed_flags(
    observed: Mapping[str, Any],
    counts: Counter[str],
) -> None:
    for metric in HARD_ZERO_METRICS:
        if metric not in DERIVED_METRICS and observed.get(metric) is True:
            counts[metric] += 1


def evaluate_case(
    case: Mapping[str, Any],
    observed: Mapping[str, Any],
) -> dict[str, Any]:
    truth = validate_case(case)
    state = _choice(observed.get("state"), REPORTED_STATE, "observed state")
    owner = observed.get("owner")
    counts = _hard_zero_counts()
    if state == "resolved":
        _grade_resolved(truth, owner, counts)
    _grade_abstention(truth, state, counts)
    _grade_observed_flags(observed, counts)
    correct_resolution = (
        truth.semantic_truth == "unique-owner"
        and truth.admitted_evidence_truth == "sufficient"
        and state == "resolved"
        and owner == truth.expected_owner
    )
    return {
        "case_id": case["case_id"],
        "case_identity": case_identity(case),
        "semantic_truth": truth.semantic_truth,
        "admitted_evidence_truth": truth.admitted_evidence_truth,
        "reported_state": state,
        "hard_zero": dict(counts),
        "correct_resolution": correct_resolution,
    }


def _selective_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    sufficient = [
        row
        for row in rows
        if row["semantic_truth"] == "unique-owner"
        and row["admitted_evidence_truth"] == "sufficient"
    ]
    resolved = [row for row in rows if row["reported_state"] == "resolved"]
    unsafe_keys = {
        "false_owner",
        "false_unique",
        "true_ambiguity_collapsed",
        "non_edit_promoted_to_edit",
        "explicit_test_laundered_to_implementation_owner",
    }
    incorrect = sum(
        any(int(row["hard_zero"][key]) > 0 for key in unsafe_keys)
        for row in resolved
    )
    return {
        "resolved": len(resolved),
        "incorrect": incorrect,
        "sufficient": len(sufficient),
        "correct": sum(bool(row["correct_resolution"]) for row in sufficient),
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _corpus_identity(rows: Sequence[Mapping[str, Any]]) -> str:
    payload = json.dumps(
        sorted(str(row["case_identity"]) for row in rows),
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    totals = _hard_zero_counts()
    semantic_counts: Counter[str] = Counter()
    for row in rows:
        semantic_counts[str(row["semantic_truth"])] += 1
        totals.update({name: int(count) for name, count in row["hard_zero"].items()})
    selective = _selective_counts(rows)
    return {
        "schema": REPORT_SCHEMA,
        "metric_policy": METRIC_POLICY,
        "qualification": (
            "qualified" if sum(totals.values()) == 0 else "not-qualified"
        ),
        "hard_zero": dict(totals),
        "selective_quality": {
            "resolved_cases": selective["resolved"],
            "incorrect_resolved_cases": selective["incorrect"],
            "selective_owner_risk": _ratio(
                selective["incorrect"], selective["resolved"]
            ),
            "sufficient_unique_cases": selective["sufficient"],
            "correctly_resolved_unique_cases": selective["correct"],
            "resolvable_owner_coverage": _ratio(
                selective["correct"], selective["sufficient"]
            ),
        },
        "corpus": {
            "cases": len(rows),
            "identity": _corpus_identity(rows),
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
