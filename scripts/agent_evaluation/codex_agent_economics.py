from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_S = Path(__file__).resolve().parent
_R = _S.parent.parent
for x in (str(_R), str(_S)):
    if x not in sys.path:
        sys.path.insert(0, x)
from .metrics_blind_worker_ab import (  # noqa: E402 - import follows standalone script path setup
    _load_corpus,
    _sha256_bytes,
    materialize_challenge,
)

SCHEMA = "hashmarks.codex-agent-economics.v1"
PROTOCOL = "hashmarks.codex-agent-economics-protocol.v1"
FAMILY = "hashmarks-v0.10.47-real-codex-a"
LANES = ("native", "hashmarks", "selective")


def _identity(v: object) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(v, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )


def _schema(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "task_id",
                    "first_edit_target",
                    "verification_target",
                    "confidence",
                    "notes",
                ],
                "properties": {
                    "task_id": {"type": "string"},
                    "first_edit_target": {"type": ["string", "null"]},
                    "verification_target": {"type": ["string", "null"]},
                    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                    "notes": {"type": "string"},
                },
            },
            indent=2,
        )
        + "\n"
    )


def _prompt(lane: str, task: dict[str, str], workspace: Path, bridge: Path) -> str:
    common = f"""You are an isolated coding-repository worker in a controlled economics benchmark.\nTask id: {task["id"]}\nTask: {task["query"]}\nRepository root: {workspace}\nDo not modify repository files. Determine the single best first edit target and the best verification/test target. Use only evidence available in this repository and allowed tools. Return only the structured result required by the output schema. Never invent a path.\n"""
    if lane == "native":
        return (
            common
            + """Strategy: NATIVE ARCHAEOLOGY. Do not invoke Hashmarks or any hashmarks script/module. Use normal repository archaeology (grep/rg/find/read/list) as needed.\n"""
        )
    mode = "current" if lane == "hashmarks" else "selective"
    return (
        common
        + f"""Strategy: HASHMARKS {mode.upper()}. Before other repository search, run this exact evidence command from any directory:\n{shlex.quote(sys.executable)} {shlex.quote(str(bridge))} --workspace {shlex.quote(str(workspace))} --mode {mode} --query {shlex.quote(task["query"])}\nUse that evidence packet as your map. You may read the returned files to verify them. Avoid broad grep/list scans unless the packet is insufficient.\n"""
    )


def _usage_from_jsonl(text: str) -> dict[str, int | None]:
    totals = {
        "input_tokens": None,
        "cached_input_tokens": None,
        "output_tokens": None,
        "reasoning_output_tokens": None,
        "total_tokens": None,
    }
    best = {}

    def walk(v: Any):
        if isinstance(v, dict):
            yield v
            for x in v.values():
                yield from walk(x)
        elif isinstance(v, list):
            for x in v:
                yield from walk(x)

    for line in text.splitlines():
        try:
            obj = json.loads(line)
        except Exception:
            continue
        for d in walk(obj):
            for key in totals:
                val = d.get(key)
                if isinstance(val, int) and val >= 0:
                    best[key] = max(best.get(key, 0), val)
    totals.update(best)
    return totals


