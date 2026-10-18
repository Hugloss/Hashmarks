from __future__ import annotations

import argparse
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, NotRequired, TypedDict

from hashmarks._command_output import log_command_output
from hashmarks.codemap import (
    CodeMap,
)

from .metrics_blind_worker_ab import (
    _grep_worker,
    _load_corpus,
    _repository_files,
    _sha256_bytes,
    materialize_challenge,
)

logger = logging.getLogger(__name__)

SCHEMA = "hashmarks.agent-economics.v1"
PROTOCOL_SCHEMA = "hashmarks.agent-economics-protocol.v1"
FAMILY = "hashmarks-agent-economics-a"


class FileCostRow(TypedDict):
    path: str
    bytes: int


class FileCost(TypedDict):
    files: int
    bytes: int
    approx_tokens: int
    rows: list[FileCostRow]


class WorkerTaskObservation(TypedDict):
    id: str
    query: str
    first_edit_target: str | None
    verification_target: str | None
    search_ms: float
    repository_scan_files: int
    repository_scan_bytes: int
    evidence_read: FileCost
    verification_candidates_examined: int
    search_calls: NotRequired[int]
    hashmarks_calls: NotRequired[int]
    ambiguous: NotRequired[bool]


class WorkerObservation(TypedDict):
    strategy: str
    cold_setup_ms: float
    tasks: list[WorkerTaskObservation]
    elapsed_ms: float


class TaskEconomicsScore(TypedDict):
    id: str
    correct_first_edit: bool
    correct_verification: bool
    first_edit_target: str
    verification_target: str
    evidence_read: FileCost
    search_ms: float
    repository_scan_files: int
    repository_scan_bytes: int
    verification_candidates_examined: int


class EconomicsScore(TypedDict):
    summary: dict[str, int | float]
    tasks: list[TaskEconomicsScore]
    cold_setup_ms: NotRequired[float]
    elapsed_ms: NotRequired[float]


class EconomicsRepositoryReport(TypedDict):
    name: str
    public_task_sha256: str
    hidden_corpus_sha256: str
    strategies: dict[str, EconomicsScore]


