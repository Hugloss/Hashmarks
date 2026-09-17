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


def worker(
    repo_s: str, task: dict[str, str], strategy: str, limit: int, trace_dir_s: str
) -> dict[str, Any]:
    repo = Path(repo_s)
    td = Path(trace_dir_s)
    td.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    ev = []
    cold = 0.0
    scans_f = scans_b = 0
    q = task["query"]
    ambiguity = False
    alternatives = []
    if strategy == "native":
        fs = _repository_files(repo)
        sb = sum(p.stat().st_size for p in fs)
        t = time.perf_counter()
        h = _grep_worker(repo, q, limit=limit)
        search = (time.perf_counter() - t) * 1000
        cand = [str(x.get("path") or "") for x in h]
        scans_f += len(fs)
        scans_b += sb
        first = cand[0] if cand else None
        ev.append(
            {
                "op": "grep",
                "elapsed_ms": search,
                "scan_files": len(fs),
                "scan_bytes": sb,
                "candidates": cand[:10],
            }
        )
        t = time.perf_counter()
        vh = _grep_worker(repo, q + " test verification", limit=limit)
        vms = (time.perf_counter() - t) * 1000
        vp = [str(x.get("path") or "") for x in vh]
        scans_f += len(fs)
        scans_b += sb
    else:
        with CodeMap(repo) as cm:
            t = time.perf_counter()
            cm.sync()
            cold = (time.perf_counter() - t) * 1000
            ev.append({"op": "sync", "elapsed_ms": cold})
            if strategy == "find-task":
                t = time.perf_counter()
                h = cm.find_task(q, limit=limit)
                search = (time.perf_counter() - t) * 1000
                cand = [x.path for x in h]
                first = cand[0] if cand else None
                ev.append(
                    {"op": "find_task", "elapsed_ms": search, "candidates": cand[:10]}
                )
            else:
                t = time.perf_counter()
                e = cm.task_entry_points(q, limit=limit)
                search = (time.perf_counter() - t) * 1000
                rec = [x for x in e.get("recommended", []) if isinstance(x, dict)]
                cand = [str(x.get("path") or "") for x in rec]
                first = cand[0] if cand else None
                amb = (
                    e.get("ambiguity", {})
                    if isinstance(e.get("ambiguity"), dict)
                    else {}
                )
                ambiguity = bool(amb.get("ambiguous"))
                alternatives = list(amb.get("alternatives", [])) if ambiguity else []
                ev.append(
                    {
                        "op": "task_entry_points",
                        "elapsed_ms": search,
                        "ambiguous": ambiguity,
                        "candidates": cand[:10],
                    }
                )
                if strategy == "task-entry-selective" and ambiguity:
                    r = _resolve_after_inspection(q, alternatives)
                    ev.append(
                        {"op": "resolve", "resolution": r, "alternatives": alternatives}
                    )
                    if r.get("resolved"):
                        first = str(r.get("target") or first)
            t = time.perf_counter()
            vh = cm.find_task(q + " test verification", limit=limit)
            vms = (time.perf_counter() - t) * 1000
            vp = [x.path for x in vh]
    verify = next((p for p in vp if is_test(p)), None)
    ev.append(
        {
            "op": "verify_search",
            "elapsed_ms": vms,
            "selected": verify,
            "candidates": vp[:10],
        }
    )
    evidence = list(
        dict.fromkeys(
            ([first] if first else []) + cand[:3] + ([verify] if verify else [])
        )
    )
    c = cost(repo, evidence)
    elapsed = (time.perf_counter() - start) * 1000
    r = {
        "schema": TRACE,
        "pid": os.getpid(),
        "strategy": strategy,
        "task": task,
        "first_edit_target": first,
        "top_candidates": cand[:limit],
        "verification_target": verify,
        "ambiguous": ambiguity,
        "cold_setup_ms": cold,
        "repository_scan_files": scans_f,
        "repository_scan_bytes": scans_b,
        "evidence_read": c,
        "elapsed_ms": elapsed,
        "events": ev,
    }
    path = td / f"{strategy}__{task['id']}.json"
    path.write_text(json.dumps(r, indent=2, sort_keys=True) + "\n")
    r["trace_file"] = str(path)
    return r


