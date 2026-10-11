"""The evaluator cannot convert missing observations into successful proof."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.repository_evaluation.backend_matrix import capability_matrix
from scripts.repository_evaluation.common import CASES_SCHEMA, GRADER_SCHEMA
from scripts.repository_evaluation.grade_cases import grade_run
from scripts.repository_evaluation.run_cases import run_cases


def test_source_observation_is_graded_from_separate_oracle(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "backend.py").write_text("def handler():\n    return {'id': 1}\n")
    cases = tmp_path / "cases.json"
    cases.write_text(
        json.dumps(
            {
                "schema": CASES_SCHEMA,
                "suite": "source-facts",
                "cases": [
                    {
                        "id": "handler",
                        "operation": "task_evidence",
                        "inputs": {"task": "Inspect handler in backend.py"},
                    }
                ],
            }
        )
    )
    run = run_cases(
        workspace=repo, cases_path=cases, receipts_dir=tmp_path / "receipts"
    )
    rule = {
        "checks": [
            {
                "id": "owner",
                "pointer": "/ownership/owner/path",
                "predicate": "equals",
                "value": "backend.py",
                "authority_check": True,
            }
        ]
    }
    report = grade_run(
        run=run, grader={"schema": GRADER_SCHEMA, "cases": {"handler": rule}}
    )
    assert report["cases"][0]["checks"][0]["classification"] == "PASS"
    assert "checks" not in run["cases"][0]["result"]
    rule["checks"][0]["value"] = "unrelated.py"
    wrong = grade_run(run=run, grader={"cases": {"handler": rule}})
    assert wrong["cases"][0]["authority_violations"] == 1
    assert wrong["complete"] is False
    assert wrong["counters"]["OTHER_FAILURE"] == 1


def test_missing_fact_is_incomplete_even_for_exclusion_rule() -> None:
    run = {"cases": [{"id": "x", "result": {"packet": {}}}]}
    rule = {
        "checks": [
            {
                "id": "no_false_owner",
                "pointer": "/owner",
                "predicate": "excludes",
                "value": "wrong.py",
            }
        ]
    }
    report = grade_run(run=run, grader={"cases": {"x": rule}})
    assert report["complete"] is False
    assert report["cases"][0]["classification"] == "INCOMPLETE"


def test_duplicate_results_cannot_hide_missing_case() -> None:
    result = {"id": "a", "result": {"action": {}}}
    with pytest.raises(ValueError, match="duplicate"):
        grade_run(run={"cases": [result, result]}, grader={"cases": {"a": {}, "b": {}}})


def _workflows() -> list[dict]:
    return [
        {
            "id": str(index),
            "repository": f"repo-{index % 3}",
            "problem_id": str(index),
            "capabilities": list(range(1, 21)),
            "native_required": True,
        }
        for index in range(20)
    ]


def _outcomes(workflows: list[dict]) -> list[dict]:
    gates = {
        name: True
        for name in (
            "facts",
            "authority",
            "revision",
            "freshness",
            "cli",
            "mcp",
            "owner_top_three",
            "debug_correspondence",
            "initial_evidence",
            "presentation",
            "live",
            "language_parity",
            "performance",
        )
    }
    return [{"id": workflow["id"], "gates": dict(gates)} for workflow in workflows]


def test_matrix_requires_every_capability_gate_and_full_membership() -> None:
    workflows = _workflows()
    outcomes = _outcomes(workflows)
    matrix = capability_matrix(workflows, outcomes)
    assert matrix["status"] == "PASS"
    assert all(row["local_e2e_rating"] == 5 for row in matrix["capabilities"])
    outcomes[0]["gates"]["authority"] = False
    failed = capability_matrix(workflows, outcomes)
    assert failed["status"] == "FAIL"
    assert all(row["local_e2e_rating"] is None for row in failed["capabilities"])
    incomplete = capability_matrix(workflows, outcomes[1:])
    assert incomplete["status"] == "INCOMPLETE"
    assert incomplete["missing_outcomes"] == ["0"]


def test_genuine_workflows_cannot_be_manufactured_from_format_variants() -> None:
    workflows = _workflows()
    for workflow in workflows:
        workflow["problem_id"] = "same-upstream-problem"
    matrix = capability_matrix(workflows, _outcomes(workflows))
    assert matrix["status"] == "INCOMPLETE"
    assert matrix["capabilities"][0]["genuine_workflows"] == 3


def test_recall_thresholds_do_not_relax_authority_or_count_rewordings() -> None:
    workflows = _workflows()
    outcomes = _outcomes(workflows)
    outcomes[0]["gates"]["owner_top_three"] = False
    assert capability_matrix(workflows, outcomes)["status"] == "PASS"
    outcomes[1]["gates"]["owner_top_three"] = False
    for index in range(20, 100):
        workflows.append({**workflows[0], "id": str(index)})
        outcomes.append({"id": str(index), "gates": dict(outcomes[2]["gates"])})
    matrix = capability_matrix(workflows, outcomes)
    assert matrix["capabilities"][0]["gates"]["owner_top_three"]["fraction"] == 0.9
    assert matrix["status"] == "FAIL"


def test_matrix_rejects_duplicate_or_unexpected_outcomes() -> None:
    workflows = _workflows()
    outcomes = _outcomes(workflows)
    with pytest.raises(ValueError, match="duplicate"):
        capability_matrix(workflows, [*outcomes, outcomes[0]])
    with pytest.raises(ValueError, match="unexpected"):
        capability_matrix(workflows, [{"id": "not-selected", "gates": {}}])
