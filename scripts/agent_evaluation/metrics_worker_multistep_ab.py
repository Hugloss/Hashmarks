from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypedDict

from hashmarks._command_output import log_command_output
from hashmarks.codemap import (
    CodeMap,
)

from .metrics_blind_worker_ab import (
    _load_corpus,
    _sha256_bytes,
    materialize_challenge,
)
from .metrics_worker_inspection_ab import (
    _entry_state,
    _resolve_after_inspection,
)

logger = logging.getLogger(__name__)

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent

SCHEMA = "hashmarks.worker-multistep-ab.v1"
PROTOCOL_SCHEMA = "hashmarks.worker-multistep-ab-protocol.v1"
FAMILY = "hashmarks-worker-multistep-a"


class _EditDecision(TypedDict):
    target: str | None
    inspection_paths: list[str]
    recovered: bool
    reason: str | None


def _identity(value: object) -> str:
    data = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _is_test_path(path: str) -> bool:
    p = path.casefold()
    name = Path(path).name.casefold()
    return (
        "/tests/" in f"/{p}"
        or name.startswith("test_")
        or ".test." in name
        or ".spec." in name
    )


def _verification_state(
    source: Path | CodeMap, query: str, *, limit: int
) -> dict[str, object]:
    if isinstance(source, CodeMap):
        hits = source.find_task(query + " test verification", limit=limit)
    else:
        with CodeMap(source) as codemap:
            codemap.sync()
            hits = codemap.find_task(query + " test verification", limit=limit)
    candidates = [hit.path for hit in hits]
    target = next((path for path in candidates if _is_test_path(path)), None)
    examined = candidates.index(target) + 1 if target in candidates else len(candidates)
    return {
        "target": target,
        "candidates_examined": examined,
        "candidates": candidates[:examined],
    }


