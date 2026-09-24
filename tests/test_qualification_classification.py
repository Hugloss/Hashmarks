from pathlib import Path

from hashmarks.qualification_classification import (
    classification_map,
    classify_nodeids,
    load_classification_policy,
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


def test_classification_policy_is_code_owned_and_root_independent(
    tmp_path: Path,
) -> None:
    root = _root()
    policy = load_classification_policy(root)
    assert policy == load_classification_policy(tmp_path)
    assert policy["unmatched_node_policy"] == "fail-closed"
    nodeids = ["tests/test_new.py::test_new"]
    original_artifact = classify_nodeids(root, nodeids)
    assert (
        original_artifact["policy_identity"]
        == classify_nodeids(tmp_path, nodeids)["policy_identity"]
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


def test_policy_classifies_process_and_empirical_from_shard_constants() -> None:
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
    try:
        classify_nodeids(tmp_path, ["other/test_new.py::test_new"])
    except ValueError as exc:
        assert "unclassified qualification node" in str(exc)
    else:
        raise AssertionError("unmatched qualification node silently classified")
