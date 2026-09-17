from pathlib import Path

from hashmarks.qualification_classification import classify_nodeids
from hashmarks.qualification_economics import qualification_classification_economics
from hashmarks.test_shards import _nodeids


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_classification_economics_preserves_exact_membership_and_separates_work() -> None:
    result = qualification_classification_economics(_root())
    assert result["exact_total_membership_preserved"] is True
    assert result["baseline_all_ordinary_correctness_members"] == result["total_verification_membership"]
    assert result["classified_ordinary_correctness_members"] == result["release_correctness_members"]
    assert result["ordinary_correctness_members_avoided"] == (
        result["process_sensitive_members"] + result["empirical_benchmark_members"]
    )
    assert result["owner_unit_count"] > 0
    assert result["singleton_unit_count"] >= 7
    assert result["authority"] == "repository-intelligence-economics-only"


def test_classification_change_economics_reports_identity_bound_delta() -> None:
    root = _root()
    nodeids = [nodeid for nodeid, _weight in _nodeids(root)]
    current = classify_nodeids(root, nodeids)
    result = qualification_classification_economics(
        root,
        previous_classification=current,
    )
    assert result["classification_change_count"] == 0
    assert result["classification_changes"] == []