def _identity(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _approx_tokens(num_bytes: int) -> int:
    return max(1, (num_bytes + 3) // 4) if num_bytes else 0


def _file_cost(workspace: Path, paths: list[str]) -> FileCost:
    seen: set[str] = set()
    rows: list[FileCostRow] = []
    total = 0
    for rel in paths:
        if not rel or rel in seen:
            continue
        seen.add(rel)
        p = workspace / rel
        if not p.is_file():
            continue
        size = p.stat().st_size
        total += size
        rows.append({"path": rel, "bytes": size})
    return {
        "files": len(rows),
        "bytes": total,
        "approx_tokens": _approx_tokens(total),
        "rows": rows,
    }


def _verification_target(
    workspace: Path, query: str, *, limit: int, codemap: CodeMap | None = None
) -> tuple[str | None, int]:
    if codemap is not None:
        hits = codemap.search.find_task(query + " test verification", limit=limit)
        paths = [h.path for h in hits]
    else:
        paths = [
            str(r.get("path") or "")
            for r in _grep_worker(workspace, query + " test verification", limit=limit)
        ]
    for idx, path in enumerate(paths, 1):
        low = path.casefold()
        name = Path(path).name.casefold()
        if (
            "/tests/" in f"/{low}"
            or name.startswith("test_")
            or ".test." in name
            or ".spec." in name
        ):
            return path, idx
    return None, len(paths)


def _native_worker(
    workspace: Path, tasks: list[dict[str, str]], *, limit: int
) -> WorkerObservation:
    repo_files = _repository_files(workspace)
    scan_bytes = sum(p.stat().st_size for p in repo_files)
    rows: list[WorkerTaskObservation] = []
    started = time.perf_counter()
    for task in tasks:
        q = task["query"]
        t0 = time.perf_counter()
        hits = _grep_worker(workspace, q, limit=limit)
        search_ms = (time.perf_counter() - t0) * 1000
        first = str(hits[0].get("path") or "") if hits else None
        verify, vpos = _verification_target(workspace, q, limit=limit, codemap=None)
        read = _file_cost(workspace, [first or "", verify or ""])
        rows.append(
            {
                "id": task["id"],
                "query": q,
                "first_edit_target": first,
                "verification_target": verify,
                "search_ms": search_ms,
                "search_calls": 2,
                "repository_scan_files": len(repo_files) * 2,
                "repository_scan_bytes": scan_bytes * 2,
                "evidence_read": read,
                "verification_candidates_examined": vpos,
            }
        )
    return {
        "strategy": "native-archaeology",
        "cold_setup_ms": 0.0,
        "tasks": rows,
        "elapsed_ms": (time.perf_counter() - started) * 1000,
    }


def _hashmarks_worker(
    workspace: Path, tasks: list[dict[str, str]], *, limit: int
) -> WorkerObservation:
    rows: list[WorkerTaskObservation] = []
    started = time.perf_counter()
    with CodeMap(workspace) as cm:
        t0 = time.perf_counter()
        cm.index.sync()
        cold_ms = (time.perf_counter() - t0) * 1000
        for task in tasks:
            q = task["query"]
            t1 = time.perf_counter()
            entry = cm.tasks.entry_points(q, limit=limit)
            query_ms = (time.perf_counter() - t1) * 1000
            rec = entry.get("recommended", [])
            if not isinstance(rec, list):
                raise ValueError("task entry recommendations must be an array")
            rec = [row for row in rec if isinstance(row, dict)]
            ambiguity = entry.get("ambiguity")
            first = str(rec[0].get("path") or "") if rec else None
            verify, vpos = _verification_target(workspace, q, limit=limit, codemap=cm)
            selected = [str(r.get("path") or "") for r in rec[:3]]
            read = _file_cost(workspace, selected + [verify or ""])
            rows.append(
                {
                    "id": task["id"],
                    "query": q,
                    "first_edit_target": first,
                    "verification_target": verify,
                    "search_ms": query_ms,
                    "hashmarks_calls": 2,
                    "repository_scan_files": 0,
                    "repository_scan_bytes": 0,
                    "evidence_read": read,
                    "verification_candidates_examined": vpos,
                    "ambiguous": bool(ambiguity.get("ambiguous"))
                    if isinstance(ambiguity, dict)
                    else False,
                }
            )
    return {
        "strategy": "hashmarks-current",
        "cold_setup_ms": cold_ms,
        "tasks": rows,
        "elapsed_ms": (time.perf_counter() - started) * 1000,
    }


def _score(
    repo_name: str, hidden: list[dict[str, Any]], result: WorkerObservation
) -> EconomicsScore:
    expected_verification = {
        "python-orders": "tests/test_orders.py",
        "typescript-dashboard": "tests/MetricsPanel.test.tsx",
        "release-contracts": "tests/test_release_contract.py",
    }[repo_name]
    by_id = {str(r.get("id") or ""): r for r in result["tasks"]}
    rows: list[TaskEconomicsScore] = []
    for task in hidden:
        tid = str(task.get("id") or "")
        expected = {str(x) for x in task.get("expected_files") or ()}
        obs = by_id[tid]
        first = str(obs.get("first_edit_target") or "")
        verification = str(obs.get("verification_target") or "")
        rows.append(
            {
                "id": tid,
                "correct_first_edit": first in expected,
                "correct_verification": verification == expected_verification,
                "first_edit_target": first,
                "verification_target": verification,
                "evidence_read": obs["evidence_read"],
                "search_ms": obs["search_ms"],
                "repository_scan_files": obs.get("repository_scan_files", 0),
                "repository_scan_bytes": obs.get("repository_scan_bytes", 0),
                "verification_candidates_examined": obs.get(
                    "verification_candidates_examined", 0
                ),
            }
        )
    n = len(rows)
    evidence_bytes = sum(int(r["evidence_read"]["bytes"]) for r in rows)
    return {
        "summary": {
            "tasks": n,
            "correct_first_edits": sum(bool(r["correct_first_edit"]) for r in rows),
            "correct_verifications": sum(bool(r["correct_verification"]) for r in rows),
            "wrong_first_edits": sum(not bool(r["correct_first_edit"]) for r in rows),
            "evidence_files_read": sum(int(r["evidence_read"]["files"]) for r in rows),
            "evidence_bytes_read": evidence_bytes,
            "evidence_approx_tokens": _approx_tokens(evidence_bytes),
            "repository_scan_files": sum(int(r["repository_scan_files"]) for r in rows),
            "repository_scan_bytes": sum(int(r["repository_scan_bytes"]) for r in rows),
            "search_ms": sum(float(r["search_ms"]) for r in rows),
            "verification_candidates_examined": sum(
                int(r["verification_candidates_examined"]) for r in rows
            ),
        },
        "tasks": rows,
    }


def collect(
    root: Path, *, strategies: tuple[str, ...], limit: int = 20
) -> dict[str, object]:
    reports = []
    for name, workspace, corpus, public_path in materialize_challenge(
        root / "challenge"
    ):
        public = json.loads(public_path.read_text())["tasks"]
        hidden = _load_corpus(corpus)
        repo: EconomicsRepositoryReport = {
            "name": name,
            "public_task_sha256": _sha256_bytes(public_path.read_bytes()),
            "hidden_corpus_sha256": _sha256_bytes(corpus.read_bytes()),
            "strategies": {},
        }
        for strategy in strategies:
            raw = (
                _native_worker(workspace, public, limit=limit)
                if strategy == "native"
                else _hashmarks_worker(workspace, public, limit=limit)
            )
            scored = _score(name, hidden, raw)
            scored["cold_setup_ms"] = raw["cold_setup_ms"]
            scored["elapsed_ms"] = raw["elapsed_ms"]
            repo["strategies"][strategy] = scored
        reports.append(repo)

    def aggregate(strategy: str, key: str) -> float:
        return sum(float(r["strategies"][strategy]["summary"][key]) for r in reports)

    tasks = sum(
        int(r["strategies"][strategies[0]]["summary"]["tasks"]) for r in reports
    )
    summary: dict[str, int | float] = {"repositories": len(reports), "tasks": tasks}
    for strategy in strategies:
        prefix = "native" if strategy == "native" else "hashmarks"
        for key in (
            "correct_first_edits",
            "wrong_first_edits",
            "correct_verifications",
            "evidence_files_read",
            "evidence_bytes_read",
            "evidence_approx_tokens",
            "repository_scan_files",
            "repository_scan_bytes",
            "verification_candidates_examined",
        ):
            summary[f"{prefix}_{key}"] = aggregate(strategy, key)
        summary[f"{prefix}_cold_setup_ms"] = sum(
            float(r["strategies"][strategy]["cold_setup_ms"]) for r in reports
        )
        summary[f"{prefix}_search_ms"] = aggregate(strategy, "search_ms")
    protocol = {
        "schema": PROTOCOL_SCHEMA,
        "family": FAMILY,
        "strategies": list(strategies),
        "worker_public_fields": ["id", "query"],
        "hidden_fields": [
            "expected_files",
            "expected_symbols",
            "expected_verification",
        ],
        "cost_model": {
            "cold_setup": "reported separately",
            "native_scan": "actual repository file bytes scanned per grep-style search",
            "hashmarks_task": "selected worker evidence bytes only; index sync amortized separately",
            "token_estimate": "selected evidence bytes/4, deterministic proxy only",
        },
        "limit": limit,
        "repositories": [
            {
                "name": r["name"],
                "public_task_sha256": r["public_task_sha256"],
                "hidden_corpus_sha256": r["hidden_corpus_sha256"],
            }
            for r in reports
        ],
    }
    return {
        "schema": SCHEMA,
        "protocol": protocol,
        "protocol_identity": _identity(protocol),
        "summary": summary,
        "repositories": reports,
    }


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--mode", choices=["native", "paired"], default="paired")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--output", type=Path)
    return p


def main() -> int:
    p = _parser()
    a = p.parse_args()
    strategies = ("native",) if a.mode == "native" else ("native", "hashmarks")
    result = collect(a.root, strategies=strategies, limit=a.limit)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(text)
    log_command_output(logger, text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