def _run_one(
    codex: str,
    lane: str,
    task: dict[str, str],
    workspace: Path,
    run_dir: Path,
    *,
    model: str | None,
    effort: str | None,
    sandbox: str,
    bridge: Path,
    timeout_s: int,
) -> dict[str, object]:
    run_dir.mkdir(parents=True, exist_ok=True)
    schema = run_dir / "output.schema.json"
    final = run_dir / "final.json"
    events = run_dir / "events.jsonl"
    stderr = run_dir / "stderr.txt"
    _schema(schema)
    cmd = [
        codex,
        "exec",
        "-C",
        str(workspace),
        "--skip-git-repo-check",
        "--sandbox",
        sandbox,
        "--json",
        "--output-schema",
        str(schema),
        "--output-last-message",
        str(final),
    ]
    if model:
        cmd += ["-m", model]
    if effort:
        cmd += ["-c", f'model_reasoning_effort="{effort}"']
    cmd += ["-"]
    prompt = _prompt(lane, task, workspace, bridge)
    (run_dir / "prompt.txt").write_text(prompt)
    t = time.perf_counter()
    try:
        cp = subprocess.run(
            cmd,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=timeout_s,
            env=dict(os.environ),
        )
        rc = cp.returncode
        out = cp.stdout
        err = cp.stderr
    except subprocess.TimeoutExpired as exc:
        rc = 124
        out = exc.stdout or ""
        err = (exc.stderr or "") + "\nTIMEOUT"
    elapsed = (time.perf_counter() - t) * 1000
    events.write_text(out)
    stderr.write_text(err)
    parsed = None
    parse_error = None
    if final.is_file():
        try:
            parsed = json.loads(final.read_text())
        except Exception as e:
            parse_error = f"{type(e).__name__}: {e}"
    return {
        "lane": lane,
        "task_id": task["id"],
        "returncode": rc,
        "elapsed_ms": elapsed,
        "command": cmd,
        "final_message_present": final.is_file(),
        "final": parsed,
        "parse_error": parse_error,
        "usage": _usage_from_jsonl(out),
        "events_sha256": "sha256:" + hashlib.sha256(out.encode()).hexdigest(),
        "stderr_sha256": "sha256:" + hashlib.sha256(err.encode()).hexdigest(),
    }


def _score(
    repo_name: str, hidden: list[dict[str, Any]], runs: list[dict[str, object]]
) -> dict[str, object]:
    expected_verify = {
        "python-orders": "tests/test_orders.py",
        "typescript-dashboard": "tests/MetricsPanel.test.tsx",
        "release-contracts": "tests/test_release_contract.py",
    }[repo_name]
    by_id = {str(r["task_id"]): r for r in runs}
    rows = []
    for t in hidden:
        r = by_id[str(t["id"])]
        final = r.get("final") if isinstance(r.get("final"), dict) else {}
        exp = {str(x) for x in t.get("expected_files", [])}
        edit = str(final.get("first_edit_target") or "")
        verify = str(final.get("verification_target") or "")
        rows.append(
            {
                "id": t["id"],
                "completed": r["returncode"] == 0 and bool(final),
                "correct_first_edit": edit in exp,
                "correct_verification": verify == expected_verify,
                "first_edit_target": edit or None,
                "verification_target": verify or None,
                "elapsed_ms": r["elapsed_ms"],
                "usage": r["usage"],
            }
        )
    n = len(rows)

    def tsum(k):
        return sum(int((r["usage"] or {}).get(k) or 0) for r in rows)

    return {
        "summary": {
            "tasks": n,
            "completed": sum(bool(r["completed"]) for r in rows),
            "correct_first_edits": sum(bool(r["correct_first_edit"]) for r in rows),
            "correct_verifications": sum(bool(r["correct_verification"]) for r in rows),
            "wrong_first_edits": sum(not bool(r["correct_first_edit"]) for r in rows),
            "elapsed_ms": sum(float(r["elapsed_ms"]) for r in rows),
            "input_tokens": tsum("input_tokens"),
            "cached_input_tokens": tsum("cached_input_tokens"),
            "output_tokens": tsum("output_tokens"),
            "reasoning_output_tokens": tsum("reasoning_output_tokens"),
            "total_tokens": tsum("total_tokens"),
        },
        "tasks": rows,
    }


