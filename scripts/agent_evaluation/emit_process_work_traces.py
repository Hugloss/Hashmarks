from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hashmarks._command_output import log_command_output
from hashmarks.codemap import CodeMap
from scripts.agent_evaluation.sanitized_agent_swarm import _guard, _load_public

logger = logging.getLogger(__name__)

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
        codemap.index.sync()
        for task in public:
            events = []
            started = time.perf_counter_ns()
            packet = codemap.tasks.decision_packet(task["query"])
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
            raw_edit = packet.get("edit")
            edit = raw_edit if isinstance(raw_edit, dict) else None
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
            discrimination = packet.get("discrimination")
            if not isinstance(discrimination, dict):
                discrimination = {}
            if bool(discrimination.get("needed")):
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
            raw_verify = packet.get("verify")
            verify = raw_verify if isinstance(raw_verify, dict) else None
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
    log_command_output(
        logger,
        json.dumps(
            {"traces": len(paths), "trace_dir": str(args.trace_dir)}, sort_keys=True
        ),
    )


if __name__ == "__main__":
    main()
