from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


_MODULE = __import__("scripts.agent_evaluation.metrics_agent_regret_suite", fromlist=["*"])


def _load():
    return _MODULE

def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_run(root: Path, task: str, mode: str, events: list[dict]) -> tuple[Path, Path]:
    trace = root / f"{task}-{mode}.json"
    evidence = root / f"{task}-evidence.json"
    trace.write_text(json.dumps({
        "schema": "hashmarks.agent-trace.v2", "task_id": task, "task_revision": "v1",
        "repository_identity": "sha256:repo", "mode": mode, "run_id": f"{task}-{mode}",
        "model_identity": "model-x", "model_config_identity": "sha256:model", "events": events,
    }))
    if not evidence.exists():
        evidence.write_text(json.dumps({
            "schema": "hashmarks.agent-retrieval-evidence.v1", "task_id": task, "task_revision": "v1",
            "repository_identity": "sha256:repo", "evidence_authority_identity": "grader:evidence:v1",
            "required_paths": ["src/target.py"],
        }))
    return trace, evidence


def _entry(root: Path, trace: Path, evidence: Path) -> dict:
    return {"trace": trace.name, "evidence": evidence.name, "trace_sha256": _sha(trace), "evidence_sha256": _sha(evidence)}


def test_suite_ranks_observed_opportunities_and_pairs_modes(tmp_path: Path) -> None:
    module = _load()
    base, evidence = _write_run(tmp_path, "t1", "baseline", [
        {"kind": "grep", "query": "x", "estimated_tokens": 50},
        {"kind": "grep", "query": "x", "estimated_tokens": 50},
        {"kind": "file_read", "path": "src/wrong.py", "estimated_tokens": 300},
        {"kind": "file_read", "path": "src/wrong.py", "estimated_tokens": 300},
        {"kind": "file_read", "path": "src/target.py", "estimated_tokens": 100},
    ])
    hm, _ = _write_run(tmp_path, "t1", "hashmarks", [
        {"kind": "hashmarks_find", "query": "x", "returned_paths": ["src/target.py"], "estimated_tokens": 50},
    ])
    manifest = tmp_path / "suite.json"
    manifest.write_text(json.dumps({
        "schema": "hashmarks.agent-retrieval-regret-suite.v1", "suite_id": "suite-1",
        "entries": [_entry(tmp_path, base, evidence), _entry(tmp_path, hm, evidence)],
    }))
    report = module.analyze(manifest)
    assert report["summary"]["paired_tasks"] == 1
    assert report["summary"]["complete_required_evidence_runs"] == 2
    assert report["summary"]["observed_opportunities_ranked"][0]["kind"] == "late_all_required_evidence"
    assert report["summary"]["observed_opportunity_totals"]["repeated_queries"] == 50
    assert report["summary"]["observed_opportunity_totals"]["repeated_reads"] == 300
    assert report["summary"]["opportunities_overlap"] is True


def test_suite_binds_exact_trace_and_evidence_bytes(tmp_path: Path) -> None:
    module = _load(); trace, evidence = _write_run(tmp_path, "t1", "baseline", [{"kind": "file_read", "path": "src/target.py"}])
    manifest = tmp_path / "suite.json"
    entry = _entry(tmp_path, trace, evidence); entry["trace_sha256"] = "sha256:" + "0" * 64
    manifest.write_text(json.dumps({"schema": "hashmarks.agent-retrieval-regret-suite.v1", "suite_id": "suite-1", "entries": [entry]}))
    with pytest.raises(ValueError, match="trace_sha256 mismatch"):
        module.analyze(manifest)


def test_suite_rejects_path_escape(tmp_path: Path) -> None:
    module = _load(); manifest = tmp_path / "suite.json"
    manifest.write_text(json.dumps({
        "schema": "hashmarks.agent-retrieval-regret-suite.v1", "suite_id": "suite-1",
        "entries": [{"trace": "../trace.json", "evidence": "evidence.json", "trace_sha256": "sha256:x", "evidence_sha256": "sha256:y"}],
    }))
    with pytest.raises(ValueError, match="inside the suite directory"):
        module.analyze(manifest)
