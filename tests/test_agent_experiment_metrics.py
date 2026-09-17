from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


_MODULE = __import__("scripts.agent_evaluation.metrics_agent_experiment", fromlist=["*"])


def _load():
    return _MODULE

def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _experiment(tmp_path: Path, *, mismatch: tuple[str, str] | None = None, omit_raw: bool = False) -> Path:
    runs = []
    for mode, run_id, tokens in (("baseline", "run-base", 10000), ("hashmarks", "run-hm", 6000)):
        raw_grader = tmp_path / f"{mode}.grader.raw"
        raw_provider = tmp_path / f"{mode}.provider.raw"
        raw_grader.write_bytes(f"grader:{mode}".encode())
        raw_provider.write_bytes(f"provider:{mode}:{tokens}".encode())
        subject = tmp_path / f"{mode}.patch"
        subject.write_bytes(f"patch:{mode}".encode())
        trace = {
            "schema": "hashmarks.agent-trace.v2", "task_id": "t1", "task_revision": "task-v1",
            "repository_identity": "sha256:repo", "mode": mode, "run_id": run_id,
            "model_identity": "model-x", "model_config_identity": "sha256:model-config",
            "runner_identity": "runner:test",
            "model_input_tokens_source": "external-provider-usage-required", "events": [],
        }
        if mismatch and mismatch[0] == mode:
            trace["repository_identity"] = mismatch[1]
        trace_path = tmp_path / f"{mode}.trace.json"
        trace_path.write_text(json.dumps(trace))
        verdict_path = tmp_path / f"{mode}.verdict.json"
        verdict_path.write_text(json.dumps({
            "schema": "hashmarks.agent-verdict.v1", "task_id": "t1", "mode": mode, "run_id": run_id,
            "grader_identity": "grader:test:v1", "evidence_digest": _digest(raw_grader),
            "subject_digest": _digest(subject), "success": True, "patch_correct": True,
        }))
        usage_path = tmp_path / f"{mode}.usage.json"
        usage_path.write_text(json.dumps({
            "schema": "hashmarks.agent-model-usage.v1", "task_id": "t1", "mode": mode, "run_id": run_id,
            "provider_identity": "provider:test:v1", "evidence_digest": _digest(raw_provider),
            "model_input_tokens": tokens,
        }))
        run = {
            "task_id": "t1", "task_revision": "task-v1", "repository_identity": "sha256:repo",
            "mode": mode, "run_id": run_id,
            "trace": trace_path.name, "verdict": verdict_path.name, "usage": usage_path.name,
            "subject": subject.name,
        }
        if not omit_raw:
            run.update({"grader_evidence": raw_grader.name, "provider_evidence": raw_provider.name})
        runs.append(run)
    manifest = tmp_path / "experiment.json"
    manifest.write_text(json.dumps({
        "schema": "hashmarks.agent-experiment.v1", "experiment_id": "experiment-1",
        "model_identity": "model-x", "model_config_identity": "sha256:model-config",
        "runner_identity": "runner:test", "runner_version": "1.0",
        "grader_identity": "grader:test:v1", "provider_identity": "provider:test:v1",
        "runs": runs,
    }))
    return manifest


def test_manifest_validates_complete_experiment_and_raw_evidence(tmp_path: Path) -> None:
    module = _load()
    report = module.run_experiment(_experiment(tmp_path), strict_raw_evidence=True)
    assert report["schema"] == "hashmarks.agent-experiment-report.v1"
    assert report["tasks"] == 1
    assert report["repositories"] == 1
    assert report["comparison"]["summary"]["token_reduction_claim_eligible"] is True
    assert report["comparison"]["summary"]["average_model_input_token_reduction"] == 0.4


def test_manifest_rejects_trace_identity_drift(tmp_path: Path) -> None:
    module = _load()
    with pytest.raises(ValueError, match="trace repository_identity mismatch"):
        module.run_experiment(_experiment(tmp_path, mismatch=("hashmarks", "sha256:wrong")))


def test_manifest_rejects_raw_evidence_digest_mismatch(tmp_path: Path) -> None:
    module = _load()
    manifest = _experiment(tmp_path)
    (tmp_path / "baseline.provider.raw").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="provider raw evidence digest mismatch"):
        module.run_experiment(manifest, strict_raw_evidence=True)


def test_strict_raw_evidence_requires_retained_raw_files(tmp_path: Path) -> None:
    module = _load()
    with pytest.raises(ValueError, match="requires grader_evidence"):
        module.run_experiment(_experiment(tmp_path, omit_raw=True), strict_raw_evidence=True)


def test_manifest_rejects_unpaired_expected_task(tmp_path: Path) -> None:
    module = _load()
    manifest = _experiment(tmp_path)
    payload = json.loads(manifest.read_text())
    payload["runs"] = payload["runs"][:1]
    manifest.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="unpaired tasks: t1"):
        module.load_manifest(manifest)


def test_manifest_paths_cannot_escape_experiment_directory(tmp_path: Path) -> None:
    module = _load()
    manifest = _experiment(tmp_path)
    payload = json.loads(manifest.read_text())
    payload["runs"][0]["trace"] = "../escape.json"
    manifest.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="escapes experiment directory"):
        module.run_experiment(manifest)


def test_verdict_is_bound_to_exact_subject_bytes(tmp_path: Path) -> None:
    module = _load()
    manifest = _experiment(tmp_path)
    (tmp_path / "hashmarks.patch").write_bytes(b"different patch")
    with pytest.raises(ValueError, match="verdict subject_digest mismatch"):
        module.run_experiment(manifest, strict_raw_evidence=True)
