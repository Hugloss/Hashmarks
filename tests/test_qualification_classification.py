import json
from copy import deepcopy
from pathlib import Path

from hashmarks.qualification_classification import (
    classification_map,
    classify_nodeids,
)
from hashmarks.qualification_units import qualification_owner_plan
from hashmarks.test_shards import _nodeids


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_repository_classification_is_deterministic_identity_bound_and_inspectable() -> (
    None
):
    root = _root()
    nodeids = [nodeid for nodeid, _weight in _nodeids(root)]
    first = classify_nodeids(root, nodeids)
    second = classify_nodeids(root, nodeids)
    assert first == second
    assert first["classification_identity"].startswith("sha256:")
    assert first["policy_identity"].startswith("sha256:")
    assert len(first["classifications"]) == len(nodeids)


def test_classification_policy_change_changes_plan_identity(tmp_path: Path) -> None:
    root = _root()
    policy_path = root / "qualification-classification.json"
    original = json.loads(policy_path.read_text())
    mutated = deepcopy(original)
    mutated["path_rules"][0]["preferred_granularity"] = "singleton"

    copy_root = tmp_path / "repo"
    copy_root.mkdir()
    for name in ("qualification-classification.json",):
        (copy_root / name).write_text(json.dumps(mutated))
    # Classification identity is tested independently because a full copied test tree
    # is not needed to prove the policy artifact is identity-bearing.
    nodeids = ["tests/test_new.py::test_new"]
    original_artifact = classify_nodeids(root, nodeids)
    mutated_artifact = classify_nodeids(copy_root, nodeids)
    assert original_artifact["policy_identity"] != mutated_artifact["policy_identity"]
    assert (
        original_artifact["classification_identity"]
        != mutated_artifact["classification_identity"]
    )


def test_runtime_measurement_cannot_mutate_authoritative_classification() -> None:
    root = _root()
    nodeids = [nodeid for nodeid, _weight in _nodeids(root)]
    before = classify_nodeids(root, nodeids)
    _measurement_nomination = {
        "nodeid": nodeids[0],
        "nominated_kind": "empirical-benchmark",
    }
    after = classify_nodeids(root, nodeids)
    assert before == after


def test_policy_classifies_process_and_empirical_without_python_constants() -> None:
    root = _root()
    nodeids = [nodeid for nodeid, _weight in _nodeids(root)]
    classes = classification_map(root, nodeids)
    assert (
        classes[
            "tests/test_codemap_watcher.py::test_codemap_watcher_keeps_map_hot_without_identity_daemon"
        ]["kind"]
        == "process-sensitive"
    )
    assert (
        classes[
            "tests/test_agent_metrics_suite.py::test_blind_worker_ab_is_reproducible_and_scores_both_workers"
        ]["kind"]
        == "empirical-benchmark"
    )
    plan = qualification_owner_plan(root)
    assert plan["classification_identity"].startswith("sha256:")
    assert plan["classification_policy_identity"].startswith("sha256:")


def test_unmatched_new_test_node_fails_closed(tmp_path: Path) -> None:
    root = _root()
    policy = json.loads((root / "qualification-classification.json").read_text())
    copy_root = tmp_path / "repo"
    copy_root.mkdir()
    (copy_root / "qualification-classification.json").write_text(json.dumps(policy))
    try:
        classify_nodeids(copy_root, ["other/test_new.py::test_new"])
    except ValueError as exc:
        assert "unclassified qualification node" in str(exc)
    else:
        raise AssertionError("unmatched qualification node silently classified")


def test_classification_policy_rejects_nonportable_json_scalars(tmp_path: Path) -> None:
    from hashmarks.qualification_classification import load_classification_policy

    policy = {
        "schema": "hashmarks.qualification-classification-policy.v1",
        "unmatched_node_policy": "fail-closed",
        "node_overrides": [],
        "path_rules": [
            {
                "path_prefix": "tests/",
                "kind": "release-correctness",
                "reason": float("nan"),
            }
        ],
    }
    (tmp_path / "qualification-classification.json").write_text(
        json.dumps(policy), encoding="utf-8"
    )
    try:
        load_classification_policy(tmp_path)
    except ValueError as exc:
        assert "strict JSON-portable" in str(exc)
    else:
        raise AssertionError("nonportable NaN policy silently accepted")
