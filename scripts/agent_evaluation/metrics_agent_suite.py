from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from scripts._module_loader import import_sibling
except ModuleNotFoundError:  # direct script execution
    from _module_loader import import_sibling

collect = import_sibling("metrics_agent_corpus", __package__).collect

SCHEMA = "hashmarks.agent-suite-metrics.v1"
PROTOCOL_SCHEMA = "hashmarks.agent-suite-protocol.v1"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _protocol_identity(protocol: dict[str, object]) -> str:
    payload = json.dumps(protocol, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _parse_repo(value: str) -> tuple[str, Path, Path]:
    if "=" not in value or "::" not in value:
        raise argparse.ArgumentTypeError("repo must be NAME=WORKSPACE::CORPUS")
    name, rest = value.split("=", 1)
    workspace, corpus = rest.split("::", 1)
    if not name.strip() or not workspace.strip() or not corpus.strip():
        raise argparse.ArgumentTypeError("repo must be NAME=WORKSPACE::CORPUS")
    return name.strip(), Path(workspace), Path(corpus)



def _validate_repository_roots(repos: list[tuple[str, Path, Path]]) -> None:
    resolved = [(name, workspace.resolve()) for name, workspace, _ in repos]
    for index, (name, root) in enumerate(resolved):
        for other_name, other_root in resolved[index + 1:]:
            if root == other_root or root in other_root.parents or other_root in root.parents:
                raise ValueError(
                    f"repository workspaces must be disjoint: {name}={root} overlaps {other_name}={other_root}"
                )

def _weighted(results: list[dict[str, Any]], key: str) -> float:
    total_tasks = sum(int(row["parameters"]["tasks"]) for row in results)
    if total_tasks <= 0:
        return 0.0
    return sum(
        float(row["summary"][key]) * int(row["parameters"]["tasks"])
        for row in results
    ) / total_tasks


def collect_suite(
    repos: list[tuple[str, Path, Path]], *, budget: int = 1200, limit: int = 20
) -> dict[str, object]:
    if not repos:
        raise ValueError("at least one repository is required")
    _validate_repository_roots(repos)
    reports: list[dict[str, Any]] = []
    for name, workspace, corpus in repos:
        report = collect(workspace, corpus, budget=budget, limit=limit)
        reports.append({"name": name, **report})
    total_tasks = sum(int(row["parameters"]["tasks"]) for row in reports)
    protocol_repositories = []
    for (name, workspace, corpus), report in zip(repos, reports):
        protocol_repositories.append({
            "name": name,
            "workspace_fingerprint": str(report["sync"]["workspace_fingerprint"]),
            "corpus_sha256": _sha256_file(corpus),
            "tasks": int(report["parameters"]["tasks"]),
        })
    protocol = {
        "schema": PROTOCOL_SCHEMA,
        "retrieval": "CodeMap.find_task + CodeMap.context",
        "budget": int(budget),
        "limit": int(limit),
        "repositories": protocol_repositories,
    }
    return {
        "schema": SCHEMA,
        "benchmark_protocol": protocol,
        "benchmark_protocol_identity": _protocol_identity(protocol),
        "parameters": {"budget": budget, "limit": limit, "repositories": len(reports), "tasks": total_tasks},
        "summary": {
            "file_recall": _weighted(reports, "file_recall"),
            "symbol_recall": _weighted(reports, "symbol_recall"),
            "first_query_hit_rate": _weighted(reports, "first_query_hit_rate"),
            "fallback_search_rate": _weighted(reports, "fallback_search_rate"),
            "average_context_tokens": _weighted(reports, "average_context_tokens"),
            "average_candidate_file_reduction": _weighted(reports, "average_candidate_file_reduction"),
            "average_find_ms": _weighted(reports, "average_find_ms"),
            "average_context_ms": _weighted(reports, "average_context_ms"),
            "max_repo_p95_find_ms": max(float(row["summary"]["p95_find_ms"]) for row in reports),
            "max_repo_p95_context_ms": max(float(row["summary"]["p95_context_ms"]) for row in reports),
            "selected_file_tokens_avoided": sum(int(row["summary"]["selected_file_tokens_avoided"]) for row in reports),
            "seconds": sum(float(row["summary"]["seconds"]) for row in reports),
        },
        "repositories": reports,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay agent-localization corpora across multiple repositories")
    parser.add_argument("--repo", action="append", type=_parse_repo, required=True, metavar="NAME=WORKSPACE::CORPUS")
    parser.add_argument("--budget", type=int, default=1200)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-file-recall", type=float, default=0.0)
    parser.add_argument("--min-symbol-recall", type=float, default=0.0)
    parser.add_argument("--max-fallback-rate", type=float, default=1.0)
    parser.add_argument("--max-average-find-ms", type=float)
    parser.add_argument("--max-average-context-ms", type=float)
    args = parser.parse_args()
    payload = collect_suite(args.repo, budget=args.budget, limit=args.limit)
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    summary = payload["summary"]
    failed = (
        float(summary["file_recall"]) < args.min_file_recall
        or float(summary["symbol_recall"]) < args.min_symbol_recall
        or float(summary["fallback_search_rate"]) > args.max_fallback_rate
        or (args.max_average_find_ms is not None and float(summary["average_find_ms"]) > args.max_average_find_ms)
        or (args.max_average_context_ms is not None and float(summary["average_context_ms"]) > args.max_average_context_ms)
    )
    if failed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
