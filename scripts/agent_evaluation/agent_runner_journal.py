from __future__ import annotations

import argparse
import logging

from hashmarks._command_output import log_command_output

try:
    from scripts._module_loader import import_sibling
except ModuleNotFoundError:  # direct script execution
    from _module_loader import import_sibling
import contextlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

JOURNAL_SCHEMA = "hashmarks.agent-runner-journal.v1"
RAW_SCHEMA = "hashmarks.agent-runner-log.v1"


@dataclass(frozen=True)
class JournalIdentity:
    runner_identity: str
    task_id: str
    task_revision: str
    repository_identity: str
    mode: str
    run_id: str
    model_identity: str
    model_config_identity: str


def _load_normalizer() -> Any:
    return import_sibling("normalize_agent_trace", __package__)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _atomic_create_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(prefix=".event-", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(tmp, path)
        except FileExistsError as exc:
            raise ValueError(f"journal member already exists: {path}") from exc
    finally:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()


def init_journal(
    journal: Path,
    identity: JournalIdentity,
    tool_map: dict[str, Any],
) -> dict[str, Any]:
    normalizer = _load_normalizer()
    if journal.exists() and any(journal.iterdir()):
        raise ValueError(f"journal already exists and is not empty: {journal}")
    if identity.mode not in {"baseline", "hashmarks"}:
        raise ValueError("mode must be baseline or hashmarks")
    if not isinstance(tool_map, dict) or not tool_map:
        raise ValueError("tool_map must be a non-empty object")
    for tool, kind in tool_map.items():
        _nonempty(tool, "tool_map key")
        if kind is not None and kind not in normalizer.ALLOWED_KINDS:
            raise ValueError(
                f"unsupported canonical navigation kind for {tool!r}: {kind!r}"
            )
    header = {
        "schema": JOURNAL_SCHEMA,
        "runner_identity": _nonempty(identity.runner_identity, "runner_identity"),
        "task_id": _nonempty(identity.task_id, "task_id"),
        "task_revision": _nonempty(identity.task_revision, "task_revision"),
        "repository_identity": _nonempty(
            identity.repository_identity, "repository_identity"
        ),
        "mode": identity.mode,
        "run_id": _nonempty(identity.run_id, "run_id"),
        "model_identity": _nonempty(identity.model_identity, "model_identity"),
        "model_config_identity": _nonempty(
            identity.model_config_identity, "model_config_identity"
        ),
        "normalization_policy_schema": normalizer.POLICY_SCHEMA,
        "normalization_policy_identity": normalizer.normalization_policy_identity(
            tool_map
        ),
        "tool_map": tool_map,
    }
    journal.mkdir(parents=True, exist_ok=True)
    (journal / "events").mkdir(exist_ok=True)
    _atomic_create_json(journal / "header.json", header)
    return header


def record_event(journal: Path, event: dict[str, Any]) -> Path:
    normalizer = _load_normalizer()
    header_path = journal / "header.json"
    if not header_path.is_file():
        raise ValueError(f"journal header is missing: {journal}")
    header = _read_json(header_path)
    if not isinstance(header, dict) or header.get("schema") != JOURNAL_SCHEMA:
        raise ValueError(f"unsupported journal header: {header_path}")
    sequence = event.get("sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        raise ValueError("event sequence must be a non-negative integer")
    tool = _nonempty(event.get("tool"), "event tool")
    tool_map = header.get("tool_map")
    if not isinstance(tool_map, dict) or tool not in tool_map:
        raise ValueError(
            f"event tool {tool!r} is not explicitly declared in journal tool_map"
        )
    clean: dict[str, Any] = {"sequence": sequence, "tool": tool}
    for field in normalizer.PASSTHROUGH_FIELDS:
        if field in event and event[field] is not None:
            clean[field] = normalizer._validate_event_value(
                field, event[field], header_path
            )
    target = journal / "events" / f"{sequence:020d}.json"
    _atomic_create_json(target, clean)
    return target


def _journal_events(journal: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    last = -1
    for member in sorted((journal / "events").glob("*.json")):
        event = _read_json(member)
        if not isinstance(event, dict):
            raise ValueError(f"journal event must be an object: {member}")
        sequence = event.get("sequence")
        if (
            not isinstance(sequence, int)
            or isinstance(sequence, bool)
            or sequence <= last
        ):
            raise ValueError(f"journal sequences must be strictly increasing: {member}")
        if member.name != f"{sequence:020d}.json":
            raise ValueError(f"journal filename/sequence mismatch: {member}")
        expected = len(events)
        if sequence != expected:
            raise ValueError(
                f"journal sequence gap: expected {expected}, got {sequence}: {member}"
            )
        last = sequence
        events.append(event)
    return events


def _write_validated_raw(output: Path, raw: dict[str, Any], normalizer: Any) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=".runner-log-", suffix=".tmp", dir=output.parent
    )
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        tmp.write_text(
            json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        normalizer.load_raw(tmp)
        os.replace(tmp, output)
    finally:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()


def finalize_journal(
    journal: Path, output: Path, *, normalized_output: Path | None = None
) -> dict[str, Any]:
    normalizer = _load_normalizer()
    header_path = journal / "header.json"
    header = _read_json(header_path)
    if not isinstance(header, dict) or header.get("schema") != JOURNAL_SCHEMA:
        raise ValueError(f"unsupported journal header: {header_path}")
    raw = {key: value for key, value in header.items() if key != "schema"}
    raw["schema"] = RAW_SCHEMA
    raw["events"] = _journal_events(journal)
    _write_validated_raw(output, raw, normalizer)
    if normalized_output is not None:
        normalized = normalizer.normalize(output)
        normalized_output.parent.mkdir(parents=True, exist_ok=True)
        normalized_output.write_text(
            json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return raw


def _tool_map(path: Path) -> dict[str, Any]:
    value = _read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"tool map must be a JSON object: {path}")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Crash-safe runner-neutral agent navigation journal"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("journal", type=Path)
    init.add_argument("--runner-identity", required=True)
    init.add_argument("--task-id", required=True)
    init.add_argument("--task-revision", required=True)
    init.add_argument("--repository-identity", required=True)
    init.add_argument("--mode", choices=("baseline", "hashmarks"), required=True)
    init.add_argument("--run-id", required=True)
    init.add_argument("--model-identity", required=True)
    init.add_argument("--model-config-identity", required=True)
    init.add_argument("--tool-map", type=Path, required=True)

    event = sub.add_parser("event")
    event.add_argument("journal", type=Path)
    event.add_argument("--sequence", type=int, required=True)
    event.add_argument("--tool", required=True)
    event.add_argument("--query")
    event.add_argument("--path")
    event.add_argument("--paths", action="append")
    event.add_argument("--returned-path", dest="returned_paths", action="append")
    event.add_argument("--evidence-path", dest="evidence_paths", action="append")
    event.add_argument("--bytes", type=int)
    event.add_argument("--estimated-tokens", type=int)
    event.add_argument("--model-input-tokens", type=int)
    event.add_argument("--started-at-ns", type=int)
    event.add_argument("--finished-at-ns", type=int)
    event.add_argument("--fallback", action="store_true")

    final = sub.add_parser("finalize")
    final.add_argument("journal", type=Path)
    final.add_argument("--output", type=Path, required=True)
    final.add_argument("--normalized-output", type=Path)

    return parser


def _event_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = {
        "sequence": args.sequence,
        "tool": args.tool,
        "query": args.query,
        "path": args.path,
        "paths": args.paths,
        "returned_paths": args.returned_paths,
        "evidence_paths": args.evidence_paths,
        "bytes": args.bytes,
        "estimated_tokens": args.estimated_tokens,
        "model_input_tokens": args.model_input_tokens,
        "started_at_ns": args.started_at_ns,
        "finished_at_ns": args.finished_at_ns,
    }
    if args.fallback:
        payload["fallback"] = True
    return payload


def _dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "init":
        return init_journal(
            args.journal,
            JournalIdentity(
                runner_identity=args.runner_identity,
                task_id=args.task_id,
                task_revision=args.task_revision,
                repository_identity=args.repository_identity,
                mode=args.mode,
                run_id=args.run_id,
                model_identity=args.model_identity,
                model_config_identity=args.model_config_identity,
            ),
            _tool_map(args.tool_map),
        )
    if args.command == "event":
        target = record_event(args.journal, _event_payload(args))
        return {"recorded": str(target)}
    return finalize_journal(
        args.journal, args.output, normalized_output=args.normalized_output
    )


def main() -> None:
    payload = _dispatch(_parser().parse_args())
    log_command_output(logger, json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
