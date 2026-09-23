# Imports below follow the standalone script path bootstrap.
# ruff: noqa: E402
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_S = Path(__file__).resolve().parent
_R = _S.parent.parent
for p in (str(_R), str(_S)):
    if p not in sys.path:
        sys.path.insert(0, p)
from hashmarks.codemap import (
    CodeMap,
)

from .metrics_blind_worker_ab import (
    _grep_worker,
    _repository_files,
)
from .metrics_worker_inspection_ab import (
    _resolve_after_inspection,
)

SCHEMA = "hashmarks.process-swarm-real-repo.v2"
TRACE = "hashmarks.process-swarm-trace.v2"
STRATEGIES = ("native", "find-task", "task-entry-points", "task-entry-selective")


def ident(x: object) -> str:
    b = json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return "sha256:" + hashlib.sha256(b).hexdigest()


def is_test(p: str) -> bool:
    s = p.casefold()
    n = Path(p).name.casefold()
    return (
        "/tests/" in f"/{s}" or n.startswith("test_") or ".test." in n or ".spec." in n
    )


def cost(repo: Path, paths: list[str]) -> dict[str, int]:
    seen = set()
    b = 0
    n = 0
    for rel in paths:
        if not rel or rel in seen:
            continue
        seen.add(rel)
        p = repo / rel
        if p.is_file():
            n += 1
            b += p.stat().st_size
    return {"files": n, "bytes": b, "approx_tokens": (b + 3) // 4 if b else 0}


@dataclass
class WorkerObservation:
    candidates: list[str]
    first: str | None
    verification_candidates: list[str]
    ambiguity: bool
    cold_setup_ms: float
    repository_scan_files: int
    repository_scan_bytes: int
    events: list[dict[str, Any]]


@dataclass(frozen=True)
class SwarmRunConfig:
    repo: Path
    public_path: Path
    secret_path: Path
    output: Path
    trace_dir: Path
    workers: int
    limit: int


def _native_observation(repo: Path, query: str, *, limit: int) -> WorkerObservation:
    files = _repository_files(repo)
    scan_bytes = sum(path.stat().st_size for path in files)
    started = time.perf_counter()
    hits = _grep_worker(repo, query, limit=limit)
    search_ms = (time.perf_counter() - started) * 1000
    candidates = [str(hit.get("path") or "") for hit in hits]
    started = time.perf_counter()
    verification_hits = _grep_worker(repo, query + " test verification", limit=limit)
    verification_ms = (time.perf_counter() - started) * 1000
    return WorkerObservation(
        candidates=candidates,
        first=candidates[0] if candidates else None,
        verification_candidates=[
            str(hit.get("path") or "") for hit in verification_hits
        ],
        ambiguity=False,
        cold_setup_ms=0.0,
        repository_scan_files=len(files) * 2,
        repository_scan_bytes=scan_bytes * 2,
        events=[
            {
                "op": "grep",
                "elapsed_ms": search_ms,
                "scan_files": len(files),
                "scan_bytes": scan_bytes,
                "candidates": candidates[:10],
            },
            {
                "op": "verify_search",
                "elapsed_ms": verification_ms,
                "selected": next(
                    (
                        str(hit.get("path") or "")
                        for hit in verification_hits
                        if is_test(str(hit.get("path") or ""))
                    ),
                    None,
                ),
                "candidates": [
                    str(hit.get("path") or "") for hit in verification_hits[:10]
                ],
            },
        ],
    )


def _codemap_candidates(
    codemap: CodeMap, query: str, strategy: str, *, limit: int
) -> tuple[list[str], str | None, bool, list[dict[str, Any]], dict[str, Any]]:
    started = time.perf_counter()
    if strategy == "find-task":
        hits = codemap.find_task(query, limit=limit)
        candidates = [hit.path for hit in hits]
        return (
            candidates,
            candidates[0] if candidates else None,
            False,
            [],
            {
                "op": "find_task",
                "elapsed_ms": (time.perf_counter() - started) * 1000,
                "candidates": candidates[:10],
            },
        )
    entry_points = codemap.task_entry_points(query, limit=limit)
    recommended = [
        row for row in entry_points.get("recommended", []) if isinstance(row, dict)
    ]
    candidates = [str(row.get("path") or "") for row in recommended]
    ambiguity = entry_points.get("ambiguity")
    ambiguity = ambiguity if isinstance(ambiguity, dict) else {}
    is_ambiguous = bool(ambiguity.get("ambiguous"))
    alternatives = list(ambiguity.get("alternatives", [])) if is_ambiguous else []
    return (
        candidates,
        candidates[0] if candidates else None,
        is_ambiguous,
        alternatives,
        {
            "op": "task_entry_points",
            "elapsed_ms": (time.perf_counter() - started) * 1000,
            "ambiguous": is_ambiguous,
            "candidates": candidates[:10],
        },
    )


def _codemap_observation(
    repo: Path, query: str, strategy: str, *, limit: int
) -> WorkerObservation:
    with CodeMap(repo) as codemap:
        started = time.perf_counter()
        codemap.sync()
        cold_ms = (time.perf_counter() - started) * 1000
        candidates, first, ambiguity, alternatives, search_event = _codemap_candidates(
            codemap, query, strategy, limit=limit
        )
        events = [{"op": "sync", "elapsed_ms": cold_ms}, search_event]
        if strategy == "task-entry-selective" and ambiguity:
            resolution = _resolve_after_inspection(query, alternatives)
            events.append(
                {
                    "op": "resolve",
                    "resolution": resolution,
                    "alternatives": alternatives,
                }
            )
            if resolution.get("resolved"):
                first = str(resolution.get("target") or first)
        started = time.perf_counter()
        verification_hits = codemap.find_task(query + " test verification", limit=limit)
        verification_ms = (time.perf_counter() - started) * 1000
    observation = WorkerObservation(
        candidates=candidates,
        first=first,
        verification_candidates=[hit.path for hit in verification_hits],
        ambiguity=ambiguity,
        cold_setup_ms=cold_ms,
        repository_scan_files=0,
        repository_scan_bytes=0,
        events=events,
    )
    observation.events.append(
        {
            "op": "verify_search",
            "elapsed_ms": verification_ms,
            "selected": next(
                (path for path in observation.verification_candidates if is_test(path)),
                None,
            ),
            "candidates": observation.verification_candidates[:10],
        }
    )
    return observation


def worker(
    repo_s: str, task: dict[str, str], strategy: str, limit: int, trace_dir_s: str
) -> dict[str, Any]:
    repo = Path(repo_s)
    trace_dir = Path(trace_dir_s)
    trace_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    observation = (
        _native_observation(repo, task["query"], limit=limit)
        if strategy == "native"
        else _codemap_observation(repo, task["query"], strategy, limit=limit)
    )
    verify = next(
        (path for path in observation.verification_candidates if is_test(path)), None
    )
    evidence = list(
        dict.fromkeys(
            ([observation.first] if observation.first else [])
            + observation.candidates[:3]
            + ([verify] if verify else [])
        )
    )
    result = {
        "schema": TRACE,
        "pid": os.getpid(),
        "strategy": strategy,
        "task": task,
        "first_edit_target": observation.first,
        "top_candidates": observation.candidates[:limit],
        "verification_target": verify,
        "ambiguous": observation.ambiguity,
        "cold_setup_ms": observation.cold_setup_ms,
        "repository_scan_files": observation.repository_scan_files,
        "repository_scan_bytes": observation.repository_scan_bytes,
        "evidence_read": cost(repo, evidence),
        "elapsed_ms": (time.perf_counter() - started) * 1000,
        "events": observation.events,
    }
    path = trace_dir / f"{strategy}__{task['id']}.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    result["trace_file"] = str(path)
    return result


def _collect_worker_traces(
    config: SwarmRunConfig, public_tasks: list[dict[str, str]]
) -> tuple[list[dict[str, Any]], int, float]:
    jobs = [(task, strategy) for task in public_tasks for strategy in STRATEGIES]
    frozen = []
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=config.workers) as executor:
        futures = [
            executor.submit(
                worker,
                str(config.repo),
                task,
                strategy,
                config.limit,
                str(config.trace_dir),
            )
            for task, strategy in jobs
        ]
        for future in as_completed(futures):
            frozen.append(future.result())
    frozen.sort(key=lambda row: (row["task"]["id"], row["strategy"]))
    return frozen, len(jobs), (time.perf_counter() - started) * 1000


