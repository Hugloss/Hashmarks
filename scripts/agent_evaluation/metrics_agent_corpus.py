from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Any

from hashmarks.codemap import CodeMap

SCHEMA = "hashmarks.agent-corpus-metrics.v1"


def _load(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "hashmarks.agent-task-corpus.v1":
        raise ValueError("unsupported agent task corpus schema")
    tasks = value.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("agent task corpus must contain tasks")
    return [row for row in tasks if isinstance(row, dict)]


def collect(
    workspace: Path, corpus: Path, *, budget: int = 1200, limit: int = 20
) -> dict[str, object]:
    workspace = workspace.resolve(strict=False)
    tasks = _load(corpus)
    started = time.perf_counter()
    rows = []
    with CodeMap(workspace) as codemap:
        sync = codemap.sync()
        full_tokens = {
            str(row["path"]): int(row["full_tokens"])
            for row in (codemap.store.outline(path) for path in codemap.store.paths())
            if row is not None
        }
        repository_file_count = len(full_tokens)
        repository_source_tokens = sum(full_tokens.values())
        for task in tasks:
            query = str(task.get("query") or "")
            expected_files = {str(value) for value in task.get("expected_files") or ()}
            expected_symbols = {
                str(value) for value in task.get("expected_symbols") or ()
            }
            t0 = time.perf_counter()
            hits = codemap.find(query, limit=limit)
            find_seconds = time.perf_counter() - t0
            t1 = time.perf_counter()
            pack = codemap.context(query, token_budget=budget, limit=limit)
            context_seconds = time.perf_counter() - t1
            hit_files = {hit.path for hit in hits}
            hit_symbols = {hit.qualname for hit in hits if hit.qualname} | {
                hit.name for hit in hits if hit.name
            }
            context_files = {item.path for item in pack.items}
            context_symbols = {item.symbol for item in pack.items if item.symbol}
            relevant_files = hit_files | context_files
            relevant_symbols = hit_symbols | context_symbols
            file_hits = expected_files & relevant_files
            symbol_hits = expected_symbols & relevant_symbols
            baseline_tokens = sum(full_tokens.get(path, 0) for path in expected_files)
            context_full_file_tokens = sum(
                full_tokens.get(path, 0) for path in context_files
            )
            ratio = (
                None
                if pack.estimated_tokens <= 0
                else baseline_tokens / pack.estimated_tokens
            )
            context_ratio = (
                None
                if pack.estimated_tokens <= 0
                else context_full_file_tokens / pack.estimated_tokens
            )
            source_range_tokens = sum(
                item.estimated_tokens
                for item in pack.items
                if item.representation == "source-range"
            )
            structural_tokens = pack.estimated_tokens - source_range_tokens
            rows.append(
                {
                    "id": str(task.get("id") or query),
                    "query": query,
                    "expected_files": sorted(expected_files),
                    "expected_symbols": sorted(expected_symbols),
                    "file_recall": 1.0
                    if not expected_files
                    else len(file_hits) / len(expected_files),
                    "symbol_recall": 1.0
                    if not expected_symbols
                    else len(symbol_hits) / len(expected_symbols),
                    "first_hit_file": None if not hits else hits[0].path,
                    "first_query_hit": bool(hits and hits[0].path in expected_files),
                    "fallback_search_required": not expected_files.issubset(
                        relevant_files
                    ),
                    "confidence": pack.confidence,
                    "abstained": pack.abstained,
                    "find_seconds": find_seconds,
                    "context_seconds": context_seconds,
                    "context_tokens": pack.estimated_tokens,
                    "context_files": len(context_files),
                    "candidate_files": len(relevant_files),
                    "repository_files": repository_file_count,
                    "candidate_file_reduction": (
                        1.0 - (len(relevant_files) / repository_file_count)
                        if repository_file_count
                        else 0.0
                    ),
                    "source_range_tokens": source_range_tokens,
                    "structural_tokens": structural_tokens,
                    "source_range_fraction": (
                        source_range_tokens / pack.estimated_tokens
                        if pack.estimated_tokens
                        else 0.0
                    ),
                    "selected_files_full_tokens": context_full_file_tokens,
                    "selected_full_to_context_ratio": context_ratio,
                    "selected_file_tokens_avoided": max(
                        0, context_full_file_tokens - pack.estimated_tokens
                    ),
                    "expected_full_file_tokens": baseline_tokens,
                    "expected_full_to_context_ratio": ratio,
                }
            )
        status = codemap.status()
    task_count = len(rows)

    def percentile(values: list[float], fraction: float) -> float:
        ordered = sorted(values)
        if not ordered:
            return 0.0
        index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))
        return ordered[index]

    find_values = [float(row["find_seconds"]) for row in rows]
    context_values = [float(row["context_seconds"]) for row in rows]
    return {
        "schema": SCHEMA,
        "workspace": str(workspace),
        "corpus": str(corpus),
        "parameters": {"budget": budget, "limit": limit, "tasks": task_count},
        "repository": {
            "files": repository_file_count,
            "source_tokens": repository_source_tokens,
        },
        "sync": sync.as_dict(),
        "index": {
            key: status[key]
            for key in ("files", "symbols", "edges", "projects", "project_edges")
        },
        "summary": {
            "file_recall": sum(row["file_recall"] for row in rows) / task_count,
            "symbol_recall": sum(row["symbol_recall"] for row in rows) / task_count,
            "first_query_hit_rate": sum(bool(row["first_query_hit"]) for row in rows)
            / task_count,
            "fallback_search_rate": sum(
                bool(row["fallback_search_required"]) for row in rows
            )
            / task_count,
            "average_context_tokens": sum(int(row["context_tokens"]) for row in rows)
            / task_count,
            "average_candidate_file_reduction": sum(
                float(row["candidate_file_reduction"]) for row in rows
            )
            / task_count,
            "average_source_range_fraction": sum(
                float(row["source_range_fraction"]) for row in rows
            )
            / task_count,
            "selected_file_tokens_avoided": sum(
                int(row["selected_file_tokens_avoided"]) for row in rows
            ),
            "average_find_ms": 1000.0 * sum(find_values) / task_count,
            "p95_find_ms": 1000.0 * percentile(find_values, 0.95),
            "average_context_ms": 1000.0 * sum(context_values) / task_count,
            "p95_context_ms": 1000.0 * percentile(context_values, 0.95),
            "selected_full_to_context_ratio": (
                sum(int(row["selected_files_full_tokens"]) for row in rows)
                / max(1, sum(int(row["context_tokens"]) for row in rows))
            ),
            "seconds": time.perf_counter() - started,
        },
        "tasks": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay agent localization tasks against Hashmarks CodeMap"
    )
    parser.add_argument("--workspace", type=Path, default=Path("."))
    parser.add_argument(
        "--corpus", type=Path, default=Path("benchmarks/agent_tasks.json")
    )
    parser.add_argument("--budget", type=int, default=1200)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = collect(args.workspace, args.corpus, budget=args.budget, limit=args.limit)
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)  # noqa: T201 - intentional command output


if __name__ == "__main__":
    main()
