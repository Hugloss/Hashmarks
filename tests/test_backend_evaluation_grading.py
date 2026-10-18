"""The evaluator cannot convert missing observations into successful proof."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.repository_evaluation.backend_matrix import capability_matrix
from scripts.repository_evaluation.common import CASES_SCHEMA, GRADER_SCHEMA
from scripts.repository_evaluation.fact_grading import FactGrade
from scripts.repository_evaluation.grade_cases import grade_run
from scripts.repository_evaluation.run_cases import run_cases


@pytest.mark.parametrize(
    "actual,expected", [(False, 0), (0, 0.0), ({"x": False}, {"x": 0}), ([0], [False])]
)
def test_source_oracle_does_not_conflate_json_types(
    actual: object, expected: object
) -> None:
    from scripts.repository_evaluation.fact_grading import grade_facts

    rule = {
        "checks": [
            {
                "id": "typed",
                "pointer": "/value",
                "predicate": "equals",
                "value": expected,
            }
        ]
    }
    assert (
        grade_facts("typed", {"packet": {"value": actual}}, rule)["classification"]
        == "OTHER_FAILURE"
    )


def test_class_oracle_scopes_revision_but_checks_authority_of_all_class_records() -> (
    None
):
    from scripts.repository_evaluation.fact_grading import grade_facts

    context = {
        "authority": "indexed-lexical-declarations-only",
        "ownership_authority": False,
        "runtime_members": "not-established",
        "negative_evidence_admissible": False,
    }
    rows = [
        {
            "path": "backend.py",
            "symbol": "Backend",
            "class_declarations": {**context, "source_revision": "backend-revision"},
        },
        {
            "path": "other.py",
            "symbol": "Other",
            "class_declarations": {**context, "source_revision": "other-revision"},
        },
    ]
    checks: list[dict[str, object]] = [
        {
            "id": key,
            "pointer": "/retrieval/results/*/class_declarations/" + key,
            "predicate": "all_equal",
            "value": value,
            "authority_check": True,
        }
        for key, value in context.items()
    ]
    checks.append(
        {
            "id": "target-revision",
            "pointer": "/retrieval/results/*",
            "predicate": "includes_scoped_record",
            "authority_check": True,
            "value": {
                "scope": {"path": "backend.py", "symbol": "Backend"},
                "pointer": "/class_declarations",
                "record": {"source_revision": "backend-revision"},
            },
        }
    )

    def grade() -> FactGrade:
        return grade_facts(
            "classes", {"packet": {"retrieval": {"results": rows}}}, {"checks": checks}
        )

    assert grade()["classification"] == "PASS"
    rows[1]["class_declarations"]["ownership_authority"] = True
    assert grade()["authority_violations"] == 1
    rows[1]["class_declarations"]["ownership_authority"] = False
    rows[0]["class_declarations"]["source_revision"] = "other-revision"
    assert grade()["classification"] == "OTHER_FAILURE"
    rows.pop(0)
    assert grade()["classification"] == "OTHER_FAILURE"


def test_native_summary_cannot_qualify_a_definition_without_observation_membership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.repository_evaluation import aggregate_backend

    monkeypatch.setattr(aggregate_backend, "_verify_artifacts", lambda *_: None)
    with pytest.raises(ValueError, match="required observations"):
        aggregate_backend._verify_native_outcome(
            {"id": "forged"},
            {},
            {
                "artifacts": {"before/definition-token.json": "digest"},
                "gates": {"before_binding": True},
            },
            (tmp_path, tmp_path),
            ({}, {}),
        )


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


def _witness_context(unit: str, check: str, stage: str) -> dict:
    return {
        "gate": "facts",
        "unit_id": unit,
        "stage": stage,
        "profile": "default",
        "surface": "api",
        "format": "none",
        "check_id": check,
    }


def _workflows() -> list[dict]:
    return [
        {
            "id": str(index),
            "repository": f"repo-{index % 3}",
            "problem_id": str(index),
            "capabilities": list(range(1, 21)),
            "native_required": True,
            "debug_frame_units": ["frame-0"],
            "metric_eligibility": {
                name: {"eligible": True, "reason": "controlled metric population"}
                for name in (
                    "owner_top_three",
                    "initial_evidence",
                    "debug_correspondence",
                )
            },
            "capability_proofs": {
                str(capability): {
                    "reviewed": True,
                    "positive_check_ids": ["positive"],
                    "adversarial_check_ids": ["adversarial"],
                    "required_witnesses": [
                        {**_witness_context(str(index), check, stage), "role": check}
                        for stage in ("before", "after")
                        for check in ("positive", "adversarial")
                    ],
                }
                for capability in range(1, 21)
            },
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
            "initial_size",
            "presentation",
            "native_binding",
            "fresh_acquisition",
            "language_parity",
            "performance",
        )
    }
    return [
        {
            "id": workflow["id"],
            "gates": dict(gates),
            "gate_witnesses": [
                {
                    **_witness_context(workflow["id"], check, stage),
                    "state": "PASS",
                    "artifact": stage + "/api.json",
                    "artifact_sha256": "0" * 64,
                    "oracle_pointer": "/controlled/checks",
                    "source_bindings": [
                        {
                            "repository": workflow["repository"],
                            "path": "owner.py",
                            "revision": "controlled",
                        }
                    ],
                }
                for stage in ("before", "after")
                for check in ("positive", "adversarial")
            ],
            "debug_frame_observations": [
                {"unit_id": "frame-0", "correspondence": True}
            ],
        }
        for workflow in workflows
    ]


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


def test_explicit_target_variants_cannot_improve_blind_owner_recall() -> None:
    workflows = _workflows()
    outcomes = _outcomes(workflows)
    for workflow in workflows:
        workflow["metric_eligibility"]["owner_top_three"] = {
            "eligible": False,
            "reason": "explicit target",
        }
    gate = capability_matrix(workflows, outcomes)["capabilities"][0]["gates"][
        "owner_top_three"
    ]
    assert gate["state"] == "INCOMPLETE"
    assert gate["expected"] == 0
    assert len(gate["ineligible_workflows"]) == 20


def test_capability_tags_do_not_replace_reviewed_positive_and_adversarial_proof() -> (
    None
):
    workflows = _workflows()
    outcomes = _outcomes(workflows)
    for workflow in workflows:
        workflow.pop("capability_proofs")
    matrix = capability_matrix(workflows, outcomes)
    assert matrix["status"] == "INCOMPLETE"
    assert all(
        row["gates"]["capability_proof"]["state"] == "INCOMPLETE"
        for row in matrix["capabilities"]
    )


def test_known_authority_failure_is_not_hidden_by_missing_outcomes() -> None:
    workflows = _workflows()
    outcome = _outcomes(workflows)[0]
    outcome["gates"]["authority"] = False
    report = capability_matrix(workflows, [outcome])
    assert report["status"] == "FAIL"
    assert report["capabilities"][0]["gates"]["authority"]["state"] == "FAIL"
    assert report["missing_outcomes"]


def test_initial_size_cannot_be_averaged_into_a_recall_pass() -> None:
    workflows = _workflows()
    outcomes = _outcomes(workflows)
    outcomes[0]["gates"]["initial_size"] = False
    matrix = capability_matrix(workflows, outcomes)
    assert matrix["status"] == "FAIL"
    assert all(row["status"] == "FAIL" for row in matrix["capabilities"])


def test_legacy_outcomes_without_initial_size_remain_incomplete() -> None:
    workflows = _workflows()
    outcomes = _outcomes(workflows)
    for row in outcomes:
        del row["gates"]["initial_size"]
    assert capability_matrix(workflows, outcomes)["status"] == "INCOMPLETE"


def test_native_requirement_is_scoped_to_eligible_workflows() -> None:
    workflows = _workflows()
    outcomes = _outcomes(workflows)
    workflows[0]["native_required"] = False
    outcomes[0]["gates"]["native_binding"] = None
    matrix = capability_matrix(workflows, outcomes)
    assert matrix["capabilities"][0]["status"] == "PASS"
    assert matrix["capabilities"][0]["gates"]["native_binding"]["expected"] == 19
    assert matrix["capabilities"][17]["status"] == "INCOMPLETE"


def test_debug_correspondence_counts_frames_instead_of_successful_problems() -> None:
    workflows = _workflows()[:12]
    outcomes = _outcomes(workflows)
    workflows[-1]["debug_frame_units"] = [f"frame-{index}" for index in range(100)]
    outcomes[-1]["debug_frame_observations"] = [
        {"unit_id": unit, "correspondence": False}
        for unit in workflows[-1]["debug_frame_units"]
    ]
    gate = capability_matrix(workflows, outcomes)["capabilities"][3]["gates"][
        "debug_correspondence"
    ]
    assert gate["state"] == "FAIL"
    assert gate["passed"] == 11
    assert gate["expected"] == 111
    assert gate["fraction"] == 11 / 111


def test_missing_recall_cannot_hide_an_unreachable_threshold() -> None:
    workflows = _workflows()
    outcomes = _outcomes(workflows)
    outcomes[0]["gates"]["owner_top_three"] = False
    outcomes[1]["gates"]["owner_top_three"] = False
    outcomes.pop()
    gate = capability_matrix(workflows, outcomes)["capabilities"][0]["gates"][
        "owner_top_three"
    ]
    assert gate["state"] == "FAIL"
    assert gate["observed"] == 19


def test_unreviewed_frames_are_not_qualified_by_a_debug_summary_boolean() -> None:
    workflows = _workflows()
    outcomes = _outcomes(workflows)
    for workflow in workflows:
        workflow.pop("debug_frame_units")
    assert (
        capability_matrix(workflows, outcomes)["capabilities"][3]["status"]
        == "INCOMPLETE"
    )


def test_exact_record_checks_bind_symbol_to_its_own_source_range() -> None:
    from scripts.repository_evaluation.fact_grading import grade_facts

    check = {
        "id": "changed-declaration",
        "pointer": "/symbols/*",
        "predicate": "includes_record",
        "value": {"path": "backend.py", "symbol": "handler", "start_line": 10},
    }
    packet = {
        "symbols": [
            {"path": "backend.py", "symbol": "handler", "start_line": 5},
            {"path": "other.py", "symbol": "handler", "start_line": 10},
        ]
    }
    report = grade_facts("range", {"packet": packet}, {"checks": [check]})
    assert report["classification"] == "OTHER_FAILURE"
    packet["symbols"][0]["start_line"] = 10
    assert (
        grade_facts("range", {"packet": packet}, {"checks": [check]})["classification"]
        == "PASS"
    )


def test_exact_source_facts_can_appear_in_different_public_records() -> None:
    from scripts.repository_evaluation.fact_grading import grade_facts

    expected = {"path": "backend.py", "start_line": 5, "end_line": 8}
    check = {
        "id": "changed-declaration",
        "pointer": "/retrieval/results/*",
        "predicate": "includes_record",
        "value": {**expected, "symbol": "Backend.handler"},
        "alternative_records": [
            {
                "pointer": "/ownership/candidate",
                "value": {**expected, "qualname": "Backend.handler"},
            },
        ],
    }
    packet = {"ownership": {"candidate": {**expected, "qualname": "Backend.handler"}}}
    assert (
        grade_facts("range", {"packet": packet}, {"checks": [check]})["classification"]
        == "PASS"
    )
    packet["ownership"]["candidate"]["start_line"] = 4
    assert (
        grade_facts("range", {"packet": packet}, {"checks": [check]})["classification"]
        == "OTHER_FAILURE"
    )
    check["authority_check"] = True
    with pytest.raises(ValueError, match="positive source-fact"):
        grade_facts("range", {"packet": packet}, {"checks": [check]})


def test_scoped_sites_cannot_mix_declarations_or_pass_empty_oracles() -> None:
    from scripts.repository_evaluation.fact_grading import grade_facts

    check = {
        "id": "awaited-stop",
        "pointer": "/functions/*",
        "predicate": "includes_scoped_record",
        "value": {
            "scope": {"subject": "service.py::stop.worker"},
            "pointer": "/sites/*",
            "record": {"line": 8, "callee_identifier_syntax": "sub.stop"},
        },
    }
    packet = {
        "functions": [
            {"subject": "service.py::stop.worker", "sites": []},
            {
                "subject": "service.py::stop",
                "sites": [{"line": 8, "callee_identifier_syntax": "sub.stop"}],
            },
        ]
    }
    assert (
        grade_facts("scopes", {"packet": packet}, {"checks": [check]})["classification"]
        == "OTHER_FAILURE"
    )
    packet["functions"][0]["sites"] = packet["functions"][1]["sites"]
    assert (
        grade_facts("scopes", {"packet": packet}, {"checks": [check]})["classification"]
        == "PASS"
    )
    check["value"]["record"] = {}
    with pytest.raises(ValueError, match="scoped source fact"):
        grade_facts("scopes", {"packet": packet}, {"checks": [check]})


@pytest.mark.parametrize(
    "mutation", [None, "wrong-path", "wrong-revision", "split-scope"]
)
def test_positive_scoped_alternatives_keep_their_own_source_binding(
    mutation: str | None,
) -> None:
    from scripts.repository_evaluation.fact_grading import grade_facts

    binding = {"path": "tests/test_worker.py", "revision": "exact"}
    check = {
        "id": "relevant-existing-test",
        "pointer": "/selected/*",
        "predicate": "includes_scoped_record",
        "value": {
            "scope": binding,
            "pointer": "/tests/*",
            "record": {"symbol": "test_sync"},
        },
        "alternative_records": [
            {
                "pointer": "/candidates/*",
                "value": {
                    "scope": binding,
                    "pointer": "/tests/*",
                    "record": {"symbol": "test_async"},
                },
            },
        ],
        "support": "supported",
    }
    candidate = {**binding, "tests": [{"symbol": "test_async"}]}
    packet = {"selected": [], "candidates": [candidate]}
    if mutation == "wrong-path":
        candidate["path"] = "tests/test_other.py"
    elif mutation == "wrong-revision":
        candidate["revision"] = "stale"
    elif mutation == "split-scope":
        packet["candidates"] = [
            {**binding, "tests": []},
            {
                "path": "tests/other.py",
                "revision": "exact",
                "tests": [{"symbol": "test_async"}],
            },
        ]
    assert grade_facts("scopes", {"packet": packet}, {"checks": [check]})[
        "classification"
    ] == ("PASS" if mutation is None else "OTHER_FAILURE")
    check["authority_check"] = True
    with pytest.raises(ValueError, match="positive source-fact"):
        grade_facts("scopes", {"packet": packet}, {"checks": [check]})


def test_initial_source_oracle_reads_lossless_tables_without_hydrating_missing_facts() -> (
    None
):
    from hashmarks.operation_contract import operation_schema
    from scripts.repository_evaluation.fact_grading import grade_facts

    packet = {
        "schema": operation_schema("task_evidence", "initial"),
        "verification": {
            "candidates_encoding": {
                "kind": "columns-rows-with-extras.v1",
                "columns": ["path", "current"],
            },
            "candidates": [["tests/test_backend.py", False, {}]],
        },
    }
    check = {
        "id": "existing-test",
        "pointer": "/verification/candidates/*",
        "predicate": "includes_record",
        "value": {"path": "tests/test_backend.py", "current": False},
    }
    assert (
        grade_facts("initial", {"packet": packet}, {"checks": [check]})[
            "classification"
        ]
        == "PASS"
    )
    check["value"]["current"] = True
    assert (
        grade_facts("initial", {"packet": packet}, {"checks": [check]})[
            "classification"
        ]
        == "OTHER_FAILURE"
    )
    packet["verification"]["candidates"][0][-1] = {"current": True}
    with pytest.raises(ValueError, match="overwrite"):
        grade_facts("initial", {"packet": packet}, {"checks": [check]})


def test_non_initial_provider_data_does_not_acquire_table_semantics() -> None:
    from scripts.repository_evaluation.fact_grading import pointer_values

    raw = [["literal", False, {}]]
    packet = {
        "records": raw,
        "records_encoding": {
            "kind": "columns-rows-with-extras.v1",
            "columns": ["name", "present"],
        },
    }
    assert pointer_values(packet, "/records") == [raw]


def test_capability_proof_requires_every_frozen_witness_context() -> None:
    workflows = _workflows()
    outcomes = _outcomes(workflows)
    outcomes[0]["gate_witnesses"] = [
        row for row in outcomes[0]["gate_witnesses"] if row["stage"] == "before"
    ]
    report = capability_matrix(workflows, outcomes)
    assert report["status"] == "INCOMPLETE"
    assert report["capabilities"][0]["gates"]["capability_proof"]["observed"] == 19


def test_capability_proof_rejects_duplicate_contexts() -> None:
    workflows = _workflows()
    outcomes = _outcomes(workflows)
    outcomes[0]["gate_witnesses"].append(dict(outcomes[0]["gate_witnesses"][0]))
    with pytest.raises(ValueError, match="duplicate backend gate witness context"):
        capability_matrix(workflows, outcomes)


def test_unknown_eligibility_does_not_manufacture_a_metric_unit() -> None:
    workflows = _workflows()
    del workflows[0]["metric_eligibility"]["owner_top_three"]
    report = capability_matrix(workflows, _outcomes(workflows))
    gate = report["capabilities"][0]["gates"]["owner_top_three"]
    assert gate["expected"] == 19
    assert gate["eligibility_missing"] == ["0"]
    assert gate["state"] == "INCOMPLETE"
