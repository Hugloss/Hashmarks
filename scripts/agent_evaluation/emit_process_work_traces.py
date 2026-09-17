from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from hashmarks.codemap import CodeMap

try:
    from scripts._module_loader import import_sibling
except ModuleNotFoundError:  # direct script execution
    from _module_loader import import_sibling

_sanitized = import_sibling("sanitized_agent_swarm", __package__)
_guard = _sanitized._guard
_load_public = _sanitized._load_public

TRACE_SCHEMA = "hashmarks.agent-work-trace.v1"


def emit(
    repo: Path, public_path: Path, secret_path: Path, trace_dir: Path
) -> list[Path]:
    # SECRET is passed only so the same isolation guard can prove it lives outside
    # the worker repository. It is deliberately never opened in this function.
    _guard(repo, public_path, secret_path)
    public = _load_public(public_path)
    trace_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    with CodeMap(repo) as codemap:
        codemap.sync()
        for task in public:
            events = []
            started = time.perf_counter_ns()
            packet = codemap.task_decision_packet(task["query"])
            after_packet = time.perf_counter_ns()
            events.append(
                {
                    "sequence": 1,
                    "kind": "action_packet",
                    "started_at_ns": started,
                    "finished_at_ns": after_packet,
                }
            )
            sequence = 2
            edit = packet.get("edit") if isinstance(packet.get("edit"), dict) else None
            if edit is not None:
                now = time.perf_counter_ns()
                events.append(
                    {
                        "sequence": sequence,
                        "kind": "edit_attempt",
                        "path": str(edit["path"]),
                        "started_at_ns": now,
                        "finished_at_ns": now,
                    }
                )
                sequence += 1
            if bool((packet.get("discrimination") or {}).get("needed")):
                now = time.perf_counter_ns()
                events.append(
                    {
                        "sequence": sequence,
                        "kind": "scout",
                        "started_at_ns": now,
                        "finished_at_ns": now,
                    }
                )
                sequence += 1
            verify = (
                packet.get("verify") if isinstance(packet.get("verify"), dict) else None
            )
            if verify is not None:
                now = time.perf_counter_ns()
                events.append(
                    {
                        "sequence": sequence,
                        "kind": "verification",
                        "path": str(verify["path"]),
                        "edit_target": str(edit["path"]) if edit is not None else None,
                        "outcome": "not-run",
                        "started_at_ns": now,
                        "finished_at_ns": now,
                    }
                )
            trace = {
                "schema": TRACE_SCHEMA,
                "task_id": task["id"],
                "worker_kind": "process-worker",
                "repository_evidence": "shared-warm-codemap",
                "events": events,
            }
            path = trace_dir / f"{task['id']}.json"
            path.write_text(json.dumps(trace, indent=2, sort_keys=True) + "\n")
            paths.append(path)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--secret", type=Path, required=True)
    parser.add_argument("--trace-dir", type=Path, required=True)
    args = parser.parse_args()
    paths = emit(args.repo, args.public, args.secret, args.trace_dir)
    print(  # noqa: T201 - intentional command output
        json.dumps(
            {"traces": len(paths), "trace_dir": str(args.trace_dir)}, sort_keys=True
        )
    )


if __name__ == "__main__":
    main()
