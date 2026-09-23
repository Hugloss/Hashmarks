from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from hashmarks.codemap import CodeMap
from scripts.agent_evaluation.decision_qa import (
    evaluate_decision_packet,
    summarize_decision_qa,
)


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _freeze_packets(
    repo: Path, tasks: list[dict[str, object]], *, token_budget: int
) -> tuple[list[dict[str, Any]], float]:
    frozen: list[dict[str, Any]] = []
    with CodeMap(repo) as codemap:
        sync_started = time.perf_counter()
        codemap.sync()
        sync_ms = (time.perf_counter() - sync_started) * 1000
        for task in tasks:
            packet = codemap.task_decision_packet(
                str(task["query"]), token_budget=token_budget
            )
            frozen.append({"id": str(task["id"]), "packet": packet})
    return frozen, sync_ms


def _grade_packets(
    frozen: list[dict[str, Any]], expected: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    graded: list[dict[str, Any]] = []
    categories: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for frozen_row in frozen:
        truth = expected[frozen_row["id"]]
        grade = evaluate_decision_packet(
            frozen_row["packet"],
            expected_edit_path=str(truth["expected_edit_path"]),
            expected_verify_path=str(truth["expected_verify_path"]),
            expected_safe=bool(truth["expected_safe"]),
        )
        row = {
            "id": frozen_row["id"],
            "category": str(truth["category"]),
            "edit_correct": grade["edit_correct"],
            "verify_correct": grade["verify_correct"],
            "safety_class": grade["safety_class"],
            "packet_consistent": grade["packet_consistent"],
            "fully_correct": grade["fully_correct"],
            "discrimination_needed": grade["discrimination_needed"],
            "safe": bool(frozen_row["packet"].get("work_context", {}).get("safe")),
        }
        graded.append(row)
        categories[row["category"]].append(row)
    return graded, categories


def run(
    repo: Path,
    public_path: Path,
    secret_path: Path,
    output: Path,
    *,
    token_budget: int = 512,
) -> dict[str, Any]:
    public = json.loads(public_path.read_text(encoding="utf-8"))
    tasks = public.get("tasks")
    if (
        not isinstance(tasks, list)
        or not tasks
        or any(set(row) != {"id", "query"} for row in tasks)
    ):
        raise ValueError("PUBLIC tasks must contain exactly id/query")
    started = time.perf_counter()
    frozen, sync_ms = _freeze_packets(repo, tasks, token_budget=token_budget)
    frozen_identity = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(frozen, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )

    # SECRET is opened only after every worker packet has been frozen.
    secret = json.loads(secret_path.read_text(encoding="utf-8"))
    expected = {str(row["id"]): row for row in secret.get("tasks") or []}
    if set(expected) != {row["id"] for row in frozen}:
        raise ValueError("SECRET task set does not match frozen PUBLIC task set")
    graded, categories = _grade_packets(frozen, expected)
    summary = summarize_decision_qa(graded)
    category_summary = {}
    for name, rows in sorted(categories.items()):
        category_summary[name] = {
            "tasks": len(rows),
            "edit_correct": sum(r["edit_correct"] for r in rows),
            "verify_correct": sum(r["verify_correct"] for r in rows),
            "fully_correct": sum(r["fully_correct"] for r in rows),
            "false_safe": sum(r["safety_class"] == "false-safe" for r in rows),
            "false_unsafe": sum(r["safety_class"] == "false-unsafe" for r in rows),
            "discrimination_needed": sum(r["discrimination_needed"] for r in rows),
        }
    payload = {
        "schema": "hashmarks.hard-agent-decision-replay.v1",
        "protocol": {
            "public_fields": ["id", "query"],
            "trace_freeze_before_grading": True,
            "secret_outside_worker_repo": True,
            "public_sha256": _sha(public_path),
            "secret_sha256": _sha(secret_path),
            "frozen_packets_identity": frozen_identity,
        },
        "summary": {
            **summary,
            "sync_ms": sync_ms,
            "wall_ms": (time.perf_counter() - started) * 1000,
        },
        "categories": category_summary,
        "results": graded,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--secret", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--token-budget", type=int, default=512)
    args = parser.parse_args()
    result = run(
        args.repo, args.public, args.secret, args.output, token_budget=args.token_budget
    )
    print(  # noqa: T201 - intentional command output
        json.dumps(
            {"summary": result["summary"], "categories": result["categories"]},
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
