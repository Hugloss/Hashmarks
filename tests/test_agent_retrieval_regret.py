from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

_MODULE = __import__("scripts.agent_evaluation.metrics_agent_regret", fromlist=["*"])


def _load():
    return _MODULE


def _evidence(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema": "hashmarks.agent-retrieval-evidence.v1",
                "task_id": "task-1",
                "task_revision": "v1",
                "repository_identity": "sha256:repo",
                "evidence_authority_identity": "grader:required-evidence:v1",
                "required_paths": ["src/target.py", "src/helper.py"],
            }
        )
    )


def _trace(path: Path, mode: str, events: list[dict]) -> None:
    path.write_text(
        json.dumps(
            {
                "schema": "hashmarks.agent-trace.v2",
                "task_id": "task-1",
                "task_revision": "v1",
                "repository_identity": "sha256:repo",
                "mode": mode,
                "run_id": f"run-{mode}",
                "model_identity": "model-x",
                "model_config_identity": "sha256:model",
                "events": events,
            }
        )
    )


def test_regret_measures_work_before_independent_required_evidence(
    tmp_path: Path,
) -> None:
    module = _load()
    evidence = tmp_path / "evidence.json"
    trace = tmp_path / "trace.json"
    _evidence(evidence)
    _trace(
        trace,
        "baseline",
        [
            {"kind": "grep", "query": "wrong", "estimated_tokens": 100},
            {"kind": "file_read", "path": "src/wrong.py", "estimated_tokens": 400},
            {"kind": "grep", "query": "wrong", "estimated_tokens": 50},
            {"kind": "file_read", "path": "src/target.py", "estimated_tokens": 300},
            {"kind": "file_read", "path": "src/target.py", "estimated_tokens": 300},
            {"kind": "file_read", "path": "src/helper.py", "estimated_tokens": 200},
        ],
    )
    report = module.analyze(trace, evidence)
    s = report["summary"]
    assert s["tokens_before_first_required_evidence"] == 550
    assert s["searches_before_first_required_evidence"] == 2
    assert s["reads_before_first_required_evidence"] == 1
    assert s["tokens_before_all_required_evidence"] == 1150
    assert s["searches_before_all_required_evidence"] == 2
    assert s["reads_before_all_required_evidence"] == 3
    assert s["duplicate_queries"] == 1
    assert s["duplicate_query_estimated_tokens"] == 50
    assert s["duplicate_reads"] == 1
    assert s["duplicate_read_estimated_tokens"] == 300
    assert s["irrelevant_reads"] == 1
    assert s["irrelevant_read_estimated_tokens"] == 400
    assert s["required_evidence_complete"] is True
    assert report["observed_opportunities"]["repeated_queries"][0]["query"] == "wrong"
    assert (
        report["observed_opportunities"]["repeated_reads"][0]["path"] == "src/target.py"
    )


def test_regret_uses_returned_paths_as_discovery_without_self_attested_usefulness(
    tmp_path: Path,
) -> None:
    module = _load()
    evidence = tmp_path / "evidence.json"
    trace = tmp_path / "trace.json"
    _evidence(evidence)
    _trace(
        trace,
        "hashmarks",
        [
            {
                "kind": "hashmarks_find",
                "query": "target",
                "returned_paths": ["src/target.py"],
                "estimated_tokens": 80,
            },
            {
                "kind": "hashmarks_context",
                "evidence_paths": ["src/helper.py"],
                "estimated_tokens": 120,
            },
        ],
    )
    report = module.analyze(trace, evidence)
    assert report["summary"]["tokens_before_first_required_evidence"] == 0
    assert report["summary"]["required_evidence_complete"] is True


