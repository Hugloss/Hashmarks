"""Native report acquisition binds observations from the current invocation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.repository_evaluation import run_backend_native as runner
from scripts.repository_evaluation.backend_native import NativeSpecimenOptions
from scripts.repository_evaluation.common import write_json


@pytest.fixture
def native_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    workflows = [
        {"id": name, "before": "old", "after": "new"} for name in ("one", "two")
    ]
    suite = {
        "workflows": workflows,
        "sources": {name: {"content_identity": name} for name in ("old", "new")},
    }
    monkeypatch.setattr(
        runner,
        "load_corpus",
        lambda *_: (suite, {"cases": {name: {} for name in ("one", "two")}}),
    )
    monkeypatch.setattr(runner, "_check_implementation", lambda _: None)
    monkeypatch.setattr(runner, "_observer_identity", lambda: "observer")
    monkeypatch.setattr(
        runner, "evaluator_implementation_identity", lambda: "evaluator"
    )
    captures = tmp_path / "captures"
    calls = []

    def acquire(
        workflow,
        _rule,
        stage,
        _source,
        _definition,
        destination,
        *,
        acquisition_id=None,
    ):
        calls.append((workflow["id"], stage))
        write_json(destination / "capture.json", {"id": workflow["id"], "stage": stage})

    def qualify(workflow, _rule, _sources, _definitions, output, _options):
        # Acquisition must finish before observation, and report digests must
        # be computed after the observer has written its output.
        for stage in ("before", "after"):
            assert (captures / workflow["id"] / stage / "capture.json").is_file()
            write_json(
                output / stage / "api.json", {"id": workflow["id"], "stage": stage}
            )
        return {"id": workflow["id"], "status": "INCOMPLETE", "gates": {"mcp": None}}

    monkeypatch.setattr(runner, "prepare_capture", acquire)
    monkeypatch.setattr(runner, "record_capture_acquisition", lambda *_: None)
    monkeypatch.setattr(runner, "qualify_native_workflow", qualify)
    monkeypatch.setattr(
        runner,
        "capture_artifact_digests",
        lambda root: {
            "capture.json": hashlib.sha256(
                (root / "capture.json").read_bytes()
            ).hexdigest()
        },
    )
    return captures, calls, acquire


@pytest.mark.parametrize(
    "fresh,selection", [(False, ["one"]), (False, None), (True, None)]
)
def test_runner_attaches_current_workflow_artifacts_after_observation(
    tmp_path, native_runner, fresh, selection
):
    captures, calls, acquire = native_runner
    if not fresh:
        for name in ("one", "two"):
            for stage in ("before", "after"):
                acquire({"id": name}, {}, stage, None, None, captures / name / stage)
        calls.clear()
    output = tmp_path / "reports"
    report = runner.run_native(
        sources={"old": tmp_path, "new": tmp_path},
        output=output,
        options=NativeSpecimenOptions(captures, (), fresh),
        workflow_ids=selection,
    )
    assert report["status"] == "INCOMPLETE"
    assert len(calls) == (4 if fresh else 0)
    for outcome in report["outcomes"]:
        name = outcome["id"]
        assert set(outcome["artifacts"]) == {"before/api.json", "after/api.json"}
        for relative, digest in outcome["artifacts"].items():
            artifact = output / name / relative
            assert json.loads(artifact.read_text())["id"] == name
            assert hashlib.sha256(artifact.read_bytes()).hexdigest() == digest
        assert json.loads((output / name / "report.json").read_text()) == outcome


@pytest.mark.parametrize(
    "overlap", ["same", "capture-inside", "report-inside", "existing"]
)
def test_runner_rejects_reused_or_overlapping_destinations_before_acquisition(
    tmp_path, native_runner, overlap
):
    captures, calls, _acquire = native_runner
    output = tmp_path / "reports"
    if overlap == "same":
        output = captures
    elif overlap == "capture-inside":
        captures = output / "one" / "captures"
    elif overlap == "report-inside":
        output = captures / "one" / "reports"
    else:
        (output / "one").mkdir(parents=True)
    with pytest.raises(ValueError, match="new output directory|separate destinations"):
        runner.run_native(
            sources={"old": tmp_path, "new": tmp_path},
            output=output,
            options=NativeSpecimenOptions(captures, (), True),
            workflow_ids=["one"],
        )
    assert calls == []


def test_fresh_preflight_checks_later_workflows_before_first_acquisition(
    tmp_path, native_runner
):
    captures, calls, _acquire = native_runner
    (captures / "two/after").mkdir(parents=True)
    with pytest.raises(
        ValueError, match="fresh backend captures require a new output directory"
    ):
        runner.run_native(
            sources={"old": tmp_path, "new": tmp_path},
            output=tmp_path / "reports",
            options=NativeSpecimenOptions(captures, (), True),
        )
    assert calls == []
