from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


_MODULE = __import__("scripts.agent_evaluation.metrics_agent_experiment_set", fromlist=["*"])


def _load():
    return _MODULE

def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _experiment(root: Path, number: int, *, repo: str | None = None, tasks: int = 1, task_policy: str = "sha256:policy-v1", model_config: str = "sha256:model-config") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    runs = []
    repo_id = repo or f"sha256:repo-{number}"
    for task_number in range(tasks):
        task_id = f"task-{number}-{task_number}"
        for mode, suffix, tokens in (("baseline", "b", 10000), ("hashmarks", "h", 6000)):
            run_id = f"run-{number}-{task_number}-{suffix}"
            raw_grader = root / f"{run_id}.grader.raw"
            raw_provider = root / f"{run_id}.provider.raw"
            subject = root / f"{run_id}.patch"
            raw_grader.write_bytes(f"grader:{run_id}".encode())
            raw_provider.write_bytes(f"provider:{run_id}:{tokens}".encode())
            subject.write_bytes(f"patch:{run_id}".encode())
            trace = root / f"{run_id}.trace.json"
            trace.write_text(json.dumps({
                "schema": "hashmarks.agent-trace.v2", "task_id": task_id, "task_revision": "task-v1",
                "repository_identity": repo_id, "mode": mode, "run_id": run_id,
                "model_identity": "model-x", "model_config_identity": model_config,
                "runner_identity": "runner:test", "model_input_tokens_source": "external-provider-usage-required", "events": [],
            }))
            verdict = root / f"{run_id}.verdict.json"
            verdict.write_text(json.dumps({
                "schema": "hashmarks.agent-verdict.v1", "task_id": task_id, "mode": mode, "run_id": run_id,
                "grader_identity": "grader:test:v1", "evidence_digest": _digest(raw_grader),
                "subject_digest": _digest(subject), "success": True, "patch_correct": True,
            }))
            usage = root / f"{run_id}.usage.json"
            usage.write_text(json.dumps({
                "schema": "hashmarks.agent-model-usage.v1", "task_id": task_id, "mode": mode, "run_id": run_id,
                "provider_identity": "provider:test:v1", "evidence_digest": _digest(raw_provider), "model_input_tokens": tokens,
            }))
            runs.append({
                "task_id": task_id, "task_revision": "task-v1", "repository_identity": repo_id,
                "mode": mode, "run_id": run_id, "trace": trace.name, "verdict": verdict.name,
                "usage": usage.name, "subject": subject.name, "grader_evidence": raw_grader.name,
                "provider_evidence": raw_provider.name,
            })
    manifest = root / "experiment.json"
    manifest.write_text(json.dumps({
        "schema": "hashmarks.agent-experiment.v1", "experiment_id": f"experiment-{number}",
        "model_identity": "model-x", "model_config_identity": model_config,
        "task_policy_identity": task_policy, "benchmark_protocol_identity": "sha256:protocol-v1",
        "runner_identity": "runner:test", "grader_identity": "grader:test:v1", "provider_identity": "provider:test:v1",
        "runs": runs,
    }))
    return manifest


def _set(tmp_path: Path, *, experiments: int = 2, tasks_each: int = 2) -> Path:
    entries = []
    for i in range(experiments):
        exp = _experiment(tmp_path / f"e{i}", i, tasks=tasks_each)
        entries.append({"manifest": str(exp.relative_to(tmp_path)), "manifest_sha256": _digest(exp)})
    path = tmp_path / "set.json"
    path.write_text(json.dumps({
        "schema": "hashmarks.agent-experiment-set.v2", "experiment_set_id": "set-1",
        "model_identity": "model-x", "model_config_identity": "sha256:model-config",
        "task_policy_identity": "sha256:policy-v1", "benchmark_protocol_identity": "sha256:protocol-v1",
        "runner_identity": "runner:test", "grader_identity": "grader:test:v1", "provider_identity": "provider:test:v1",
        "replication_policy": {"min_repeats_per_group": 2, "confidence": 0.95, "bootstrap_samples": 1000},
        "experiments": [dict(entry, replication_group=f"group-{i}") for i, entry in enumerate(entries)],
    }))
    return path


def test_set_aggregates_exact_tokens_but_does_not_overclaim_breadth(tmp_path: Path) -> None:
    module = _load()
    report = module.run_experiment_set(_set(tmp_path))
    assert report["summary"]["aggregate_model_input_token_reduction"] == 0.4
    assert report["summary"]["internal_controlled_claim_eligible"] is True
    assert report["summary"]["public_broad_claim_eligible"] is False
    assert report["summary"]["experiment_count"] == 2
    assert report["summary"]["repository_count"] == 2
    assert report["summary"]["unique_task_count"] == 4


def test_set_rejects_model_config_drift(tmp_path: Path) -> None:
    module = _load()
    set_path = _set(tmp_path, experiments=1)
    payload = json.loads(set_path.read_text())
    drift = _experiment(tmp_path / "drift", 9, model_config="sha256:other")
    payload["experiments"].append({"manifest": str(drift.relative_to(tmp_path)), "manifest_sha256": _digest(drift)})
    set_path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="model_config_identity mismatch"):
        module.run_experiment_set(set_path)


def test_set_rejects_task_policy_drift(tmp_path: Path) -> None:
    module = _load()
    set_path = _set(tmp_path, experiments=1)
    payload = json.loads(set_path.read_text())
    drift = _experiment(tmp_path / "drift", 9, task_policy="sha256:other-policy")
    payload["experiments"].append({"manifest": str(drift.relative_to(tmp_path)), "manifest_sha256": _digest(drift)})
    set_path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="task_policy_identity mismatch"):
        module.run_experiment_set(set_path)


