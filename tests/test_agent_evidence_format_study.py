from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from hashmarks.codemap.repository_intelligence_query import repository_query_response
from hashmarks.mcp_contract import mcp_projection_summary
from scripts.agent_evaluation.agent_evidence_format_study import (
    emit_trials,
    summarize_grades,
    trial_identity,
)


def _manifest() -> dict[str, Any]:
    packet = {
        "schema": "hashmarks.repository-intelligence-delta.v1",
        "delta_identity": "fixture:delta",
        "semantic": {
            "possible_symbol_moves": [{"name": "move", "from": "a.py", "to": "b.py"}]
        },
    }
    return {
        "cases": [
            {
                "id": "candidate-not-move",
                "prompt": "Was this source move proven?",
                "operation": "repository_intelligence_query",
                "result_mode": "default",
                "packet": repository_query_response("delta", packet),
            }
        ]
    }


def test_production_study_uses_exact_live_query_envelopes_without_oracle_leak() -> None:
    manifest = _manifest()
    manifest["cases"][0]["oracle"] = "not-proven"
    trials: list[dict[str, Any]] = emit_trials(manifest)
    assert trials == emit_trials(manifest)
    assert len(trials) == 4
    assert len({row["prompt"] for row in trials}) == 1
    assert all("oracle" not in json.dumps(row) for row in trials)
    native = manifest["cases"][0]["packet"]
    for trial, format in zip(
        trials, ("none", "structured", "compact", "text"), strict=True
    ):
        assert trial["tool_response"] == repository_query_response(
            "delta", native["result"], presentation=format
        )
        assert trial["study_axis"] == "production-response"
    assert (
        trials[1]["tool_response"]["presentation"]["groups"][0]["findings"][0][
            "assertion"
        ]
        == "candidate_correspondence"
    )


def test_encoding_only_keeps_identical_facts_and_qualifications() -> None:
    trials: list[dict[str, Any]] = emit_trials(_manifest(), axis="encoding-only")
    assert len(trials) == 3
    assert json.loads(trials[0]["tool_response"]) == json.loads(
        trials[1]["tool_response"]
    )
    for trial in trials:
        assert "candidate_correspondence" in trial["tool_response"]
        assert "fixture:delta" in trial["tool_response"]
        assert "projection-only" in trial["tool_response"]
        assert "a.py" in trial["tool_response"] and "b.py" in trial["tool_response"]


def _grades(trials):
    return [
        {
            "case_id": row["case_id"],
            "model": "model-x",
            "variant": row["variant"],
            "correct": index != 0,
            "unsupported_claims": int(index == 0),
            "tokens": 100 - 10 * index,
        }
        for index, row in enumerate(trials)
    ]


def test_summary_accounts_for_wholly_missing_expected_pairs_and_names_exclusions() -> (
    None
):
    trials: list[dict[str, Any]] = emit_trials(_manifest())
    second = copy.deepcopy(trials)
    for row in second:
        row["case_id"] = "missing-case"
        row["trial_identity"] = trial_identity(row)
    result: dict[str, Any] = summarize_grades(
        _grades(trials), trials=trials + second, models=["model-x", "model-y"]
    )
    assert result["expected_pairs"] == 4
    assert result["complete_pairs"] == 1
    assert result["incomplete_pairs_excluded"] == 3
    assert {row["case_id"] for row in result["excluded_pairs"]} == {
        "missing-case",
        "candidate-not-move",
    }
    assert result["arms"][0]["correct"] == 0
    assert result["arms"][1]["correct"] == 1


def test_failure_nonresponse_and_missing_metrics_are_not_success_or_zero() -> None:
    trials: list[dict[str, Any]] = emit_trials(_manifest())
    grades = _grades(trials)
    grades[0] = {**grades[0], "status": "failure", "correct": True, "tokens": None}
    grades[1] = {
        **grades[1],
        "status": "nonresponse",
        "correct": True,
        "unsupported_claims": None,
    }
    result: dict[str, Any] = summarize_grades(grades, trials=trials, models=["model-x"])
    assert result["arms"][0]["correct"] == 0 and result["arms"][0]["failures"] == 1
    assert result["arms"][0]["total_tokens"] is None
    assert result["arms"][0]["total_tokens_unknown_runs"] == 1
    assert result["arms"][1]["correct"] == 0 and result["arms"][1]["nonresponses"] == 1
    assert result["arms"][1]["unsupported_claims"] is None


