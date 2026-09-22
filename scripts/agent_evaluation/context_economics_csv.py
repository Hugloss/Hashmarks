from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA = "hashmarks.context-economics-csv.v1"
INPUT_SCHEMA = "hashmarks.codex-agent-economics.v1"
LANES = ("native", "hashmarks")


def _load_report(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict) or value.get("schema") != INPUT_SCHEMA:
        raise ValueError(f"input must use schema {INPUT_SCHEMA}")
    repositories = value.get("repositories")
    if not isinstance(repositories, list):
        raise ValueError("input repositories must be a list")
    return value


def _raw_runs_by_task(lane_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw: dict[str, dict[str, Any]] = {}
    for item in lane_report.get("raw_runs", []):
        if not isinstance(item, dict):
            continue
        task_id = str(item.get("task_id") or "")
        if not task_id:
            continue
        if task_id in raw:
            raise ValueError(f"duplicate raw run task_id: {task_id}")
        raw[task_id] = item
    return raw


@dataclass
class _ProjectionContext:
    protocol: dict[str, Any]
    protocol_identity: object
    seen: set[tuple[str, str, str]] = field(default_factory=set)

    def task_row(
        self,
        repository: str,
        lane: str,
        task: object,
        raw: dict[str, dict[str, Any]],
    ) -> dict[str, object]:
        if not isinstance(task, dict):
            raise ValueError("task rows must be objects")
        task_id = str(task.get("id") or "")
        if not task_id:
            raise ValueError("task id must not be empty")
        identity = (repository, task_id, lane)
        if identity in self.seen:
            raise ValueError(
                f"duplicate economics row: repository={repository} "
                f"task_id={task_id} condition={lane}"
            )
        self.seen.add(identity)
        usage = task.get("usage") or {}
        if not isinstance(usage, dict):
            raise ValueError("task usage must be an object")
        run = raw.get(task_id, {})
        return self._project_task(repository, lane, task_id, task, usage, run)

    def _project_task(
        self,
        repository: str,
        lane: str,
        task_id: str,
        task: dict[str, Any],
        usage: dict[str, Any],
        run: dict[str, Any],
    ) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "protocol_identity": self.protocol_identity,
            "family": self.protocol.get("family"),
            "model": self.protocol.get("model"),
            "reasoning_effort": self.protocol.get("reasoning_effort"),
            "repository": repository,
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


def _projection_context(report: dict[str, Any]) -> _ProjectionContext:
    protocol = report.get("protocol", {})
    if not isinstance(protocol, dict):
        raise ValueError("input protocol must be an object")
    return _ProjectionContext(
        protocol=protocol,
        protocol_identity=report.get("protocol_identity"),
    )


def _repository_rows(
    repo: object,
    context: _ProjectionContext,
) -> list[dict[str, object]]:
    if not isinstance(repo, dict):
        raise ValueError("repository rows must be objects")
    name = str(repo.get("name") or "")
    if not name:
        raise ValueError("repository name must not be empty")
    lanes = repo.get("lanes", {})
    if not isinstance(lanes, dict):
        raise ValueError("repository lanes must be an object")
    rows: list[dict[str, object]] = []
    for lane in LANES:
        lane_report = lanes.get(lane)
        if not isinstance(lane_report, dict):
            continue
        raw = _raw_runs_by_task(lane_report)
        rows.extend(
            context.task_row(name, lane, task, raw)
            for task in lane_report.get("tasks", [])
        )
    return rows


def _rows(report: dict[str, Any]) -> list[dict[str, object]]:
    context = _projection_context(report)
    rows: list[dict[str, object]] = []
    for repo in report.get("repositories", []):
        rows.extend(_repository_rows(repo, context))
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
                "mean_reduction_pct": (
                    statistics.fmean(reductions) if reductions else None
                ),
                "median_reduction_pct": (
                    statistics.median(reductions) if reductions else None
                ),
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
                "mean_reduction_pct": (
                    successes / len(lane_rows) if lane_rows else None
                ),
                "median_reduction_pct": (
                    sum(tokens) / successes if tokens and successes else None
                ),
                "p90_reduction_pct": None,
                "p95_reduction_pct": None,
            }
        )
    return out


def _write_csv(path: Path, rows: list[dict[str, object]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
    else:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Project native-vs-Hashmarks Codex economics evidence to CSV."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--raw-csv", type=Path, required=True)
    parser.add_argument("--summary-csv", type=Path, required=True)
    args = parser.parse_args()
    report = _load_report(args.input)
    rows = _rows(report)
    summary = _summary(rows)
    raw_sha256 = _write_csv(args.raw_csv, rows)
    summary_sha256 = _write_csv(args.summary_csv, summary)
    print(  # noqa: T201 - intentional command output
        json.dumps(
            {
                "schema": SCHEMA,
                "input_schema": INPUT_SCHEMA,
                "raw_rows": len(rows),
                "summary_rows": len(summary),
                "raw_csv": str(args.raw_csv),
                "raw_csv_sha256": raw_sha256,
                "summary_csv": str(args.summary_csv),
                "summary_csv_sha256": summary_sha256,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
