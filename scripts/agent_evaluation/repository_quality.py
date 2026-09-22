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
BENCHMARK_REGISTRY = "hashmarks.repository-quality-registry.v1"
GROUND_TRUTH_SCHEMA = "hashmarks.repository-quality-ground-truth.v1"
QUALIFICATION_POLICY = "hashmarks.repository-quality-qualification.v1"
EVALUATION_PROFILES = {"navigation.v1", "change-support.v1", "release-critical.v1"}
PROOF_MODES = {"unit", "boundary", "lifecycle", "adversarial", "mutation"}

GROUND_TRUTH_STATUS = {
    "valid",
    "ambiguous-ground-truth",
    "invalid-case",
    "insufficient-ground-truth",
}
CORPUS_CLASS = {"qualification", "shadow", "canary", "fresh-dogfood"}
CASE_LIFECYCLE = {"active", "shadow", "historical", "superseded"}
CRITICAL_SLICE_MINIMUMS = {
    "unique-owner": 1,
    "true-ambiguity": 1,
    "non-edit": 1,
    "explicit-test-edit": 1,
}

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
    payload = json.dumps(
        case, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
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
        "task_family",
        "risk_class",
        "label_basis",
        "benchmark_registry",
        "ground_truth_schema",
        "metric_policy",
        "qualification_policy",
        "evaluation_profile",
        "proof_mode",
    ):
        if not isinstance(case.get(field), str) or not str(case[field]).strip():
            raise ValueError(f"{field} must be a non-empty string")
    _choice(case.get("ground_truth_status"), GROUND_TRUTH_STATUS, "ground_truth_status")
    _choice(case.get("corpus_class"), CORPUS_CLASS, "corpus_class")
    _choice(case.get("lifecycle"), CASE_LIFECYCLE, "lifecycle")
    _choice(case.get("evaluation_profile"), EVALUATION_PROFILES, "evaluation_profile")
    _choice(case.get("proof_mode"), PROOF_MODES, "proof_mode")
    if case["benchmark_registry"] != BENCHMARK_REGISTRY:
        raise ValueError("case benchmark_registry does not match evaluator")
    if case["ground_truth_schema"] != GROUND_TRUTH_SCHEMA:
        raise ValueError("case ground_truth_schema does not match evaluator")
    if case["metric_policy"] != METRIC_POLICY:
        raise ValueError("case metric_policy does not match evaluator")
    if case["qualification_policy"] != QUALIFICATION_POLICY:
        raise ValueError("case qualification_policy does not match evaluator")
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
        "ground_truth_status": case["ground_truth_status"],
        "corpus_class": case["corpus_class"],
        "lifecycle": case["lifecycle"],
        "task_family": case["task_family"],
        "risk_class": case["risk_class"],
        "evaluation_profile": case["evaluation_profile"],
        "proof_mode": case["proof_mode"],
        "ranking": dict(observed.get("ranking") or {}),
        "verification": dict(observed.get("verification") or {}),
        "stability": dict(observed.get("stability") or {}),
        "economics": dict(observed.get("economics") or {}),
        "semantic_truth": truth.semantic_truth,
        "admitted_evidence_truth": truth.admitted_evidence_truth,
        "reported_state": state,
        "hard_zero": dict(counts),
        "correct_resolution": correct_resolution,
        "confusion_key": f"{truth.semantic_truth}|{truth.admitted_evidence_truth}|{state}",
    }


def _confusion_counts(rows: Sequence[Mapping[str, Any]]) -> Counter[str]:
    return Counter(str(row["confusion_key"]) for row in rows)


