from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hashmarks._command_output import log_command_output

logger = logging.getLogger(__name__)

TRACE_SCHEMA = "hashmarks.agent-work-trace.v1"
REPORT_SCHEMA = "hashmarks.agent-work-score.v1"
EVENT_KINDS = {
    "search",
    "read",
    "action_packet",
    "edit_attempt",
    "verification",
    "scout",
}
_NON_NEGATIVE_FIELDS = (
    "started_at_ns",
    "finished_at_ns",
    "bytes",
    "estimated_tokens",
    "model_input_tokens",
    "model_output_tokens",
    "reasoning_tokens",
)


def _validate_event(event: object, path: Path, last_sequence: int) -> int:
    if not isinstance(event, dict) or event.get("kind") not in EVENT_KINDS:
        raise ValueError(f"invalid work event: {path}")
    sequence = event.get("sequence")
    if (
        not isinstance(sequence, int)
        or isinstance(sequence, bool)
        or sequence <= last_sequence
    ):
        raise ValueError(f"event sequence must be strictly increasing: {path}")
    for field in _NON_NEGATIVE_FIELDS:
        if field in event and (
            not isinstance(event[field], int)
            or isinstance(event[field], bool)
            or event[field] < 0
        ):
            raise ValueError(f"{field} must be a non-negative integer: {path}")
    if (
        "started_at_ns" in event
        and "finished_at_ns" in event
        and event["finished_at_ns"] < event["started_at_ns"]
    ):
        raise ValueError(f"event time moved backwards: {path}")
    return sequence


