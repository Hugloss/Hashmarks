"""Behavior of source admission, revision workflows and durable observations."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from hashmarks.digest import FILE_DOMAIN, hash_file
from hashmarks.test_shards import repository_content_identity
from scripts.repository_evaluation.backend_corpus import SCHEMA, load_corpus
from scripts.repository_evaluation.common import GRADER_SCHEMA, write_json
from scripts.repository_evaluation.run_backend import run_backend


@pytest.fixture
def corpus(tmp_path: Path):
    sources = {}
    definitions = {}
    labels = {}
    for stage, value in (("before", 1), ("after", 2)):
        root = tmp_path / stage
        root.mkdir()
        path = root / "backend.py"
        path.write_text(f"def handler():\n    return {value}\n")
        sources[stage] = root
        definitions[stage] = {
            "repository": "controlled-fixture",
            "content_identity": repository_content_identity(root),
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
    workflow = {
        "id": "handler",
        "repository": "controlled-fixture",
        "problem_id": "return-value",
        "task": "Change handler in backend.py",
        "before": "before",
        "after": "after",
        "changed_paths": ["backend.py"],
        "capabilities": [1, 6, 7, 17],
    }
    rule = {
        "expected_owner_path": "backend.py",
        "source_labels": labels,
        "checks": [
            {
                "id": "source-owner",
                "pointer": "/ownership/owner/path",
                "predicate": "equals",
                "value": "backend.py",
            }
        ],
        "delta_checks": [
            {
                "id": "new-revision",
                "pointer": "/path_changes/0/revision",
                "predicate": "equals",
                "value": hash_file(
                    sources["after"] / "backend.py", domain=FILE_DOMAIN
                ).hash,
                "authority_check": True,
            }
        ],
    }
    suite_path = tmp_path / "suite.json"
    write_json(
        suite_path,
        {
            "schema": SCHEMA,
            "suite": "controlled-workflow",
            "sources": definitions,
            "workflows": [workflow],
            "grader_file": "grader.json",
        },
    )
    write_json(
        tmp_path / "grader.json", {"schema": GRADER_SCHEMA, "cases": {"handler": rule}}
    )
    return suite_path, sources


def test_api_revision_workflow_cannot_qualify_missing_transports_or_breadth(
    corpus, tmp_path: Path
):
    suite_path, sources = corpus
    report = run_backend(
        sources=sources,
        suite_path=suite_path,
        output_dir=tmp_path / "output",
        transports=(),
    )
    outcome = report["outcomes"][0]
    assert outcome["gates"]["facts"] is True
    assert outcome["gates"]["authority"] is True
    assert outcome["gates"]["revision"] is True
    assert outcome["gates"]["freshness"] is True
    assert outcome["gates"]["cli"] is None
    assert outcome["gates"]["mcp"] is None
    assert report["status"] == "INCOMPLETE"
    assert all(row["local_e2e_rating"] is None for row in report["capabilities"])


def test_exact_workflow_receipt_reuses_then_rejects_changed_observation(
    corpus, tmp_path: Path
):
    suite_path, sources = corpus
    options: dict[str, Any] = {
        "sources": sources,
        "suite_path": suite_path,
        "output_dir": tmp_path / "output",
        "transports": (),
    }
    first = run_backend(**options)
    second = run_backend(**options)
    assert first["outcomes"][0]["receipt_reused"] is False
    assert second["outcomes"][0]["receipt_reused"] is True
    capture = tmp_path / "output/handler/observations/before/api.json"
    packet = json.loads(capture.read_text())
    packet["ownership"]["status"] = "fabricated"
    write_json(capture, packet)
    with pytest.raises(ValueError, match="observation integrity"):
        run_backend(**options)


def test_changed_archive_and_oracle_ranges_fail_before_observation(corpus):
    suite_path, sources = corpus
    path = sources["before"] / "backend.py"
    original = path.read_bytes()
    path.write_bytes(original + b"# changed archive\n")
    with pytest.raises(ValueError, match="source identity"):
        load_corpus(suite_path, sources)
    path.write_bytes(original)
    grader_path = suite_path.parent / "grader.json"
    grader = json.loads(grader_path.read_text())
    grader["cases"]["handler"]["source_labels"]["before"][0]["sha256"] = "0" * 64
    write_json(grader_path, grader)
    with pytest.raises(ValueError, match="source range changed"):
        load_corpus(suite_path, sources)


def test_invalid_workflow_selection_is_not_an_empty_success(corpus, tmp_path: Path):
    suite_path, sources = corpus
    for selected in ([], ["missing"], ["handler", "handler"]):
        with pytest.raises(ValueError, match="selection"):
            run_backend(
                sources=sources,
                suite_path=suite_path,
                output_dir=tmp_path / "output",
                workflow_ids=selected,
                transports=(),
            )


def test_transport_source_mutation_invalidates_the_observation(
    corpus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.repository_evaluation import backend_workflows

    suite_path, sources = corpus

    def changing_transport(workspace: Path, *_args):
        (workspace / "backend.py").write_text("def handler():\n    return 999\n")
        return []

    monkeypatch.setattr(backend_workflows, "capture_cli", changing_transport)
    with pytest.raises(ValueError, match="source changed.*snapshot"):
        run_backend(
            sources=sources,
            suite_path=suite_path,
            output_dir=tmp_path / "output",
            transports=("cli",),
        )
    assert not (tmp_path / "output/summary.json").exists()


def _add_boundary_observations(suite_path: Path, sources: dict[str, Path]) -> None:
    suite = json.loads(suite_path.read_text())
    grader_path = suite_path.parent / "grader.json"
    grader = json.loads(grader_path.read_text())
    workflow = suite["workflows"][0]
    rule = grader["cases"]["handler"]
    span = {"path": "backend.py", "start_line": 2, "end_line": 2}
    workflow["boundary_observations"] = {}
    rule["function_boundary_oracles"] = {}
    for stage in ("before", "after"):
        workflow["boundary_observations"][stage] = {
            "task": "Inspect caller-reported source lines",
            "changed_paths": ["backend.py"],
            "changed_line_spans": [span],
            "max_depth": 1,
        }
        rule["function_boundary_oracles"][stage] = {
            "source": stage,
            "source_label": rule["source_labels"][stage][0],
            "reported_span": span,
            "literal_source_line_sha256": hashlib.sha256(
                (sources[stage] / "backend.py")
                .read_bytes()
                .splitlines(keepends=True)[1]
            ).hexdigest(),
            "checks": [
                {
                    "id": "direct-authority",
                    "pointer": "/changed_line_evidence/observations/0/function_boundary_syntax/authority",
                    "predicate": "equals",
                    "value": "direct-static-syntax-only",
                    "authority_check": True,
                },
                {
                    "id": "declaration",
                    "pointer": "/changed_line_evidence/observations/0/function_boundary_syntax/observations/*",
                    "predicate": "includes_record",
                    "value": {
                        "subject": "backend.py::handler",
                        "declaration_syntax": "sync",
                    },
                },
            ],
        }
    write_json(suite_path, suite)
    write_json(grader_path, grader)


def test_boundary_revision_observations_preserve_actual_cli_facts_and_missing_mcp(
    corpus, tmp_path: Path
) -> None:
    suite_path, sources = corpus
    _add_boundary_observations(suite_path, sources)
    report = run_backend(
        sources=sources,
        suite_path=suite_path,
        output_dir=tmp_path / "output",
        transports=("cli",),
    )
    outcome = report["outcomes"][0]
    assert outcome["gates"]["facts"] is True
    assert outcome["gates"]["freshness"] is True
    assert outcome["gates"]["mcp"] is None
    for stage in ("before", "after"):
        boundary = outcome["boundary_observations"][stage]
        assert boundary["gates"] == {
            "facts": True,
            "authority": True,
            "revision": True,
            "cli": True,
            "mcp": None,
        }
        assert len(boundary["cli"]["grades"]) == 4
    assert outcome["gates"]["initial_evidence"] is False
    assert report["status"] == "FAIL"
    assert all(row["local_e2e_rating"] is None for row in report["capabilities"])


def test_boundary_failed_fact_cannot_be_compensated_by_task_or_revision_success(
    corpus, tmp_path: Path
) -> None:
    suite_path, sources = corpus
    _add_boundary_observations(suite_path, sources)
    grader_path = suite_path.parent / "grader.json"
    grader = json.loads(grader_path.read_text())
    grader["cases"]["handler"]["function_boundary_oracles"]["after"]["checks"][1][
        "value"
    ]["declaration_syntax"] = "async"
    write_json(grader_path, grader)
    report = run_backend(
        sources=sources,
        suite_path=suite_path,
        output_dir=tmp_path / "output",
        transports=(),
    )
    outcome = report["outcomes"][0]
    assert outcome["before"]["classification"] == "PASS"
    assert outcome["after"]["classification"] == "PASS"
    assert outcome["gates"]["revision"] is True
    assert outcome["gates"]["facts"] is False
    assert report["status"] == "FAIL"


@pytest.mark.parametrize("mutation", ["missing-stage", "line-hash", "scope"])
def test_boundary_source_admission_rejects_incomplete_or_unbound_oracles(
    corpus, mutation: str
) -> None:
    suite_path, sources = corpus
    _add_boundary_observations(suite_path, sources)
    grader_path = suite_path.parent / "grader.json"
    grader = json.loads(grader_path.read_text())
    oracles = grader["cases"]["handler"]["function_boundary_oracles"]
    if mutation == "missing-stage":
        del oracles["after"]
    elif mutation == "line-hash":
        oracles["after"]["literal_source_line_sha256"] = "0" * 64
    else:
        oracles["after"]["source"] = "before"
    write_json(grader_path, grader)
    with pytest.raises(ValueError, match="backend boundary"):
        load_corpus(suite_path, sources)


def test_existing_verifier_oracle_cannot_name_a_test_absent_at_that_revision(
    corpus,
) -> None:
    suite_path, sources = corpus
    grader_path = suite_path.parent / "grader.json"
    grader = json.loads(grader_path.read_text())
    grader["cases"]["handler"]["checks"].append(
        {
            "id": "existing-verifier-visible",
            "pointer": "/verification/relevance/candidates/*/path",
            "predicate": "includes",
            "value": "tests/not_yet_introduced.py",
        }
    )
    write_json(grader_path, grader)
    with pytest.raises(ValueError, match="not a repository file"):
        load_corpus(suite_path, sources)


def _add_declaration_observations(suite_path: Path, sources: dict[str, Path]) -> None:
    suite = json.loads(suite_path.read_text())
    grader_path = suite_path.parent / "grader.json"
    grader = json.loads(grader_path.read_text())
    workflow = suite["workflows"][0]
    rule = grader["cases"]["handler"]
    workflow["declaration_observations"] = {}
    rule["declaration_oracles"] = {}
    for stage in ("before", "after"):
        path = sources[stage] / "backend.py"
        source = path.read_bytes() + b"class Payload(BaseModel):\n    value: int\n"
        path.write_bytes(source)
        suite["sources"][stage]["content_identity"] = repository_content_identity(
            sources[stage]
        )
        workflow["declaration_observations"][stage] = {
            "groups": [],
            "result_mode": "discovery",
            "python_backend_paths": ["backend.py"],
            "include_class_fields": False,
        }
        rule["declaration_oracles"][stage] = {
            "source": stage,
            "source_labels": [
                {
                    "path": "backend.py",
                    "start_line": 3,
                    "end_line": 4,
                    "sha256": hashlib.sha256(
                        b"".join(source.splitlines(keepends=True)[2:4])
                    ).hexdigest(),
                }
            ],
            "checks": [
                {
                    "id": "direct-field",
                    "pointer": "/declarations/groups/*",
                    "predicate": "includes_scoped_record",
                    "value": {
                        "scope": {
                            "scope": {
                                "path": "backend.py",
                                "class_name_syntax": "Payload",
                                "class_line": 3,
                            }
                        },
                        "pointer": "/declarations/0/value/fields/*",
                        "record": {
                            "name": "value",
                            "line": 4,
                            "runtime_validation": "not-established",
                        },
                    },
                },
                {
                    "id": "runtime-unknown",
                    "pointer": "/declarations/groups/*/declarations/*/value/runtime_binding",
                    "predicate": "all_equal",
                    "value": "not-established",
                    "authority_check": True,
                },
            ],
        }
    rule["delta_checks"][0]["value"] = hash_file(
        sources["after"] / "backend.py", domain=FILE_DOMAIN
    ).hash
    write_json(suite_path, suite)
    write_json(grader_path, grader)


def test_declaration_workflow_preserves_real_cli_facts_and_missing_mcp(
    corpus, tmp_path: Path
) -> None:
    suite_path, sources = corpus
    _add_declaration_observations(suite_path, sources)
    report = run_backend(
        sources=sources,
        suite_path=suite_path,
        output_dir=tmp_path / "result",
        transports=("cli",),
    )
    outcome = report["outcomes"][0]
    for stage in ("before", "after"):
        observation = outcome["declaration_observations"][stage]
        assert observation["gates"] == {
            "facts": True,
            "authority": True,
            "revision": True,
            "cli": True,
            "mcp": None,
        }
        assert len(observation["cli"]["grades"]) == 4
    assert outcome["gates"]["mcp"] is None
    assert outcome["gates"]["freshness"] is True
    assert outcome["gates"]["facts"] is True


def test_failed_declaration_fact_cannot_be_masked_by_successful_task(
    corpus, tmp_path: Path
) -> None:
    suite_path, sources = corpus
    _add_declaration_observations(suite_path, sources)
    path = suite_path.parent / "grader.json"
    grader = json.loads(path.read_text())
    grader["cases"]["handler"]["declaration_oracles"]["after"]["checks"][0]["value"][
        "record"
    ]["name"] = "unrelated"
    write_json(path, grader)
    report = run_backend(
        sources=sources,
        suite_path=suite_path,
        output_dir=tmp_path / "result",
        transports=(),
    )
    outcome = report["outcomes"][0]
    assert outcome["gates"]["freshness"] is True
    assert outcome["gates"]["revision"] is True
    assert outcome["gates"]["facts"] is False
    assert outcome["declaration_observations"]["after"]["gates"]["facts"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-stage",
        "empty-checks",
        "duplicate-checks",
        "unlabeled-path",
        "wrong-source",
    ],
)
def test_declaration_admission_requires_complete_source_oracles(
    corpus, mutation: str
) -> None:
    suite_path, sources = corpus
    _add_declaration_observations(suite_path, sources)
    suite = json.loads(suite_path.read_text())
    path = suite_path.parent / "grader.json"
    grader = json.loads(path.read_text())
    oracle = grader["cases"]["handler"]["declaration_oracles"]
    if mutation == "missing-stage":
        del oracle["after"]
    elif mutation == "empty-checks":
        oracle["after"]["checks"] = []
    elif mutation == "duplicate-checks":
        oracle["after"]["checks"].append(oracle["after"]["checks"][0].copy())
    elif mutation == "unlabeled-path":
        suite["workflows"][0]["declaration_observations"]["after"][
            "python_backend_paths"
        ].append("unlabeled.py")
    else:
        oracle["after"]["source"] = "before"
    write_json(suite_path, suite)
    write_json(path, grader)
    with pytest.raises(ValueError, match="backend declaration"):
        load_corpus(suite_path, sources)
