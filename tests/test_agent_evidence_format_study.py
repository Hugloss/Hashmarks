from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from hashmarks.codemap.repository_intelligence_query import repository_query_response
from scripts.agent_evaluation.agent_evidence_format_study import (
    emit_trials,
    summarize_grades,
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