def _read_cost(workspace: Path, paths: list[str]) -> dict[str, object]:
    unique: list[str] = []
    seen: set[str] = set()
    total_bytes = 0
    approx_tokens = 0
    for rel in paths:
        if not rel or rel in seen:
            continue
        seen.add(rel)
        path = workspace / rel
        if not path.is_file():
            continue
        data = path.read_bytes()
        total_bytes += len(data)
        # Deliberately simple deterministic approximation; not model tokenizer authority.
        approx_tokens += max(1, (len(data) + 3) // 4)
        unique.append(rel)
    return {
        "paths": unique,
        "files": len(unique),
        "bytes": total_bytes,
        "approx_tokens": approx_tokens,
    }


def _edit_decision(policy: str, state: Mapping[str, Any], query: str) -> _EditDecision:
    if policy not in {"direct-sequence", "uncertainty-aware-sequence"}:
        raise ValueError(f"unsupported policy: {policy}")
    first = state["first_path"]
    if policy == "direct-sequence" or not state["ambiguous"]:
        return {
            "target": first,
            "inspection_paths": [],
            "recovered": False,
            "reason": None,
        }
    inspection_paths = [
        str(row.get("path") or "")
        for row in state["alternatives"]
        if isinstance(row, dict)
    ]
    resolution = _resolve_after_inspection(query, list(state["alternatives"]))
    target = str(resolution["target"]) if resolution["resolved"] else None
    return {
        "target": target,
        "inspection_paths": inspection_paths,
        "recovered": target is not None and target != first,
        "reason": resolution["reason"],
    }


def run_worker(
    *, policy: str, workspace: Path, tasks_path: Path, output: Path, limit: int
) -> None:
    payload = json.loads(tasks_path.read_text())
    if payload.get("schema") != "hashmarks.blind-worker-tasks.v1":
        raise ValueError("unsupported public task input")
    rows = []
    with CodeMap(workspace) as codemap:
        codemap.sync()
        for row in payload.get("tasks", []):
            if not isinstance(row, dict) or set(row) - {"id", "query"}:
                raise ValueError("worker input may contain only id and query")
            task_id, query = str(row.get("id") or ""), str(row.get("query") or "")
            state = _entry_state(codemap, query, limit=limit)
            first = state["first_path"]
            decision = _edit_decision(policy, state, query)
            verification = _verification_state(codemap, query, limit=limit)
            verification_target = verification["target"]
            read_paths = (
                ([str(first)] if first else [])
                + list(decision["inspection_paths"])
                + ([str(verification_target)] if verification_target else [])
            )
            cost = _read_cost(workspace, read_paths)
            rows.append(
                {
                    "id": task_id,
                    "query": query,
                    "first_hypothesis": first,
                    "ambiguous": bool(state["ambiguous"]),
                    "inspection_paths": decision["inspection_paths"],
                    "edit_target": decision["target"],
                    "recovered_from_first_hypothesis": decision["recovered"],
                    "resolution_reason": decision["reason"],
                    "verification_target": verification_target,
                    "verification_candidates_examined": verification[
                        "candidates_examined"
                    ],
                    "evidence_read": cost,
                }
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "schema": "hashmarks.worker-multistep-output.v1",
                "policy": policy,
                "tasks": rows,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _expected_verification(repo_name: str) -> str:
    return {
        "python-orders": "tests/test_orders.py",
        "typescript-dashboard": "tests/MetricsPanel.test.tsx",
        "release-contracts": "tests/test_release_contract.py",
    }[repo_name]


def _score(
    repo_name: str, tasks: list[dict[str, Any]], output: dict[str, Any]
) -> dict[str, object]:
    by_id = {
        str(r.get("id") or ""): r
        for r in output.get("tasks", [])
        if isinstance(r, dict)
    }
    rows = []
    expected_verification = _expected_verification(repo_name)
    for task in tasks:
        tid = str(task.get("id") or task.get("query") or "")
        expected = {str(x) for x in task.get("expected_files") or ()}
        observed = by_id.get(tid, {})
        edit = observed.get("edit_target") if isinstance(observed, dict) else None
        verify = (
            observed.get("verification_target") if isinstance(observed, dict) else None
        )
        correct_edit = str(edit) in expected
        rows.append(
            {
                "id": tid,
                "expected_files": sorted(expected),
                "expected_verification": expected_verification,
                "first_hypothesis": observed.get("first_hypothesis"),
                "edit_target": edit,
                "correct_edit": correct_edit,
                "unsafe_wrong_edit": bool(edit) and not correct_edit,
                "deferred_edit": edit is None,
                "verification_target": verify,
                "correct_verification": verify == expected_verification,
                "recovered_from_wrong_first_hypothesis": bool(
                    observed.get("recovered_from_first_hypothesis")
                )
                and correct_edit,
                "evidence_read": observed.get("evidence_read", {}),
                "verification_candidates_examined": observed.get(
                    "verification_candidates_examined"
                ),
            }
        )
    n = len(rows)
    return {
        "summary": {
            "tasks": n,
            "correct_edits": sum(r["correct_edit"] for r in rows),
            "unsafe_wrong_edits": sum(r["unsafe_wrong_edit"] for r in rows),
            "deferrals": sum(r["deferred_edit"] for r in rows),
            "correct_verifications": sum(r["correct_verification"] for r in rows),
            "recovered_wrong_first_hypotheses": sum(
                r["recovered_from_wrong_first_hypothesis"] for r in rows
            ),
            "evidence_files_read": sum(
                int(r["evidence_read"].get("files", 0)) for r in rows
            ),
            "evidence_bytes_read": sum(
                int(r["evidence_read"].get("bytes", 0)) for r in rows
            ),
            "evidence_approx_tokens": sum(
                int(r["evidence_read"].get("approx_tokens", 0)) for r in rows
            ),
            "verification_candidates_examined": sum(
                int(r["verification_candidates_examined"] or 0) for r in rows
            ),
        },
        "tasks": rows,
    }


def collect(root: Path, *, limit: int = 20) -> dict[str, object]:
    reports = []
    for name, workspace, corpus, public_path in materialize_challenge(
        root / "challenge"
    ):
        outputs = {}
        for policy in ("direct-sequence", "uncertainty-aware-sequence"):
            output = root / "worker-outputs" / f"{name}-{policy}.json"
            env = dict(os.environ)
            prior = env.get("PYTHONPATH")
            src = str(_REPO_ROOT)
            env["PYTHONPATH"] = src if not prior else src + os.pathsep + prior
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.agent_evaluation.metrics_worker_multistep_ab",
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
                "public_task_sha256": _sha256_bytes(public_path.read_bytes()),
                "hidden_corpus_sha256": _sha256_bytes(corpus.read_bytes()),
                "direct_sequence": _score(
                    name, hidden, json.loads(outputs["direct-sequence"].read_text())
                ),
                "uncertainty_aware_sequence": _score(
                    name,
                    hidden,
                    json.loads(outputs["uncertainty-aware-sequence"].read_text()),
                ),
            }
        )

    def total(policy, key):
        return sum(int(r[policy]["summary"][key]) for r in reports)

    tasks = total("direct_sequence", "tasks")
    direct_wrong = total("direct_sequence", "unsafe_wrong_edits")
    guided_wrong = total("uncertainty_aware_sequence", "unsafe_wrong_edits")
    direct_correct = total("direct_sequence", "correct_edits")
    guided_correct = total("uncertainty_aware_sequence", "correct_edits")
    protocol = {
        "schema": PROTOCOL_SCHEMA,
        "family": FAMILY,
        "worker_isolation": "subprocess-per-repository-policy",
        "worker_input_fields": ["id", "query"],
        "hidden_fields": [
            "expected_files",
            "expected_symbols",
            "expected_verification",
        ],
        "policies": ["direct-sequence", "uncertainty-aware-sequence"],
        "stages": [
            "orient",
            "inspect-if-ambiguous",
            "choose-edit-target",
            "choose-verification-target",
        ],
        "verification_query_suffix": "test verification",
        "evidence_cost": "actual selected file bytes plus deterministic bytes/4 token approximation",
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
        "summary": {
            "repositories": len(reports),
            "tasks": tasks,
            "direct_correct_edits": direct_correct,
            "direct_unsafe_wrong_edits": direct_wrong,
            "direct_correct_verifications": total(
                "direct_sequence", "correct_verifications"
            ),
            "guided_correct_edits": guided_correct,
            "guided_unsafe_wrong_edits": guided_wrong,
            "guided_deferrals": total("uncertainty_aware_sequence", "deferrals"),
            "guided_correct_verifications": total(
                "uncertainty_aware_sequence", "correct_verifications"
            ),
            "guided_recovered_wrong_first_hypotheses": total(
                "uncertainty_aware_sequence", "recovered_wrong_first_hypotheses"
            ),
            "unsafe_wrong_edits_prevented": max(0, direct_wrong - guided_wrong),
            "direct_evidence_files_read": total(
                "direct_sequence", "evidence_files_read"
            ),
            "guided_evidence_files_read": total(
                "uncertainty_aware_sequence", "evidence_files_read"
            ),
            "direct_evidence_bytes_read": total(
                "direct_sequence", "evidence_bytes_read"
            ),
            "guided_evidence_bytes_read": total(
                "uncertainty_aware_sequence", "evidence_bytes_read"
            ),
            "direct_evidence_approx_tokens": total(
                "direct_sequence", "evidence_approx_tokens"
            ),
            "guided_evidence_approx_tokens": total(
                "uncertainty_aware_sequence", "evidence_approx_tokens"
            ),
            "direct_verification_candidates_examined": total(
                "direct_sequence", "verification_candidates_examined"
            ),
            "guided_verification_candidates_examined": total(
                "uncertainty_aware_sequence", "verification_candidates_examined"
            ),
        },
        "repositories": reports,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--root", type=Path, default=Path(".hashmarks/benchmarks/worker-multistep-ab")
    )
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--output", type=Path)
    p.add_argument("--worker", action="store_true")
    p.add_argument(
        "--policy", choices=["direct-sequence", "uncertainty-aware-sequence"]
    )
    p.add_argument("--workspace", type=Path)
    p.add_argument("--tasks", type=Path)
    a = p.parse_args()
    if a.worker:
        if not a.policy or not a.workspace or not a.tasks or not a.output:
            p.error("worker mode requires policy/workspace/tasks/output")
        run_worker(
            policy=a.policy,
            workspace=a.workspace,
            tasks_path=a.tasks,
            output=a.output,
            limit=a.limit,
        )
        return 0
    result = collect(a.root, limit=a.limit)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(text)
    log_command_output(logger, text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
