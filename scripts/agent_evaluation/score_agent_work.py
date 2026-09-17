from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

TRACE_SCHEMA = "hashmarks.agent-work-trace.v1"
REPORT_SCHEMA = "hashmarks.agent-work-score.v1"
EVENT_KINDS = {"search", "read", "action_packet", "edit_attempt", "verification", "scout"}


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
    last = -1
    for event in events:
        if not isinstance(event, dict) or event.get("kind") not in EVENT_KINDS:
            raise ValueError(f"invalid work event: {path}")
        seq = event.get("sequence")
        if not isinstance(seq, int) or isinstance(seq, bool) or seq <= last:
            raise ValueError(f"event sequence must be strictly increasing: {path}")
        last = seq
        for field in ("started_at_ns", "finished_at_ns", "bytes", "estimated_tokens", "model_input_tokens", "model_output_tokens", "reasoning_tokens"):
            if field in event and (not isinstance(event[field], int) or isinstance(event[field], bool) or event[field] < 0):
                raise ValueError(f"{field} must be a non-negative integer: {path}")
        if "started_at_ns" in event and "finished_at_ns" in event and event["finished_at_ns"] < event["started_at_ns"]:
            raise ValueError(f"event time moved backwards: {path}")
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


def score_trace(trace: dict[str, Any], expected_files: set[str]) -> dict[str, Any]:
    events = trace["events"]
    edits = [event for event in events if event["kind"] == "edit_attempt" and isinstance(event.get("path"), str)]
    reads = [str(event["path"]) for event in events if event["kind"] == "read" and isinstance(event.get("path"), str)]
    verifications = [event for event in events if event["kind"] == "verification"]
    scouts = [event for event in events if event["kind"] == "scout"]
    searches = [event for event in events if event["kind"] == "search"]

    first_edit = str(edits[0]["path"]) if edits else None
    final_edit = str(edits[-1]["path"]) if edits else None
    first_correct = first_edit in expected_files if first_edit else False
    final_correct = final_edit in expected_files if final_edit else False
    wrong_edits = sum(str(event["path"]) not in expected_files for event in edits)

    disproven: set[str] = set()
    repeated_disproven = 0
    passed_targets: set[str] = set()
    verification_failures = 0
    verification_not_run = 0
    for event in events:
        if event["kind"] == "edit_attempt" and isinstance(event.get("path"), str):
            if str(event["path"]) in disproven:
                repeated_disproven += 1
        if event["kind"] != "verification":
            continue
        target = event.get("edit_target")
        outcome = event.get("outcome")
        if outcome == "failed" and isinstance(target, str):
            disproven.add(target)
            verification_failures += 1
        elif outcome == "passed" and isinstance(target, str):
            passed_targets.add(target)
        elif outcome in {"not-run", "selected"}:
            verification_not_run += 1

    verified_solution = bool(final_correct and final_edit in passed_targets)
    duplicate_reads = len(reads) - len(set(reads))
    bytes_read = sum(int(event.get("bytes", 0)) for event in events)
    evidence_tokens = sum(int(event.get("estimated_tokens", 0)) for event in events)
    model_input = sum(int(event.get("model_input_tokens", 0)) for event in events)
    model_output = sum(int(event.get("model_output_tokens", 0)) for event in events)
    reasoning = sum(int(event.get("reasoning_tokens", 0)) for event in events)

    starts = [int(event["started_at_ns"]) for event in events if "started_at_ns" in event]
    finishes = [int(event["finished_at_ns"]) for event in events if "finished_at_ns" in event]
    trace_start = min(starts) if starts else None
    trace_finish = max(finishes) if finishes else None
    wall_ns = trace_finish - trace_start if trace_start is not None and trace_finish is not None else None
    first_correct_edit_ns = None
    if trace_start is not None:
        for event in edits:
            if str(event["path"]) in expected_files and "started_at_ns" in event:
                first_correct_edit_ns = int(event["started_at_ns"]) - trace_start
                break

    # Transparent decision/work rubric. Verification is deliberately worth 20
    # points, so a process worker that only selects a test cannot receive 100.
    work_score = 0
    work_score += 35 if final_correct else 0
    work_score += 15 if first_correct else 0
    work_score += 20 if verified_solution else 0
    work_score += 10 if repeated_disproven == 0 else 0
    work_score += 10 if wrong_edits == 0 else 0
    work_score += 5 if duplicate_reads == 0 else 0
    work_score += 5 if len(scouts) == 0 else 0

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
        "edit_attempts": len(edits),
        "wrong_edit_attempts": wrong_edits,
        "repeated_disproven_targets": repeated_disproven,
        "verification_events": len(verifications),
        "verification_failures": verification_failures,
        "verification_not_run": verification_not_run,
        "duplicate_reads": duplicate_reads,
        "search_calls": len(searches),
        "scout_calls": len(scouts),
        "bytes_read": bytes_read,
        "estimated_evidence_tokens": evidence_tokens,
        "model_input_tokens": model_input or None,
        "model_output_tokens": model_output or None,
        "reasoning_tokens": reasoning or None,
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
    total_model_tokens = sum((row["model_input_tokens"] or 0) + (row["model_output_tokens"] or 0) + (row["reasoning_tokens"] or 0) for row in rows)
    total_wall_ns = sum(row["wall_ns"] or 0 for row in rows)
    return {
        "schema": REPORT_SCHEMA,
        "summary": {
            "traces": n,
            "first_edit_correct": sum(row["first_edit_correct"] for row in rows),
            "final_edit_correct": sum(row["final_edit_correct"] for row in rows),
            "verified_solutions": verified,
            "average_work_score": (sum(row["work_score"] for row in rows) / n) if n else None,
            "wrong_edit_attempts": sum(row["wrong_edit_attempts"] for row in rows),
            "repeated_disproven_targets": sum(row["repeated_disproven_targets"] for row in rows),
            "duplicate_reads": sum(row["duplicate_reads"] for row in rows),
            "scout_calls": sum(row["scout_calls"] for row in rows),
            "verification_failures": sum(row["verification_failures"] for row in rows),
            "verification_not_run": sum(row["verification_not_run"] for row in rows),
            "total_model_tokens": total_model_tokens or None,
            "model_tokens_per_verified_solution": (total_model_tokens / verified) if verified and total_model_tokens else None,
            "wall_ms_per_verified_solution": (total_wall_ns / 1_000_000 / verified) if verified and total_wall_ns else None,
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
    print(rendered)


if __name__ == "__main__":
    main()
