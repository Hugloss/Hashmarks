from __future__ import annotations

import json

import pytest

from scripts.agent_evaluation.agent_evidence_format_study import (
    emit_trials,
    summarize_grades,
)


def _manifest() -> dict[str, object]:
    return {
        "cases": [
            {
                "id": "candidate-not-move",
                "prompt": "Was this source move proven?",
                "packet": {
                    "schema": "hashmarks.repository-intelligence-delta.v1",
                    "delta_identity": "fixture:delta",
                    "semantic": {
                        "possible_symbol_moves": [
                            {"name": "move", "from": "a.py", "to": "b.py"}
                        ]
                    },
                },
            }
        ]
    }


def test_format_study_exports_four_fixed_task_arms_without_oracle_leak() -> None:
    value = _manifest()
    value["cases"][0]["oracle"] = "not-proven"
    first = emit_trials(value)
    assert first == emit_trials(value)
    assert len(first) == 4
    assert len({row["prompt"] for row in first}) == 1
    assert [row["variant"] for row in first] == [
        "native-json",
        "typed-json",
        "compact-json",
        "grouped-text",
    ]
    assert all("oracle" not in json.dumps(row) for row in first)
    assert first[1]["tool_response"]["groups"][0]["findings"][0]["assertion"] == (
        "candidate_correspondence"
    )


def test_format_study_only_scores_complete_paired_runs() -> None:
    variants = ("native-json", "typed-json", "compact-json", "grouped-text")
    grades = [
        {
            "case_id": "case1",
            "model": "model-x",
            "variant": variant,
            "correct": index != 0,
            "unsupported_claims": int(index == 0),
            "tokens": 100 - 10 * index,
        }
        for index, variant in enumerate(variants)
    ]
    grades.append(
        {
            "case_id": "case2",
            "model": "model-x",
            "variant": "native-json",
            "correct": True,
            "unsupported_claims": 0,
            "tokens": 10,
        }
    )
    result = summarize_grades(grades)
    assert result["complete_pairs"] == 1
    assert result["incomplete_pairs_excluded"] == 1
    assert result["arms"][0]["correct"] == 0
    assert result["arms"][1]["correct"] == 1
    assert result["arms"][0]["unsupported_claims"] == 1


def test_format_study_fail_closes_on_duplicate_trials_and_unsupported_format() -> None:
    with pytest.raises(ValueError, match="unique"):
        emit_trials({"cases": [_manifest()["cases"][0], _manifest()["cases"][0]]})
    with pytest.raises(ValueError, match="unknown trial variant"):
        summarize_grades([{"case_id": "one", "model": "m", "variant": "wrong"}])
