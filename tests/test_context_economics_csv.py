from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from contract_assertions import assert_array, assert_object, assert_records

from scripts.agent_evaluation.context_economics_csv import INPUT_SCHEMA, main


def _lane(tokens: int | None, elapsed: int) -> dict[str, object]:
    return {
        "tasks": [
            {
                "id": "t1",
                "completed": True,
                "correct_first_edit": True,
                "correct_verification": True,
                "elapsed_ms": elapsed,
                "usage": {
                    "input_tokens": tokens,
                    "cached_input_tokens": 0,
                    "output_tokens": 100,
                    "reasoning_output_tokens": 50,
                    "total_tokens": None if tokens is None else tokens + 100,
                },
            }
        ],
        "raw_runs": [
            {
                "task_id": "t1",
                "events_sha256": "sha256:x",
                "stderr_sha256": "sha256:y",
            }
        ],
    }


def _report(
    native: dict[str, object] | None = None, hashmarks: dict[str, object] | None = None
) -> dict[str, object]:
    return {
        "schema": INPUT_SCHEMA,
        "protocol_identity": "sha256:p",
        "protocol": {
            "family": "fixture",
            "model": "m",
            "reasoning_effort": "high",
        },
        "repositories": [
            {
                "name": "repo",
                "lanes": {
                    "native": native or _lane(1000, 100),
                    "hashmarks": hashmarks or _lane(500, 60),
                },
            }
        ],
    }


def _run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, report: dict[str, object]
) -> tuple[Path, Path]:
    source = tmp_path / "r.json"
    raw = tmp_path / "raw.csv"
    summary = tmp_path / "summary.csv"
    source.write_text(json.dumps(report), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "context_economics_csv",
            "--input",
            str(source),
            "--raw-csv",
            str(raw),
            "--summary-csv",
            str(summary),
        ],
    )
    assert main() == 0
    return raw, summary


def test_context_economics_csv_preserves_token_counters_and_paired_reduction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw, summary = _run(tmp_path, monkeypatch, _report())
    with raw.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["total_tokens"] for row in rows] == ["1100", "600"]
    with summary.open(encoding="utf-8", newline="") as handle:
        rows = {row["metric"]: row for row in csv.DictReader(handle)}
    assert float(rows["input_tokens"]["median_reduction_pct"]) == 50.0


def test_context_economics_csv_does_not_infer_missing_token_usage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lane = _lane(None, 10)
    raw, _ = _run(tmp_path, monkeypatch, _report(lane, lane))
    with raw.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert all(
        row["token_metrics_available"] == "False" and row["total_tokens"] == ""
        for row in rows
    )


def test_context_economics_csv_rejects_wrong_input_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _report()
    report["schema"] = "wrong"
    with pytest.raises(ValueError, match="input must use schema"):
        _run(tmp_path, monkeypatch, report)


def test_context_economics_csv_rejects_duplicate_condition_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _report()
    lanes = assert_object(assert_records(report["repositories"])[0]["lanes"])
    tasks = assert_array(assert_object(lanes["native"])["tasks"])
    tasks.append(dict(assert_object(tasks[0])))
    with pytest.raises(ValueError, match="duplicate economics row"):
        _run(tmp_path, monkeypatch, report)


def test_context_economics_csv_rejects_duplicate_raw_run_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _report()
    lanes = assert_object(assert_records(report["repositories"])[0]["lanes"])
    runs = assert_array(assert_object(lanes["native"])["raw_runs"])
    runs.append(dict(assert_object(runs[0])))
    with pytest.raises(ValueError, match="duplicate raw run task_id"):
        _run(tmp_path, monkeypatch, report)


@pytest.mark.parametrize("counter", ["input_tokens", "total_tokens"])
def test_context_economics_csv_rejects_boolean_measurement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, counter: str
) -> None:
    lane = _lane(1000, 100)
    task = assert_records(lane["tasks"])[0]
    assert_object(task["usage"])[counter] = True
    with pytest.raises(ValueError, match="measurements must be numeric"):
        _run(tmp_path, monkeypatch, _report(native=lane))