def test_every_grade_is_validated_even_when_pair_is_incomplete() -> None:
    trials: list[dict[str, Any]] = emit_trials(_manifest())
    for key in ("tokens", "unsupported_claims"):
        grade = _grades(trials)[0]
        grade[key] = True
        with pytest.raises(ValueError, match="metrics"):
            summarize_grades([grade], trials=trials, models=["model-x"])
    with pytest.raises(ValueError, match="unexpected"):
        summarize_grades(
            [{**_grades(trials)[0], "case_id": "unexpected"}],
            trials=trials,
            models=["model-x"],
        )
    with pytest.raises(ValueError, match="duplicate grade"):
        summarize_grades([_grades(trials)[0]] * 2, trials=trials, models=["model-x"])
    with pytest.raises(ValueError, match="unique"):
        emit_trials({"cases": _manifest()["cases"] * 2})
    with pytest.raises(ValueError, match="operation and result_mode"):
        manifest = _manifest()
        manifest["cases"][0].pop("operation")
        emit_trials(manifest)


def _host_capture(trial: dict[str, Any], *, model: str = "model-x") -> dict[str, Any]:
    response = trial["tool_response"]
    visible = (
        response
        if isinstance(response, str)
        else json.dumps(response, sort_keys=True, ensure_ascii=False)
    )
    return {
        "case_id": trial["case_id"],
        "model": model,
        "variant": trial["variant"],
        "trial_identity": trial["trial_identity"],
        "model_visible_response": visible,
    }


def test_exported_trials_are_reproducibly_bound_without_leaking_oracles() -> None:
    manifest = _manifest()
    manifest["cases"][0]["oracle"] = "never export answer"
    trials = emit_trials(manifest)
    assert all(t["trial_identity"] == trial_identity(t) for t in trials)
    assert len({t["trial_identity"] for t in trials}) == len(trials)
    assert trials == emit_trials(manifest)
    assert all("never export answer" not in json.dumps(t) for t in trials)
    mutated = copy.deepcopy(trials)
    mutated[0]["tool_response"]["result"]["delta_identity"] = "tampered"
    with pytest.raises(ValueError, match="trial identity mismatch"):
        summarize_grades([], trials=mutated, models=["model-x"])


@pytest.mark.parametrize("axis", ["production-response", "encoding-only"])
def test_capture_equivalence_requires_same_frozen_trial_and_actual_content(
    axis: str,
) -> None:
    trials = emit_trials(_manifest(), axis=axis)
    grades = _grades(trials)
    captures = [_host_capture(t) for t in trials]
    qualified = summarize_grades(
        grades, trials=trials, models=["model-x"], captures=captures
    )
    assert qualified["capture_equivalent_complete_pairs"] == 1
    assert qualified["capture_audit"]["observed_captures"] == len(trials)
    assert qualified["capture_audit"]["host_authenticity_proven"] is False
    assert qualified["capture_audit"]["content_mismatches"] == []
    assert all(
        item["model_visible_sha256"].startswith("sha256:")
        for item in qualified["capture_audit"]["capture_digests"]
    )
    assert qualified["capture_equivalent_arms"] == qualified["arms"]

    contaminated = copy.deepcopy(captures)
    contaminated[0]["model_visible_response"] = "wrong payload"
    rejected = summarize_grades(
        grades, trials=trials, models=["model-x"], captures=contaminated
    )
    assert rejected["complete_pairs"] == 1
    assert rejected["capture_equivalent_complete_pairs"] == 0
    assert rejected["capture_equivalent_arms"][0]["paired_runs"] == 0
    assert rejected["capture_audit"]["content_mismatches"] == [
        {
            "case_id": trials[0]["case_id"],
            "model": "model-x",
            "variant": trials[0]["variant"],
        }
    ]


