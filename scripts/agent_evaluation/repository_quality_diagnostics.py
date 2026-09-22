from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

PROOF_MODES = {"unit", "boundary", "lifecycle", "adversarial", "mutation"}


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def group_quality(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, Any]:
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


def proof_mode_health(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(row["proof_mode"]) for row in rows)
    return {
        "counts": {name: counts[name] for name in sorted(PROOF_MODES)},
        "present": sorted(name for name in PROOF_MODES if counts[name]),
        "missing": sorted(name for name in PROOF_MODES if not counts[name]),
    }


def _rank_discount(rank: int) -> float:
    if rank < 1:
        raise ValueError("ranking rank must be >= 1")
    return 1.0 if rank == 1 else 1 / math.log2(rank + 1)


def rank_metrics(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, Any]:
    ranks = [
        int(row[field]["rank"])
        for row in rows
        if isinstance(row.get(field), Mapping) and row[field].get("rank") is not None
    ]
    if any(rank < 1 for rank in ranks):
        raise ValueError(f"{field} rank must be >= 1")
    if not ranks:
        return {
            "cases": 0,
            "recall_at_1": None,
            "recall_at_5": None,
            "mrr": None,
            "ndcg": None,
        }
    return {
        "cases": len(ranks),
        "recall_at_1": sum(rank <= 1 for rank in ranks) / len(ranks),
        "recall_at_5": sum(rank <= 5 for rank in ranks) / len(ranks),
        "mrr": sum(1 / rank for rank in ranks) / len(ranks),
        "ndcg": sum(_rank_discount(rank) for rank in ranks) / len(ranks),
    }


def stability_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
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
        key: _ratio(
            sum(item.get(key) is True for item in observed if key in item),
            sum(key in item for item in observed),
        )
        for key in keys
    }


def _economics_metric(
    observed: Sequence[Mapping[str, Any]], key: str
) -> dict[str, Any]:
    values = [item[key] for item in observed if item.get(key) is not None]
    if any(not isinstance(value, (int, float)) or value < 0 for value in values):
        raise ValueError(f"economics {key} must be a non-negative number")
    return {
        "samples": len(values),
        "min": min(values) if values else None,
        "max": max(values) if values else None,
    }


def economics_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    observed = [
        row["economics"]
        for row in rows
        if isinstance(row.get("economics"), Mapping) and row["economics"]
    ]
    keys = ("latency_ms", "rows_inspected", "candidate_count", "peak_memory_bytes")
    return {
        "cases": len(observed),
        "metrics": {key: _economics_metric(observed, key) for key in keys},
    }


def evidence_retention(rows: Sequence[Mapping[str, Any]]) -> dict[str, float | None]:
    keys = (
        "related_dependency_retained",
        "impact_evidence_retained",
        "caller_callee_retained",
        "import_relation_retained",
        "verification_surface_retained",
    )
    observed = [
        row["evidence_retention"]
        for row in rows
        if isinstance(row.get("evidence_retention"), Mapping)
        and row["evidence_retention"]
    ]
    return {
        key: _ratio(
            sum(item.get(key) is True for item in observed if key in item),
            sum(key in item for item in observed),
        )
        for key in keys
    }


def environment_health(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    observed = [
        row["environment"]
        for row in rows
        if isinstance(row.get("environment"), Mapping) and row["environment"]
    ]
    allowed_modes = {"cold", "warm", "incremental"}
    modes = Counter(str(item.get("mode") or "unknown") for item in observed)
    invalid_modes = sorted(mode for mode in modes if mode not in allowed_modes)
    if invalid_modes:
        raise ValueError(f"environment mode must be one of {sorted(allowed_modes)}")
    if any(not str(item.get("fingerprint") or "").strip() for item in observed):
        raise ValueError(
            "environment fingerprint must be non-empty when environment is observed"
        )
    identities = sorted(
        {str(item["fingerprint"]) for item in observed if item.get("fingerprint")}
    )
    return {
        "cases": len(observed),
        "modes": dict(sorted(modes.items())),
        "fingerprints": identities,
    }


def metamorphic_health(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    families = Counter(
        str(row["metamorphic_family"]) for row in rows if row.get("metamorphic_family")
    )
    observations = [
        row["metamorphic_observation"]
        for row in rows
        if isinstance(row.get("metamorphic_observation"), Mapping)
        and row["metamorphic_observation"]
    ]
    observed_families = Counter(str(item["family"]) for item in observations)
    return {
        "families": dict(sorted(families.items())),
        "cases": sum(families.values()),
        "executed": len(observations),
        "executed_families": dict(sorted(observed_families.items())),
        "violations": sum(bool(item.get("violation")) for item in observations),
    }


def _wilson_interval(successes: int, total: int) -> dict[str, float | int | None]:
    if total == 0:
        return {"successes": 0, "total": 0, "estimate": None, "low": None, "high": None}
    z = 1.959963984540054
    estimate = successes / total
    denominator = 1 + z * z / total
    center = (estimate + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            estimate * (1 - estimate) / total + z * z / (4 * total * total)
        )
        / denominator
    )
    return {
        "successes": successes,
        "total": total,
        "estimate": estimate,
        "low": max(0.0, center - margin),
        "high": min(1.0, center + margin),
    }


def uncertainty_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    resolvable = [
        row
        for row in rows
        if row["semantic_truth"] == "unique-owner"
        and row["admitted_evidence_truth"] == "sufficient"
    ]
    correct = sum(bool(row["correct_resolution"]) for row in resolvable)
    resolved = [row for row in rows if row["reported_state"] == "resolved"]
    safe = sum(not any(int(value) for value in row["hard_zero"].values()) for row in resolved)
    return {
        "resolvable_owner_coverage_95pct": _wilson_interval(correct, len(resolvable)),
        "resolved_without_hard_zero_95pct": _wilson_interval(safe, len(resolved)),
        "interpretation": "descriptive-only-no-qualification-threshold",
    }
