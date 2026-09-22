from __future__ import annotations

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


def rank_metrics(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, Any]:
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
        key: _ratio(sum(item.get(key) is True for item in observed), len(observed))
        for key in keys
    }


def _economics_metric(
    observed: Sequence[Mapping[str, Any]], key: str
) -> dict[str, Any]:
    values = [item[key] for item in observed if item.get(key) is not None]
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