def test_set_rejects_duplicate_experiment_id(tmp_path: Path) -> None:
    module = _load()
    set_path = _set(tmp_path, experiments=1)
    payload = json.loads(set_path.read_text())
    duplicate = _experiment(tmp_path / "duplicate", 0, repo="sha256:other-repo")
    payload["experiments"].append({"manifest": str(duplicate.relative_to(tmp_path)), "manifest_sha256": _digest(duplicate)})
    set_path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="duplicate experiment_id"):
        module.run_experiment_set(set_path)


def test_set_rejects_reused_task_identity_for_padding(tmp_path: Path) -> None:
    module = _load()
    first = _experiment(tmp_path / "e1", 1, repo="sha256:same")
    second = _experiment(tmp_path / "e2", 2, repo="sha256:same")
    payload = json.loads(second.read_text())
    for run in payload["runs"]:
        run["task_id"] = "task-1-0"
        trace_path = second.parent / run["trace"]
        trace = json.loads(trace_path.read_text())
        trace["task_id"] = "task-1-0"
        trace_path.write_text(json.dumps(trace))
        for field in ("verdict", "usage"):
            p = second.parent / run[field]
            record = json.loads(p.read_text())
            record["task_id"] = "task-1-0"
            p.write_text(json.dumps(record))
    second.write_text(json.dumps(payload))
    set_path = tmp_path / "set.json"
    set_path.write_text(json.dumps({
        "schema": "hashmarks.agent-experiment-set.v2", "experiment_set_id": "set-dup-task",
        "model_identity": "model-x", "model_config_identity": "sha256:model-config",
        "task_policy_identity": "sha256:policy-v1", "benchmark_protocol_identity": "sha256:protocol-v1",
        "runner_identity": "runner:test", "grader_identity": "grader:test:v1", "provider_identity": "provider:test:v1",
        "replication_policy": {"min_repeats_per_group": 2, "confidence": 0.95, "bootstrap_samples": 1000},
        "experiments": [
            {"manifest": str(first.relative_to(tmp_path)), "manifest_sha256": _digest(first), "replication_group": "group-a"},
            {"manifest": str(second.relative_to(tmp_path)), "manifest_sha256": _digest(second), "replication_group": "group-b"},
        ],
    }))
    with pytest.raises(ValueError, match="task identity reused"):
        module.run_experiment_set(set_path)


def test_set_binds_exact_experiment_manifest_bytes(tmp_path: Path) -> None:
    module = _load()
    set_path = _set(tmp_path, experiments=1)
    payload = json.loads(set_path.read_text())
    experiment_path = tmp_path / payload["experiments"][0]["manifest"]
    experiment = json.loads(experiment_path.read_text())
    experiment["runner_version"] = "mutated-after-set-created"
    experiment_path.write_text(json.dumps(experiment))
    with pytest.raises(ValueError, match="experiment manifest digest mismatch"):
        module.run_experiment_set(set_path)


def test_public_broad_claim_requires_fixed_breadth_floors(tmp_path: Path) -> None:
    module = _load()
    report = module.run_experiment_set(_set(tmp_path, experiments=3, tasks_each=10))
    assert report["summary"]["experiment_count"] == 3
    assert report["summary"]["repository_count"] == 3
    assert report["summary"]["unique_task_count"] == 30
    assert report["summary"]["public_broad_claim_eligible"] is True
    assert module.gate(report, require_public_broad_claim=True) == []


def _replicated_set(tmp_path: Path, *, repeats: int = 3) -> Path:
    entries = []
    for i in range(repeats):
        exp = _experiment(tmp_path / f"r{i}", i, repo=f"sha256:repo-repeat-{i}", tasks=1)
        entries.append({"manifest": str(exp.relative_to(tmp_path)), "manifest_sha256": _digest(exp), "replication_group": "same-controlled-condition"})
    path = tmp_path / "replicated-set.json"
    path.write_text(json.dumps({
        "schema": "hashmarks.agent-experiment-set.v2", "experiment_set_id": "replicated-set",
        "model_identity": "model-x", "model_config_identity": "sha256:model-config",
        "task_policy_identity": "sha256:policy-v1", "benchmark_protocol_identity": "sha256:protocol-v1",
        "runner_identity": "runner:test", "grader_identity": "grader:test:v1", "provider_identity": "provider:test:v1",
        "replication_policy": {"min_repeats_per_group": 3, "confidence": 0.95, "bootstrap_samples": 2000},
        "experiments": entries,
    }))
    return path


def test_v2_replication_reports_repeat_variance_and_descriptive_ci(tmp_path: Path) -> None:
    module = _load()
    report = module.run_experiment_set(_replicated_set(tmp_path))
    rep = report["summary"]["replication"]
    assert report["schema"] == "hashmarks.agent-experiment-set-report.v2"
    assert rep["statistical_claim_eligible"] is True
    assert rep["group_count"] == 1
    assert rep["groups"][0]["repeat_count"] == 3
    assert rep["descriptive_confidence_interval"]["scope"] == "exact-retained-experiments-only"
    assert rep["descriptive_confidence_interval"]["lower"] == pytest.approx(0.4)
    assert rep["descriptive_confidence_interval"]["upper"] == pytest.approx(0.4)


def test_v2_replication_requires_minimum_repeats(tmp_path: Path) -> None:
    module = _load()
    report = module.run_experiment_set(_replicated_set(tmp_path, repeats=2))
    assert report["summary"]["replication"]["statistical_claim_eligible"] is False


def test_v2_requires_explicit_replication_group(tmp_path: Path) -> None:
    module = _load()
    path = _replicated_set(tmp_path)
    payload = json.loads(path.read_text())
    del payload["experiments"][0]["replication_group"]
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="replication_group"):
        module.run_experiment_set(path)
