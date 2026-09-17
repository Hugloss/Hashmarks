from __future__ import annotations

import argparse
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from hashmarks.codemap import CodeMap

SCHEMA = "hashmarks.sanitized-agent-swarm.v1"
PUBLIC_FIELDS = {"id", "query"}
HIDDEN_FIELDS = {"expected_files", "expected_symbols"}


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _load_public(path: Path) -> list[dict[str, str]]:
    rows = json.loads(path.read_text())["tasks"]
    if not isinstance(rows, list):
        raise ValueError("public tasks must be a list")
    for row in rows:
        if not isinstance(row, dict) or set(row) != PUBLIC_FIELDS:
            raise ValueError("public tasks must contain exactly id/query")
        if any(field in row for field in HIDDEN_FIELDS):
            raise ValueError("public tasks contain hidden grader fields")
    return [{"id": str(row["id"]), "query": str(row["query"])} for row in rows]


def _guard(repo: Path, public_path: Path, secret_path: Path) -> None:
    repo = repo.resolve()
    if (repo / "benchmarks" / "agent_tasks.json").exists():
        raise RuntimeError(
            "worker repository contains benchmarks/agent_tasks.json answer key"
        )
    if _inside(secret_path, repo):
        raise RuntimeError("SECRET grader file must live outside worker repository")
    if _inside(public_path, repo):
        # PUBLIC may be mounted inside a worker repo in production, but keeping it
        # external here makes the benchmark isolation invariant mechanically clear.
        raise RuntimeError("PUBLIC task manifest must live outside worker repository")


def _trace_task(
    codemap: CodeMap, task: dict[str, str], trace_dir: Path
) -> dict[str, Any]:
    started = time.perf_counter()
    action = codemap.task_action_map(task["query"], limit=20)
    row = {
        "schema": "hashmarks.sanitized-agent-trace.v1",
        "task": task,
        "edit_target": action["edit"]["path"] if action["edit"] else None,
        "verification_target": action["verify"]["path"] if action["verify"] else None,
        "ambiguous": bool(action["ambiguity"]["ambiguous"]),
        "canonical": [entry["path"] for entry in action["canonical"]],
        "elapsed_ms": (time.perf_counter() - started) * 1000.0,
    }
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace = trace_dir / f"{task['id']}.json"
    trace.write_text(json.dumps(row, indent=2, sort_keys=True) + "\n")
    row["trace"] = str(trace)
    return row


def run(
    repo: Path,
    public_path: Path,
    secret_path: Path,
    output: Path,
    trace_dir: Path,
    workers: int = 8,
) -> dict[str, Any]:
    _guard(repo, public_path, secret_path)
    public = _load_public(public_path)

    # Shared warm authority: exactly one sync for the entire swarm.
    started = time.perf_counter()
    with CodeMap(repo) as codemap:
        sync_started = time.perf_counter()
        codemap.sync()
        sync_ms = (time.perf_counter() - sync_started) * 1000.0
        frozen: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(_trace_task, codemap, task, trace_dir) for task in public
            ]
            for future in as_completed(futures):
                frozen.append(future.result())

    frozen.sort(key=lambda row: row["task"]["id"])
    # SECRET is intentionally opened only after all worker traces are frozen.
    secret_rows = json.loads(secret_path.read_text())["tasks"]
    expected = {
        str(row["id"]): set(map(str, row.get("expected_files") or []))
        for row in secret_rows
    }
    scored = []
    for row in frozen:
        exp = expected[row["task"]["id"]]
        canonical = row["canonical"]
        scored.append(
            {
                **row,
                "correct_edit": row["edit_target"] in exp,
                "top5_any_expected": bool(exp.intersection(canonical[:5])),
                "top20_all_expected": exp.issubset(set(canonical[:20])),
                "verification_found": bool(row["verification_target"]),
            }
        )
    n = len(scored)
    result = {
        "schema": SCHEMA,
        "protocol": {
            "public_fields": sorted(PUBLIC_FIELDS),
            "secret_outside_worker_repo": True,
            "answer_key_removed_from_repo": True,
            "trace_freeze_before_grading": True,
            "shared_warm_codemap": True,
            "public_sha256": _sha(public_path),
            "secret_sha256": _sha(secret_path),
        },
        "summary": {
            "tasks": n,
            "correct_edits": sum(row["correct_edit"] for row in scored),
            "verification_found": sum(row["verification_found"] for row in scored),
            "top5_any_expected": sum(row["top5_any_expected"] for row in scored),
            "top20_all_expected": sum(row["top20_all_expected"] for row in scored),
            "ambiguous_tasks": sum(row["ambiguous"] for row in scored),
            "sync_ms": sync_ms,
            "wall_ms": (time.perf_counter() - started) * 1000.0,
        },
        "results": scored,
    }
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--secret", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trace-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    result = run(
        args.repo,
        args.public,
        args.secret,
        args.output,
        args.trace_dir,
        workers=args.workers,
    )
    print(json.dumps(result["summary"], indent=2, sort_keys=True))  # noqa: T201 - intentional command output


if __name__ == "__main__":
    main()
