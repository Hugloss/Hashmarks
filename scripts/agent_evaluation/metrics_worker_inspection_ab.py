from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from hashmarks.codemap import (
    CodeMap,
)

from .metrics_blind_worker_ab import (
    _load_corpus,
    _sha256_bytes,
    materialize_challenge,
)

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent

SCHEMA = "hashmarks.worker-inspection-ab.v1"
PROTOCOL_SCHEMA = "hashmarks.worker-inspection-ab-protocol.v1"
FAMILY = "hashmarks-worker-inspection-a"

ROLE_CUES: dict[str, tuple[str, ...]] = {
    "authority": ("agents", "agent instructions", "authority", "policy", "rules"),
    "config_build": (
        "vite",
        "pyproject",
        "package.json",
        "config",
        "build",
        "environment",
    ),
    "contract": ("schema", "contract", "openapi", "api"),
    "verification": ("test", "tests", "pytest", "vitest", "assert"),
    "implementation": (
        "implement",
        "implementation",
        "handler",
        "service",
        "component",
        "function",
    ),
}


def _identity(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _entry_state(
    source: Path | CodeMap, query: str, *, limit: int
) -> dict[str, object]:
    if isinstance(source, CodeMap):
        value = source.task_entry_points(query, limit=limit)
    else:
        with CodeMap(source) as codemap:
            codemap.sync()
            value = codemap.task_entry_points(query, limit=limit)
    recommended = [row for row in value.get("recommended", []) if isinstance(row, dict)]
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
        "first_path": str(recommended[0].get("path") or "") if recommended else None,
        "first_role": recommended[0].get("role") if recommended else None,
        "ambiguous": bool(ambiguity.get("ambiguous")),
        "ambiguity_reason": ambiguity.get("reason"),
        "ambiguity_roles": list(ambiguity.get("explicit_roles", [])),
        "alternatives": alternatives,
    }


def _cue_score(query: str, role: str, path: str) -> tuple[int, int, int]:
    q = query.casefold()
    query_tokens = {token for token in re.split(r"[^a-z0-9]+", q) if token}
    role_score = sum(1 for cue in ROLE_CUES.get(role, ()) if cue in q)
    basename = Path(path).name.casefold()
    stem_tokens = [
        token for token in re.split(r"[^a-z0-9]+", basename) if len(token) >= 3
    ]
    name_score = sum(1 for token in stem_tokens if token in query_tokens)
    exact_surface = int(
        bool(stem_tokens) and all(token in query_tokens for token in stem_tokens)
    )
    return (exact_surface, name_score, role_score)


def _resolve_after_inspection(
    query: str, alternatives: list[dict[str, object]]
) -> dict[str, object]:
    candidates = [row for row in alternatives if row.get("path")]
    unique_paths = {str(row.get("path")) for row in candidates}
    if len(unique_paths) == 1 and unique_paths:
        path = next(iter(unique_paths))
        return {"resolved": True, "target": path, "reason": "same-path-role-collapse"}
    scored = []
    for row in candidates:
        role = str(row.get("role") or "")
        path = str(row.get("path") or "")
        score = _cue_score(query, role, path)
        rank = int(row.get("canonical_rank") or 10**9)
        scored.append((score, -rank, path, role))
    if not scored:
        return {"resolved": False, "target": None, "reason": "no-competing-evidence"}
    scored.sort(reverse=True)
    best = scored[0]
    if best[0] == (0, 0, 0):
        return {"resolved": False, "target": None, "reason": "no-public-task-cue"}
    if len(scored) > 1 and best[0] == scored[1][0]:
        return {"resolved": False, "target": None, "reason": "tied-public-task-cues"}
    return {"resolved": True, "target": best[2], "reason": "public-task-role-cue"}


def _worker_action(
    policy: str, query: str, state: dict[str, object]
) -> dict[str, object]:
    if policy not in {"defer-only", "inspect-then-resolve"}:
        raise ValueError(f"unsupported policy: {policy}")
    if not state["ambiguous"]:
        return {
            "action": "edit" if state["first_path"] else "no-evidence",
            "target": state["first_path"],
            "inspected": False,
            "resolved_after_inspection": False,
            "resolution_reason": None,
        }
    if policy == "defer-only":
        return {
            "action": "inspect-competing-evidence",
            "target": None,
            "inspected": True,
            "resolved_after_inspection": False,
            "resolution_reason": None,
        }
    resolution = _resolve_after_inspection(query, list(state["alternatives"]))
    resolved = bool(resolution["resolved"])
    return {
        "action": "edit-after-inspection" if resolved else "defer-after-inspection",
        "target": resolution["target"] if resolved else None,
        "inspected": True,
        "resolved_after_inspection": resolved,
        "resolution_reason": resolution["reason"],
    }