def test_missing_host_captures_do_not_turn_into_measured_absence() -> None:
    trials = emit_trials(_manifest())
    baseline = summarize_grades(_grades(trials), trials=trials, models=["model-x"])
    assert baseline["capture_audit"] is None
    assert baseline["capture_equivalent_complete_pairs"] is None
    captures = [_host_capture(t) for t in trials[1:]]
    observed = summarize_grades(
        _grades(trials), trials=trials, models=["model-x", "model-y"], captures=captures
    )
    assert observed["expected_pairs"] == 2
    assert observed["complete_pairs"] == 1
    assert observed["capture_equivalent_complete_pairs"] == 0
    assert len(observed["capture_audit"]["missing_captures"]) == len(trials) + 1
    assert observed["capture_unqualified_complete_pairs"] == [
        {"case_id": trials[0]["case_id"], "model": "model-x"}
    ]


def test_captures_fail_on_forged_trial_duplicates_and_unexpected_models() -> None:
    trials = emit_trials(_manifest())
    valid = _host_capture(trials[0])
    cases = [
        ([{**valid, "trial_identity": "sha256:forged"}], "identity mismatch"),
        ([valid, valid], "duplicate host capture"),
        ([{**valid, "model": "unknown-model"}], "unexpected host capture"),
        ([{**valid, "model_visible_response": False}], "must be a string"),
        ([{**valid, "model_visible_response": "x" * 1_048_577}], "byte limit"),
    ]
    for captures, message in cases:
        with pytest.raises(ValueError, match=message):
            summarize_grades(
                _grades(trials),
                trials=trials,
                models=["model-x"],
                captures=captures,
            )


def test_encoding_capture_checks_exact_text_not_only_equivalent_json() -> None:
    trials = emit_trials(_manifest(), axis="encoding-only")
    captures = [_host_capture(t) for t in trials]
    formatted_json = captures[1]["model_visible_response"]
    captures[1]["model_visible_response"] = json.dumps(json.loads(formatted_json))
    assert captures[1]["model_visible_response"] != formatted_json
    summary = summarize_grades(
        _grades(trials), trials=trials, models=["model-x"], captures=captures
    )
    assert summary["capture_equivalent_complete_pairs"] == 0


def _projection(names: tuple[str, ...] = ("find",)) -> dict[str, Any]:
    return mcp_projection_summary(
        {"contract_identity": "sha256:" + "a" * 64}, names
    )


def _projected_trials(axis: str = "production-response") -> list[dict[str, Any]]:
    manifest = _manifest()
    manifest["mcp_projection"] = _projection(("find", "task_evidence"))
    return emit_trials(manifest, axis=axis)


def _projected_capture(trial: dict[str, Any]) -> dict[str, Any]:
    capture = _host_capture(trial)
    projection = trial["mcp_projection"]
    return {
        **capture,
        "observed_tools": projection["tools"],
        "observed_contract_identity": projection["source_contract_identity"],
        "observed_projection_identity": projection["projection_identity"],
    }


@pytest.mark.parametrize("axis", ["production-response", "encoding-only"])
def test_projection_is_frozen_in_each_format_arm_without_oracle_leak(axis: str) -> None:
    manifest = _manifest()
    manifest["cases"][0]["oracle"] = "private answer"
    manifest["mcp_projection"] = _projection(("find", "task_evidence"))
    trials = emit_trials(manifest, axis=axis)
    assert len(trials) == (4 if axis == "production-response" else 3)
    assert all(row["mcp_projection"] == manifest["mcp_projection"] for row in trials)
    assert all(row["trial_identity"] == trial_identity(row) for row in trials)
    assert all("private answer" not in json.dumps(row) for row in trials)
    assert len({row["trial_identity"] for row in trials}) == len(trials)
    assert all("mcp_projection" not in row["tool_response"] for row in trials
               if isinstance(row["tool_response"], dict))
    different = copy.deepcopy(trials[0])
    different["mcp_projection"] = _projection(("task_evidence",))
    assert trial_identity(different) != trials[0]["trial_identity"]