def load_trace(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or value.get("schema") != TRACE_SCHEMA:
        raise ValueError(f"unsupported work trace: {path}")
    for field in ("task_id", "worker_kind"):
        if not isinstance(value.get(field), str) or not str(value[field]).strip():
            raise ValueError(f"{field} must be a non-empty string: {path}")
    events = value.get("events")
    if not isinstance(events, list):
        raise ValueError(f"events must be a list: {path}")
    last_sequence = -1
    for event in events:
        last_sequence = _validate_event(event, path, last_sequence)
    return value


def load_secret(path: Path) -> dict[str, set[str]]:
    value = json.loads(path.read_text())
    rows = value.get("tasks") if isinstance(value, dict) else None
    if not isinstance(rows, list):
        raise ValueError("SECRET tasks must be a list")
    result: dict[str, set[str]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            raise ValueError("invalid SECRET task row")
        result[row["id"]] = set(map(str, row.get("expected_files") or []))
    return result


@dataclass(frozen=True)
class EventGroups:
    edits: list[dict[str, Any]]
    reads: list[str]
    verifications: list[dict[str, Any]]
    scouts: list[dict[str, Any]]
    searches: list[dict[str, Any]]


@dataclass(frozen=True)
class VerificationHistory:
    repeated_disproven: int
    passed_targets: set[str]
    failures: int
    not_run: int


@dataclass(frozen=True)
class ResourceTotals:
    bytes_read: int
    evidence_tokens: int
    model_input: int
    model_output: int
    reasoning: int


def _event_groups(events: list[dict[str, Any]]) -> EventGroups:
    return EventGroups(
        edits=[
            event
            for event in events
            if event["kind"] == "edit_attempt" and isinstance(event.get("path"), str)
        ],
        reads=[
            str(event["path"])
            for event in events
            if event["kind"] == "read" and isinstance(event.get("path"), str)
        ],
        verifications=[event for event in events if event["kind"] == "verification"],
        scouts=[event for event in events if event["kind"] == "scout"],
        searches=[event for event in events if event["kind"] == "search"],
    )


def _verification_history(events: list[dict[str, Any]]) -> VerificationHistory:
    disproven: set[str] = set()
    passed_targets: set[str] = set()
    repeated_disproven = failures = not_run = 0
    for event in events:
        if event["kind"] == "edit_attempt" and isinstance(event.get("path"), str):
            repeated_disproven += str(event["path"]) in disproven
        if event["kind"] != "verification":
            continue
        target = event.get("edit_target")
        outcome = event.get("outcome")
        if outcome == "failed" and isinstance(target, str):
            disproven.add(target)
            failures += 1
        elif outcome == "passed" and isinstance(target, str):
            passed_targets.add(target)
        elif outcome in {"not-run", "selected"}:
            not_run += 1
    return VerificationHistory(repeated_disproven, passed_targets, failures, not_run)


def _resource_totals(events: list[dict[str, Any]]) -> ResourceTotals:
    return ResourceTotals(
        bytes_read=sum(int(event.get("bytes", 0)) for event in events),
        evidence_tokens=sum(int(event.get("estimated_tokens", 0)) for event in events),
        model_input=sum(int(event.get("model_input_tokens", 0)) for event in events),
        model_output=sum(int(event.get("model_output_tokens", 0)) for event in events),
        reasoning=sum(int(event.get("reasoning_tokens", 0)) for event in events),
    )


def _timing_metrics(
    events: list[dict[str, Any]], edits: list[dict[str, Any]], expected_files: set[str]
) -> tuple[int | None, int | None]:
    starts = [
        int(event["started_at_ns"]) for event in events if "started_at_ns" in event
    ]
    finishes = [
        int(event["finished_at_ns"]) for event in events if "finished_at_ns" in event
    ]
    trace_start = min(starts) if starts else None
    trace_finish = max(finishes) if finishes else None
    wall_ns = (
        trace_finish - trace_start
        if trace_start is not None and trace_finish is not None
        else None
    )
    if trace_start is None:
        return wall_ns, None
    first_correct = next(
        (
            int(event["started_at_ns"]) - trace_start
            for event in edits
            if str(event["path"]) in expected_files and "started_at_ns" in event
        ),
        None,
    )
    return wall_ns, first_correct


def score_trace(trace: dict[str, Any], expected_files: set[str]) -> dict[str, Any]:
    events = trace["events"]
    groups = _event_groups(events)
    first_edit = str(groups.edits[0]["path"]) if groups.edits else None
    final_edit = str(groups.edits[-1]["path"]) if groups.edits else None
    first_correct = first_edit in expected_files if first_edit else False
    final_correct = final_edit in expected_files if final_edit else False
    wrong_edits = sum(
        str(event["path"]) not in expected_files for event in groups.edits
    )
    history = _verification_history(events)
    verified_solution = bool(final_correct and final_edit in history.passed_targets)
    duplicate_reads = len(groups.reads) - len(set(groups.reads))
    resources = _resource_totals(events)
    wall_ns, first_correct_edit_ns = _timing_metrics(
        events, groups.edits, expected_files
    )

    # Transparent decision/work rubric. Verification is deliberately worth 20
    # points, so a process worker that only selects a test cannot receive 100.
    work_score = 0
    work_score += 35 if final_correct else 0
    work_score += 15 if first_correct else 0
    work_score += 20 if verified_solution else 0
    work_score += 10 if history.repeated_disproven == 0 else 0
    work_score += 10 if wrong_edits == 0 else 0
    work_score += 5 if duplicate_reads == 0 else 0
    work_score += 5 if len(groups.scouts) == 0 else 0

    return {
        "task_id": trace["task_id"],
        "worker_kind": trace["worker_kind"],
        "model_identity": trace.get("model_identity"),
        "first_edit_target": first_edit,
        "final_edit_target": final_edit,
        "first_edit_correct": first_correct,
        "final_edit_correct": final_correct,
        "verified_solution": verified_solution,
        "work_score": work_score,
        "edit_attempts": len(groups.edits),
        "wrong_edit_attempts": wrong_edits,
        "repeated_disproven_targets": history.repeated_disproven,
        "verification_events": len(groups.verifications),
        "verification_failures": history.failures,
        "verification_not_run": history.not_run,
        "duplicate_reads": duplicate_reads,
        "search_calls": len(groups.searches),
        "scout_calls": len(groups.scouts),
        "bytes_read": resources.bytes_read,
        "estimated_evidence_tokens": resources.evidence_tokens,
        "model_input_tokens": resources.model_input or None,
        "model_output_tokens": resources.model_output or None,
        "reasoning_tokens": resources.reasoning or None,
        "wall_ns": wall_ns,
        "time_to_first_correct_edit_ns": first_correct_edit_ns,
    }


def score(paths: list[Path], secret_path: Path) -> dict[str, Any]:
    secret = load_secret(secret_path)
    rows = []
    for path in paths:
        trace = load_trace(path)
        task_id = str(trace["task_id"])
        if task_id not in secret:
            raise ValueError(f"SECRET has no task {task_id!r}")
        rows.append(score_trace(trace, secret[task_id]))
    rows.sort(key=lambda row: (row["task_id"], row["worker_kind"]))
    n = len(rows)
    verified = sum(row["verified_solution"] for row in rows)
    total_model_tokens = sum(
        (row["model_input_tokens"] or 0)
        + (row["model_output_tokens"] or 0)
        + (row["reasoning_tokens"] or 0)
        for row in rows
    )
    total_wall_ns = sum(row["wall_ns"] or 0 for row in rows)
    return {
        "schema": REPORT_SCHEMA,
        "summary": {
            "traces": n,
            "first_edit_correct": sum(row["first_edit_correct"] for row in rows),
            "final_edit_correct": sum(row["final_edit_correct"] for row in rows),
            "verified_solutions": verified,
            "average_work_score": (sum(row["work_score"] for row in rows) / n)
            if n
            else None,
            "wrong_edit_attempts": sum(row["wrong_edit_attempts"] for row in rows),
            "repeated_disproven_targets": sum(
                row["repeated_disproven_targets"] for row in rows
            ),
            "duplicate_reads": sum(row["duplicate_reads"] for row in rows),
            "scout_calls": sum(row["scout_calls"] for row in rows),
            "verification_failures": sum(row["verification_failures"] for row in rows),
            "verification_not_run": sum(row["verification_not_run"] for row in rows),
            "total_model_tokens": total_model_tokens or None,
            "model_tokens_per_verified_solution": (total_model_tokens / verified)
            if verified and total_model_tokens
            else None,
            "wall_ms_per_verified_solution": (total_wall_ns / 1_000_000 / verified)
            if verified and total_wall_ns
            else None,
        },
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("traces", nargs="+", type=Path)
    parser.add_argument("--secret", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = score(args.traces, args.secret)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n")
    log_command_output(logger, rendered)


if __name__ == "__main__":
    main()