def _grade_worker_traces(
    frozen: list[dict[str, Any]], secret_tasks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    expected_files = {
        str(task["id"]): set(map(str, task.get("expected_files") or []))
        for task in secret_tasks
    }
    expected_symbols = {
        str(task["id"]): set(map(str, task.get("expected_symbols") or []))
        for task in secret_tasks
    }
    rows = []
    for trace in frozen:
        task_id = trace["task"]["id"]
        expected = expected_files[task_id]
        top = trace["top_candidates"]
        rows.append(
            {
                **trace,
                "expected_files": sorted(expected),
                "expected_symbols": sorted(expected_symbols[task_id]),
                "correct_first_edit": trace["first_edit_target"] in expected,
                "top5_any_expected": bool(expected.intersection(top[:5])),
                "top20_all_expected": expected.issubset(set(top[:20])),
                "verification_found": bool(trace["verification_target"]),
            }
        )
    return rows


def _strategy_summary(rows: list[dict[str, Any]]) -> dict[str, object]:
    count = len(rows)
    return {
        "tasks": count,
        "correct_first_edits": sum(row["correct_first_edit"] for row in rows),
        "correct_first_edit_rate": sum(row["correct_first_edit"] for row in rows)
        / count,
        "top5_any_expected": sum(row["top5_any_expected"] for row in rows),
        "top20_all_expected": sum(row["top20_all_expected"] for row in rows),
        "verification_found": sum(row["verification_found"] for row in rows),
        "ambiguous_tasks": sum(row["ambiguous"] for row in rows),
        "cold_setup_ms": sum(float(row["cold_setup_ms"]) for row in rows),
        "worker_elapsed_ms": sum(float(row["elapsed_ms"]) for row in rows),
        "repository_scan_files": sum(int(row["repository_scan_files"]) for row in rows),
        "repository_scan_bytes": sum(int(row["repository_scan_bytes"]) for row in rows),
        "evidence_bytes_read": sum(int(row["evidence_read"]["bytes"]) for row in rows),
        "evidence_approx_tokens": sum(
            int(row["evidence_read"]["approx_tokens"]) for row in rows
        ),
    }


def _run_summary(
    config: SwarmRunConfig,
    public_tasks: list[dict[str, str]],
    rows: list[dict[str, Any]],
    jobs: int,
    wall_ms: float,
) -> dict[str, object]:
    return {
        "repo": str(config.repo),
        "tasks": len(public_tasks),
        "workers_launched": jobs,
        "max_parallel_workers": config.workers,
        "wall_ms": wall_ms,
        "strategies": {
            strategy: _strategy_summary(
                [row for row in rows if row["strategy"] == strategy]
            )
            for strategy in STRATEGIES
        },
    }


def _protocol(config: SwarmRunConfig) -> dict[str, object]:
    return {
        "public_fields": ["id", "query"],
        "hidden_fields": ["expected_files", "expected_symbols"],
        "secret_outside_worker_repo": True,
        "answer_key_removed_from_repo": not (
            config.repo / "benchmarks/agent_tasks.json"
        ).exists(),
        "trace_freeze_before_grading": True,
        "strategies": list(STRATEGIES),
        "limit": config.limit,
        "public_sha256": "sha256:"
        + hashlib.sha256(config.public_path.read_bytes()).hexdigest(),
        "secret_sha256": "sha256:"
        + hashlib.sha256(config.secret_path.read_bytes()).hexdigest(),
    }


def run(config: SwarmRunConfig) -> dict[str, Any]:
    public_tasks = json.loads(config.public_path.read_text())["tasks"]
    secret_tasks = json.loads(config.secret_path.read_text())["tasks"]
    allowed = {"id", "query"}
    if any(set(task) != allowed for task in public_tasks):
        raise ValueError("public tasks must contain only id/query")
    frozen, jobs, wall_ms = _collect_worker_traces(config, public_tasks)
    rows = _grade_worker_traces(frozen, secret_tasks)
    protocol = _protocol(config)
    result = {
        "schema": SCHEMA,
        "protocol": protocol,
        "protocol_identity": ident(protocol),
        "summary": _run_summary(config, public_tasks, rows, jobs, wall_ms),
        "results": rows,
    }
    config.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--public", type=Path, required=True)
    p.add_argument("--secret", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--trace-dir", type=Path, required=True)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--limit", type=int, default=20)
    a = p.parse_args()
    r = run(
        SwarmRunConfig(
            repo=a.repo,
            public_path=a.public,
            secret_path=a.secret,
            output=a.output,
            trace_dir=a.trace_dir,
            workers=a.workers,
            limit=a.limit,
        )
    )
    print(json.dumps(r["summary"], indent=2, sort_keys=True))  # noqa: T201 - intentional command output


if __name__ == "__main__":
    main()
