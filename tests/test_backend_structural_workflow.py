"""Selected static segments retain source, transport and pure replay proof."""

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
from scripts.repository_evaluation import backend_structural
from scripts.repository_evaluation.backend_corpus import SCHEMA, load_corpus
from scripts.repository_evaluation.backend_regrading import (
    regrade_task_workflow,
    verify_task_summary,
)
from scripts.repository_evaluation.common import GRADER_SCHEMA, write_json
from scripts.repository_evaluation.run_backend import run_backend

Corpus = tuple[Path, dict[str, Path]]
Observation = tuple[Corpus, Path, dict[str, object]]


def _source_label(path: Path, name: str, start: int, end: int) -> dict[str, object]:
    return {
        "path": "backend.py",
        "symbol": name,
        "start_line": start,
        "end_line": end,
        "sha256": hashlib.sha256(
            b"".join(path.read_bytes().splitlines(True)[start - 1 : end])
        ).hexdigest(),
    }


@pytest.fixture(scope="module")
def structural_corpus(tmp_path_factory: pytest.TempPathFactory) -> Corpus:
    base = tmp_path_factory.mktemp("structural-corpus")
    sources, definitions, labels, oracles = {}, {}, {}, {}
    direct = {
        "source_symbol_id": "backend.py::handler",
        "path": "backend.py",
        "line": 7,
        "target_text": "leaf",
        "resolved_symbol_id": "backend.py::leaf",
    }
    dynamic = {
        "source_symbol_id": "backend.py::handler",
        "path": "backend.py",
        "line": 8,
        "target_text": "receiver.deliver",
        "resolved_symbol_id": None,
    }
    checks = [
        {
            "id": name,
            "pointer": "/edges/*",
            "predicate": "includes_record",
            "value": value,
            "support": "supported",
            "authority_check": name == "dynamic",
        }
        for name, value in (("direct", direct), ("dynamic", dynamic))
    ]
    for stage, value in (("before", 1), ("after", 2)):
        root = base / stage
        root.mkdir()
        path = root / "backend.py"
        path.write_text(
            'raise RuntimeError("source must not execute")\n'
            f"def leaf():\n    return {value}\n"
            "def handler(receiver):\n    def callback():\n        return leaf()\n"
            "    leaf()\n    return receiver.deliver()\n"
        )
        sources[stage] = root
        definitions[stage] = {
            "repository": "controlled-static",
            "content_identity": repository_content_identity(root),
        }
        labels[stage] = [
            _source_label(path, "handler", 4, 8),
            _source_label(path, "leaf", 2, 3),
        ]
        oracles[stage] = {
            "source": stage,
            "source_labels": labels[stage],
            "checks": checks,
            "display_checks": {
                mode: [
                    {**check, "pointer": "/groups/*/findings/*/details/*"}
                    for check in checks
                ]
                for mode in ("structured", "compact", "text")
            },
        }
    workflow = {
        "id": "handler",
        "repository": "controlled-static",
        "problem_id": "controlled-source-only",
        "task": "Fix handler in backend.py",
        "before": "before",
        "after": "after",
        "capabilities": [2],
        "changed_paths": ["backend.py"],
        "transitions": [
            {"kind": "modify", "before_path": "backend.py", "after_path": "backend.py"}
        ],
        "structural_observations": {
            stage: {"target": "backend.py::handler"} for stage in sources
        },
    }
    rule = {
        "source_labels": labels,
        "structural_oracles": oracles,
        "expected_owner_path": "backend.py",
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
                "id": "current",
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
            "suite": "controlled-structural",
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
def observed_structural(
    structural_corpus: Corpus, tmp_path_factory: pytest.TempPathFactory
) -> Observation:
    suite, sources = structural_corpus
    output = tmp_path_factory.mktemp("observed-structural")
    report = run_backend(sources=sources, suite_path=suite, output_dir=output)
    return (
        structural_corpus,
        output / "handler/observations",
        assert_object(assert_array(report["outcomes"])[0]),
    )


def _admitted(corpus: Corpus) -> tuple[dict[str, object], dict[str, object]]:
    path, sources = corpus
    suite, grader = load_corpus(path, sources)
    return assert_object(assert_array(suite["workflows"])[0]), assert_object(
        assert_object(grader["cases"])["handler"]
    )


@pytest.mark.host_mcp_sdk
def test_structural_family_retains_native_and_display_witnesses(
    observed_structural: Observation,
) -> None:
    _, _, outcome = observed_structural
    components = assert_object(outcome["structural_observations"])
    for stage in ("before", "after"):
        component = assert_object(components[stage])
        assert all(
            value is True for value in assert_object(component["gates"]).values()
        )
    rows = [
        row
        for row in assert_records(outcome["gate_witnesses"])
        if str(row["gate"]).startswith("structural_")
    ]
    assert len(rows) == 60
    assert all(row["state"] == "PASS" and row["artifact_sha256"] for row in rows)
    assert {row["surface"] for row in rows} == {"api", "cli", "mcp"}
    assert {row["gate"] for row in rows} == {
        "structural_facts",
        "structural_presentation",
    }


@pytest.mark.host_mcp_sdk
def test_structural_summary_regrades_without_observation(
    observed_structural: Observation, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus, root, outcome = observed_structural
    workflow, rule = _admitted(corpus)

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("pure structural replay launched an observer")

    for name in ("CodeMap", "capture_cli", "capture_mcp"):
        monkeypatch.setattr(backend_structural, name, forbidden)
    verify_task_summary(root, workflow, rule, corpus[1], outcome)


@pytest.mark.host_mcp_sdk
def test_structural_tamper_cannot_reuse_passing_summary(
    observed_structural: Observation, tmp_path: Path
) -> None:
    corpus, original, outcome = observed_structural
    root = tmp_path / "observations"
    shutil.copytree(original, root)
    path = root / "before/structural/api.json"
    packet = assert_object(json.loads(path.read_bytes()))
    assert_records(packet["edges"])[0]["resolved_symbol_id"] = (
        "backend.py::handler.callback"
    )
    write_json(path, packet)
    workflow, rule = _admitted(corpus)
    with pytest.raises(ValueError, match="differ"):
        verify_task_summary(root, workflow, rule, corpus[1], outcome)


@pytest.mark.host_mcp_sdk
def test_structural_missing_transport_is_incomplete(
    observed_structural: Observation, tmp_path: Path
) -> None:
    corpus, original, _ = observed_structural
    root = tmp_path / "observations"
    shutil.copytree(original, root)
    write_json(root / "after/structural/mcp.json", [])
    workflow, rule = _admitted(corpus)
    graded = regrade_task_workflow(root, workflow, rule, corpus[1])
    assert assert_object(graded["gates"])["mcp"] is None


@pytest.mark.parametrize(
    "change", ["target", "source", "stage", "execution", "labels", "display"]
)
def test_structural_admission_rejects_wrong_scope(
    structural_corpus: Corpus, tmp_path: Path, change: str
) -> None:
    suite, sources = structural_corpus
    manifest = assert_object(json.loads(suite.read_bytes()))
    grader = assert_object(json.loads((suite.parent / "grader.json").read_bytes()))
    workflow = assert_object(assert_array(manifest["workflows"])[0])
    requests = assert_object(workflow["structural_observations"])
    rule = assert_object(assert_object(grader["cases"])["handler"])
    oracle = assert_object(assert_object(rule["structural_oracles"])["before"])
    if change == "target":
        assert_object(requests["before"])["target"] = "backend.py::leaf"
    elif change == "source":
        oracle["source"] = "after"
    elif change == "stage":
        requests.pop("after")
    elif change == "execution":
        assert_object(requests["before"])["argv"] = ["python", "backend.py"]
    elif change == "labels":
        assert_records(oracle["source_labels"])[0]["sha256"] = "wrong"
    else:
        assert_object(oracle["display_checks"]).pop("compact")
    write_json(tmp_path / "suite.json", manifest)
    write_json(tmp_path / "grader.json", grader)
    with pytest.raises(ValueError, match="structural|source range"):
        load_corpus(tmp_path / "suite.json", copy.copy(sources))