def run(
    repo: Path,
    public_path: Path,
    secret_path: Path,
    out: Path,
    trace_dir: Path,
    workers: int,
    limit: int,
) -> dict[str, Any]:
    pub = json.loads(public_path.read_text())["tasks"]
    sec = json.loads(secret_path.read_text())["tasks"]
    allowed = {"id", "query"}
    if any(set(t) != allowed for t in pub):
        raise ValueError("public tasks must contain only id/query")
    jobs = [(t, s) for t in pub for s in STRATEGIES]
    frozen = []
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = [
            ex.submit(worker, str(repo), t, s, limit, str(trace_dir)) for t, s in jobs
        ]
        for f in as_completed(futs):
            frozen.append(f.result())
    frozen.sort(key=lambda r: (r["task"]["id"], r["strategy"]))
    exp = {str(t["id"]): set(map(str, t.get("expected_files") or [])) for t in sec}
    syms = {str(t["id"]): set(map(str, t.get("expected_symbols") or [])) for t in sec}
    rows = []
    for r in frozen:
        e = exp[r["task"]["id"]]
        top = r["top_candidates"]
        rows.append(
            {
                **r,
                "expected_files": sorted(e),
                "expected_symbols": sorted(syms[r["task"]["id"]]),
                "correct_first_edit": r["first_edit_target"] in e,
                "top5_any_expected": bool(e.intersection(top[:5])),
                "top20_all_expected": e.issubset(set(top[:20])),
                "verification_found": bool(r["verification_target"]),
            }
        )
    sm = {
        "repo": str(repo),
        "tasks": len(pub),
        "workers_launched": len(jobs),
        "max_parallel_workers": workers,
        "wall_ms": (time.perf_counter() - t0) * 1000,
        "strategies": {},
    }
    for s in STRATEGIES:
        rs = [r for r in rows if r["strategy"] == s]
        n = len(rs)
        sm["strategies"][s] = {
            "tasks": n,
            "correct_first_edits": sum(x["correct_first_edit"] for x in rs),
            "correct_first_edit_rate": sum(x["correct_first_edit"] for x in rs) / n,
            "top5_any_expected": sum(x["top5_any_expected"] for x in rs),
            "top20_all_expected": sum(x["top20_all_expected"] for x in rs),
            "verification_found": sum(x["verification_found"] for x in rs),
            "ambiguous_tasks": sum(x["ambiguous"] for x in rs),
            "cold_setup_ms": sum(float(x["cold_setup_ms"]) for x in rs),
            "worker_elapsed_ms": sum(float(x["elapsed_ms"]) for x in rs),
            "repository_scan_files": sum(int(x["repository_scan_files"]) for x in rs),
            "repository_scan_bytes": sum(int(x["repository_scan_bytes"]) for x in rs),
            "evidence_bytes_read": sum(int(x["evidence_read"]["bytes"]) for x in rs),
            "evidence_approx_tokens": sum(
                int(x["evidence_read"]["approx_tokens"]) for x in rs
            ),
        }
    protocol = {
        "public_fields": ["id", "query"],
        "hidden_fields": ["expected_files", "expected_symbols"],
        "secret_outside_worker_repo": True,
        "answer_key_removed_from_repo": not (
            repo / "benchmarks/agent_tasks.json"
        ).exists(),
        "trace_freeze_before_grading": True,
        "strategies": list(STRATEGIES),
        "limit": limit,
        "public_sha256": "sha256:"
        + hashlib.sha256(public_path.read_bytes()).hexdigest(),
        "secret_sha256": "sha256:"
        + hashlib.sha256(secret_path.read_bytes()).hexdigest(),
    }
    result = {
        "schema": SCHEMA,
        "protocol": protocol,
        "protocol_identity": ident(protocol),
        "summary": sm,
        "results": rows,
    }
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
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
    r = run(a.repo, a.public, a.secret, a.output, a.trace_dir, a.workers, a.limit)
    print(json.dumps(r["summary"], indent=2, sort_keys=True))  # noqa: T201 - intentional command output


if __name__ == "__main__":
    main()
