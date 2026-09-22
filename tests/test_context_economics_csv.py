from __future__ import annotations

import csv
import json

import pytest

from scripts.agent_evaluation.context_economics_csv import INPUT_SCHEMA, main


def _lane(tokens, elapsed):
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


def _report(native=None, hashmarks=None):
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


def _run(tmp_path, monkeypatch, report):
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
    tmp_path, monkeypatch
):
    raw, summary = _run(tmp_path, monkeypatch, _report())
    with raw.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["total_tokens"] for row in rows] == ["1100", "600"]
    with summary.open(encoding="utf-8", newline="") as handle:
        rows = {row["metric"]: row for row in csv.DictReader(handle)}
    assert float(rows["input_tokens"]["median_reduction_pct"]) == 50.0


def test_context_economics_csv_does_not_infer_missing_token_usage(
    tmp_path, monkeypatch
):
    lane = _lane(None, 10)
    raw, _ = _run(tmp_path, monkeypatch, _report(lane, lane))
    with raw.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert all(
        row["token_metrics_available"] == "False" and row["total_tokens"] == ""
        for row in rows
    )


def test_context_economics_csv_rejects_wrong_input_schema(tmp_path, monkeypatch):
    report = _report()
    report["schema"] = "wrong"
    with pytest.raises(ValueError, match="input must use schema"):
        _run(tmp_path, monkeypatch, report)


def test_context_economics_csv_rejects_duplicate_condition_rows(
    tmp_path, monkeypatch
):
    report = _report()
    duplicate = dict(report["repositories"][0]["lanes"]["native"]["tasks"][0])
    report["repositories"][0]["lanes"]["native"]["tasks"].append(duplicate)
    with pytest.raises(ValueError, match="duplicate economics row"):
        _run(tmp_path, monkeypatch, report)


def test_context_economics_csv_rejects_duplicate_raw_run_identity(
    tmp_path, monkeypatch
):
    report = _report()
    duplicate = dict(report["repositories"][0]["lanes"]["native"]["raw_runs"][0])
    report["repositories"][0]["lanes"]["native"]["raw_runs"].append(duplicate)
    with pytest.raises(ValueError, match="duplicate raw run task_id"):
        _run(tmp_path, monkeypatch, report)
