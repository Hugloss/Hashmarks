from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

from hashmarks._command_output import log_command_output

logger = logging.getLogger(__name__)

TRACE_SCHEMA = "hashmarks.agent-trace.v2"
VERDICT_SCHEMA = "hashmarks.agent-verdict.v1"
USAGE_SCHEMA = "hashmarks.agent-model-usage.v1"
REPORT_SCHEMA = "hashmarks.agent-trace-report.v3"
SEARCH_KINDS = {
    "grep",
    "glob",
    "repository_search",
    "hashmarks_find",
    "hashmarks_grep",
    "hashmarks_context",
}
FILE_READ_KINDS = {"file_read", "hashmarks_source"}
HASHMARKS_KINDS = {
    "hashmarks_map",
    "hashmarks_find",
    "hashmarks_grep",
    "hashmarks_context",
    "hashmarks_source",
}


def _validate_trace_event(event: Any, path: Path) -> None:
    if not isinstance(event, dict) or not isinstance(event.get("kind"), str):
        raise ValueError(f"invalid trace event: {path}")
    for field in (
        "bytes",
        "estimated_tokens",
        "model_input_tokens",
        "started_at_ns",
        "finished_at_ns",
    ):
        if field in event and (
            not isinstance(event[field], int)
            or isinstance(event[field], bool)
            or event[field] < 0
        ):
            raise ValueError(f"{field} must be a non-negative integer: {path}")
    for field in ("paths", "returned_paths", "evidence_paths"):
        if field in event and (
            not isinstance(event[field], list)
            or any(
                not isinstance(item, str) or not item.strip() for item in event[field]
            )
        ):
            raise ValueError(f"{field} must be a list of non-empty strings: {path}")
    if "path" in event and (
        not isinstance(event["path"], str) or not event["path"].strip()
    ):
        raise ValueError(f"path must be a non-empty string: {path}")
    if (
        "started_at_ns" in event
        and "finished_at_ns" in event
        and event["finished_at_ns"] < event["started_at_ns"]
    ):
        raise ValueError(f"finished_at_ns must be >= started_at_ns: {path}")


def _validate_exact_model_tokens(value: Any, path: Path) -> None:
    if value is not None and (
        not isinstance(value, int) or isinstance(value, bool) or value < 0
    ):
        raise ValueError(f"model_input_tokens must be a non-negative integer: {path}")


