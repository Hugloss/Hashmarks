"""Runtime family admission, revision workflow, public transport and pure regrade."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest
from contract_assertions import assert_array, assert_object, assert_records

from hashmarks.digest import FILE_DOMAIN, hash_file
from hashmarks.test_shards import repository_content_identity
from scripts.repository_evaluation.backend_corpus import SCHEMA, load_corpus
from scripts.repository_evaluation.backend_regrading import (
    regrade_task_workflow,
    verify_task_summary,
)
from scripts.repository_evaluation.backend_runtime_witnesses import (
    freeze_runtime_oracles,
    runtime_frame_checks,
)
from scripts.repository_evaluation.capture_backend_failure import _repository_frames
from scripts.repository_evaluation.common import GRADER_SCHEMA, write_json
from scripts.repository_evaluation.run_backend import run_backend

Corpus = tuple[Path, dict[str, Path]]
Observed = tuple[Corpus, Path, dict[str, object]]


def _runtime_capture(
    source: Path, text: str, stage: str, identity: str
) -> tuple[dict[str, object], dict[str, object]]:
    namespace: dict[str, object] = {}
    exec(compile(text, str(source / "backend.py"), "exec"), namespace)
    frames: list[dict[str, object]] = []
    try:
        eval("handler()", namespace)
    except ZeroDivisionError as exc:
        frames, _ = _repository_frames(exc, source)
    capture: dict[str, object] = {
        "workflow": "handler",
        "stage": stage,
        "frames": frames,
        "source_identity": identity,
    }
    oracle = freeze_runtime_oracles(
        source, capture, repository="controlled-runtime", bundle_id="runtime:1"
    )
    oracle["checks"] = {
        variant: runtime_frame_checks(oracle, invalidated=variant == "invalidated")
        for variant in ("qualified", "invalidated")
    }
    return {"bundle_id": "runtime:1", "capture": capture}, oracle


@pytest.fixture(scope="module")
def runtime_corpus(tmp_path_factory: pytest.TempPathFactory) -> Corpus:
    base = tmp_path_factory.mktemp("runtime-corpus")
    sources: dict[str, Path] = {}
    definitions, labels, requests, oracles = {}, {}, {}, {}
    for stage, text in (
        ("before", "def handler():\n    return [1 / 0 for value in [1]]\n"),
        ("after", "def handler():\n    return 2\n"),
    ):
        source = base / stage
        source.mkdir()
        path = source / "backend.py"
        path.write_text(text)
        sources[stage] = source
        identity = repository_content_identity(source)
        definitions[stage] = {
            "repository": "controlled-runtime",
            "content_identity": identity,
        }
        labels[stage] = [
            {
                "path": "backend.py",
                "symbol": "handler",
                "start_line": 1,
                "end_line": 2,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        ]
        requests[stage], oracles[stage] = _runtime_capture(
            source, text, stage, identity
        )
    workflow = {
        "id": "handler",
        "repository": "controlled-runtime",
        "problem_id": "runtime-frames",
        "task": "Fix handler in backend.py",
        "before": "before",
        "after": "after",
        "changed_paths": ["backend.py"],
        "transitions": [
            {"kind": "modify", "before_path": "backend.py", "after_path": "backend.py"}
        ],
        "capabilities": [4],
        "runtime_observations": requests,
        "debug_frame_units": ["before:frame-0", "before:frame-1"],
        "metric_eligibility": {
            "debug_correspondence": {
                "eligible": True,
                "reason": "Controlled metric plumbing; no genuine-corpus breadth claim",
            }
        },
    }
    rule = {
        "expected_owner_path": "backend.py",
        "source_labels": labels,
        "runtime_oracles": oracles,
        "owner_oracle": {
            "scope": "file",
            "resolution": "unique",
            "candidates": [{"path": "backend.py"}],
        },
        "checks": [
            {
                "id": "owner",
                "pointer": "/ownership/owner/path",
                "predicate": "equals",
                "value": "backend.py",
            }
        ],
        "delta_checks": [
            {
                "id": "revision",
                "pointer": "/path_changes/0/revision",
                "predicate": "equals",
                "value": hash_file(
                    sources["after"] / "backend.py", domain=FILE_DOMAIN
                ).hash,
            }
        ],
    }
    suite = base / "suite.json"
    write_json(
        suite,
        {
            "schema": SCHEMA,
            "suite": "controlled-runtime",
            "sources": definitions,
            "grader_file": "grader.json",
            "workflows": [workflow],
        },
    )
    write_json(
        base / "grader.json", {"schema": GRADER_SCHEMA, "cases": {"handler": rule}}
    )
    return suite, sources


@pytest.fixture(scope="module")
def observed_runtime(
    runtime_corpus: Corpus, tmp_path_factory: pytest.TempPathFactory
) -> Observed:
    suite, sources = runtime_corpus
    output = tmp_path_factory.mktemp("observed-runtime")
    result = run_backend(sources=sources, suite_path=suite, output_dir=output)
    outcome = assert_object(assert_array(result["outcomes"])[0])
    return runtime_corpus, output / "handler/observations", outcome


@pytest.mark.host_mcp_sdk
def test_runtime_family_preserves_all_frames_and_uses_actual_public_transports(
    observed_runtime: Observed,
) -> None:
    _, root, outcome = observed_runtime
    runtime = assert_object(outcome["runtime_observations"])
    before = assert_object(runtime["before"])
    assert all(value is True for value in assert_object(before["gates"]).values())
    frames = assert_records(outcome["debug_frame_observations"])
    assert frames == [
        {
            "unit_id": "before:frame-0",
            "correspondence": True,
            "declaration_state": "exact",
        },
        {
            "unit_id": "before:frame-1",
            "correspondence": False,
            "declaration_state": "unsupported",
        },
    ]
    witnesses = assert_records(before["gate_witnesses"])
    assert {row["surface"] for row in witnesses} == {"api", "cli", "mcp"}
    assert all(row["state"] == "PASS" for row in witnesses)
    assert all(str(row["artifact"]).startswith("before/runtime/") for row in witnesses)
    assert assert_object(runtime["after"])["debug_frame_observations"] == []
    assert (root / "after/runtime/capture.json").is_file()


@pytest.mark.host_mcp_sdk
def test_runtime_regrading_never_launches_observer_or_external_capture(
    observed_runtime: Observed, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.repository_evaluation import backend_runtime

    (suite, sources), root, outcome = observed_runtime
    workflow = assert_object(
        assert_array(assert_object(json.loads(suite.read_bytes()))["workflows"])[0]
    )
    rule = assert_object(
        assert_object(json.loads((suite.parent / "grader.json").read_bytes()))["cases"]
    )["handler"]

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("retained-byte regrading launched a producer")

    for name in ("CodeMap", "capture_cli", "capture_mcp"):
        monkeypatch.setattr(backend_runtime, name, forbidden)
    verify_task_summary(root, workflow, assert_object(rule), sources, outcome)


@pytest.mark.host_mcp_sdk
@pytest.mark.parametrize("artifact", ["capture", "request", "api"])
def test_runtime_regrade_rejects_changed_artifact_bytes(
    observed_runtime: Observed, tmp_path: Path, artifact: str
) -> None:
    (suite, sources), original, outcome = observed_runtime
    root = tmp_path / "observations"
    shutil.copytree(original, root)
    relative = (
        "runtime/capture.json"
        if artifact == "capture"
        else f"runtime/qualified/{artifact}.json"
    )
    path = root / "before" / relative
    changed = assert_object(json.loads(path.read_bytes()))
    changed["tampered"] = True
    write_json(path, changed)
    workflow = assert_object(
        assert_array(assert_object(json.loads(suite.read_bytes()))["workflows"])[0]
    )
    rule = assert_object(
        assert_object(
            assert_object(json.loads((suite.parent / "grader.json").read_bytes()))[
                "cases"
            ]
        )["handler"]
    )
    with pytest.raises(ValueError, match="differs|differ"):
        verify_task_summary(root, workflow, rule, sources, outcome)


@pytest.mark.parametrize(
    "change", ["membership", "oracle", "capture", "execution", "stage"]
)
def test_runtime_source_admission_rejects_unproved_or_omitted_units(
    runtime_corpus: Corpus, tmp_path: Path, change: str
) -> None:
    suite_path, sources = runtime_corpus
    suite = assert_object(json.loads(suite_path.read_bytes()))
    grader = assert_object(json.loads((suite_path.parent / "grader.json").read_bytes()))
    workflow = assert_object(assert_array(suite["workflows"])[0])
    rule = assert_object(assert_object(grader["cases"])["handler"])
    if change == "membership":
        workflow["debug_frame_units"] = ["before:frame-0"]
    elif change == "oracle":
        assert_array(
            assert_object(assert_object(rule["runtime_oracles"])["before"])["frames"]
        ).pop()
    elif change == "capture":
        assert_object(
            assert_object(assert_object(workflow["runtime_observations"])["before"])[
                "capture"
            ]
        )["source_identity"] = "wrong"
    elif change == "execution":
        assert_object(assert_object(workflow["runtime_observations"])["before"])[
            "argv"
        ] = ["echo"]
    else:
        assert_object(workflow["runtime_observations"]).pop("after")
    write_json(tmp_path / "suite.json", suite)
    write_json(tmp_path / "grader.json", grader)
    with pytest.raises(ValueError, match="runtime|source archive|debug frame"):
        load_corpus(tmp_path / "suite.json", sources)


@pytest.mark.host_mcp_sdk
def test_missing_runtime_transport_remains_incomplete_in_retained_regrade(
    observed_runtime: Observed, tmp_path: Path
) -> None:
    (suite, sources), original, _ = observed_runtime
    root = tmp_path / "observations"
    shutil.copytree(original, root)
    write_json(root / "before/runtime/qualified/mcp.json", [])
    workflow = assert_object(
        assert_array(assert_object(json.loads(suite.read_bytes()))["workflows"])[0]
    )
    rule = assert_object(
        assert_object(
            assert_object(json.loads((suite.parent / "grader.json").read_bytes()))[
                "cases"
            ]
        )["handler"]
    )
    observed = regrade_task_workflow(root, workflow, rule, sources)
    before = assert_object(assert_object(observed["runtime_observations"])["before"])
    assert assert_object(before["gates"])["mcp"] is None
    assert all(
        row["correspondence"] is None
        for row in assert_records(before["debug_frame_observations"])
    )
