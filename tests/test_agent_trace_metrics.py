from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.agent_evaluation import metrics_agent_trace as trace_metrics


def _trace(
    path: Path, mode: str, *, task_id: str = "task-1", tokens: int = 100
) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema": trace_metrics.TRACE_SCHEMA,
                "task_id": task_id,
                "task_revision": "task-v1",
                "repository_identity": "sha256:repo",
                "mode": mode,
                "run_id": f"run-{mode}",
                "model_identity": "model-1",
                "model_config_identity": "sha256:model-config",
                "model_input_tokens_source": "runner",
                "model_input_tokens": tokens,
                "success": True,
                "patch_correct": True,
                "events": [
                    {
                        "kind": "file_read",
                        "path": "src/owner.py",
                        "bytes": 10,
                        "estimated_tokens": 3,
                        "started_at_ns": 1,
                        "finished_at_ns": 2,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.update(schema="wrong"), "unsupported agent trace schema"),
        (
            lambda value: value.update(mode="wrong"),
            "mode must be baseline or hashmarks",
        ),
        (lambda value: value.update(task_id=""), "task_id must be a non-empty string"),
        (lambda value: value.update(events={}), "events must be a list"),
        (lambda value: value.update(events=[{"kind": 3}]), "invalid trace event"),
        (
            lambda value: value.update(events=[{"kind": "file_read", "bytes": -1}]),
            "bytes must be a non-negative integer",
        ),
        (
            lambda value: value.update(events=[{"kind": "file_read", "paths": [""]}]),
            "paths must be a list of non-empty strings",
        ),
        (
            lambda value: value.update(
                events=[{"kind": "file_read", "started_at_ns": 2, "finished_at_ns": 1}]
            ),
            "finished_at_ns must be >= started_at_ns",
        ),
        (
            lambda value: value.update(model_input_tokens=True),
            "model_input_tokens must be a non-negative integer",
        ),
    ],
)
def test_trace_rejects_malformed_evidence(
    tmp_path: Path, mutation, message: str
) -> None:
    path = _trace(tmp_path / "trace.json", "baseline")
    value = json.loads(path.read_text())
    mutation(value)
    path.write_text(json.dumps(value))

    with pytest.raises(ValueError, match=message):
        trace_metrics.load_trace(path)


def test_compare_binds_complete_pair_and_exact_token_reduction(tmp_path: Path) -> None:
    baseline = _trace(tmp_path / "baseline.json", "baseline", tokens=100)
    hashmarks = _trace(tmp_path / "hashmarks.json", "hashmarks", tokens=60)

    report = trace_metrics.compare([baseline, hashmarks], require_complete_pairs=True)

    assert report["pairs"][0]["claim_eligible"] is True
    assert report["summary"]["token_reduction_claim_eligible"] is True
    assert report["summary"]["average_model_input_token_reduction"] == 0.4


def test_compare_reports_pair_identity_drift_as_ineligible(tmp_path: Path) -> None:
    baseline = _trace(tmp_path / "baseline.json", "baseline")
    hashmarks = _trace(tmp_path / "hashmarks.json", "hashmarks")
    value = json.loads(hashmarks.read_text())
    value["repository_identity"] = "sha256:other"
    hashmarks.write_text(json.dumps(value))

    report = trace_metrics.compare([baseline, hashmarks])

    assert report["pairs"][0]["claim_eligible"] is False
    assert "paired_repository_identity_mismatch" in report["pairs"][0]["claim_blockers"]


def test_compare_rejects_duplicate_and_unpaired_traces(tmp_path: Path) -> None:
    baseline = _trace(tmp_path / "baseline.json", "baseline")
    duplicate = _trace(tmp_path / "duplicate.json", "baseline")
    with pytest.raises(ValueError, match="duplicate task/mode traces"):
        trace_metrics.compare([baseline, duplicate])
    with pytest.raises(ValueError, match="unpaired task traces"):
        trace_metrics.compare([baseline], require_complete_pairs=True)
