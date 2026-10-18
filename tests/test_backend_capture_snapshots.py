"""Retained capture surfaces and bytes cannot exchange authority."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.repository_evaluation.backend_grading import FactObservation
from scripts.repository_evaluation.backend_transport import _capture
from scripts.repository_evaluation.backend_witnesses import (
    captured_fact_observations,
    captured_fact_witnesses,
)
from scripts.repository_evaluation.common import write_json
from scripts.repository_evaluation.fact_grading import grade_facts


def _context() -> FactObservation:
    return FactObservation(
        "facts",
        "problem",
        "before",
        None,
        "api",
        "none",
        "/cases/problem/checks",
        None,
        ({"repository": "repo", "path": "owner.py", "revision": "revision"},),
    )


def test_cli_bytes_in_mcp_artifact_cannot_become_mcp_witness(tmp_path: Path) -> None:
    write_json(tmp_path / "api.json", {"value": 1})
    write_json(tmp_path / "cli.json", [])
    write_json(
        tmp_path / "mcp.json",
        [{"format": "none", **_capture({"value": 1}, '{"value":1}', transport="cli")}],
    )
    with pytest.raises(ValueError, match="transport differs from artifact surface"):
        captured_fact_witnesses(
            tmp_path,
            "",
            {
                "checks": [
                    {
                        "id": "value",
                        "pointer": "/value",
                        "predicate": "equals",
                        "value": 1,
                    }
                ]
            },
            _context(),
        )


def test_duplicate_capture_format_cannot_increase_witness_membership(
    tmp_path: Path,
) -> None:
    write_json(tmp_path / "api.json", {"value": 1})
    capture = {
        "format": "none",
        **_capture({"value": 1}, '{"value":1}', transport="cli"),
    }
    write_json(tmp_path / "cli.json", [capture, capture])
    write_json(tmp_path / "mcp.json", [])
    with pytest.raises(ValueError, match="duplicate formats"):
        list(captured_fact_observations(tmp_path, "", _context()))


def test_decoded_fact_and_bound_bytes_share_one_capture_snapshot(
    tmp_path: Path,
) -> None:
    write_json(tmp_path / "api.json", {"value": 1})
    write_json(tmp_path / "cli.json", [])
    write_json(tmp_path / "mcp.json", [])
    observations = captured_fact_observations(tmp_path, "", _context())
    first = next(observations)
    original = (tmp_path / "api.json").read_bytes()
    write_json(tmp_path / "api.json", {"value": 2})
    assert first.packet == first.response == {"value": 1}
    assert first.context.artifact == ("before/api.json", original)
    assert list(observations) == []


@pytest.mark.parametrize(
    "actual,expected,classification",
    [
        ([1, 2], [1, 2], "PASS"),
        ([2, 1], [1, 2], "OTHER_FAILURE"),
        ([True], [1], "OTHER_FAILURE"),
        ([1, 1], [1], "OTHER_FAILURE"),
        ([], [1], "OTHER_FAILURE"),
    ],
)
def test_ordered_fact_values_prove_exact_nonempty_returned_membership(
    actual: list[object], expected: list[object], classification: str
) -> None:
    result = grade_facts(
        "membership",
        {"packet": {"values": actual}},
        {
            "checks": [
                {
                    "id": "membership",
                    "pointer": "/values/*",
                    "predicate": "ordered_values_equal",
                    "value": expected,
                    "support": "supported",
                }
            ]
        },
    )
    assert result["classification"] == classification


@pytest.mark.parametrize("expected", [[], None, 1, {}])
def test_ordered_fact_values_cannot_manufacture_empty_absence(expected: object) -> None:
    with pytest.raises(ValueError, match="nonempty expected array"):
        grade_facts(
            "membership",
            {"packet": {}},
            {
                "checks": [
                    {
                        "id": "membership",
                        "pointer": "/missing/*",
                        "predicate": "ordered_values_equal",
                        "value": expected,
                    }
                ]
            },
        )