def collect(
    root: Path,
    *,
    codex_bin: str,
    model: str | None,
    effort: str | None,
    sandbox: str = "read-only",
    limit: int = 20,
    timeout_s: int = 900,
    lanes: tuple[str, ...] = LANES,
    max_tasks: int | None = None,
) -> dict[str, object]:
    codex_path = (
        shutil.which(codex_bin)
        if os.sep not in codex_bin
        else (codex_bin if Path(codex_bin).is_file() else None)
    )
    if not codex_path:
        raise FileNotFoundError(f"Codex executable not found: {codex_bin}")
    bridge = (_S / "codex_context_bridge.py").resolve()
    reports = []
    for name, workspace, corpus, public_path in materialize_challenge(
        root / "challenge"
    ):
        public = json.loads(public_path.read_text())["tasks"]
        hidden = _load_corpus(corpus)
        if max_tasks is not None:
            public = public[:max_tasks]
            hidden = hidden[:max_tasks]
        repo = {
            "name": name,
            "public_task_sha256": _sha256_bytes(public_path.read_bytes()),
            "hidden_corpus_sha256": _sha256_bytes(corpus.read_bytes()),
            "lanes": {},
        }
        for lane in lanes:
            runs = []
            for task in public:
                runs.append(
                    _run_one(
                        str(codex_path),
                        lane,
                        task,
                        workspace,
                        root / "runs" / name / lane / task["id"],
                        model=model,
                        effort=effort,
                        sandbox=sandbox,
                        bridge=bridge,
                        timeout_s=timeout_s,
                    )
                )
            repo["lanes"][lane] = _score(name, hidden, runs)
            repo["lanes"][lane]["raw_runs"] = runs
        reports.append(repo)
    summary = {
        "repositories": len(reports),
        "tasks": sum(int(r["lanes"][lanes[0]]["summary"]["tasks"]) for r in reports),
    }
    for lane in lanes:
        for k in (
            "completed",
            "correct_first_edits",
            "correct_verifications",
            "wrong_first_edits",
            "elapsed_ms",
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "reasoning_output_tokens",
            "total_tokens",
        ):
            summary[f"{lane}_{k}"] = sum(
                float(r["lanes"][lane]["summary"][k]) for r in reports
            )
    protocol = {
        "schema": PROTOCOL,
        "family": FAMILY,
        "execution": "independent-codex-exec-per-repository-task-lane",
        "lanes": list(lanes),
        "public_task_fields": ["id", "query"],
        "hidden_grader_fields": [
            "expected_files",
            "expected_symbols",
            "expected_verification",
        ],
        "sandbox": sandbox,
        "model": model,
        "reasoning_effort": effort,
        "output_contract": "codex exec --output-schema + --output-last-message",
        "jsonl_usage": "best available token counters from codex --json stream; zero means unavailable, never inferred",
        "history": "fresh independent codex exec process; no parent conversation inheritance",
        "limit": limit,
    }
    return {
        "schema": SCHEMA,
        "protocol": protocol,
        "protocol_identity": _identity(protocol),
        "summary": summary,
        "repositories": reports,
    }


def preflight(codex_bin: str) -> dict[str, object]:
    path = shutil.which(codex_bin) if os.sep not in codex_bin else codex_bin
    if not path or not Path(path).exists():
        return {
            "available": False,
            "codex_bin": codex_bin,
            "reason": "executable-not-found",
        }
    cp = subprocess.run(
        [str(path), "--version"], text=True, capture_output=True, timeout=20
    )
    return {
        "available": cp.returncode == 0,
        "codex_bin": str(path),
        "version": (cp.stdout or cp.stderr).strip(),
        "returncode": cp.returncode,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--root", type=Path, default=Path(".hashmarks/benchmarks/codex-agent-economics")
    )
    p.add_argument("--codex-bin", default="codex")
    p.add_argument("--model")
    p.add_argument("--reasoning-effort")
    p.add_argument("--sandbox", default="read-only")
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--max-tasks", type=int)
    p.add_argument("--lanes", default=",".join(LANES))
    p.add_argument("--preflight", action="store_true")
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    if a.preflight:
        value = {
            "schema": "hashmarks.codex-agent-preflight.v1",
            **preflight(a.codex_bin),
        }
    else:
        value = collect(
            a.root,
            codex_bin=a.codex_bin,
            model=a.model,
            effort=a.reasoning_effort,
            sandbox=a.sandbox,
            timeout_s=a.timeout,
            lanes=tuple(x.strip() for x in a.lanes.split(",") if x.strip()),
            max_tasks=a.max_tasks,
        )
    text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(text)
    print(text, end="")  # noqa: T201 - intentional command output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
