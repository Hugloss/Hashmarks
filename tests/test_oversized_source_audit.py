from pathlib import Path

from scripts.oversized_source_audit import audit


def test_oversized_source_audit_classifies_current_sources_by_measured_size() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = audit(root)
    policy = payload["policy"]

    critical = payload["critical_files"]
    high = payload["high_files"]
    review = payload["review_files"]

    assert all(row["lines"] >= policy["critical_file_lines"] for row in critical)
    assert all(
        policy["high_file_lines"] <= row["lines"] < policy["critical_file_lines"]
        for row in high
    )
    assert all(
        policy["review_file_lines"] <= row["lines"] < policy["high_file_lines"]
        for row in review
    )
    assert payload["authority"] == "development-quality-only"


def test_oversized_source_audit_does_not_encode_historical_file_sizes() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = audit(root)
    critical_paths = {row["path"] for row in payload["critical_files"]}
    engine_lines = len(
        (root / "hashmarks/codemap/engine.py").read_text(encoding="utf-8").splitlines()
    )

    # Classification follows the bytes in the candidate, not a historical expectation
    # that engine.py was a >10k-line monolith before responsibility extraction.
    assert ("hashmarks/codemap/engine.py" in critical_paths) == (
        engine_lines >= payload["policy"]["critical_file_lines"]
    )


def test_oversized_source_audit_thresholds_are_review_nominations() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = audit(root)
    assert (
        payload["policy"]["critical_file_lines"] > payload["policy"]["high_file_lines"]
    )
    assert "nominate review" in payload["policy"]["note"]