def test_missing_required_evidence_is_explicit_not_treated_as_zero_regret(
    tmp_path: Path,
) -> None:
    module = _load()
    evidence = tmp_path / "evidence.json"
    trace = tmp_path / "trace.json"
    _evidence(evidence)
    _trace(
        trace,
        "baseline",
        [{"kind": "file_read", "path": "src/wrong.py", "estimated_tokens": 100}],
    )
    report = module.analyze(trace, evidence)
    assert report["summary"]["required_evidence_complete"] is False
    assert report["summary"]["tokens_before_first_required_evidence"] is None
    assert report["summary"]["missing_required_paths"] == [
        "src/helper.py",
        "src/target.py",
    ]


def test_trace_and_evidence_identity_must_match(tmp_path: Path) -> None:
    module = _load()
    evidence = tmp_path / "evidence.json"
    trace = tmp_path / "trace.json"
    _evidence(evidence)
    _trace(trace, "baseline", [])
    payload = json.loads(trace.read_text())
    payload["repository_identity"] = "sha256:other"
    trace.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="repository_identity mismatch"):
        module.analyze(trace, evidence)


def test_comparison_reports_regret_reduction_only_for_same_evidence(
    tmp_path: Path,
) -> None:
    module = _load()
    evidence = tmp_path / "evidence.json"
    base = tmp_path / "base.json"
    hm = tmp_path / "hm.json"
    _evidence(evidence)
    _trace(
        base,
        "baseline",
        [
            {"kind": "grep", "query": "x", "estimated_tokens": 100},
            {"kind": "file_read", "path": "src/wrong.py", "estimated_tokens": 300},
            {"kind": "file_read", "path": "src/target.py", "estimated_tokens": 100},
            {"kind": "file_read", "path": "src/helper.py", "estimated_tokens": 100},
        ],
    )
    _trace(
        hm,
        "hashmarks",
        [
            {
                "kind": "hashmarks_find",
                "returned_paths": ["src/target.py", "src/helper.py"],
                "estimated_tokens": 100,
            },
        ],
    )
    comparison = module.compare(
        module.analyze(base, evidence), module.analyze(hm, evidence)
    )
    assert comparison["schema"] == "hashmarks.agent-retrieval-regret-comparison.v2"
    assert (
        comparison["reductions"]["tokens_before_first_required_evidence_reduction"]
        == 400
    )
    assert (
        comparison["reductions"]["tokens_before_all_required_evidence_reduction"] == 500
    )
    assert comparison["reductions"]["irrelevant_read_estimated_tokens_reduction"] == 300


def test_retrieval_evidence_rejects_parent_path_escape(tmp_path: Path) -> None:
    module = _load()
    evidence = tmp_path / "evidence.json"
    _evidence(evidence)
    value = json.loads(evidence.read_text())
    value["required_paths"] = ["../secret.py"]
    evidence.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="repository-relative"):
        module.load_evidence(evidence)


def test_regret_reports_navigation_time_when_runner_timing_exists(
    tmp_path: Path,
) -> None:
    module = _load()
    evidence = tmp_path / "evidence.json"
    trace = tmp_path / "trace.json"
    _evidence(evidence)
    _trace(
        trace,
        "baseline",
        [
            {
                "kind": "grep",
                "query": "x",
                "estimated_tokens": 10,
                "started_at_ns": 1_000_000_000,
                "finished_at_ns": 1_100_000_000,
            },
            {
                "kind": "file_read",
                "path": "src/target.py",
                "estimated_tokens": 20,
                "started_at_ns": 1_200_000_000,
                "finished_at_ns": 1_300_000_000,
            },
            {
                "kind": "file_read",
                "path": "src/helper.py",
                "estimated_tokens": 20,
                "started_at_ns": 1_500_000_000,
                "finished_at_ns": 1_600_000_000,
            },
        ],
    )
    s = module.analyze(trace, evidence)["summary"]
    assert s["navigation_ms_before_first_required_evidence"] == 200.0
    assert s["navigation_ms_before_all_required_evidence"] == 500.0
    assert s["total_navigation_ms"] == 600.0