def load_trace(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != TRACE_SCHEMA:
        raise ValueError(f"unsupported agent trace schema: {path}")
    if value.get("mode") not in {"baseline", "hashmarks"}:
        raise ValueError(f"trace mode must be baseline or hashmarks: {path}")
    task_id = value.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError(f"trace task_id must be a non-empty string: {path}")
    for field in ("success", "patch_correct"):
        if field in value and not isinstance(value[field], bool):
            raise ValueError(f"trace {field} must be a boolean when present: {path}")
    events = value.get("events")
    if not isinstance(events, list):
        raise ValueError(f"trace events must be a list: {path}")
    for event in events:
        _validate_trace_event(event, path)
    _validate_exact_model_tokens(value.get("model_input_tokens"), path)
    return value


def load_verdict(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != VERDICT_SCHEMA:
        raise ValueError(f"unsupported agent verdict schema: {path}")
    for field in ("task_id", "mode", "run_id", "grader_identity", "evidence_digest"):
        item = value.get(field)
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"verdict {field} must be a non-empty string: {path}")
    if value["mode"] not in {"baseline", "hashmarks"}:
        raise ValueError(f"verdict mode must be baseline or hashmarks: {path}")
    for field in ("success", "patch_correct"):
        if not isinstance(value.get(field), bool):
            raise ValueError(f"verdict {field} must be a boolean: {path}")
    return value


def load_usage(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != USAGE_SCHEMA:
        raise ValueError(f"unsupported agent model-usage schema: {path}")
    for field in ("task_id", "mode", "run_id", "provider_identity", "evidence_digest"):
        item = value.get(field)
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"model usage {field} must be a non-empty string: {path}")
    if value["mode"] not in {"baseline", "hashmarks"}:
        raise ValueError(f"model usage mode must be baseline or hashmarks: {path}")
    tokens = value.get("model_input_tokens")
    if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens < 0:
        raise ValueError(
            f"model usage model_input_tokens must be a non-negative integer: {path}"
        )
    output_tokens = value.get("model_output_tokens")
    if output_tokens is not None and (
        not isinstance(output_tokens, int)
        or isinstance(output_tokens, bool)
        or output_tokens < 0
    ):
        raise ValueError(
            f"model usage model_output_tokens must be a non-negative integer when present: {path}"
        )
    return value


def summarize(trace: dict[str, Any]) -> dict[str, object]:
    events = trace["events"]
    exact_model_tokens = trace.get("model_input_tokens")
    event_model_tokens = sum(int(e.get("model_input_tokens", 0)) for e in events)
    estimated_tokens = sum(int(e.get("estimated_tokens", 0)) for e in events)
    return {
        "trace_schema": trace["schema"],
        "task_id": str(trace["task_id"]),
        "mode": trace["mode"],
        "run_id": trace.get("run_id"),
        "repository_identity": trace.get("repository_identity"),
        "task_revision": trace.get("task_revision"),
        "model_identity": trace.get("model_identity"),
        "model_config_identity": trace.get("model_config_identity"),
        "model_input_tokens_source": trace.get("model_input_tokens_source"),
        "success": trace.get("success"),
        "patch_correct": trace.get("patch_correct"),
        "events": len(events),
        "search_calls": sum(e["kind"] in SEARCH_KINDS for e in events),
        "file_reads": sum(e["kind"] in FILE_READ_KINDS for e in events),
        "hashmarks_calls": sum(e["kind"] in HASHMARKS_KINDS for e in events),
        "fallback_searches": sum(bool(e.get("fallback", False)) for e in events),
        "bytes_returned": sum(int(e.get("bytes", 0)) for e in events),
        "estimated_exploration_tokens": estimated_tokens,
        "model_input_tokens": exact_model_tokens
        if exact_model_tokens is not None
        else (event_model_tokens or None),
    }


def _paired_identity_blockers(
    baseline: dict[str, object], hashmarks: dict[str, object]
) -> list[str]:
    reasons: list[str] = []
    for field in (
        "repository_identity",
        "task_revision",
        "model_identity",
        "model_config_identity",
    ):
        left, right = baseline.get(field), hashmarks.get(field)
        if (
            not isinstance(left, str)
            or not left.strip()
            or not isinstance(right, str)
            or not right.strip()
        ):
            reasons.append(f"paired_{field}_missing")
        elif left != right:
            reasons.append(f"paired_{field}_mismatch")
    return reasons


def _mode_blockers(
    mode: str,
    row: dict[str, object],
    require_external_verdict: bool,
    require_external_usage: bool,
) -> list[str]:
    reasons = []
    if not isinstance(row.get("run_id"), str) or not str(row.get("run_id")).strip():
        reasons.append(f"{mode}_run_id_missing")
    if not isinstance(row.get("model_input_tokens"), int):
        reasons.append(f"{mode}_exact_model_tokens_missing")
    if (
        not isinstance(row.get("model_input_tokens_source"), str)
        or not str(row.get("model_input_tokens_source")).strip()
    ):
        reasons.append(f"{mode}_model_token_provenance_missing")
    if row.get("success") is not True:
        reasons.append(f"{mode}_success_not_true")
    if row.get("patch_correct") is not True:
        reasons.append(f"{mode}_patch_correct_not_true")
    if require_external_verdict and row.get("verdict_source") != "external":
        reasons.append(f"{mode}_external_verdict_missing")
    if require_external_usage and row.get("model_usage_source") != "external":
        reasons.append(f"{mode}_external_model_usage_missing")
    return reasons


def _pair_gate(
    baseline: dict[str, object],
    hashmarks: dict[str, object],
    *,
    require_external_verdict: bool,
    require_external_usage: bool,
) -> tuple[bool, list[str]]:
    reasons = _paired_identity_blockers(baseline, hashmarks)
    for mode, row in (("baseline", baseline), ("hashmarks", hashmarks)):
        reasons.extend(
            _mode_blockers(mode, row, require_external_verdict, require_external_usage)
        )
    if baseline.get("success") is True and hashmarks.get("success") is not True:
        reasons.append("success_regression")
    if (
        baseline.get("patch_correct") is True
        and hashmarks.get("patch_correct") is not True
    ):
        reasons.append("patch_correctness_regression")
    return not reasons, reasons


def _records_by_run(
    records: list[dict[str, Any]], record_name: str
) -> dict[tuple[str, str, str], dict[str, Any]]:
    indexed = {}
    for record in records:
        key = (
            str(record["task_id"]),
            str(record["mode"]),
            str(record["run_id"]),
        )
        if key in indexed:
            raise ValueError(f"duplicate {record_name} for run: " + ":".join(key))
        indexed[key] = record
    return indexed


def _bind_external_records(
    rows: list[dict[str, object]],
    verdicts: dict[tuple[str, str, str], dict[str, Any]],
    usages: dict[tuple[str, str, str], dict[str, Any]],
) -> None:
    for row in rows:
        run_id = row.get("run_id")
        key = (
            (str(row["task_id"]), str(row["mode"]), str(run_id))
            if isinstance(run_id, str)
            else None
        )
        verdict = verdicts.get(key) if key is not None else None
        if verdict is not None:
            row.update(
                success=verdict["success"],
                patch_correct=verdict["patch_correct"],
                verdict_source="external",
                grader_identity=verdict["grader_identity"],
                grader_evidence_digest=verdict["evidence_digest"],
            )
        else:
            row["verdict_source"] = (
                "trace"
                if row.get("success") is not None
                or row.get("patch_correct") is not None
                else None
            )
        usage = usages.get(key) if key is not None else None
        if usage is not None:
            row.update(
                model_input_tokens=usage["model_input_tokens"],
                model_usage_source="external",
                model_input_tokens_source="external-provider-usage",
                model_usage_provider_identity=usage["provider_identity"],
                model_usage_evidence_digest=usage["evidence_digest"],
            )
            if "model_output_tokens" in usage:
                row["model_output_tokens"] = usage["model_output_tokens"]
        else:
            row["model_usage_source"] = (
                "trace" if row.get("model_input_tokens") is not None else None
            )


def _rows_by_task(
    rows: list[dict[str, object]], require_complete_pairs: bool
) -> tuple[dict[str, dict[str, dict[str, object]]], list[str]]:
    by_task: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    duplicates = []
    for row in rows:
        task_id = str(row["task_id"])
        mode = str(row["mode"])
        if mode in by_task[task_id]:
            duplicates.append(f"{task_id}:{mode}")
        else:
            by_task[task_id][mode] = row
    if duplicates:
        raise ValueError("duplicate task/mode traces: " + ", ".join(sorted(duplicates)))
    incomplete = sorted(
        task_id
        for task_id, modes in by_task.items()
        if set(modes) != {"baseline", "hashmarks"}
    )
    if require_complete_pairs and incomplete:
        raise ValueError("unpaired task traces: " + ", ".join(incomplete))
    return by_task, incomplete


def _comparison_pair(
    task_id: str,
    baseline: dict[str, object],
    hashmarks: dict[str, object],
    require_external_verdict: bool,
    require_external_usage: bool,
) -> dict[str, object]:
    base_tokens = baseline.get("model_input_tokens")
    hashmarks_tokens = hashmarks.get("model_input_tokens")
    token_reduction = None
    if (
        isinstance(base_tokens, int)
        and isinstance(hashmarks_tokens, int)
        and base_tokens > 0
    ):
        token_reduction = 1.0 - (hashmarks_tokens / base_tokens)
    eligible, reasons = _pair_gate(
        baseline,
        hashmarks,
        require_external_verdict=require_external_verdict,
        require_external_usage=require_external_usage,
    )
    return {
        "task_id": task_id,
        "baseline": baseline,
        "hashmarks": hashmarks,
        "claim_eligible": eligible,
        "claim_blockers": reasons,
        "model_input_token_reduction": token_reduction,
        "search_call_reduction": int(baseline["search_calls"])
        - int(hashmarks["search_calls"]),
        "file_read_reduction": int(baseline["file_reads"])
        - int(hashmarks["file_reads"]),
        "estimated_exploration_token_reduction": int(
            baseline["estimated_exploration_tokens"]
        )
        - int(hashmarks["estimated_exploration_tokens"]),
    }


def compare(
    paths: list[Path],
    *,
    verdict_paths: list[Path] | None = None,
    usage_paths: list[Path] | None = None,
    require_complete_pairs: bool = False,
    require_external_verdict: bool = False,
    require_external_usage: bool = False,
) -> dict[str, object]:
    rows = [summarize(load_trace(path)) for path in paths]
    verdicts = [load_verdict(path) for path in (verdict_paths or [])]
    usages = [load_usage(path) for path in (usage_paths or [])]
    _bind_external_records(
        rows,
        _records_by_run(verdicts, "verdict"),
        _records_by_run(usages, "model usage"),
    )
    by_task, incomplete_tasks = _rows_by_task(rows, require_complete_pairs)
    pairs = []
    for task_id, modes in sorted(by_task.items()):
        if "baseline" not in modes or "hashmarks" not in modes:
            continue
        pairs.append(
            _comparison_pair(
                task_id,
                modes["baseline"],
                modes["hashmarks"],
                require_external_verdict,
                require_external_usage,
            )
        )

    eligible_pairs = [p for p in pairs if p["claim_eligible"]]
    eligible_token_pairs = [
        p for p in eligible_pairs if p["model_input_token_reduction"] is not None
    ]
    baseline_tokens_total = sum(
        int(p["baseline"]["model_input_tokens"]) for p in eligible_token_pairs
    )
    hashmarks_tokens_total = sum(
        int(p["hashmarks"]["model_input_tokens"]) for p in eligible_token_pairs
    )
    weighted_reduction = (
        1.0 - (hashmarks_tokens_total / baseline_tokens_total)
        if baseline_tokens_total > 0
        else None
    )
    all_pairs_claim_eligible = bool(pairs) and len(eligible_pairs) == len(pairs)
    token_claim_eligible = (
        all_pairs_claim_eligible
        and not incomplete_tasks
        and len(eligible_token_pairs) == len(pairs)
        and weighted_reduction is not None
    )

    return {
        "schema": REPORT_SCHEMA,
        "traces": rows,
        "pairs": pairs,
        "summary": {
            "traces": len(rows),
            "external_verdicts": len(verdicts),
            "external_model_usages": len(usages),
            "tasks_seen": len(by_task),
            "paired_tasks": len(pairs),
            "incomplete_tasks": incomplete_tasks,
            "claim_eligible_pairs": len(eligible_pairs),
            "all_pairs_claim_eligible": all_pairs_claim_eligible,
            "token_reduction_claim_eligible": token_claim_eligible,
            "average_model_input_token_reduction": weighted_reduction
            if token_claim_eligible
            else None,
            "baseline_model_input_tokens": baseline_tokens_total
            if eligible_token_pairs
            else None,
            "hashmarks_model_input_tokens": hashmarks_tokens_total
            if eligible_token_pairs
            else None,
            "search_calls_avoided": sum(int(p["search_call_reduction"]) for p in pairs),
            "file_reads_avoided": sum(int(p["file_read_reduction"]) for p in pairs),
            "estimated_exploration_tokens_avoided": sum(
                int(p["estimated_exploration_token_reduction"]) for p in pairs
            ),
            "baseline_successes": sum(
                p["baseline"].get("success") is True for p in pairs
            ),
            "hashmarks_successes": sum(
                p["hashmarks"].get("success") is True for p in pairs
            ),
            "baseline_correct_patches": sum(
                p["baseline"].get("patch_correct") is True for p in pairs
            ),
            "hashmarks_correct_patches": sum(
                p["hashmarks"].get("patch_correct") is True for p in pairs
            ),
        },
    }


def gate(
    report: dict[str, object],
    *,
    min_pairs: int,
    max_token_reduction: float | None = None,
) -> list[str]:
    summary = report["summary"]
    assert isinstance(summary, dict)
    failures: list[str] = []
    if int(summary["paired_tasks"]) < min_pairs:
        failures.append(
            f"paired_tasks {summary['paired_tasks']} < required {min_pairs}"
        )
    if summary["incomplete_tasks"]:
        failures.append("unpaired task traces are present")
    if not summary["all_pairs_claim_eligible"]:
        failures.append(
            "task success, patch correctness, or exact model-token evidence is incomplete/regressed"
        )
    if not summary["token_reduction_claim_eligible"]:
        failures.append("model-input token reduction claim is not eligible")
    reduction = summary["average_model_input_token_reduction"]
    if (
        max_token_reduction is not None
        and isinstance(reduction, float)
        and reduction > max_token_reduction
    ):
        failures.append(
            f"token reduction {reduction:.6f} exceeds sanity ceiling {max_token_reduction:.6f}"
        )
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare baseline and Hashmarks coding-agent traces"
    )
    parser.add_argument("trace", nargs="+", type=Path)
    parser.add_argument(
        "--verdict",
        action="append",
        default=[],
        type=Path,
        help="independent hashmarks.agent-verdict.v1 evidence",
    )
    parser.add_argument(
        "--usage",
        action="append",
        default=[],
        type=Path,
        help="independent hashmarks.agent-model-usage.v1 provider evidence",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail unless every task has a complete, correctness-preserving pair",
    )
    parser.add_argument("--min-pairs", type=int, default=1)
    args = parser.parse_args()
    if args.min_pairs < 1:
        parser.error("--min-pairs must be >= 1")
    payload = compare(
        args.trace,
        verdict_paths=args.verdict,
        usage_paths=args.usage,
        require_complete_pairs=args.strict,
        require_external_verdict=args.strict,
        require_external_usage=args.strict,
    )
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    log_command_output(logger, rendered)
    if args.strict:
        failures = gate(payload, min_pairs=args.min_pairs)
        if failures:
            raise SystemExit("agent trace gate failed: " + "; ".join(failures))


if __name__ == "__main__":
    main()
