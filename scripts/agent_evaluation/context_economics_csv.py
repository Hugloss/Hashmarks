from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path
from typing import Any

SCHEMA = "hashmarks.context-economics-csv.v1"
LANES = ("native", "hashmarks")


def _rows(report: dict[str, Any]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    protocol = report.get("protocol", {})
    protocol_identity = report.get("protocol_identity")
    for repo in report.get("repositories", []):
        name = str(repo["name"])
        for lane in LANES:
            lane_report = repo.get("lanes", {}).get(lane)
            if not isinstance(lane_report, dict):
                continue
            raw = {
                str(item.get("task_id")): item
                for item in lane_report.get("raw_runs", [])
                if isinstance(item, dict)
            }
            for task in lane_report.get("tasks", []):
                task_id = str(task["id"])
                run = raw.get(task_id, {})
                usage = task.get("usage") or {}
                rows.append(
                    {
                        "schema": SCHEMA,
                        "protocol_identity": protocol_identity,
                        "family": protocol.get("family"),
                        "model": protocol.get("model"),
                        "reasoning_effort": protocol.get("reasoning_effort"),
                        "repository": name,
                        "task_id": task_id,
                        "condition": lane,
                        "completed": bool(task.get("completed")),
                        "correct_first_edit": bool(task.get("correct_first_edit")),
                        "correct_verification": bool(task.get("correct_verification")),
                        "joint_success": bool(task.get("correct_first_edit"))
                        and bool(task.get("correct_verification")),
                        "elapsed_ms": float(task.get("elapsed_ms") or 0),
                        "input_tokens": usage.get("input_tokens"),
                        "cached_input_tokens": usage.get("cached_input_tokens"),
                        "output_tokens": usage.get("output_tokens"),
                        "reasoning_output_tokens": usage.get("reasoning_output_tokens"),
                        "total_tokens": usage.get("total_tokens"),
                        "token_metrics_available": usage.get("total_tokens") is not None,
                        "events_sha256": run.get("events_sha256"),
                        "stderr_sha256": run.get("stderr_sha256"),
                    }
                )
    return rows


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * p
    lo, hi = math.floor(index), math.ceil(index)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (index - lo)


def _summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    by_key: dict[tuple[str, str], dict[str, dict[str, object]]] = {}
    for row in rows:
        by_key.setdefault((str(row["repository"]), str(row["task_id"])), {})[
            str(row["condition"])
        ] = row
    paired = [pair for pair in by_key.values() if set(pair) == set(LANES)]
    out: list[dict[str, object]] = []
    for metric in ("input_tokens", "total_tokens", "elapsed_ms"):
        usable = [
            pair
            for pair in paired
            if pair["native"].get(metric) is not None
            and pair["hashmarks"].get(metric) is not None
            and float(pair["native"][metric]) > 0
        ]
        reductions = [
            100.0
            * (float(pair["native"][metric]) - float(pair["hashmarks"][metric]))
            / float(pair["native"][metric])
            for pair in usable
        ]
        out.append(
            {
                "metric": metric,
                "paired_tasks": len(usable),
                "mean_reduction_pct": statistics.fmean(reductions) if reductions else None,
                "median_reduction_pct": statistics.median(reductions) if reductions else None,
                "p90_reduction_pct": _percentile(reductions, 0.90),
                "p95_reduction_pct": _percentile(reductions, 0.95),
            }
        )
    for lane in LANES:
        lane_rows = [row for row in rows if row["condition"] == lane]
        successes = sum(bool(row["joint_success"]) for row in lane_rows)
        tokens = [
            float(row["total_tokens"])
            for row in lane_rows
            if row["total_tokens"] is not None
        ]
        out.append(
            {
                "metric": f"{lane}_outcomes",
                "paired_tasks": len(lane_rows),
                "mean_reduction_pct": successes / len(lane_rows) if lane_rows else None,
                "median_reduction_pct": sum(tokens) / successes
                if tokens and successes
                else None,
                "p90_reduction_pct": None,
                "p95_reduction_pct": None,
            }
        )
    return out


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Project native-vs-Hashmarks Codex economics evidence to CSV."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--raw-csv", type=Path, required=True)
    parser.add_argument("--summary-csv", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.input.read_text())
    rows = _rows(report)
    _write_csv(args.raw_csv, rows)
    _write_csv(args.summary_csv, _summary(rows))
    print(  # noqa: T201 - intentional command output
        json.dumps(
            {
                "schema": SCHEMA,
                "raw_rows": len(rows),
                "raw_csv": str(args.raw_csv),
                "summary_csv": str(args.summary_csv),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
