from __future__ import annotations

import json
from typing import TYPE_CHECKING

from scripts.agent_evaluation import score_agent_work as M

if TYPE_CHECKING:
    from pathlib import Path


def test_work_score_distinguishes_verified_solution_from_selected_test(
    tmp_path: Path,
) -> None:
    secret = tmp_path / "secret.json"
    secret.write_text(
        json.dumps({"tasks": [{"id": "t", "expected_files": ["src/a.py"]}]})
    )
    selected = tmp_path / "selected.json"
    selected.write_text(
        json.dumps(
            {
                "schema": M.TRACE_SCHEMA,
                "task_id": "t",
                "worker_kind": "process-worker",
                "events": [
                    {
                        "sequence": 1,
                        "kind": "edit_attempt",
                        "path": "src/a.py",
                        "started_at_ns": 10,
                        "finished_at_ns": 11,
                    },
                    {
                        "sequence": 2,
                        "kind": "verification",
                        "path": "tests/test_a.py",
                        "edit_target": "src/a.py",
                        "outcome": "not-run",
                        "started_at_ns": 12,
                        "finished_at_ns": 13,
                    },
                ],
            }
        )
    )
    verified = tmp_path / "verified.json"
    verified.write_text(
        json.dumps(
            {
                "schema": M.TRACE_SCHEMA,
                "task_id": "t",
                "worker_kind": "codex",
                "events": [
                    {
                        "sequence": 1,
                        "kind": "edit_attempt",
                        "path": "src/a.py",
                        "started_at_ns": 10,
                        "finished_at_ns": 11,
                    },
                    {
                        "sequence": 2,
                        "kind": "verification",
                        "path": "tests/test_a.py",
                        "edit_target": "src/a.py",
                        "outcome": "passed",
                        "started_at_ns": 12,
                        "finished_at_ns": 20,
                    },
                ],
            }
        )
    )
    report = M.score([selected, verified], secret)
    rows = {row["worker_kind"]: row for row in report["rows"]}
    assert rows["process-worker"]["verified_solution"] is False
    assert rows["process-worker"]["work_score"] == 80
    assert rows["codex"]["verified_solution"] is True
    assert rows["codex"]["work_score"] == 100


def test_work_score_penalizes_thrashing_and_duplicate_reads(tmp_path: Path) -> None:
    trace = {
        "schema": M.TRACE_SCHEMA,
        "task_id": "t",
        "worker_kind": "codex",
        "events": [
            {"sequence": 1, "kind": "read", "path": "src/wrong.py"},
            {"sequence": 2, "kind": "read", "path": "src/wrong.py"},
            {"sequence": 3, "kind": "edit_attempt", "path": "src/wrong.py"},
            {
                "sequence": 4,
                "kind": "verification",
                "edit_target": "src/wrong.py",
                "outcome": "failed",
            },
            {"sequence": 5, "kind": "edit_attempt", "path": "src/wrong.py"},
            {"sequence": 6, "kind": "edit_attempt", "path": "src/right.py"},
            {
                "sequence": 7,
                "kind": "verification",
                "edit_target": "src/right.py",
                "outcome": "passed",
            },
        ],
    }
    row = M.score_trace(trace, {"src/right.py"})
    assert row["verified_solution"] is True
    assert row["wrong_edit_attempts"] == 2
    assert row["repeated_disproven_targets"] == 1
    assert row["duplicate_reads"] == 1
    assert row["work_score"] < 100
