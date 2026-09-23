from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

RAW_SCHEMA = "hashmarks.agent-runner-log.v1"
TRACE_SCHEMA = "hashmarks.agent-trace.v2"
POLICY_SCHEMA = "hashmarks.agent-trace-normalization-policy.v1"
ALLOWED_KINDS = {
    "grep",
    "glob",
    "repository_search",
    "file_read",
    "hashmarks_map",
    "hashmarks_find",
    "hashmarks_grep",
    "hashmarks_context",
    "hashmarks_source",
}
PASSTHROUGH_FIELDS = (
    "query",
    "path",
    "paths",
    "returned_paths",
    "evidence_paths",
    "bytes",
    "estimated_tokens",
    "model_input_tokens",
    "started_at_ns",
    "finished_at_ns",
    "fallback",
)


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def normalization_policy_identity(tool_map: dict[str, Any]) -> str:
    payload = {"schema": POLICY_SCHEMA, "tool_map": tool_map}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _nonempty(value: Any, field: str, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string: {path}")
    return value


def _relative_path(value: str, field: str, path: Path) -> str:
    normalized = value.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized or normalized.startswith("/") or ".." in Path(normalized).parts:
        raise ValueError(f"{field} must be repository-relative: {path}")
    return normalized


def _nonnegative_integer(value: Any, field: str, path: Path) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer: {path}")
    return value


def _relative_paths(value: Any, field: str, path: Path) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"{field} must be a list of non-empty strings: {path}")
    return [_relative_path(item, field, path) for item in value]


def _validate_event_value(field: str, value: Any, path: Path) -> Any:
    if field in {
        "bytes",
        "estimated_tokens",
        "model_input_tokens",
        "started_at_ns",
        "finished_at_ns",
    }:
        return _nonnegative_integer(value, field, path)
    if field == "fallback":
        if not isinstance(value, bool):
            raise ValueError(f"fallback must be a boolean: {path}")
        return value
    if field == "query":
        return _nonempty(value, field, path)
    if field == "path":
        return _relative_path(_nonempty(value, field, path), field, path)
    if field in {"paths", "returned_paths", "evidence_paths"}:
        return _relative_paths(value, field, path)
    return value


def _validate_header(value: dict[str, Any], path: Path) -> None:
    if not isinstance(value, dict) or value.get("schema") != RAW_SCHEMA:
        raise ValueError(f"unsupported runner log schema: {path}")
    for field in (
        "runner_identity",
        "task_id",
        "task_revision",
        "repository_identity",
        "mode",
        "run_id",
        "model_identity",
        "model_config_identity",
        "normalization_policy_identity",
    ):
        _nonempty(value.get(field), field, path)
    if value["mode"] not in {"baseline", "hashmarks"}:
        raise ValueError(f"mode must be baseline or hashmarks: {path}")
    if value.get("normalization_policy_schema") != POLICY_SCHEMA:
        raise ValueError(f"unsupported normalization policy schema: {path}")


def _validated_tool_map(value: dict[str, Any], path: Path) -> dict[str, Any]:
    tool_map = value.get("tool_map")
    if not isinstance(tool_map, dict) or not tool_map:
        raise ValueError(f"tool_map must be a non-empty object: {path}")
    for tool, kind in tool_map.items():
        _nonempty(tool, "tool_map key", path)
        if kind is not None and kind not in ALLOWED_KINDS:
            raise ValueError(f"tool_map kind is unsupported for {tool!r}: {path}")
    computed_policy = normalization_policy_identity(tool_map)
    if value["normalization_policy_identity"] != computed_policy:
        raise ValueError(
            f"normalization_policy_identity mismatch: expected {computed_policy}, got {value['normalization_policy_identity']}: {path}"
        )
    return tool_map


def _validate_event(
    event: Any, tool_map: dict[str, Any], last_sequence: int, path: Path
) -> int:
    if not isinstance(event, dict):
        raise ValueError(f"runner event must be an object: {path}")
    sequence = event.get("sequence")
    if (
        not isinstance(sequence, int)
        or isinstance(sequence, bool)
        or sequence < 0
        or sequence <= last_sequence
    ):
        raise ValueError(
            f"runner event sequence must be strictly increasing non-negative integers: {path}"
        )
    tool = _nonempty(event.get("tool"), "event tool", path)
    if tool not in tool_map:
        raise ValueError(
            f"event tool {tool!r} is not explicitly declared in tool_map: {path}"
        )
    started = event.get("started_at_ns")
    finished = event.get("finished_at_ns")
    if started is not None:
        _validate_event_value("started_at_ns", started, path)
    if finished is not None:
        _validate_event_value("finished_at_ns", finished, path)
    if started is not None and finished is not None and finished < started:
        raise ValueError(f"finished_at_ns must be >= started_at_ns: {path}")
    return sequence


def _validate_events(
    value: dict[str, Any], tool_map: dict[str, Any], path: Path
) -> None:
    events = value.get("events")
    if not isinstance(events, list):
        raise ValueError(f"events must be a list: {path}")
    last_sequence = -1
    for event in events:
        last_sequence = _validate_event(event, tool_map, last_sequence, path)


def load_raw(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _validate_header(value, path)
    tool_map = _validated_tool_map(value, path)
    _validate_events(value, tool_map, path)
    return value


def normalize(path: Path) -> dict[str, Any]:
    raw = load_raw(path)
    tool_map = raw["tool_map"]
    normalized_events: list[dict[str, Any]] = []
    ignored = 0
    for event in raw["events"]:
        kind = tool_map[event["tool"]]
        if kind is None:
            ignored += 1
            continue
        item: dict[str, Any] = {
            "kind": kind,
            "runner_sequence": event["sequence"],
            "runner_tool": event["tool"],
        }
        for field in PASSTHROUGH_FIELDS:
            if field in event:
                item[field] = _validate_event_value(field, event[field], path)
        normalized_events.append(item)
    trace = {
        "schema": TRACE_SCHEMA,
        "task_id": raw["task_id"],
        "task_revision": raw["task_revision"],
        "repository_identity": raw["repository_identity"],
        "mode": raw["mode"],
        "run_id": raw["run_id"],
        "model_identity": raw["model_identity"],
        "model_config_identity": raw["model_config_identity"],
        "runner_identity": raw["runner_identity"],
        "raw_runner_log_sha256": _sha256(path),
        "normalization_policy_identity": raw["normalization_policy_identity"],
        "normalization": {
            "schema": POLICY_SCHEMA,
            "raw_events": len(raw["events"]),
            "navigation_events": len(normalized_events),
            "explicitly_ignored_events": ignored,
        },
        "events": normalized_events,
    }
    return trace


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize an explicit runner tool log into hashmarks.agent-trace.v2"
    )
    parser.add_argument("runner_log", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = normalize(args.runner_log)
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)  # noqa: T201 - intentional command output


if __name__ == "__main__":
    main()
