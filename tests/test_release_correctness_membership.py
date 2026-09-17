from pathlib import Path

from hashmarks.qualification_classification import classification_map
from hashmarks.test_shards import _nodeids, release_correctness_nodeids


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_release_correctness_membership_matches_repository_classification_policy() -> (
    None
):
    root = _root()
    all_nodes = [nodeid for nodeid, _weight in _nodeids(root)]
    classes = classification_map(root, all_nodes)
    selected = set(release_correctness_nodeids(root))
    expected = {
        nodeid
        for nodeid in all_nodes
        if classes[nodeid]["kind"] == "release-correctness"
    }
    assert selected == expected
    assert (
        "tests/test_product_acceptance.py::test_executable_acceptance_suite_passes_small_repository"
        in selected
    )


def test_process_sensitive_and_empirical_members_are_not_release_correctness() -> None:
    root = _root()
    selected = set(release_correctness_nodeids(root))
    assert (
        "tests/test_codemap.py::test_codemap_watcher_keeps_map_hot_without_identity_daemon"
        not in selected
    )
    assert (
        "tests/test_agent_metrics_suite.py::test_selective_scout_targets_only_observed_ambiguity"
        not in selected
    )