@pytest.mark.parametrize("axis", ["production-response", "encoding-only"])
def test_model_visible_tool_catalog_qualifies_only_matching_projection(
    axis: str,
) -> None:
    trials = _projected_trials(axis)
    grades = _grades(trials)
    captures = [_projected_capture(trial) for trial in trials]
    result = summarize_grades(
        grades, trials=trials, models=["model-x"], captures=captures
    )
    assert result["capture_equivalent_complete_pairs"] == 1
    assert result["capture_audit"]["projection_equivalent_captures"] == len(trials)
    assert result["capture_audit"]["projection_catalog_mismatches"] == []
    assert result["capture_equivalent_arms"] == result["arms"]
    altered = copy.deepcopy(captures)
    altered[0]["observed_tools"] = ["find", "task_evidence", "structural_locality"]
    rejected = summarize_grades(
        grades, trials=trials, models=["model-x"], captures=altered
    )
    assert rejected["capture_equivalent_complete_pairs"] == 0
    assert rejected["capture_audit"]["content_equivalent_captures"] == len(trials)
    assert rejected["capture_audit"]["content_mismatches"] == []
    assert rejected["capture_audit"]["projection_equivalent_captures"] == len(trials) - 1
    assert rejected["capture_audit"]["projection_catalog_mismatches"] == [
        {
            "case_id": trials[0]["case_id"],
            "model": "model-x",
            "variant": trials[0]["variant"],
        }
    ]


def test_missing_or_foreign_host_projection_never_qualifies_pair() -> None:
    trials = _projected_trials()
    grades = _grades(trials)
    for update in (
        {"observed_tools": None},
        {"observed_contract_identity": "sha256:" + "b" * 64},
        {"observed_projection_identity": "sha256:" + "c" * 64},
        {"observed_tools": list(reversed(trials[0]["mcp_projection"]["tools"]))},
    ):
        captures = [_projected_capture(trial) for trial in trials]
        captures[0].update(update)
        result = summarize_grades(
            grades, trials=trials, models=["model-x"], captures=captures
        )
        assert result["capture_equivalent_complete_pairs"] == 0
        assert result["capture_audit"]["projection_catalog_mismatches"]
    with pytest.raises(ValueError, match="observed_tools"):
        captures = [_projected_capture(trial) for trial in trials]
        captures[0]["observed_tools"] = "find"
        summarize_grades(grades, trials=trials, models=["model-x"], captures=captures)


def test_projection_manifest_rejects_unknown_tools_reordering_and_forgery() -> None:
    invalid = [
        {"tools": []},
        {"tools": ["invented_tool"]},
        {"tools": ["find", "find"]},
        {"tools": ["task_evidence", "find"]},
        {"source_contract_identity": "not-a-sha256"},
        {"projection_identity": "sha256:wrong"},
        {"instructions": "consumer override"},
    ]
    for changes in invalid:
        manifest = _manifest()
        manifest["mcp_projection"] = {**_projection(("find", "task_evidence")), **changes}
        with pytest.raises(ValueError):
            emit_trials(manifest)
    manifest = _manifest()
    manifest["mcp_projection"] = None
    with pytest.raises(ValueError, match="must be an object"):
        emit_trials(manifest)


def test_mixed_projection_or_changed_trial_identity_rejected_before_grading() -> None:
    trials = _projected_trials()
    tampered = copy.deepcopy(trials)
    tampered[0]["mcp_projection"]["instructions"] = "overridden"
    tampered[0]["trial_identity"] = trial_identity(tampered[0])
    with pytest.raises(ValueError, match="canonical"):
        summarize_grades([], trials=tampered, models=["model-x"])
    mixed = copy.deepcopy(trials)
    mixed[0].pop("mcp_projection")
    mixed[0]["trial_identity"] = trial_identity(mixed[0])
    with pytest.raises(ValueError, match="one fixed MCP tool projection"):
        summarize_grades([], trials=mixed, models=["model-x"])
    different = copy.deepcopy(trials)
    different[0]["mcp_projection"] = _projection(("find",))
    different[0]["trial_identity"] = trial_identity(different[0])
    with pytest.raises(ValueError, match="one fixed MCP tool projection"):
        summarize_grades([], trials=different, models=["model-x"])


def test_legacy_trial_without_projection_keeps_unqualified_catalog_authority() -> None:
    trials = emit_trials(_manifest())
    result = summarize_grades(
        _grades(trials),
        trials=trials,
        models=["model-x"],
        captures=[_host_capture(trial) for trial in trials],
    )
    assert result["capture_equivalent_complete_pairs"] == 1
    assert result["capture_audit"]["projection_equivalent_captures"] is None
    assert result["capture_audit"]["projection_catalog_mismatches"] == []
    assert all(
        item["projection_equivalent"] is None
        for item in result["capture_audit"]["capture_digests"]
    )
