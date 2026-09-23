from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from hashmarks._command_output import log_command_output
from hashmarks.codemap import (
    CodeMap,
)

from .metrics_blind_worker_ab import (
    _load_corpus,
    _sha256_bytes,
    materialize_challenge,
)

logger = logging.getLogger(__name__)

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent

SCHEMA = "hashmarks.worker-behavior-ab.v1"
PROTOCOL_SCHEMA = "hashmarks.worker-behavior-ab-protocol.v1"
FAMILY = "hashmarks-worker-behavior-a"


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


def _worker_action(policy: str, state: dict[str, object]) -> tuple[str, object]:
    if policy == "direct-edit":
        return ("edit" if state["first_path"] else "no-evidence"), state["first_path"]
    if policy == "uncertainty-gated":
        if state["ambiguous"]:
            return "inspect-competing-evidence", None
        return ("edit" if state["first_path"] else "no-evidence"), state["first_path"]
    raise ValueError(f"unsupported policy: {policy}")


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
            action, target = _worker_action(policy, state)
            rows.append(
                {
                    "id": task_id,
                    "query": query,
                    "action": action,
                    "target": target,
                    "first_role": state["first_role"],
                    "ambiguous": state["ambiguous"],
                    "ambiguity_reason": state["ambiguity_reason"],
                    "ambiguity_roles": state["ambiguity_roles"],
                    "alternatives": state["alternatives"],
                }
            )
    result = {
        "schema": "hashmarks.worker-behavior-output.v1",
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
        edited = action == "edit"
        correct_edit = edited and str(target) in expected
        wrong_edit = edited and not correct_edit
        inspection = action == "inspect-competing-evidence"
        rows.append(
            {
                "id": task_id,
                "query": str(task.get("query") or ""),
                "expected_files": sorted(expected),
                "action": action,
                "target": target,
                "correct_immediate_edit": correct_edit,
                "unsafe_wrong_first_edit": wrong_edit,
                "inspection": inspection,
                "ambiguous": bool(observed.get("ambiguous"))
                if isinstance(observed, dict)
                else False,
                "ambiguity_roles": list(observed.get("ambiguity_roles") or [])
                if isinstance(observed, dict)
                else [],
                "alternatives": list(observed.get("alternatives") or [])
                if isinstance(observed, dict)
                else [],
            }
        )
    count = len(rows)
    wrong = sum(bool(row["unsafe_wrong_first_edit"]) for row in rows)
    correct = sum(bool(row["correct_immediate_edit"]) for row in rows)
    inspections = sum(bool(row["inspection"]) for row in rows)
    return {
        "summary": {
            "tasks": count,
            "correct_immediate_edit_rate": correct / count if count else 0.0,
            "unsafe_wrong_first_edit_rate": wrong / count if count else 0.0,
            "inspection_rate": inspections / count if count else 0.0,
            "correct_immediate_edits": correct,
            "unsafe_wrong_first_edits": wrong,
            "inspections": inspections,
        },
        "tasks": rows,
    }


def _run_policy_workers(
    root: Path,
    name: str,
    workspace: Path,
    public_path: Path,
    limit: int,
) -> dict[str, Path]:
    outputs = {}
    env = dict(os.environ)
    source_root = str(_REPO_ROOT)
    prior = env.get("PYTHONPATH")
    env["PYTHONPATH"] = source_root if not prior else source_root + os.pathsep + prior
    for policy in ("direct-edit", "uncertainty-gated"):
        output = root / "worker-outputs" / f"{name}-{policy}.json"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.agent_evaluation.metrics_worker_behavior_ab",
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
    return outputs


def _summary_totals(reports: list[dict[str, object]]) -> dict[str, int]:
    def total(policy: str, key: str) -> int:
        return sum(int(repo[policy]["summary"][key]) for repo in reports)  # type: ignore[index]

    return {
        "tasks": total("direct_edit", "tasks"),
        "direct_wrong": total("direct_edit", "unsafe_wrong_first_edits"),
        "gated_wrong": total("uncertainty_gated", "unsafe_wrong_first_edits"),
        "direct_correct": total("direct_edit", "correct_immediate_edits"),
        "gated_correct": total("uncertainty_gated", "correct_immediate_edits"),
        "inspections": total("uncertainty_gated", "inspections"),
    }


def collect(root: Path, *, limit: int = 20) -> dict[str, object]:
    repos = materialize_challenge(root / "challenge")
    reports = []
    for name, workspace, corpus, public_path in repos:
        outputs = _run_policy_workers(root, name, workspace, public_path, limit)

        # Hidden expectations are opened only after both policy workers have exited.
        hidden = _load_corpus(corpus)
        direct = _score(
            hidden, json.loads(outputs["direct-edit"].read_text(encoding="utf-8"))
        )
        gated = _score(
            hidden, json.loads(outputs["uncertainty-gated"].read_text(encoding="utf-8"))
        )
        reports.append(
            {
                "name": name,
                "workspace": str(workspace),
                "public_task_sha256": _sha256_bytes(public_path.read_bytes()),
                "hidden_corpus_sha256": _sha256_bytes(corpus.read_bytes()),
                "direct_edit": direct,
                "uncertainty_gated": gated,
            }
        )

    totals = _summary_totals(reports)
    prevented = max(0, totals["direct_wrong"] - totals["gated_wrong"])
    protocol = {
        "schema": PROTOCOL_SCHEMA,
        "family": FAMILY,
        "worker_isolation": "subprocess-per-repository-policy",
        "worker_input_fields": ["id", "query"],
        "hidden_fields": ["expected_files", "expected_symbols"],
        "policies": ["direct-edit", "uncertainty-gated"],
        "uncertainty_action": "inspect-competing-evidence",
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
            "tasks": totals["tasks"],
            "direct_correct_immediate_edits": totals["direct_correct"],
            "direct_correct_immediate_edit_rate": totals["direct_correct"]
            / totals["tasks"]
            if totals["tasks"]
            else 0.0,
            "direct_unsafe_wrong_first_edits": totals["direct_wrong"],
            "direct_unsafe_wrong_first_edit_rate": totals["direct_wrong"]
            / totals["tasks"]
            if totals["tasks"]
            else 0.0,
            "gated_correct_immediate_edits": totals["gated_correct"],
            "gated_correct_immediate_edit_rate": totals["gated_correct"]
            / totals["tasks"]
            if totals["tasks"]
            else 0.0,
            "gated_unsafe_wrong_first_edits": totals["gated_wrong"],
            "gated_unsafe_wrong_first_edit_rate": totals["gated_wrong"]
            / totals["tasks"]
            if totals["tasks"]
            else 0.0,
            "gated_inspections": totals["inspections"],
            "gated_inspection_rate": totals["inspections"] / totals["tasks"]
            if totals["tasks"]
            else 0.0,
            "unsafe_wrong_first_edits_prevented": prevented,
            "unsafe_wrong_first_edit_reduction": (prevented / totals["direct_wrong"])
            if totals["direct_wrong"]
            else 1.0,
            "extra_inspections_per_prevented_wrong_edit": (
                totals["inspections"] / prevented
            )
            if prevented
            else None,
            "correct_immediate_edits_deferred": max(
                0, totals["direct_correct"] - totals["gated_correct"]
            ),
        },
        "repositories": reports,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure whether uncertainty changes worker first-action safety"
    )
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--policy", choices=["direct-edit", "uncertainty-gated"])
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--tasks", type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    if args.worker:
        if (
            args.policy is None
            or args.workspace is None
            or args.tasks is None
            or args.output is None
        ):
            parser.error("worker mode requires --policy --workspace --tasks --output")
        run_worker(
            policy=args.policy,
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
    log_command_output(logger, rendered)


if __name__ == "__main__":
    main()
