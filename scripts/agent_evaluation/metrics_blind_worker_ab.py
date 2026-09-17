# Imports below follow the standalone script path bootstrap.
# ruff: noqa: E402
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from hashmarks.codemap import (
    CodeMap,
)

if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from .metrics_fresh_multi_repo import (
    materialize_fixture,
)

SCHEMA = "hashmarks.blind-worker-ab.v2"
PROTOCOL_SCHEMA = "hashmarks.blind-worker-ab-protocol.v2"
CHALLENGE_FAMILY = "hashmarks-v0.10.35-blind-worker-challenge-a"
_WORD_RE = re.compile(r"[A-Za-z0-9_./-]+")
_SKIP_ROOTS = {".git", ".hashmarks", ".venv", "node_modules"}


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _identity(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return _sha256_bytes(payload)


def _load_corpus(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "hashmarks.agent-task-corpus.v1":
        raise ValueError("unsupported corpus schema")
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("corpus has no tasks")
    return [dict(row) for row in tasks if isinstance(row, dict)]


def _public_tasks(corpus: Path) -> list[dict[str, str]]:
    return [
        {
            "id": str(row.get("id") or row.get("query") or "task"),
            "query": str(row.get("query") or ""),
        }
        for row in _load_corpus(corpus)
    ]


def _repository_files(workspace: Path) -> list[Path]:
    out: list[Path] = []
    for path in workspace.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(workspace)
        if rel.parts and rel.parts[0] in _SKIP_ROOTS:
            continue
        out.append(path)
    return sorted(out, key=lambda p: p.relative_to(workspace).as_posix())


def _grep_worker(workspace: Path, query: str, *, limit: int) -> list[dict[str, object]]:
    terms = [term.lower() for term in _WORD_RE.findall(query) if len(term) > 1]
    rows: list[dict[str, object]] = []
    for path in _repository_files(workspace):
        rel = path.relative_to(workspace).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue
        path_value = rel.lower()
        path_hits = sum(path_value.count(term) for term in terms)
        content_hits = sum(text.count(term) for term in terms)
        if not path_hits and not content_hits:
            continue
        # Deliberately simple portable grep-like baseline: path matches are useful,
        # but there is no repository-domain, symbol, graph, or authority knowledge.
        score = float(path_hits * 4 + content_hits)
        rows.append({"path": rel, "score": score})
    rows.sort(key=lambda row: (-float(row["score"]), str(row["path"])))
    return rows[:limit]


def _hashmarks_worker(
    codemap: CodeMap, query: str, *, limit: int
) -> list[dict[str, object]]:
    return [
        {
            "path": hit.path,
            "score": hit.score,
            "kind": hit.kind,
            "name": hit.name,
            "qualname": hit.qualname,
        }
        for hit in codemap.find_task(query, limit=limit)
    ]


def _entry_points_worker(
    codemap: CodeMap, query: str, *, limit: int
) -> list[dict[str, object]]:
    value = codemap.task_entry_points(query, limit=limit)
    ambiguity = value.get("ambiguity", {})
    ambiguous = (
        bool(ambiguity.get("ambiguous")) if isinstance(ambiguity, dict) else False
    )
    ambiguity_roles = (
        list(ambiguity.get("explicit_roles", [])) if isinstance(ambiguity, dict) else []
    )
    canonical = value["canonical"]
    canonical_by_path = {
        str(row.get("path") or ""): row for row in canonical if isinstance(row, dict)
    }
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for entry in value["recommended"]:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or "")
        if not path or path in seen:
            continue
        seen.add(path)
        base = canonical_by_path.get(path, {})
        rows.append(
            {
                "path": path,
                "score": base.get("score"),
                "kind": base.get("kind"),
                "worker_role": entry.get("role"),
                "canonical_rank": entry.get("canonical_rank"),
                "ambiguous": ambiguous,
                "ambiguity_roles": ambiguity_roles,
            }
        )
    for row in canonical:
        if not isinstance(row, dict):
            continue
        path = str(row.get("path") or "")
        if not path or path in seen:
            continue
        seen.add(path)
        rows.append(
            {
                "path": path,
                "score": row.get("score"),
                "kind": row.get("kind"),
                "worker_role": "canonical-remainder",
                "ambiguous": ambiguous,
                "ambiguity_roles": ambiguity_roles,
            }
        )
        if len(rows) >= limit:
            break
    return rows[:limit]


def _ambiguity_reviewer(
    codemap: CodeMap, query: str, *, limit: int
) -> dict[str, object]:
    """Independent reviewer: inspect task/repository evidence, never worker-A output or hidden answers."""
    value = codemap.task_entry_points(query, limit=limit)
    ambiguity = value.get("ambiguity", {})
    if not isinstance(ambiguity, dict):
        ambiguity = {}
    alternatives = []
    for row in ambiguity.get("alternatives", []):
        if not isinstance(row, dict):
            continue
        alternatives.append(
            {
                "role": row.get("role"),
                "path": row.get("path"),
                "canonical_rank": row.get("canonical_rank"),
            }
        )
    return {
        "ambiguous": bool(ambiguity.get("ambiguous")),
        "reason": ambiguity.get("reason"),
        "roles": list(ambiguity.get("explicit_roles", [])),
        "alternatives": alternatives,
    }


def run_worker(
    *, strategy: str, workspace: Path, tasks_path: Path, output: Path, limit: int
) -> None:
    payload = json.loads(tasks_path.read_text(encoding="utf-8"))
    if payload.get("schema") != "hashmarks.blind-worker-tasks.v1":
        raise ValueError("unsupported blind worker input")
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("blind worker tasks must be a list")
    rows = []
    codemap = None
    if strategy in {"hashmarks", "entry-points", "ambiguity-reviewer"}:
        codemap = CodeMap(workspace)
        codemap.sync()
    # Workers are intentionally unable to consume expected_* fields.
    for row in tasks:
        if not isinstance(row, dict) or set(row) - {"id", "query"}:
            raise ValueError("blind worker input may contain only id and query")
        task_id = str(row.get("id") or "")
        query = str(row.get("query") or "")
        if strategy == "grep":
            hits = _grep_worker(workspace, query, limit=limit)
        elif strategy == "hashmarks":
            hits = _hashmarks_worker(codemap, query, limit=limit)
        elif strategy == "entry-points":
            hits = _entry_points_worker(codemap, query, limit=limit)
        elif strategy == "ambiguity-reviewer":
            review = _ambiguity_reviewer(codemap, query, limit=limit)
            rows.append({"id": task_id, "query": query, "review": review})
            continue
        else:
            raise ValueError(f"unsupported strategy: {strategy}")
        rows.append({"id": task_id, "query": query, "hits": hits})
    if codemap is not None:
        codemap.close()
    rendered = {
        "schema": "hashmarks.blind-worker-output.v1",
        "strategy": strategy,
        "tasks": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(rendered, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _inject_decoys(workspace: Path, tasks: list[dict[str, str]]) -> None:
    decoys = workspace / "docs" / "historical-search-notes"
    decoys.mkdir(parents=True, exist_ok=True)
    # Each decoy is plausible prose containing the full user phrasing multiple
    # times but explicitly describes historical notes, not implementation.
    for row in tasks:
        task_id = re.sub(r"[^a-zA-Z0-9_.-]+", "-", row["id"])
        query = row["query"]
        (decoys / f"{task_id}.md").write_text(
            "# Historical search notes\n\n"
            f"Search phrase: {query}\n\n"
            f"Previous investigation mentioned {query}.\n"
            "This file is historical orientation only and is not the implementation, test, contract, or configuration authority.\n",
            encoding="utf-8",
        )


def materialize_challenge(root: Path) -> list[tuple[str, Path, Path, Path]]:
    repos = materialize_fixture(root / "base")
    result: list[tuple[str, Path, Path, Path]] = []
    for name, workspace, corpus in repos:
        public = _public_tasks(corpus)
        _inject_decoys(workspace, public)
        public_path = root / "blind-inputs" / f"{name}.json"
        public_path.parent.mkdir(parents=True, exist_ok=True)
        public_path.write_text(
            json.dumps(
                {"schema": "hashmarks.blind-worker-tasks.v1", "tasks": public},
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        result.append((name, workspace, corpus, public_path))
    return result


def _score_strategy(
    tasks: list[dict[str, Any]], output: dict[str, Any]
) -> dict[str, object]:
    by_id = {
        str(row.get("id") or ""): row
        for row in output.get("tasks", [])
        if isinstance(row, dict)
    }
    rows = []
    for task in tasks:
        task_id = str(task.get("id") or task.get("query") or "")
        expected = {str(value) for value in task.get("expected_files") or ()}
        observed = by_id.get(task_id, {})
        hits = observed.get("hits", []) if isinstance(observed, dict) else []
        paths = [str(row.get("path") or "") for row in hits if isinstance(row, dict)]
        top1 = bool(expected.intersection(paths[:1]))
        top5 = bool(expected.intersection(paths[:5]))
        top20 = expected.issubset(set(paths[:20]))
        first_expected_rank = next(
            (idx + 1 for idx, path in enumerate(paths) if path in expected), None
        )
        first_hit_row = hits[0] if hits and isinstance(hits[0], dict) else {}
        ambiguous = bool(first_hit_row.get("ambiguous"))
        ambiguity_roles = list(first_hit_row.get("ambiguity_roles") or [])
        rows.append(
            {
                "id": task_id,
                "query": str(task.get("query") or ""),
                "expected_files": sorted(expected),
                "top1": top1,
                "top5": top5,
                "top20_all_expected": top20,
                "first_expected_rank": first_expected_rank,
                "first_hit": paths[0] if paths else None,
                "ambiguous": ambiguous,
                "ambiguity_roles": ambiguity_roles,
            }
        )
    count = len(rows)
    return {
        "summary": {
            "tasks": count,
            "top1_rate": sum(bool(row["top1"]) for row in rows) / count,
            "top5_rate": sum(bool(row["top5"]) for row in rows) / count,
            "top20_all_expected_rate": sum(
                bool(row["top20_all_expected"]) for row in rows
            )
            / count,
            "failures_top1": sum(not bool(row["top1"]) for row in rows),
            "failures_top5": sum(not bool(row["top5"]) for row in rows),
            "failures_top20": sum(not bool(row["top20_all_expected"]) for row in rows),
            "ambiguous_tasks": sum(bool(row["ambiguous"]) for row in rows),
            "top1_failures_flagged_ambiguous": sum(
                (not bool(row["top1"])) and bool(row["ambiguous"]) for row in rows
            ),
            "top1_failure_ambiguity_recall": (
                sum((not bool(row["top1"])) and bool(row["ambiguous"]) for row in rows)
                / max(1, sum(not bool(row["top1"]) for row in rows))
            ),
        },
        "tasks": rows,
    }


def collect(root: Path, *, limit: int = 20) -> dict[str, object]:
    repos = materialize_challenge(root)
    repo_reports = []
    for name, workspace, corpus, public_path in repos:
        outputs: dict[str, Path] = {}
        for strategy in ("grep", "hashmarks", "entry-points", "ambiguity-reviewer"):
            output = root / "worker-outputs" / f"{name}-{strategy}.json"
            env = dict(__import__("os").environ)
            source_root = str(Path(__file__).resolve().parent.parent.parent)
            prior = env.get("PYTHONPATH")
            env["PYTHONPATH"] = (
                source_root
                if not prior
                else source_root + __import__("os").pathsep + prior
            )
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.agent_evaluation.metrics_blind_worker_ab",
                    "--worker",
                    "--strategy",
                    strategy,
                    "--workspace",
                    str(workspace),
                    "--tasks",
                    str(public_path),
                    "--output",
                    str(output),
                    "--limit",
                    str(limit),
                ],
                check=True,
                env=env,
            )
            outputs[strategy] = output
        # Hidden expectations are opened only after both workers have exited and
        # their immutable output files exist.
        tasks = _load_corpus(corpus)
        grep_output = json.loads(outputs["grep"].read_text(encoding="utf-8"))
        hashmarks_output = json.loads(outputs["hashmarks"].read_text(encoding="utf-8"))
        entry_output = json.loads(outputs["entry-points"].read_text(encoding="utf-8"))
        reviewer_output = json.loads(
            outputs["ambiguity-reviewer"].read_text(encoding="utf-8")
        )
        grep_score = _score_strategy(tasks, grep_output)
        hashmarks_score = _score_strategy(tasks, hashmarks_output)
        entry_score = _score_strategy(tasks, entry_output)
        reviewer_by_id = {
            str(row.get("id") or ""): row.get("review", {})
            for row in reviewer_output.get("tasks", [])
            if isinstance(row, dict)
        }
        repo_reports.append(
            {
                "name": name,
                "workspace": str(workspace),
                "public_task_sha256": _sha256_bytes(public_path.read_bytes()),
                "hidden_corpus_sha256": _sha256_bytes(corpus.read_bytes()),
                "grep": grep_score,
                "hashmarks": hashmarks_score,
                "entry_points": entry_score,
                "ambiguity_reviewer": reviewer_by_id,
            }
        )

    def aggregate(strategy: str, key: str) -> float:
        values = []
        for repo in repo_reports:
            score = repo[strategy]
            assert isinstance(score, dict)
            summary = score["summary"]
            assert isinstance(summary, dict)
            values.extend([float(summary[key])] * int(summary["tasks"]))
        return sum(values) / len(values) if values else 0.0

    total_tasks = sum(
        int(repo["hashmarks"]["summary"]["tasks"]) for repo in repo_reports
    )  # type: ignore[index]
    protocol = {
        "schema": PROTOCOL_SCHEMA,
        "family": CHALLENGE_FAMILY,
        "worker_isolation": "subprocess-per-repository-strategy",
        "worker_input_fields": ["id", "query"],
        "hidden_fields": ["expected_files", "expected_symbols"],
        "strategies": [
            "grep",
            "hashmarks.find_task",
            "hashmarks.task_entry_points",
            "hashmarks.ambiguity_reviewer",
        ],
        "limit": limit,
        "repositories": [
            {
                "name": repo["name"],
                "public_task_sha256": repo["public_task_sha256"],
                "hidden_corpus_sha256": repo["hidden_corpus_sha256"],
            }
            for repo in repo_reports
        ],
    }
    grep_top1 = aggregate("grep", "top1_rate")
    hm_top1 = aggregate("hashmarks", "top1_rate")
    grep_top5 = aggregate("grep", "top5_rate")
    hm_top5 = aggregate("hashmarks", "top5_rate")
    grep_top20 = aggregate("grep", "top20_all_expected_rate")
    hm_top20 = aggregate("hashmarks", "top20_all_expected_rate")
    ep_top1 = aggregate("entry_points", "top1_rate")
    ep_top5 = aggregate("entry_points", "top5_rate")
    ep_top20 = aggregate("entry_points", "top20_all_expected_rate")
    entry_rows = [
        row
        for repo in repo_reports
        for row in repo["entry_points"]["tasks"]
        if isinstance(row, dict)
    ]
    ep_failures = [row for row in entry_rows if not bool(row.get("top1"))]
    ep_successes = [row for row in entry_rows if bool(row.get("top1"))]
    ep_ambiguous = [row for row in entry_rows if bool(row.get("ambiguous"))]
    ep_ambiguous_failures = [row for row in ep_failures if bool(row.get("ambiguous"))]
    ep_ambiguous_successes = [row for row in ep_successes if bool(row.get("ambiguous"))]
    reviewer_rows = []
    for repo in repo_reports:
        reviews = repo.get("ambiguity_reviewer", {})
        entry_tasks = repo["entry_points"]["tasks"]
        for row in entry_tasks:
            if not isinstance(row, dict):
                continue
            review = (
                reviews.get(str(row.get("id") or ""), {})
                if isinstance(reviews, dict)
                else {}
            )
            warned = (
                bool(review.get("ambiguous")) if isinstance(review, dict) else False
            )
            failed = not bool(row.get("top1"))
            reviewer_rows.append(
                {"id": row.get("id"), "failed": failed, "warned": warned}
            )
    reviewer_failures = [row for row in reviewer_rows if row["failed"]]
    reviewer_successes = [row for row in reviewer_rows if not row["failed"]]
    reviewer_warnings = [row for row in reviewer_rows if row["warned"]]
    reviewer_true_warnings = [
        row for row in reviewer_rows if row["warned"] and row["failed"]
    ]
    return {
        "schema": SCHEMA,
        "protocol": protocol,
        "protocol_identity": _identity(protocol),
        "summary": {
            "repositories": len(repo_reports),
            "tasks": total_tasks,
            "grep_top1_rate": grep_top1,
            "hashmarks_top1_rate": hm_top1,
            "top1_delta": hm_top1 - grep_top1,
            "grep_top5_rate": grep_top5,
            "hashmarks_top5_rate": hm_top5,
            "top5_delta": hm_top5 - grep_top5,
            "grep_top20_all_expected_rate": grep_top20,
            "hashmarks_top20_all_expected_rate": hm_top20,
            "top20_delta": hm_top20 - grep_top20,
            "entry_points_top1_rate": ep_top1,
            "entry_points_top5_rate": ep_top5,
            "entry_points_top20_all_expected_rate": ep_top20,
            "entry_points_vs_find_task_top1_delta": ep_top1 - hm_top1,
            "entry_points_ambiguous_tasks": len(ep_ambiguous),
            "entry_points_top1_failures": len(ep_failures),
            "entry_points_top1_failures_flagged_ambiguous": len(ep_ambiguous_failures),
            "entry_points_top1_failure_ambiguity_recall": (
                len(ep_ambiguous_failures) / len(ep_failures) if ep_failures else 1.0
            ),
            "entry_points_successes_flagged_ambiguous": len(ep_ambiguous_successes),
            "entry_points_success_ambiguity_rate": (
                len(ep_ambiguous_successes) / len(ep_successes) if ep_successes else 0.0
            ),
            "reviewer_spawn": "independent-subprocess-per-repository",
            "reviewer_top1_failure_recall": (
                len(reviewer_true_warnings) / len(reviewer_failures)
                if reviewer_failures
                else 1.0
            ),
            "reviewer_success_false_positive_rate": (
                sum(row["warned"] for row in reviewer_successes)
                / len(reviewer_successes)
                if reviewer_successes
                else 0.0
            ),
            "reviewer_warning_precision": (
                len(reviewer_true_warnings) / len(reviewer_warnings)
                if reviewer_warnings
                else 1.0
            ),
            "reviewer_warnings": len(reviewer_warnings),
        },
        "repositories": repo_reports,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run answer-blind subprocess worker A/B localization benchmark"
    )
    parser.add_argument("--worker", action="store_true")
    parser.add_argument(
        "--strategy",
        choices=["grep", "hashmarks", "entry-points", "ambiguity-reviewer"],
    )
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--tasks", type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    if args.worker:
        if (
            args.strategy is None
            or args.workspace is None
            or args.tasks is None
            or args.output is None
        ):
            parser.error("worker mode requires --strategy --workspace --tasks --output")
        run_worker(
            strategy=args.strategy,
            workspace=args.workspace,
            tasks_path=args.tasks,
            output=args.output,
            limit=args.limit,
        )
        return
    if args.root is None:
        parser.error("benchmark mode requires --root")
    payload = collect(args.root, limit=args.limit)
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)  # noqa: T201 - intentional command output


if __name__ == "__main__":
    main()
