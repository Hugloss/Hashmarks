from __future__ import annotations

import csv
import json

from scripts.agent_evaluation.context_economics_csv import main


def _run(tmp_path, monkeypatch, report):
    source, raw, summary = tmp_path / "r.json", tmp_path / "raw.csv", tmp_path / "summary.csv"
    source.write_text(json.dumps(report))
    monkeypatch.setattr("sys.argv", ["context_economics_csv", "--input", str(source), "--raw-csv", str(raw), "--summary-csv", str(summary)])
    assert main() == 0
    return raw, summary


def test_context_economics_csv_preserves_token_counters_and_paired_reduction(tmp_path, monkeypatch):
    def lane(tokens, elapsed):
        return {"tasks": [{"id": "t1", "completed": True, "correct_first_edit": True, "correct_verification": True, "elapsed_ms": elapsed, "usage": {"input_tokens": tokens, "cached_input_tokens": 0, "output_tokens": 100, "reasoning_output_tokens": 50, "total_tokens": tokens + 100}}], "raw_runs": [{"task_id": "t1", "events_sha256": "sha256:x", "stderr_sha256": "sha256:y"}]}
    report = {"protocol_identity": "sha256:p", "protocol": {"family": "fixture", "model": "m", "reasoning_effort": "high"}, "repositories": [{"name": "repo", "lanes": {"native": lane(1000, 100), "hashmarks": lane(500, 60)}}]}
    raw, summary = _run(tmp_path, monkeypatch, report)
    with raw.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [r["total_tokens"] for r in rows] == ["1100", "600"]
    with summary.open(newline="") as handle:
        rows = {r["metric"]: r for r in csv.DictReader(handle)}
    assert float(rows["input_tokens"]["median_reduction_pct"]) == 50.0


def test_context_economics_csv_does_not_infer_missing_token_usage(tmp_path, monkeypatch):
    lane = {"tasks": [{"id": "t1", "completed": True, "correct_first_edit": True, "correct_verification": False, "elapsed_ms": 10, "usage": {"total_tokens": None, "input_tokens": None}}], "raw_runs": [{"task_id": "t1"}]}
    report = {"protocol_identity": "sha256:p", "protocol": {}, "repositories": [{"name": "repo", "lanes": {"native": lane, "hashmarks": lane}}]}
    raw, _ = _run(tmp_path, monkeypatch, report)
    with raw.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert all(r["token_metrics_available"] == "False" and r["total_tokens"] == "" for r in rows)
