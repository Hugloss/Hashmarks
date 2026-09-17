from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Mapping

from .qualification_classification import classify_nodeids
from .qualification_units import qualification_owner_plan
from .test_shards import _nodeids

ECONOMICS_SCHEMA = "hashmarks.qualification-classification-economics.v1"


def _classification_changes(
    rows: list[dict[str, object]],
    previous: Mapping[str, object] | None,
) -> list[str]:
    if previous is None:
        return []
    before = {
        str(row["nodeid"]): str(row["kind"])
        for row in previous.get("classifications", [])
        if isinstance(row, Mapping)
    }
    after = {str(row["nodeid"]): str(row["kind"]) for row in rows}
    return sorted(
        nodeid
        for nodeid in set(before) | set(after)
        if before.get(nodeid) != after.get(nodeid)
    )


def _distribution(plan: Mapping[str, object]) -> tuple[dict[str, int], int]:
    units = plan["units"]
    assert isinstance(units, list)
    granularities = Counter(str(unit["preferred_granularity"]) for unit in units)
    singleton_units = sum(1 for unit in units if len(unit["nodeids"]) == 1)
    return dict(sorted(granularities.items())), singleton_units


def qualification_classification_economics(
    root: Path,
    *,
    previous_classification: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Report repository-intelligence classification economics without executing tests."""
    root = root.resolve()
    nodeids = tuple(nodeid for nodeid, _weight in _nodeids(root))
    classification = classify_nodeids(root, nodeids)
    rows = classification["classifications"]
    assert isinstance(rows, list)
    counts = Counter(str(row["kind"]) for row in rows)
    plan = qualification_owner_plan(root)
    granularities, singleton_units = _distribution(plan)
    changed = _classification_changes(rows, previous_classification)
    total = len(nodeids)
    correctness = counts["release-correctness"]
    return {
        "schema": ECONOMICS_SCHEMA,
        "repository_identity": plan["repository_identity"],
        "classification_identity": classification["classification_identity"],
        "classification_policy_identity": classification["policy_identity"],
        "total_verification_membership": total,
        "release_correctness_members": correctness,
        "process_sensitive_members": counts["process-sensitive"],
        "empirical_benchmark_members": counts["empirical-benchmark"],
        "owner_unit_count": plan["unit_count"],
        "singleton_unit_count": singleton_units,
        "preferred_granularity_distribution": granularities,
        "baseline_all_ordinary_correctness_members": total,
        "classified_ordinary_correctness_members": correctness,
        "ordinary_correctness_members_avoided": total - correctness,
        "exact_total_membership_preserved": total == sum(counts.values()),
        "classification_changes": changed,
        "classification_change_count": len(changed),
        "classification_repository_identity": classification["repository_identity"],
        "previous_classification_repository_identity": (
            previous_classification.get("repository_identity")
            if previous_classification is not None
            else None
        ),
        "authority": "repository-intelligence-economics-only",
        "execution_layout": "external",
    }
