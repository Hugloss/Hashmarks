# Imports below follow the standalone script path bootstrap.
# ruff: noqa: E402
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

_S = Path(__file__).resolve().parent
_R = _S.parent.parent
for x in (str(_R), str(_S)):
    if x not in sys.path:
        sys.path.insert(0, x)
import contextlib

from .codex_agent_economics import (
    CodexRunConfig,
    _run_one,
    _usage_from_jsonl,
)
from .codex_context_bridge import (
    packet as context_packet,
)
from .metrics_blind_worker_ab import (
    _load_corpus,
    _sha256_bytes,
    materialize_challenge,
)

SCHEMA = "hashmarks.codex-selective-scout-economics.v1"
PROTOCOL = "hashmarks.codex-selective-scout-economics-protocol.v1"
FAMILY = "hashmarks-v0.10.48-real-selective-scout-a"


def _id(v: object) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(v, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )


def _scout_schema(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["task_id", "recommended_path", "confidence", "reason"],
                "properties": {
                    "task_id": {"type": "string"},
                    "recommended_path": {"type": ["string", "null"]},
                    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                    "reason": {"type": "string"},
                },
            },
            indent=2,
        )
        + "\n"
    )


def _scout_prompt(task: dict[str, str], workspace: Path, pkt: dict[str, object]) -> str:
    alts = (
        [
            {
                "role": r.get("role"),
                "path": r.get("path"),
                "canonical_rank": r.get("canonical_rank"),
            }
            for r in pkt.get("ambiguity", {}).get("alternatives", [])
            if isinstance(r, dict)
        ]
        if isinstance(pkt.get("ambiguity"), dict)
        else []
    )
    return f"""You are an isolated READ-ONLY repository scout in a controlled agent-economics benchmark.\nTask id: {task["id"]}\nTask: {task["query"]}\nRepository root: {workspace}\nThe primary Hashmarks worker found competing role evidence. Candidate evidence (worker-visible, no hidden answers):\n{json.dumps(alts, sort_keys=True)}\nInspect only these candidate files if needed. Choose the single candidate path best justified as the first edit/authority target for the task. Do not modify files. Return only the structured output schema. Never choose a path not listed above.\n"""


def _run_scout(
    codex: str,
    task: dict[str, str],
    workspace: Path,
    pkt: dict[str, object],
    run_dir: Path,
    *,
    model: str | None,
    effort: str | None,
    sandbox: str,
    timeout_s: int,
) -> dict[str, object]:
    run_dir.mkdir(parents=True, exist_ok=True)
    schema = run_dir / "output.schema.json"
    final = run_dir / "final.json"
    events = run_dir / "events.jsonl"
    stderr = run_dir / "stderr.txt"
    _scout_schema(schema)
    prompt = _scout_prompt(task, workspace, pkt)
    (run_dir / "prompt.txt").write_text(prompt)
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
    except subprocess.TimeoutExpired as e:
        rc = 124
        out = e.stdout or ""
        err = (e.stderr or "") + "\nTIMEOUT"
    elapsed = (time.perf_counter() - t) * 1000
    events.write_text(out)
    stderr.write_text(err)
    parsed = None
    if final.is_file():
        with contextlib.suppress(Exception):
            parsed = json.loads(final.read_text())
    allowed = (
        {
            str(r.get("path") or "")
            for r in pkt.get("ambiguity", {}).get("alternatives", [])
            if isinstance(r, dict)
        }
        if isinstance(pkt.get("ambiguity"), dict)
        else set()
    )
    if isinstance(parsed, dict) and parsed.get("recommended_path") not in allowed:
        parsed = {
            "task_id": task["id"],
            "recommended_path": None,
            "confidence": "low",
            "reason": "rejected-non-candidate-scout-output",
        }
    return {
        "returncode": rc,
        "elapsed_ms": elapsed,
        "final": parsed,
        "usage": _usage_from_jsonl(out),
        "events_sha256": "sha256:" + hashlib.sha256(out.encode()).hexdigest(),
        "stderr_sha256": "sha256:" + hashlib.sha256(err.encode()).hexdigest(),
    }


def _main_with_scout(
    config: CodexRunConfig,
    task: dict[str, str],
    workspace: Path,
    run_dir: Path,
    scout: dict[str, object] | None,
) -> dict[str, object]:
    # Use the v0.10.47 runner but add frozen scout guidance to the public task text; the grader remains unopened.
    enriched = dict(task)
    if scout and isinstance(scout.get("final"), dict):
        rec = scout["final"].get("recommended_path")
        reason = scout["final"].get("reason")
        enriched["query"] = (
            task["query"]
            + f"\nA separate read-only ambiguity scout recommended candidate path `{rec}` with reason: {reason}. Verify this recommendation against repository evidence before finalizing."
        )
    return _run_one(
        config,
        "hashmarks",
        enriched,
        workspace,
        run_dir,
    )


