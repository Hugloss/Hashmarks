"""Behavior of source admission, revision workflows and durable observations."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from contract_assertions import assert_object

from hashmarks.digest import FILE_DOMAIN, hash_file
from hashmarks.test_shards import repository_content_identity
from scripts.repository_evaluation.backend_corpus import SCHEMA, load_corpus
from scripts.repository_evaluation.common import GRADER_SCHEMA, write_json
from scripts.repository_evaluation.run_backend import run_backend


@pytest.fixture
def corpus(tmp_path: Path) -> tuple[Path, dict[str, Path]]:
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
        "transitions": [
            {"kind": "modify", "before_path": "backend.py", "after_path": "backend.py"}
        ],
        "capabilities": [1, 6, 7, 17],
    }
    rule = {
        "expected_owner_path": "backend.py",
        "owner_oracle": {
            "scope": "file",
            "resolution": "unique",
            "candidates": [{"path": "backend.py"}],
        },
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


def test_initial_size_grades_complete_visible_bytes_at_the_user_approved_boundary(
    corpus: tuple[Path, dict[str, Path]],
) -> None:
    from hashmarks.codemap import CodeMap
    from hashmarks.codemap.python_ast import estimate_tokens
    from hashmarks.evidence_presentation import presentation_response
    from scripts.repository_evaluation.backend_grading import validate_transport_capture
    from scripts.repository_evaluation.backend_workflows import _transport_grade
    from scripts.repository_evaluation.common import canonical_sha256

    suite_path, sources = corpus
    rule = json.loads(suite_path.with_name("grader.json").read_text())["cases"][
        "handler"
    ]
    with CodeMap(sources["before"]) as repository:
        repository.index.sync()
        full = repository.tasks.evidence("Change handler in backend.py")
        initial = repository.tasks.evidence(
            "Change handler in backend.py", result_mode="initial"
        )
    response = presentation_response(
        "task_evidence", initial, result_mode="initial", format="compact"
    )
    encoded = json.dumps(response)
    for tokens, expected in ((5999, True), (6000, True), (6001, False)):
        visible = encoded + " " * (tokens * 4 - len(encoded.encode("utf-8")))
        capture = {
            "transport": "cli",
            "format": "compact",
            "response": response,
            "consumer_visible_response": visible,
            "utf8_bytes": len(visible.encode("utf-8")),
            "estimated_tokens": estimate_tokens(visible),
            "capture_identity": "sha256:"
            + canonical_sha256({"transport": "cli", "text": visible}),
        }
        validate_transport_capture(capture)
        result = _transport_grade(
            [capture],
            rule,
            sources["before"],
            initial=True,
            source_identity=full["evidence_packet_identity"],
        )
        assert result["grades"][0]["initial_size"] is expected
        assert result["grades"][0]["parity"] is True


def test_api_revision_workflow_cannot_qualify_missing_transports_or_breadth(
    corpus: tuple[Path, dict[str, Path]], tmp_path: Path
) -> None:
    suite_path, sources = corpus
    report = run_backend(
        sources=sources,
        suite_path=suite_path,
        output_dir=tmp_path / "output",
        transports=(),
    )
    outcome = report["outcomes"][0]
    assert outcome["gates"]["facts"] is True
    assert outcome["gates"]["authority"] is None
    assert outcome["gates"]["revision"] is None
    assert outcome["gates"]["freshness"] is True
    assert outcome["gates"]["cli"] is None
    assert outcome["gates"]["mcp"] is None
    comparison = next(
        row for row in outcome["gate_witnesses"] if row["gate"] == "delta"
    )
    assert comparison["state"] == "PASS"
    assert {
        (row["stage"], row["revision"]) for row in comparison["source_bindings"]
    } == {
        (stage, hash_file(sources[stage] / "backend.py", domain=FILE_DOMAIN).hash)
        for stage in ("before", "after")
    }
    assert report["status"] == "INCOMPLETE"
    assert all(row["local_e2e_rating"] is None for row in report["capabilities"])


def test_authority_and_freshness_witnesses_are_regraded_from_actual_artifacts(
    corpus: tuple[Path, dict[str, Path]], tmp_path: Path
) -> None:
    from scripts.repository_evaluation.backend_regrading import verify_task_summary
    from scripts.repository_evaluation.backend_witnesses import freshness_fact_witnesses

    suite_path, sources = corpus
    grader_path = suite_path.parent / "grader.json"
    grader = json.loads(grader_path.read_text())
    rule = grader["cases"]["handler"]
    rule["authority_checks"] = [
        {
            "id": "owner-correspondence",
            "pointer": "/ownership/owner/path",
            "predicate": "equals",
            "value": "backend.py",
            "source_paths": ["backend.py"],
        }
    ]
    rule["freshness_checks"] = [
        {
            "id": "stale-cannot-negate",
            "pointer": "/observations/*/negative_evidence",
            "predicate": "all_equal",
            "value": "not-admissible",
            "source_paths": ["backend.py"],
        }
    ]
    write_json(grader_path, grader)
    report = run_backend(
        sources=sources,
        suite_path=suite_path,
        output_dir=tmp_path / "output",
        transports=(),
    )
    outcome = report["outcomes"][0]
    root = tmp_path / "output/handler/observations"
    workflow = json.loads(suite_path.read_text())["workflows"][0]
    authority = [w for w in outcome["gate_witnesses"] if w["gate"] == "authority"]
    assert {(w["stage"], w["profile"]) for w in authority} == {
        (stage, profile)
        for stage in ("before", "after")
        for profile in ("default", "initial")
    }
    assert all(w["state"] == "PASS" for w in authority)
    witness = next(w for w in outcome["gate_witnesses"] if w["gate"] == "freshness")
    assert witness["state"] == "PASS"
    assert {b["stage"] for b in witness["source_bindings"]} == {"before", "after"}
    assert outcome["gates"]["freshness"] is True
    verify_task_summary(root, workflow, rule, sources, outcome)
    stale = json.loads((root / "stale.json").read_text())
    stale["observations"][0]["negative_evidence"] = "admissible"
    write_json(root / "stale.json", stale)
    assert freshness_fact_witnesses(sources, root, workflow, rule)[0]["state"] == "FAIL"
    with pytest.raises(ValueError, match="witnesses differ"):
        verify_task_summary(root, workflow, rule, sources, outcome)
    (root / "stale.json").unlink()
    with pytest.raises(ValueError, match="not a repository file"):
        freshness_fact_witnesses(sources, root, workflow, rule)


def _aggregate_campaign(corpus: tuple[Path, dict[str, Path]], root: Path) -> Path:
    from scripts.repository_evaluation.aggregate_backend import CAMPAIGN_SCHEMA
    from scripts.repository_evaluation.backend_matrix import SCHEMA as MATRIX_SCHEMA
    from scripts.repository_evaluation.common import canonical_sha256

    suite_path, _sources = corpus
    suite = json.loads(suite_path.read_text())
    grader = json.loads((suite_path.parent / "grader.json").read_text())
    campaign = root / "campaign.json"
    write_json(
        campaign,
        {
            "schema": CAMPAIGN_SCHEMA,
            "matrix_schema": MATRIX_SCHEMA,
            "capabilities": list(range(1, 21)),
            "suites": [
                {
                    "id": name,
                    "suite_file": "suite.json",
                    "suite_sha256": canonical_sha256(suite),
                    "grader_sha256": canonical_sha256(grader),
                    "workflow_ids": [row["id"] for row in suite["workflows"]],
                }
                for name in ("good", "other")
            ],
        },
    )
    return campaign


def test_aggregate_retains_valid_observations_and_rejected_input(
    corpus: tuple[Path, dict[str, Path]], tmp_path: Path
) -> None:
    from scripts.repository_evaluation.aggregate_backend import aggregate_backend

    suite_path, sources = corpus
    valid_root = tmp_path / "valid"
    run_backend(
        sources=sources, suite_path=suite_path, output_dir=valid_root, transports=()
    )
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{invalid")
    output = tmp_path / "aggregate"
    report = aggregate_backend(
        campaign_path=_aggregate_campaign(corpus, tmp_path),
        sources=sources,
        selections={
            "good": {"workflow_report": str(valid_root / "summary.json")},
            "other": {"workflow_report": str(invalid)},
        },
        output_dir=output,
    )
    assert report["status"] == "FAIL"
    assert report["input_integrity"]["state"] == "FAIL"
    inputs = {(row["suite"], row["proof"]): row for row in report["input_reports"]}
    assert inputs[("good", "workflow")]["state"] == "ADMITTED"
    rejected = inputs[("other", "workflow")]
    assert rejected["state"] == "REJECTED"
    assert rejected["sha256"] == hashlib.sha256(invalid.read_bytes()).hexdigest()
    assert rejected["reason"]
    outcomes = {row["id"]: row for row in report["outcomes"]}
    assert outcomes["good/handler"]["gates"]["facts"] is True
    assert outcomes["other/handler"]["gates"]["native_binding"] is None
    assert "other/handler" in report["missing_workflow_reports"]
    assert json.loads((output / "summary.json").read_text()) == report
    assert "REJECTED" in (output / "summary.md").read_text()


def test_aggregate_missing_expected_inputs_remain_incomplete(
    corpus: tuple[Path, dict[str, Path]], tmp_path: Path
) -> None:
    from scripts.repository_evaluation.aggregate_backend import aggregate_backend

    report = aggregate_backend(
        campaign_path=_aggregate_campaign(corpus, tmp_path),
        sources=corpus[1],
        selections={},
        output_dir=tmp_path / "aggregate",
    )
    assert report["status"] == "INCOMPLETE"
    assert report["input_integrity"]["state"] == "INCOMPLETE"
    assert set(report["missing_workflow_reports"]) == {"good/handler", "other/handler"}
    assert all(row["state"] == "MISSING" for row in report["input_reports"])


def test_aggregate_unknown_selected_report_is_retained_as_rejection(
    corpus: tuple[Path, dict[str, Path]], tmp_path: Path
) -> None:
    from scripts.repository_evaluation.aggregate_backend import aggregate_backend

    report = aggregate_backend(
        campaign_path=_aggregate_campaign(corpus, tmp_path),
        sources=corpus[1],
        selections={"unexpected": {}},
        output_dir=tmp_path / "aggregate",
    )
    assert report["status"] == "FAIL"
    assert any(
        row["suite"] == "unexpected" and row["state"] == "REJECTED"
        for row in report["input_reports"]
    )


def test_exact_workflow_receipt_reuses_then_rejects_changed_observation(
    corpus: tuple[Path, dict[str, Path]], tmp_path: Path
) -> None:
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


def test_changed_archive_and_oracle_ranges_fail_before_observation(
    corpus: tuple[Path, dict[str, Path]],
) -> None:
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


@pytest.mark.parametrize("location", ["top", "stage"])
def test_independent_display_failure_is_a_hard_gate_and_has_exact_oracle_pointers(
    corpus: tuple[Path, dict[str, Path]], tmp_path: Path, location: str
) -> None:
    from hashmarks.evidence_presentation import FORMATS
    from scripts.repository_evaluation.backend_regrading import verify_task_summary
    from scripts.repository_evaluation.fact_grading import pointer_values

    suite_path, sources = corpus
    grader_path = suite_path.parent / "grader.json"
    grader = json.loads(grader_path.read_text())
    rule = grader["cases"]["handler"]
    checks = {
        profile: {
            format: [
                {
                    "id": "display-coverage",
                    "pointer": "/coverage",
                    "predicate": "equals",
                    "value": "contradicted-coverage",
                    "support": "supported",
                }
            ]
            for format in FORMATS
            if format != "none"
        }
        for profile in ("default", "initial")
    }
    if location == "top":
        rule["display_checks"] = checks
    else:
        for stage in ("before", "after"):
            rule[stage] = {"display_checks": checks}
    write_json(grader_path, grader)
    report = run_backend(
        sources=sources,
        suite_path=suite_path,
        output_dir=tmp_path / "display",
        transports=("cli",),
    )
    outcome = report["outcomes"][0]
    assert outcome["gates"]["facts"] is True
    assert outcome["gates"]["cli"] is False
    assert outcome["gates"]["presentation"] is False
    witnesses = [
        row for row in outcome["gate_witnesses"] if row["gate"] == "presentation"
    ]
    assert witnesses and all(row["state"] == "FAIL" for row in witnesses)
    for witness in witnesses:
        (check,) = pointer_values(grader, witness["oracle_pointer"])
        assert assert_object(check)["id"] == witness["check_id"]
    suite, frozen = load_corpus(suite_path, sources)
    verify_task_summary(
        tmp_path / "display/handler/observations",
        suite["workflows"][0],
        frozen["cases"]["handler"],
        sources,
        outcome,
    )


def _extend_task_source_labels(corpus: tuple[Path, dict[str, Path]]) -> dict:
    suite_path, sources = corpus
    suite = json.loads(suite_path.read_text())
    grader_path = suite_path.parent / "grader.json"
    grader = json.loads(grader_path.read_text())
    rule = grader["cases"]["handler"]
    task_labels = {}
    for stage in ("before", "after"):
        path = sources[stage] / "models.py"
        path.write_text("def model():\n    return 'declared'\n")
        task_labels[stage] = [
            *rule["source_labels"][stage],
            {
                "path": "models.py",
                "symbol": "model",
                "start_line": 1,
                "end_line": 2,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            },
        ]
        suite["sources"][stage]["content_identity"] = repository_content_identity(
            sources[stage]
        )
    rule["task_source_labels"] = task_labels
    write_json(suite_path, suite)
    write_json(grader_path, grader)
    return rule


def test_task_source_labels_extend_witnesses_without_expanding_native_targets(
    corpus: tuple[Path, dict[str, Path]], tmp_path: Path
) -> None:
    from scripts.repository_evaluation.backend_native import _capture_inputs
    from scripts.repository_evaluation.backend_regrading import verify_task_summary

    expected = _extend_task_source_labels(corpus)
    suite_path, sources = corpus
    suite, grader = load_corpus(suite_path, sources)
    rule = grader["cases"]["handler"]
    workflow = suite["workflows"][0]
    for stage in ("before", "after"):
        assert rule["source_labels"][stage] == expected["source_labels"][stage]
        assert _capture_inputs(workflow, rule, stage) == ("python", ["backend.py"])
    report = run_backend(
        sources=sources,
        suite_path=suite_path,
        output_dir=tmp_path / "expanded",
        transports=(),
    )
    outcome = report["outcomes"][0]
    assert outcome["gates"]["facts"] is True
    for witness in outcome["gate_witnesses"]:
        assert {row["path"] for row in witness["source_bindings"]} == {
            "backend.py",
            "models.py",
        }
    verify_task_summary(
        tmp_path / "expanded/handler/observations", workflow, rule, sources, outcome
    )


@pytest.mark.parametrize(
    "labels",
    [None, {"before": []}, {"before": [], "after": []}, {"before": [1], "after": [1]}],
)
def test_invalid_task_source_labels_are_rejected_before_observation(
    corpus: tuple[Path, dict[str, Path]], labels: object
) -> None:
    suite_path, sources = corpus
    grader_path = suite_path.parent / "grader.json"
    grader = json.loads(grader_path.read_text())
    grader["cases"]["handler"]["task_source_labels"] = labels
    write_json(grader_path, grader)
    with pytest.raises(ValueError, match="task source labels"):
        load_corpus(suite_path, sources)


@pytest.mark.parametrize("field", ["source_labels", "task_source_labels"])
def test_task_scope_does_not_bypass_native_or_task_source_integrity(
    corpus: tuple[Path, dict[str, Path]], field: str
) -> None:
    _extend_task_source_labels(corpus)
    suite_path, sources = corpus
    grader_path = suite_path.parent / "grader.json"
    grader = json.loads(grader_path.read_text())
    grader["cases"]["handler"][field]["before"][0]["sha256"] = "0" * 64
    write_json(grader_path, grader)
    with pytest.raises(ValueError, match="source range changed"):
        load_corpus(suite_path, sources)


@pytest.mark.parametrize(
    "native_oracles,reason",
    [
        ({"before": {}}, "both revision stages"),
        ({"before": {}, "after": {}}, "target membership"),
        (
            {
                stage: {"backend.py::handler": {"checks": []}}
                for stage in ("before", "after")
            },
            "checks must be nonempty",
        ),
    ],
)
def test_incomplete_native_oracles_fail_during_source_admission(
    corpus: tuple[Path, dict[str, Path]], native_oracles: object, reason: str
) -> None:
    suite_path, sources = corpus
    grader_path = suite_path.parent / "grader.json"
    grader = json.loads(grader_path.read_text())
    grader["cases"]["handler"]["native_oracles"] = native_oracles
    write_json(grader_path, grader)
    with pytest.raises(ValueError, match=reason):
        load_corpus(suite_path, sources)


def test_invalid_workflow_selection_is_not_an_empty_success(
    corpus: tuple[Path, dict[str, Path]], tmp_path: Path
) -> None:
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
    corpus: tuple[Path, dict[str, Path]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.repository_evaluation import backend_workflows

    suite_path, sources = corpus

    def changing_transport(workspace: Path, *_args: object) -> list[object]:
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
    corpus: tuple[Path, dict[str, Path]], tmp_path: Path
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
        witnesses = [
            row
            for row in outcome["gate_witnesses"]
            if row["gate"] == "boundary_facts" and row["stage"] == stage
        ]
        assert {row["surface"] for row in witnesses} == {"api", "cli"}
        assert all(
            row["state"] == "PASS" and row["source_bindings"][0]["path"] == "backend.py"
            for row in witnesses
        )
    assert outcome["gates"]["initial_evidence"] is None
    assert report["status"] == "INCOMPLETE"
    assert all(row["local_e2e_rating"] is None for row in report["capabilities"])


def test_boundary_failed_fact_cannot_be_compensated_by_task_or_revision_success(
    corpus: tuple[Path, dict[str, Path]], tmp_path: Path
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
    assert outcome["gates"]["revision"] is None
    assert outcome["gates"]["facts"] is False
    assert report["status"] == "FAIL"


@pytest.mark.parametrize("mutation", ["missing-stage", "line-hash", "scope"])
def test_boundary_source_admission_rejects_incomplete_or_unbound_oracles(
    corpus: tuple[Path, dict[str, Path]], mutation: str
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
    corpus: tuple[Path, dict[str, Path]],
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
    corpus: tuple[Path, dict[str, Path]], tmp_path: Path
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
        witnesses = [
            row
            for row in outcome["gate_witnesses"]
            if row["gate"] == "declarations_facts" and row["stage"] == stage
        ]
        assert {row["surface"] for row in witnesses} == {"api", "cli"}
        assert all(
            row["state"] == "PASS" and row["source_bindings"][0]["path"] == "backend.py"
            for row in witnesses
        )
    assert outcome["gates"]["mcp"] is None
    assert outcome["gates"]["freshness"] is True
    assert outcome["gates"]["facts"] is True


def test_failed_declaration_fact_cannot_be_masked_by_successful_task(
    corpus: tuple[Path, dict[str, Path]], tmp_path: Path
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
    assert outcome["gates"]["revision"] is None
    assert outcome["gates"]["facts"] is False
    assert outcome["declaration_observations"]["after"]["gates"]["facts"] is False


def _add_interface_observations(suite_path: Path, sources: dict[str, Path]) -> None:
    suite = json.loads(suite_path.read_text())
    grader_path = suite_path.parent / "grader.json"
    grader = json.loads(grader_path.read_text())
    workflow = suite["workflows"][0]
    rule = grader["cases"]["handler"]
    workflow["declaration_observations"] = {}
    rule["declaration_oracles"] = {}
    for stage in ("before", "after"):
        path = sources[stage] / "backend.py"
        statement = f'api.post("/{stage}")(handler)\n'.encode()
        path.write_bytes(path.read_bytes() + statement)
        suite["sources"][stage]["content_identity"] = repository_content_identity(
            sources[stage]
        )
        workflow["declaration_observations"][stage] = {
            "groups": [],
            "result_mode": "discovery",
            "python_interface": {"paths": ["backend.py"], "route_objects": ["api"]},
        }
        rule["declaration_oracles"][stage] = {
            "source": stage,
            "source_labels": [
                {
                    "path": "backend.py",
                    "start_line": 3,
                    "end_line": 3,
                    "sha256": hashlib.sha256(statement).hexdigest(),
                }
            ],
            "checks": [
                {
                    "id": "explicit-route-call",
                    "pointer": "/declarations/groups/*/declarations/*/value",
                    "predicate": "includes_record",
                    "value": {
                        "method_syntax": "post",
                        "literal_argument": f"/{stage}",
                        "handler_argument_syntax": "handler",
                        "handler_resolution": "unresolved",
                        "runtime_registration": "not-established",
                    },
                }
            ],
        }
    rule["delta_checks"][0]["value"] = hash_file(
        sources["after"] / "backend.py", domain=FILE_DOMAIN
    ).hash
    write_json(suite_path, suite)
    write_json(grader_path, grader)


def test_interface_workflow_keeps_artifact_bound_facts_and_pure_regrading(
    corpus: tuple[Path, dict[str, Path]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.repository_evaluation.backend_regrading import verify_task_summary

    suite_path, sources = corpus
    _add_interface_observations(suite_path, sources)
    report = run_backend(
        sources=sources,
        suite_path=suite_path,
        output_dir=tmp_path / "interface",
        transports=(),
    )
    outcome = report["outcomes"][0]
    assert outcome["gates"]["facts"] is True
    assert outcome["gates"]["cli"] is None
    assert outcome["gates"]["mcp"] is None
    suite, grader = load_corpus(suite_path, sources)
    for stage in ("before", "after"):
        assert outcome["declaration_observations"][stage]["gates"]["facts"] is True
        witnesses = [
            w
            for w in outcome["gate_witnesses"]
            if w["gate"] == "declarations_facts" and w["stage"] == stage
        ]
        assert witnesses and all(w["state"] == "PASS" for w in witnesses)
        assert all(w["source_bindings"][0]["path"] == "backend.py" for w in witnesses)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("pure regrading must not instantiate the observer")

    monkeypatch.setattr("hashmarks.codemap.engine.CodeMap.__init__", forbidden)
    verify_task_summary(
        tmp_path / "interface/handler/observations",
        suite["workflows"][0],
        grader["cases"]["handler"],
        sources,
        outcome,
    )


def test_failed_interface_declaration_fact_cannot_be_masked_by_task_facts(
    corpus: tuple[Path, dict[str, Path]],
    tmp_path: Path,
) -> None:
    suite_path, sources = corpus
    _add_interface_observations(suite_path, sources)
    path = suite_path.parent / "grader.json"
    grader = json.loads(path.read_text())
    grader["cases"]["handler"]["declaration_oracles"]["after"]["checks"][0]["value"][
        "literal_argument"
    ] = "/wrong"
    write_json(path, grader)
    report = run_backend(
        sources=sources,
        suite_path=suite_path,
        output_dir=tmp_path / "interface-failed",
        transports=(),
    )
    outcome = report["outcomes"][0]
    assert outcome["after"]["classification"] == "PASS"
    assert outcome["declaration_observations"]["after"]["gates"]["facts"] is False
    assert outcome["gates"]["facts"] is False


@pytest.mark.parametrize(
    "mutation", ["unlabeled-path", "unknown-option", "missing-stage", "wrong-source"]
)
def test_interface_workflow_requires_exact_source_and_oracle_membership(
    corpus: tuple[Path, dict[str, Path]],
    mutation: str,
) -> None:
    suite_path, sources = corpus
    _add_interface_observations(suite_path, sources)
    suite = json.loads(suite_path.read_text())
    grader_path = suite_path.parent / "grader.json"
    grader = json.loads(grader_path.read_text())
    request = suite["workflows"][0]["declaration_observations"]["after"]
    oracle = grader["cases"]["handler"]["declaration_oracles"]
    if mutation == "unlabeled-path":
        request["python_interface"]["paths"].append("unlabeled.py")
    elif mutation == "unknown-option":
        request["python_interface"]["runtime_registration"] = True
    elif mutation == "missing-stage":
        del oracle["after"]
    else:
        oracle["after"]["source"] = "before"
    write_json(suite_path, suite)
    write_json(grader_path, grader)
    with pytest.raises(ValueError):
        load_corpus(suite_path, sources)


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
    corpus: tuple[Path, dict[str, Path]], mutation: str
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


@pytest.mark.parametrize("kind", ["add", "delete", "rename"])
def test_added_deleted_and_renamed_files_preserve_revision_invalidation(
    corpus: tuple[Path, dict[str, Path]], tmp_path: Path, kind: str
) -> None:
    suite_path, sources = corpus
    suite = json.loads(suite_path.read_text())
    before = "extra.py" if kind != "add" else None
    after = "renamed.py" if kind == "rename" else "extra.py" if kind == "add" else None
    for stage, path in (("before", before), ("after", after)):
        if path is not None:
            (sources[stage] / path).write_text("def extra():\n    return 3\n")
        suite["sources"][stage]["content_identity"] = repository_content_identity(
            sources[stage]
        )
    workflow = suite["workflows"][0]
    workflow["transitions"].append(
        {"kind": kind, "before_path": before, "after_path": after}
    )
    workflow["changed_paths"] = sorted(
        {"backend.py", *[p for p in (before, after) if p is not None]}
    )
    write_json(suite_path, suite)
    report = run_backend(
        sources=sources,
        suite_path=suite_path,
        output_dir=tmp_path / "result",
        transports=(),
    )
    outcome = report["outcomes"][0]
    assert outcome["gates"]["freshness"] is True
    assert outcome["gates"]["facts"] is True
    stale = json.loads(
        (tmp_path / "result/handler/observations/stale.json").read_text()
    )
    assert {row["member"]["path"] for row in stale["observations"]} == set(
        workflow["changed_paths"]
    )
    assert all(
        row["negative_evidence"] == "not-admissible" for row in stale["observations"]
    )


def test_v2_workflow_cannot_silently_fall_back_to_legacy_transitions(
    corpus: tuple[Path, dict[str, Path]],
) -> None:
    suite_path, sources = corpus
    suite = json.loads(suite_path.read_text())
    del suite["workflows"][0]["transitions"]
    write_json(suite_path, suite)
    with pytest.raises(ValueError, match="explicit source transitions"):
        load_corpus(suite_path, sources)


def test_legacy_modification_manifest_remains_readable(
    corpus: tuple[Path, dict[str, Path]],
) -> None:
    from scripts.repository_evaluation.backend_corpus import LEGACY_SCHEMA

    suite_path, sources = corpus
    suite = json.loads(suite_path.read_text())
    suite["schema"] = LEGACY_SCHEMA
    del suite["workflows"][0]["transitions"]
    write_json(suite_path, suite)
    loaded, _ = load_corpus(suite_path, sources)
    assert loaded["schema"] == LEGACY_SCHEMA


def _campaign_for_fixture(suite_path: Path) -> Path:
    from scripts.repository_evaluation.aggregate_backend import CAMPAIGN_SCHEMA
    from scripts.repository_evaluation.backend_matrix import SCHEMA as MATRIX_SCHEMA
    from scripts.repository_evaluation.common import canonical_sha256

    suite = json.loads(suite_path.read_text())
    grader = json.loads((suite_path.parent / suite["grader_file"]).read_text())
    path = suite_path.parent / "campaign.json"
    write_json(
        path,
        {
            "schema": CAMPAIGN_SCHEMA,
            "matrix_schema": MATRIX_SCHEMA,
            "capabilities": list(range(1, 21)),
            "suites": [
                {
                    "id": "fixture",
                    "suite_file": "suite.json",
                    "suite_sha256": canonical_sha256(suite),
                    "grader_sha256": canonical_sha256(grader),
                    "workflow_ids": [row["id"] for row in suite["workflows"]],
                }
            ],
        },
    )
    return path


def _workflow_batch_reports(
    corpus: tuple[Path, dict[str, Path]], root: Path
) -> list[str]:
    suite_path, sources = corpus
    suite = json.loads(suite_path.read_text())
    suite["workflows"].append(
        {**suite["workflows"][0], "id": "second", "problem_id": "second-problem"}
    )
    grader_path = suite_path.parent / "grader.json"
    grader = json.loads(grader_path.read_text())
    grader["cases"]["second"] = grader["cases"]["handler"]
    write_json(suite_path, suite)
    write_json(grader_path, grader)
    reports = []
    for identifier in ("handler", "second"):
        output = root / identifier
        run_backend(
            sources=sources,
            suite_path=suite_path,
            output_dir=output,
            workflow_ids=[identifier],
            transports=(),
        )
        reports.append(str(output / "summary.json"))
    return reports


def test_aggregate_admits_disjoint_bounded_reports_and_preserves_namespaces(
    corpus: tuple[Path, dict[str, Path]], tmp_path: Path
) -> None:
    from scripts.repository_evaluation.aggregate_backend import aggregate_backend

    reports = _workflow_batch_reports(corpus, tmp_path / "batches")
    report = aggregate_backend(
        campaign_path=_campaign_for_fixture(corpus[0]),
        sources=corpus[1],
        selections={"fixture": {"workflow_reports": reports}},
        output_dir=tmp_path / "aggregate",
    )
    assert report["input_integrity"]["state"] == "PASS"
    assert report["missing_workflow_reports"] == []
    assert report["status"] == "INCOMPLETE"
    inputs = [row for row in report["input_reports"] if row["proof"] == "workflow"]
    assert len(inputs) == 2 and all(row["state"] == "ADMITTED" for row in inputs)
    outcomes = report["outcomes"]
    assert {row["id"] for row in outcomes} == {"fixture/handler", "fixture/second"}
    for outcome in outcomes:
        assert outcome["gates"]["facts"] is True
        binding = outcome["report_binding"]
        assert (
            binding["sha256"]
            == hashlib.sha256(Path(binding["path"]).read_bytes()).hexdigest()
        )
        assert {w["artifact_namespace"] for w in outcome["gate_witnesses"]} == {
            "workflow:sha256:" + binding["sha256"]
        }


@pytest.mark.parametrize("reverse", [False, True])
def test_aggregate_overlapping_batches_cannot_choose_a_winner(
    corpus: tuple[Path, dict[str, Path]], tmp_path: Path, reverse: bool
) -> None:
    from scripts.repository_evaluation.aggregate_backend import aggregate_backend

    reports = _workflow_batch_reports(corpus, tmp_path / "batches")
    duplicate = tmp_path / "duplicate"
    run_backend(
        sources=corpus[1],
        suite_path=corpus[0],
        output_dir=duplicate,
        workflow_ids=["handler"],
        transports=(),
    )
    reports.append(str(duplicate / "summary.json"))
    report = aggregate_backend(
        campaign_path=_campaign_for_fixture(corpus[0]),
        sources=corpus[1],
        selections={
            "fixture": {"workflow_reports": reports[::-1] if reverse else reports}
        },
        output_dir=tmp_path / "aggregate",
    )
    assert report["status"] == "FAIL"
    rejected = next(
        row for row in report["input_reports"] if row["proof"] == "workflow-membership"
    )
    assert rejected["state"] == "REJECTED" and rejected["workflows"] == ["handler"]
    outcomes = {row["id"]: row for row in report["outcomes"]}
    assert outcomes["fixture/handler"]["gates"].get("facts") is None
    assert outcomes["fixture/second"]["gates"]["facts"] is True


def test_aggregate_bad_batch_preserves_valid_batches(
    corpus: tuple[Path, dict[str, Path]], tmp_path: Path
) -> None:
    from scripts.repository_evaluation.aggregate_backend import aggregate_backend

    reports = _workflow_batch_reports(corpus, tmp_path / "batches")
    broken = Path(reports[1])
    summary = json.loads(broken.read_text())
    summary["outcomes"][0]["gates"]["facts"] = False
    write_json(broken, summary)
    report = aggregate_backend(
        campaign_path=_campaign_for_fixture(corpus[0]),
        sources=corpus[1],
        selections={"fixture": {"workflow_reports": reports}},
        output_dir=tmp_path / "aggregate",
    )
    assert report["status"] == "FAIL"
    inputs = [row for row in report["input_reports"] if row["proof"] == "workflow"]
    assert [row["state"] for row in inputs] == ["ADMITTED", "REJECTED"]
    outcomes = {row["id"]: row for row in report["outcomes"]}
    assert outcomes["fixture/handler"]["gates"]["facts"] is True
    assert report["missing_workflow_reports"] == ["fixture/second"]


@pytest.mark.parametrize(
    "selection",
    [
        {"workflow_reports": []},
        {"workflow_reports": "report.json"},
        {"workflow_report": "one.json", "workflow_reports": ["two.json"]},
        {"native_reports": [{"native_report": "native.json"}]},
        {"native_reports": ["native.json"]},
        {"native_reports": [{"native_report": "native.json", "capture_root": False}]},
        {
            "native_report": "one.json",
            "native_reports": [
                {"native_report": "two.json", "capture_root": "captures"}
            ],
        },
        {
            "native_reports": [
                {"native_report": "native.json", "capture_root": "captures"}
            ],
            "capture_root": "other",
        },
        {"argv": ["execute"]},
    ],
)
def test_aggregate_rejects_ambiguous_or_malformed_batch_selections(
    corpus: tuple[Path, dict[str, Path]], tmp_path: Path, selection: dict
) -> None:
    from scripts.repository_evaluation.aggregate_backend import aggregate_backend

    report = aggregate_backend(
        campaign_path=_campaign_for_fixture(corpus[0]),
        sources=corpus[1],
        selections={"fixture": selection},
        output_dir=tmp_path / "aggregate",
    )
    assert report["status"] == "FAIL"
    assert report["input_integrity"]["state"] == "FAIL"
    assert any(row["state"] == "REJECTED" for row in report["input_reports"])


def test_native_batches_keep_each_capture_root_and_acquisition_identity(
    corpus: tuple[Path, dict[str, Path]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.repository_evaluation import aggregate_backend as aggregation
    from scripts.repository_evaluation.common import (
        canonical_sha256,
        evaluator_implementation_identity,
    )
    from scripts.repository_evaluation.run_backend import _observer_identity

    _workflow_batch_reports(corpus, tmp_path / "batches")
    suite, grader = load_corpus(*corpus)
    entries = []
    observed = []
    for identifier in ("handler", "second"):
        path = tmp_path / identifier / "summary.json"
        write_json(
            path,
            {
                "schema": aggregation.NATIVE_SCHEMA,
                "identity": {
                    "suite": canonical_sha256(suite),
                    "grader": canonical_sha256(grader),
                    "observer": _observer_identity(),
                    "evaluator": evaluator_implementation_identity(),
                    "transports": [],
                    "regenerate": True,
                    "acquisition_id": identifier,
                    "source_identities": {
                        name: row["content_identity"]
                        for name, row in suite["sources"].items()
                    },
                },
                "qualification_scope": "explicit-source-binding-and-native-transport-only",
                "outcomes": [{"id": identifier, "gates": {"before_binding": True}}],
            },
        )
        entries.append(
            {
                "native_report": str(path),
                "capture_root": str(tmp_path / (identifier + "-captures")),
            }
        )

    def verify(*args: object, acquisition_id: str | None = None) -> None:
        observed.append((args[3], acquisition_id))

    monkeypatch.setattr(aggregation, "_verify_native_outcome", verify)
    outcomes, inputs = aggregation._admit_report_inputs(
        "fixture", "native", {"native_reports": entries}, suite, grader, corpus[1]
    )
    assert set(outcomes) == {"handler", "second"}
    assert all(row["state"] == "ADMITTED" for row in inputs)
    assert observed == [
        ((Path(entry["native_report"]).parent, Path(entry["capture_root"])), identifier)
        for entry, identifier in zip(entries, ("handler", "second"), strict=True)
    ]


def test_aggregate_reads_current_receipts_without_executing_work(
    corpus: tuple[Path, dict[str, Path]], tmp_path: Path
) -> None:
    from scripts.repository_evaluation.aggregate_backend import aggregate_backend

    suite_path, sources = corpus
    campaign = _campaign_for_fixture(suite_path)
    run_backend(
        sources=sources,
        suite_path=suite_path,
        output_dir=tmp_path / "measure",
        transports=(),
    )
    report = aggregate_backend(
        campaign_path=campaign,
        sources=sources,
        selections={
            "fixture": {"workflow_report": str(tmp_path / "measure/summary.json")}
        },
        output_dir=tmp_path / "aggregate",
    )
    assert report["status"] == "INCOMPLETE"
    assert report["outcomes"][0]["id"] == "fixture/handler"
    assert all(row["local_e2e_rating"] is None for row in report["capabilities"])
    assert (tmp_path / "aggregate/summary.md").is_file()


def test_aggregate_accounts_for_missing_reports(
    corpus: tuple[Path, dict[str, Path]], tmp_path: Path
) -> None:
    from scripts.repository_evaluation.aggregate_backend import aggregate_backend

    suite_path, sources = corpus
    report = aggregate_backend(
        campaign_path=_campaign_for_fixture(suite_path),
        sources=sources,
        selections={},
        output_dir=tmp_path / "aggregate",
    )
    assert report["status"] == "INCOMPLETE"
    assert report["missing_workflow_reports"] == ["fixture/handler"]


def test_initial_is_the_first_public_task_request_at_each_revision(
    corpus: tuple[Path, dict[str, Path]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hashmarks.operation_contract import operation_default_mode
    from scripts.repository_evaluation import backend_workflows

    suite_path, sources = corpus
    requests = []

    def capture(
        _workspace: object, _state: object, case: dict[str, object]
    ) -> list[object]:
        requests.append(assert_object(case["inputs"])["result_mode"])
        return []

    monkeypatch.setattr(backend_workflows, "capture_cli", capture)
    report = run_backend(
        sources=sources,
        suite_path=suite_path,
        output_dir=tmp_path / "result",
        transports=("cli",),
    )
    assert requests == ["initial", operation_default_mode("task_evidence")] * 2
    assert report["status"] == "INCOMPLETE"


def test_regrading_rejects_a_passing_summary_without_artifact_proof(
    corpus: tuple[Path, dict[str, Path]], tmp_path: Path
) -> None:
    from scripts.repository_evaluation.backend_regrading import verify_task_summary

    suite_path, sources = corpus
    report = run_backend(
        sources=sources,
        suite_path=suite_path,
        output_dir=tmp_path / "result",
        transports=("cli",),
    )
    suite, grader = load_corpus(suite_path, sources)
    outcome = report["outcomes"][0]
    root = tmp_path / "result/handler/observations"
    verify_task_summary(
        root, suite["workflows"][0], grader["cases"]["handler"], sources, outcome
    )
    outcome["gates"]["mcp"] = True
    with pytest.raises(ValueError, match="summary differs from artifact proof"):
        verify_task_summary(
            root, suite["workflows"][0], grader["cases"]["handler"], sources, outcome
        )


def test_regrading_recomputes_actual_visible_size(
    corpus: tuple[Path, dict[str, Path]], tmp_path: Path
) -> None:
    from scripts.repository_evaluation.backend_regrading import verify_task_summary

    suite_path, sources = corpus
    report = run_backend(
        sources=sources,
        suite_path=suite_path,
        output_dir=tmp_path / "result",
        transports=("cli",),
    )
    suite, grader = load_corpus(suite_path, sources)
    root = tmp_path / "result/handler/observations"
    path = root / "before/initial/cli.json"
    captures = json.loads(path.read_text())
    captures[0]["estimated_tokens"] = 0
    write_json(path, captures)
    with pytest.raises(ValueError, match="measurement differs from visible bytes"):
        verify_task_summary(
            root,
            suite["workflows"][0],
            grader["cases"]["handler"],
            sources,
            report["outcomes"][0],
        )


def test_correct_source_digest_cannot_qualify_wrong_symbol_name(
    corpus: tuple[Path, dict[str, Path]],
) -> None:
    suite_path, sources = corpus
    path = suite_path.parent / "grader.json"
    grader = json.loads(path.read_text())
    grader["cases"]["handler"]["source_labels"]["before"][0]["symbol"] = (
        "different_handler"
    )
    write_json(path, grader)
    with pytest.raises(
        ValueError, match="symbol does not match its source declaration"
    ):
        load_corpus(suite_path, sources)


@pytest.mark.parametrize("mutation", ["summary", "artifact", "observer", "campaign"])
def test_aggregate_rejects_unbound_or_modified_evidence(
    corpus: tuple[Path, dict[str, Path]], tmp_path: Path, mutation: str
) -> None:
    from scripts.repository_evaluation.aggregate_backend import aggregate_backend

    suite_path, sources = corpus
    campaign = _campaign_for_fixture(suite_path)
    output = tmp_path / "measure"
    run_backend(
        sources=sources, suite_path=suite_path, output_dir=output, transports=()
    )
    if mutation == "artifact":
        (output / "handler/observations/before/api.json").write_text("{}")
    elif mutation == "campaign":
        payload = json.loads(campaign.read_text())
        payload["suites"][0]["grader_sha256"] = "0" * 64
        write_json(campaign, payload)
    else:
        payload = json.loads((output / "summary.json").read_text())
        if mutation == "summary":
            payload["outcomes"][0]["gates"]["facts"] = False
        else:
            payload["identity"]["observer"] = "sha256:" + "0" * 64
        write_json(output / "summary.json", payload)
    options = {
        "campaign_path": campaign,
        "sources": sources,
        "selections": {"fixture": {"workflow_report": str(output / "summary.json")}},
        "output_dir": tmp_path / "aggregate",
    }
    if mutation == "campaign":
        with pytest.raises(ValueError, match="differs|mismatch|changed"):
            aggregate_backend(**options)
    else:
        report = aggregate_backend(**options)
        assert report["status"] == "FAIL"
        rejected = next(
            row for row in report["input_reports"] if row["proof"] == "workflow"
        )
        assert rejected["state"] == "REJECTED"
        assert any(
            word in rejected["reason"] for word in ("differs", "mismatch", "changed")
        )
        assert report["missing_workflow_reports"] == ["fixture/handler"]


@pytest.mark.parametrize(
    "field",
    ["before", "after", "delta", "transport_grades", "initial_transport_grades"],
)
def test_regrading_rejects_forged_retained_subgrades(
    corpus: tuple[Path, dict[str, Path]], tmp_path: Path, field: str
) -> None:
    from scripts.repository_evaluation.backend_regrading import verify_task_summary

    suite_path, sources = corpus
    report = run_backend(
        sources=sources,
        suite_path=suite_path,
        output_dir=tmp_path / "result",
        transports=(),
    )
    suite, grader = load_corpus(suite_path, sources)
    outcome = report["outcomes"][0]
    outcome[field] = {"classification": "PASS"}
    with pytest.raises(ValueError, match="summary differs from artifact proof"):
        verify_task_summary(
            tmp_path / "result/handler/observations",
            suite["workflows"][0],
            grader["cases"]["handler"],
            sources,
            outcome,
        )


def test_regrading_rejects_uncomputed_gate_claim(
    corpus: tuple[Path, dict[str, Path]], tmp_path: Path
) -> None:
    from scripts.repository_evaluation.backend_regrading import verify_task_summary

    suite_path, sources = corpus
    report = run_backend(
        sources=sources,
        suite_path=suite_path,
        output_dir=tmp_path / "result",
        transports=(),
    )
    suite, grader = load_corpus(suite_path, sources)
    outcome = report["outcomes"][0]
    outcome["gates"]["runtime_verified"] = True
    with pytest.raises(ValueError, match="unexpected or missing gate"):
        verify_task_summary(
            tmp_path / "result/handler/observations",
            suite["workflows"][0],
            grader["cases"]["handler"],
            sources,
            outcome,
        )