def run_worker(
    *, policy: str, workspace: Path, tasks_path: Path, output: Path, limit: int
) -> None:
    payload = json.loads(tasks_path.read_text(encoding="utf-8"))
    if payload.get("schema") != "hashmarks.blind-worker-tasks.v1":
        raise ValueError("unsupported public task input")
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("public tasks must be a list")
    rows = []
    with CodeMap(workspace) as codemap:
        codemap.sync()
        for row in tasks:
            if not isinstance(row, dict) or set(row) - {"id", "query"}:
                raise ValueError("worker input may contain only id and query")
            task_id = str(row.get("id") or "")
            query = str(row.get("query") or "")
            state = _entry_state(codemap, query, limit=limit)
            action = _worker_action(policy, query, state)
            rows.append(
                {
                    "id": task_id,
                    "query": query,
                    "action": action["action"],
                    "target": action["target"],
                    "first_role": state["first_role"],
                    "ambiguous": state["ambiguous"],
                    "ambiguity_reason": state["ambiguity_reason"],
                    "ambiguity_roles": state["ambiguity_roles"],
                    "alternatives": state["alternatives"],
                    "inspected": action["inspected"],
                    "resolved_after_inspection": action["resolved_after_inspection"],
                    "resolution_reason": action["resolution_reason"],
                }
            )
        result = {
            "schema": "hashmarks.worker-inspection-output.v1",
            "policy": policy,
            "tasks": rows,
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _score(tasks: list[dict[str, Any]], output: dict[str, Any]) -> dict[str, object]:
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
        action = str(observed.get("action") or "") if isinstance(observed, dict) else ""
        target = observed.get("target") if isinstance(observed, dict) else None
        edited = action in {"edit", "edit-after-inspection"}
        correct = edited and str(target) in expected
        wrong = edited and not correct
        inspected = (
            bool(observed.get("inspected")) if isinstance(observed, dict) else False
        )
        deferred = action in {"inspect-competing-evidence", "defer-after-inspection"}
        recovered = action == "edit-after-inspection" and correct
        rows.append(
            {
                "id": task_id,
                "query": str(task.get("query") or ""),
                "expected_files": sorted(expected),
                "action": action,
                "target": target,
                "correct_final_edit": correct,
                "unsafe_wrong_final_edit": wrong,
                "inspected": inspected,
                "deferred": deferred,
                "recovered_after_inspection": recovered,
                "resolved_after_inspection": bool(
                    observed.get("resolved_after_inspection")
                )
                if isinstance(observed, dict)
                else False,
                "resolution_reason": observed.get("resolution_reason")
                if isinstance(observed, dict)
                else None,
                "alternatives": list(observed.get("alternatives") or [])
                if isinstance(observed, dict)
                else [],
            }
        )
    n = len(rows)
    summary = {
        "tasks": n,
        "correct_final_edits": sum(bool(r["correct_final_edit"]) for r in rows),
        "unsafe_wrong_final_edits": sum(
            bool(r["unsafe_wrong_final_edit"]) for r in rows
        ),
        "inspections": sum(bool(r["inspected"]) for r in rows),
        "deferrals": sum(bool(r["deferred"]) for r in rows),
        "recovered_after_inspection": sum(
            bool(r["recovered_after_inspection"]) for r in rows
        ),
    }
    summary["correct_final_edit_rate"] = (
        summary["correct_final_edits"] / n if n else 0.0
    )
    summary["unsafe_wrong_final_edit_rate"] = (
        summary["unsafe_wrong_final_edits"] / n if n else 0.0
    )
    summary["deferral_rate"] = summary["deferrals"] / n if n else 0.0
    return {"summary": summary, "tasks": rows}


def collect(root: Path, *, limit: int = 20) -> dict[str, object]:
    repos = materialize_challenge(root / "challenge")
    reports = []
    for name, workspace, corpus, public_path in repos:
        outputs: dict[str, Path] = {}
        for policy in ("defer-only", "inspect-then-resolve"):
            output = root / "worker-outputs" / f"{name}-{policy}.json"
            env = dict(os.environ)
            source_root = str(_REPO_ROOT)
            prior = env.get("PYTHONPATH")
            env["PYTHONPATH"] = (
                source_root if not prior else source_root + os.pathsep + prior
            )
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.agent_evaluation.metrics_worker_inspection_ab",
                    "--worker",
                    "--policy",
                    policy,
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
            outputs[policy] = output
        hidden = _load_corpus(corpus)
        reports.append(
            {
                "name": name,
                "workspace": str(workspace),
                "public_task_sha256": _sha256_bytes(public_path.read_bytes()),
                "hidden_corpus_sha256": _sha256_bytes(corpus.read_bytes()),
                "defer_only": _score(
                    hidden,
                    json.loads(outputs["defer-only"].read_text(encoding="utf-8")),
                ),
                "inspect_then_resolve": _score(
                    hidden,
                    json.loads(
                        outputs["inspect-then-resolve"].read_text(encoding="utf-8")
                    ),
                ),
            }
        )

    def total(policy: str, key: str) -> int:
        return sum(int(repo[policy]["summary"][key]) for repo in reports)  # type: ignore[index]

    tasks = total("defer_only", "tasks")
    inspected = total("inspect_then_resolve", "inspections")
    recovered = total("inspect_then_resolve", "recovered_after_inspection")
    residual_wrong = total("inspect_then_resolve", "unsafe_wrong_final_edits")
    residual_deferrals = total("inspect_then_resolve", "deferrals")
    protocol = {
        "schema": PROTOCOL_SCHEMA,
        "family": FAMILY,
        "worker_isolation": "subprocess-per-repository-policy",
        "worker_input_fields": ["id", "query"],
        "hidden_fields": ["expected_files", "expected_symbols"],
        "policies": ["defer-only", "inspect-then-resolve"],
        "resolution_inputs": ["public-task-text", "worker-visible-competing-evidence"],
        "resolution_rules": [
            "same-path-role-collapse",
            "explicit-surface-or-role-cue",
            "otherwise-defer",
        ],
        "limit": limit,
        "repositories": [
            {
                "name": repo["name"],
                "public_task_sha256": repo["public_task_sha256"],
                "hidden_corpus_sha256": repo["hidden_corpus_sha256"],
            }
            for repo in reports
        ],
    }
    return {
        "schema": SCHEMA,
        "protocol": protocol,
        "protocol_identity": _identity(protocol),
        "summary": {
            "repositories": len(reports),
            "tasks": tasks,
            "defer_only_correct_final_edits": total(
                "defer_only", "correct_final_edits"
            ),
            "defer_only_unsafe_wrong_final_edits": total(
                "defer_only", "unsafe_wrong_final_edits"
            ),
            "defer_only_deferrals": total("defer_only", "deferrals"),
            "resolved_correct_final_edits": total(
                "inspect_then_resolve", "correct_final_edits"
            ),
            "resolved_unsafe_wrong_final_edits": residual_wrong,
            "resolved_deferrals": residual_deferrals,
            "inspections": inspected,
            "recovered_after_inspection": recovered,
            "inspection_recovery_rate": recovered / inspected if inspected else 0.0,
            "residual_wrong_edit_rate": residual_wrong / tasks if tasks else 0.0,
            "residual_deferral_rate": residual_deferrals / tasks if tasks else 0.0,
        },
        "repositories": reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure whether ambiguity inspection resolves worker actions safely."
    )
    parser.add_argument(
        "--root", type=Path, default=Path(".hashmarks/benchmarks/worker-inspection-ab")
    )
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--policy", choices=["defer-only", "inspect-then-resolve"])
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--tasks", type=Path)
    args = parser.parse_args()
    if args.worker:
        if not args.policy or not args.workspace or not args.tasks or not args.output:
            parser.error(
                "worker mode requires --policy, --workspace, --tasks, and --output"
            )
        run_worker(
            policy=args.policy,
            workspace=args.workspace,
            tasks_path=args.tasks,
            output=args.output,
            limit=args.limit,
        )
        return 0
    result = collect(args.root, limit=args.limit)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")  # noqa: T201 - intentional command output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