def collect(
    root: Path,
    *,
    codex_bin: str = "codex",
    model: str | None = None,
    effort: str | None = None,
    sandbox: str = "read-only",
    timeout_s: int = 900,
    max_tasks: int | None = None,
) -> dict[str, object]:
    codex = (
        shutil.which(codex_bin)
        if os.sep not in codex_bin
        else (codex_bin if Path(codex_bin).is_file() else None)
    )
    if not codex:
        raise FileNotFoundError(f"Codex executable not found: {codex_bin}")
    bridge = (_S / "codex_context_bridge.py").resolve()
    main_config = CodexRunConfig(
        codex=str(codex),
        model=model,
        effort=effort,
        sandbox=sandbox,
        bridge=bridge,
        timeout_s=timeout_s,
    )
    reports = []
    for name, workspace, corpus, public_path in materialize_challenge(
        root / "challenge"
    ):
        public = json.loads(public_path.read_text())["tasks"]
        hidden = _load_corpus(corpus)
        if max_tasks is not None:
            public = public[:max_tasks]
            hidden = hidden[:max_tasks]
        runs = []
        scouts = []
        for task in public:
            pkt = context_packet(workspace, task["query"], mode="current")
            ambiguity = (
                pkt.get("ambiguity", {})
                if isinstance(pkt.get("ambiguity"), dict)
                else {}
            )
            scout = None
            if ambiguity.get("ambiguous"):
                scout = _run_scout(
                    str(codex),
                    task,
                    workspace,
                    pkt,
                    root / "runs" / name / task["id"] / "scout",
                    model=model,
                    effort=effort,
                    sandbox=sandbox,
                    timeout_s=timeout_s,
                )
                scouts.append({"task_id": task["id"], **scout})
            main = _main_with_scout(
                main_config,
                task,
                workspace,
                root / "runs" / name / task["id"] / "main",
                scout,
            )
            runs.append(main)
        expv = {
            "python-orders": "tests/test_orders.py",
            "typescript-dashboard": "tests/MetricsPanel.test.tsx",
            "release-contracts": "tests/test_release_contract.py",
        }[name]
        byid = {str(t["id"]): t for t in hidden}
        rows = []
        for task, main in zip(public, runs, strict=False):
            h = byid[task["id"]]
            exp = {str(x) for x in h.get("expected_files", [])}
            final = main.get("final") if isinstance(main.get("final"), dict) else {}
            edit = str(final.get("first_edit_target") or "")
            verify = str(final.get("verification_target") or "")
            sr = next((s for s in scouts if s["task_id"] == task["id"]), None)
            rows.append(
                {
                    "id": task["id"],
                    "scout_spawned": sr is not None,
                    "correct_first_edit": edit in exp,
                    "correct_verification": verify == expv,
                    "main_usage": main["usage"],
                    "scout_usage": sr["usage"] if sr else None,
                    "main_elapsed_ms": main["elapsed_ms"],
                    "scout_elapsed_ms": sr["elapsed_ms"] if sr else 0.0,
                }
            )

        def tok(field, rows=rows):
            return sum(
                int((r["main_usage"] or {}).get(field) or 0)
                + int((r["scout_usage"] or {}).get(field) or 0)
                for r in rows
            )

        reports.append(
            {
                "name": name,
                "public_task_sha256": _sha256_bytes(public_path.read_bytes()),
                "hidden_corpus_sha256": _sha256_bytes(corpus.read_bytes()),
                "summary": {
                    "tasks": len(rows),
                    "correct_first_edits": sum(r["correct_first_edit"] for r in rows),
                    "correct_verifications": sum(
                        r["correct_verification"] for r in rows
                    ),
                    "scout_spawns": sum(r["scout_spawned"] for r in rows),
                    "total_tokens": tok("total_tokens"),
                    "input_tokens": tok("input_tokens"),
                    "output_tokens": tok("output_tokens"),
                    "reasoning_output_tokens": tok("reasoning_output_tokens"),
                    "combined_elapsed_ms": sum(
                        float(r["main_elapsed_ms"]) + float(r["scout_elapsed_ms"])
                        for r in rows
                    ),
                },
                "tasks": rows,
                "scout_runs": scouts,
            }
        )
    summary = {
        "repositories": len(reports),
        "tasks": sum(r["summary"]["tasks"] for r in reports),
        "correct_first_edits": sum(
            r["summary"]["correct_first_edits"] for r in reports
        ),
        "correct_verifications": sum(
            r["summary"]["correct_verifications"] for r in reports
        ),
        "scout_spawns": sum(r["summary"]["scout_spawns"] for r in reports),
        "total_tokens": sum(r["summary"]["total_tokens"] for r in reports),
        "combined_elapsed_ms": sum(
            r["summary"]["combined_elapsed_ms"] for r in reports
        ),
    }
    protocol = {
        "schema": PROTOCOL,
        "family": FAMILY,
        "execution": "independent-main-codex-exec-plus-ambiguity-only-independent-scout-codex-exec",
        "public_fields": ["id", "query"],
        "hidden_fields": [
            "expected_files",
            "expected_symbols",
            "expected_verification",
        ],
        "scout_candidates": "worker-visible task_entry_points ambiguity alternatives only",
        "scout_spawn_gate": "ambiguity.ambiguous == true",
        "cost_accounting": "main + scout visible token counters and elapsed time; missing counters remain zero/unavailable",
        "model": model,
        "reasoning_effort": effort,
        "sandbox": sandbox,
    }
    return {
        "schema": SCHEMA,
        "protocol": protocol,
        "protocol_identity": _id(protocol),
        "summary": summary,
        "repositories": reports,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--root", type=Path, default=Path(".hashmarks/benchmarks/codex-selective-scout")
    )
    p.add_argument("--codex-bin", default="codex")
    p.add_argument("--model")
    p.add_argument("--reasoning-effort")
    p.add_argument("--sandbox", default="read-only")
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--max-tasks", type=int)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    v = collect(
        a.root,
        codex_bin=a.codex_bin,
        model=a.model,
        effort=a.reasoning_effort,
        sandbox=a.sandbox,
        timeout_s=a.timeout,
        max_tasks=a.max_tasks,
    )
    text = json.dumps(v, indent=2, sort_keys=True) + "\n"
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(text)
    print(text, end="")  # noqa: T201 - intentional command output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