def _abstention_quality(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    true_ambiguity = [
        row for row in rows if row["semantic_truth"] in {"true-ambiguity", "multi-edit"}
    ]
    reported_ambiguous = [row for row in rows if row["reported_state"] == "ambiguous"]
    correct_ambiguous = sum(
        row["semantic_truth"] in {"true-ambiguity", "multi-edit"}
        for row in reported_ambiguous
    )
    ambiguity_recalled = sum(
        row["reported_state"] == "ambiguous" for row in true_ambiguity
    )
    unresolved = [row for row in rows if row["reported_state"] == "unresolved"]
    justified_unresolved = sum(
        row["admitted_evidence_truth"] != "sufficient"
        or row["semantic_truth"] == "insufficient-owner-evidence"
        for row in unresolved
    )
    non_edit = [row for row in rows if row["semantic_truth"] == "non-edit"]
    correct_non_edit = sum(
        row["reported_state"] == "no-edit-authority" for row in non_edit
    )
    return {
        "true_ambiguity_precision": _ratio(correct_ambiguous, len(reported_ambiguous)),
        "true_ambiguity_recall": _ratio(ambiguity_recalled, len(true_ambiguity)),
        "justified_unresolved_rate": _ratio(justified_unresolved, len(unresolved)),
        "unjustified_unresolved_rate": _ratio(
            len(unresolved) - justified_unresolved, len(unresolved)
        ),
        "non_edit_specificity": _ratio(correct_non_edit, len(non_edit)),
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
        any(int(row["hard_zero"][key]) > 0 for key in unsafe_keys) for row in resolved
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


def _critical_slice_health(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(row["semantic_truth"]) for row in rows)
    missing = {
        name: minimum - counts[name]
        for name, minimum in CRITICAL_SLICE_MINIMUMS.items()
        if counts[name] < minimum
    }
    return {
        "minimums": dict(CRITICAL_SLICE_MINIMUMS),
        "counts": {name: counts[name] for name in CRITICAL_SLICE_MINIMUMS},
        "missing": missing,
        "adequate": not missing,
    }


def _group_quality(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row[field]), []).append(row)
    return {
        name: {
            "cases": len(group),
            "resolvable_owner_coverage": _ratio(
                sum(bool(row["correct_resolution"]) for row in group),
                sum(
                    row["semantic_truth"] == "unique-owner"
                    and row["admitted_evidence_truth"] == "sufficient"
                    for row in group
                ),
            ),
        }
        for name, group in sorted(grouped.items())
    }


def _proof_mode_health(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(row["proof_mode"]) for row in rows)
    return {
        "counts": {name: counts[name] for name in sorted(PROOF_MODES)},
        "present": sorted(name for name in PROOF_MODES if counts[name]),
        "missing": sorted(name for name in PROOF_MODES if not counts[name]),
    }


def _rank_metrics(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, Any]:
    ranks = [
        int(row[field]["rank"])
        for row in rows
        if isinstance(row.get(field), Mapping) and row[field].get("rank") is not None
    ]
    if not ranks:
        return {"cases": 0, "recall_at_1": None, "recall_at_5": None, "mrr": None}
    return {
        "cases": len(ranks),
        "recall_at_1": sum(rank <= 1 for rank in ranks) / len(ranks),
        "recall_at_5": sum(rank <= 5 for rank in ranks) / len(ranks),
        "mrr": sum(1 / rank for rank in ranks) / len(ranks),
    }


def _stability_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    observed = [
        row["stability"]
        for row in rows
        if isinstance(row.get("stability"), Mapping) and row["stability"]
    ]
    keys = (
        "paraphrase_owner_stable",
        "retrieval_bound_owner_stable",
        "projection_authority_stable",
        "generation_authority_stable",
    )
    return {
        key: _ratio(sum(item.get(key) is True for item in observed), len(observed))
        for key in keys
    }


def _economics_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    observed = [
        row["economics"]
        for row in rows
        if isinstance(row.get("economics"), Mapping) and row["economics"]
    ]
    keys = ("latency_ms", "rows_inspected", "candidate_count", "peak_memory_bytes")
    return {
        "cases": len(observed),
        "metrics": {
            key: {
                "samples": len(values),
                "min": min(values) if values else None,
                "max": max(values) if values else None,
            }
            for key in keys
            for values in [[item[key] for item in observed if item.get(key) is not None]]
        },
    }


def _qualification_identity(rows: Sequence[Mapping[str, Any]]) -> str:
    return _corpus_identity(rows)


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    score_rows = [
        row
        for row in rows
        if row["ground_truth_status"] == "valid"
        and row["corpus_class"] == "qualification"
        and row["lifecycle"] == "active"
    ]
    adjudication = sum(
        row["ground_truth_status"]
        in {"ambiguous-ground-truth", "insufficient-ground-truth"}
        for row in rows
    )
    invalid = sum(row["ground_truth_status"] == "invalid-case" for row in rows)
    slice_health = _critical_slice_health(score_rows)
    if not rows or not score_rows or invalid or not slice_health["adequate"]:
        qualification = "benchmark-not-ready"
    elif adjudication:
        qualification = "needs-adjudication"
    else:
        qualification = None
    totals = _hard_zero_counts()
    semantic_counts: Counter[str] = Counter()
    for row in score_rows:
        semantic_counts[str(row["semantic_truth"])] += 1
        totals.update({name: int(count) for name, count in row["hard_zero"].items()})
    selective = _selective_counts(score_rows)
    confusion = _confusion_counts(score_rows)
    abstention = _abstention_quality(score_rows)
    proof_health = _proof_mode_health(score_rows)
    return {
        "schema": REPORT_SCHEMA,
        "metric_policy": METRIC_POLICY,
        "ground_truth_schema": GROUND_TRUTH_SCHEMA,
        "qualification_policy": QUALIFICATION_POLICY,
        "qualification": qualification
        or ("qualified" if sum(totals.values()) == 0 else "not-qualified"),
        "benchmark_health": {
            "registry": BENCHMARK_REGISTRY,
            "total_cases": len(rows),
            "score_bearing_cases": len(score_rows),
            "needs_adjudication": adjudication,
            "invalid_cases": invalid,
            "critical_slices": slice_health,
            "proof_modes": proof_health,
        },
        "hard_zero": dict(totals),
        "state_confusion": dict(sorted(confusion.items())),
        "abstention_quality": abstention,
        "ranking_quality": {
            "owner": _rank_metrics(score_rows, "ranking"),
            "verification": _rank_metrics(score_rows, "verification"),
        },
        "stability_quality": _stability_metrics(score_rows),
        "economics": _economics_summary(score_rows),
        "slice_quality": {
            "macro_by_task_family": _group_quality(score_rows, "task_family"),
            "macro_by_risk_class": _group_quality(score_rows, "risk_class"),
            "macro_by_evaluation_profile": _group_quality(score_rows, "evaluation_profile"),
        },
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
            "qualification_identity": _qualification_identity(score_rows),
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
