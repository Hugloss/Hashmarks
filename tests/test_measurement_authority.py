from __future__ import annotations

from pathlib import Path

from scripts.repository_evaluation.merge_runs import merge_runs

ROOT = Path(__file__).resolve().parents[1]


def test_measurement_authority_remains_outside_product_runtime() -> None:
    for path in (ROOT / "hashmarks").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "repository-evaluation-profile" not in text
        assert "performance-measurement-only" not in text


def test_controller_cutoff_has_no_product_failure_authority() -> None:
    evaluation = "\n".join(
        p.read_text(encoding="utf-8")
        for p in (ROOT / "scripts/repository_evaluation").glob("*.py")
    )
    assert "performance-measurement-only" in evaluation
    assert "CONTROLLER_TIMEOUT" not in evaluation
    assert "TIMEOUT_FAIL" not in evaluation


def test_resume_receipts_suppress_timing_authority() -> None:
    first = {
        "suite": "authority",
        "protocol_identity": "sha256:protocol",
        "repository_identity": "sha256:repository",
        "producer_implementation_identity": "sha256:producer",
        "producer_artifact_identity": None,
        "cases_sha256": "sha256:cases",
        "shard_count": 2,
        "shard_index": 0,
        "timing_comparable": True,
        "cases": [],
    }
    resumed = {**first, "shard_index": 1, "timing_comparable": False}

    assert merge_runs([first, resumed])["timing_comparable"] is False
