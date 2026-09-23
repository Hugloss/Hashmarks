from __future__ import annotations

import argparse
import hashlib
import json
import os
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
from .metrics_worker_inspection_ab import (
    _entry_state,
    _resolve_after_inspection,
)
from .metrics_worker_multistep_ab import (
    _verification_state,
)

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent

SCHEMA = "hashmarks.worker-failed-verification-ab.v1"
PROTOCOL_SCHEMA = "hashmarks.worker-failed-verification-ab-protocol.v1"
FAILURE_PACKET_SCHEMA = "hashmarks.worker-failed-verification-input.v1"
WORKER_OUTPUT_SCHEMA = "hashmarks.worker-failed-verification-output.v1"
FAMILY = "hashmarks-failed-verification-recovery-a"
POLICIES = ("repeat-failed", "fresh-research", "evidence-guided-recovery")


def _identity(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _inject_failures(
    workspace: Path,
    hidden_tasks: list[dict[str, Any]],
    output: Path,
    *,
    limit: int,
) -> list[dict[str, object]]:
    """Create controlled failed-edit packets.

    This is grader authority. Hidden expected files are used only to select the
    first canonical top-N candidate that is known not to be an expected edit
    target. The worker sees the failed path and failed verification outcome, but
    never the expected edit target or why the injected edit was wrong.
    """
    packets: list[dict[str, object]] = []
    provenance: list[dict[str, object]] = []
    with CodeMap(workspace) as codemap:
        codemap.sync()
        for task in hidden_tasks:
            task_id = str(task.get("id") or task.get("query") or "")
            query = str(task.get("query") or "")
            expected = {str(value) for value in task.get("expected_files") or ()}
            hits = list(codemap.find_task(query, limit=limit))
            injected = next(
                (
                    (rank, hit.path)
                    for rank, hit in enumerate(hits, 1)
                    if hit.path not in expected
                ),
                None,
            )
            if injected is None:
                raise RuntimeError(
                    f"no plausible wrong candidate available for {task_id}"
                )
            rank, failed_target = injected
            verification = _verification_state(codemap, query, limit=limit)
            verification_target = verification.get("target")
            packets.append(
                {
                    "id": task_id,
                    "query": query,
                    "failed_edit_target": failed_target,
                    "verification_target": verification_target,
                    "verification_outcome": "failed",
                }
            )
            provenance.append(
                {
                    "id": task_id,
                    "injected_canonical_rank": rank,
                    "selection_rule": "first-canonical-top-N-path-not-in-hidden-expected-files",
                }
            )
    payload = {"schema": FAILURE_PACKET_SCHEMA, "tasks": packets}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return provenance


def _guided_recovery(
    codemap: CodeMap, query: str, failed_target: str, *, limit: int
) -> tuple[str | None, str, int]:
    state = _entry_state(codemap, query, limit=limit)
    first = str(state.get("first_path") or "") or None
    alternatives = [
        dict(row)
        for row in state.get("alternatives", [])
        if isinstance(row, dict) and str(row.get("path") or "") != failed_target
    ]
    examined = len(alternatives)

    # If the worker projection already has a different first recommendation,
    # the failed verification is enough evidence to abandon the injected path.
    if first and first != failed_target and not state.get("ambiguous"):
        return first, "different-worker-entry-point-after-failure", max(1, examined)

    resolution = _resolve_after_inspection(query, alternatives)
    if resolution.get("resolved") and resolution.get("target") != failed_target:
        return (
            str(resolution.get("target")),
            "inspection-" + str(resolution.get("reason")),
            max(1, examined),
        )

    # Conservative fallback: re-run canonical retrieval and exclude only the path
    # that has direct negative verification evidence. No hidden answer is used.
    hits = list(codemap.find_task(query, limit=limit))
    for rank, hit in enumerate(hits, 1):
        if hit.path != failed_target:
            return hit.path, "canonical-research-excluding-failed-target", rank
    return None, "no-alternative-evidence", len(hits)


def _recovery_action(
    policy: str,
    workspace: Path,
    codemap: CodeMap,
    query: str,
    failed_target: str,
    limit: int,
) -> tuple[str | None, str, int]:
    if policy == "repeat-failed":
        return failed_target, "repeat-prior-edit", 0
    if policy == "fresh-research":
        with CodeMap(workspace) as fresh:
            fresh.sync()
            hits = list(fresh.find_task(query, limit=limit))
        return (
            hits[0].path if hits else None,
            "fresh-canonical-top1",
            1 if hits else 0,
        )
    if policy == "evidence-guided-recovery":
        return _guided_recovery(codemap, query, failed_target, limit=limit)
    raise ValueError(f"unsupported policy: {policy}")


def run_worker(
    *, policy: str, workspace: Path, tasks_path: Path, output: Path, limit: int
) -> None:
    payload = json.loads(tasks_path.read_text(encoding="utf-8"))
    if payload.get("schema") != FAILURE_PACKET_SCHEMA:
        raise ValueError("unsupported failed-verification input")
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("failed-verification tasks must be a list")
    allowed = {
        "id",
        "query",
        "failed_edit_target",
        "verification_target",
        "verification_outcome",
    }
    rows: list[dict[str, object]] = []
    with CodeMap(workspace) as codemap:
        codemap.sync()
        for row in tasks:
            if not isinstance(row, dict) or set(row) - allowed:
                raise ValueError(
                    "worker recovery input contains hidden or unsupported fields"
                )
            if row.get("verification_outcome") != "failed":
                raise ValueError(
                    "recovery worker requires a failed verification outcome"
                )
            task_id = str(row.get("id") or "")
            query = str(row.get("query") or "")
            failed_target = str(row.get("failed_edit_target") or "")
            target, reason, examined = _recovery_action(
                policy, workspace, codemap, query, failed_target, limit
            )
            rows.append(
                {
                    "id": task_id,
                    "query": query,
                    "failed_edit_target": failed_target,
                    "verification_target": row.get("verification_target"),
                    "verification_outcome": "failed",
                    "recovery_target": target,
                    "changed_target": bool(target) and str(target) != failed_target,
                    "recovery_reason": reason,
                    "recovery_candidates_examined": examined,
                }
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {"schema": WORKER_OUTPUT_SCHEMA, "policy": policy, "tasks": rows},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _score(
    hidden_tasks: list[dict[str, Any]], output: dict[str, Any]
) -> dict[str, object]:
    by_id = {
        str(row.get("id") or ""): row
        for row in output.get("tasks", [])
        if isinstance(row, dict)
    }
    rows: list[dict[str, object]] = []
    for task in hidden_tasks:
        task_id = str(task.get("id") or task.get("query") or "")
        expected = {str(value) for value in task.get("expected_files") or ()}
        observed = by_id.get(task_id, {})
        failed = str(observed.get("failed_edit_target") or "")
        target = observed.get("recovery_target")
        correct = bool(target) and str(target) in expected
        repeated_failed = bool(target) and str(target) == failed
        changed_wrong = bool(target) and str(target) != failed and not correct
        rows.append(
            {
                "id": task_id,
                "expected_files": sorted(expected),
                "failed_edit_target": failed,
                "recovery_target": target,
                "correct_recovery": correct,
                "repeated_failed_edit": repeated_failed,
                "changed_to_different_wrong_edit": changed_wrong,
                "recovery_reason": observed.get("recovery_reason"),
                "recovery_candidates_examined": observed.get(
                    "recovery_candidates_examined"
                ),
            }
        )
    n = len(rows)
    summary = {
        "tasks": n,
        "correct_recoveries": sum(bool(row["correct_recovery"]) for row in rows),
        "repeated_failed_edits": sum(bool(row["repeated_failed_edit"]) for row in rows),
        "different_wrong_edits": sum(
            bool(row["changed_to_different_wrong_edit"]) for row in rows
        ),
        "recovery_candidates_examined": sum(
            int(row["recovery_candidates_examined"] or 0) for row in rows
        ),
    }
    summary["correct_recovery_rate"] = summary["correct_recoveries"] / n if n else 0.0
    summary["repeated_failed_edit_rate"] = (
        summary["repeated_failed_edits"] / n if n else 0.0
    )
    return {"summary": summary, "tasks": rows}


def collect(root: Path, *, limit: int = 20) -> dict[str, object]:
    reports: list[dict[str, object]] = []
    for name, workspace, corpus, _public_path in materialize_challenge(
        root / "challenge"
    ):
        hidden = _load_corpus(corpus)
        packet_path = root / "failure-packets" / f"{name}.json"
        injection_provenance = _inject_failures(
            workspace, hidden, packet_path, limit=limit
        )
        outputs: dict[str, Path] = {}
        for policy in POLICIES:
            output = root / "worker-outputs" / f"{name}-{policy}.json"
            env = dict(os.environ)
            prior = env.get("PYTHONPATH")
            source_root = str(_REPO_ROOT)
            env["PYTHONPATH"] = (
                source_root if not prior else source_root + os.pathsep + prior
            )
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.agent_evaluation.metrics_worker_failed_verification_ab",
                    "--worker",
                    "--policy",
                    policy,
                    "--workspace",
                    str(workspace),
                    "--tasks",
                    str(packet_path),
                    "--output",
                    str(output),
                    "--limit",
                    str(limit),
                ],
                check=True,
                env=env,
            )
            outputs[policy] = output
        report: dict[str, object] = {
            "name": name,
            "failure_packet_sha256": _sha256_bytes(packet_path.read_bytes()),
            "hidden_corpus_sha256": _sha256_bytes(corpus.read_bytes()),
            "injection_provenance": injection_provenance,
        }
        for policy in POLICIES:
            report[policy.replace("-", "_")] = _score(
                hidden, json.loads(outputs[policy].read_text(encoding="utf-8"))
            )
        reports.append(report)

    def total(policy: str, key: str) -> int:
        return sum(int(repo[policy]["summary"][key]) for repo in reports)  # type: ignore[index]

    protocol = {
        "schema": PROTOCOL_SCHEMA,
        "family": FAMILY,
        "worker_isolation": "subprocess-per-repository-policy",
        "failure_packet_fields": [
            "id",
            "query",
            "failed_edit_target",
            "verification_target",
            "verification_outcome",
        ],
        "worker_hidden_fields": [
            "expected_files",
            "expected_symbols",
            "injected_canonical_rank",
            "selection_rule",
        ],
        "injection_authority": "grader-only",
        "injection_rule": "first canonical top-N path not in hidden expected_files",
        "verification_signal": "generic failed outcome; no expected target disclosed",
        "policies": list(POLICIES),
        "limit": limit,
        "repositories": [
            {
                "name": repo["name"],
                "failure_packet_sha256": repo["failure_packet_sha256"],
                "hidden_corpus_sha256": repo["hidden_corpus_sha256"],
            }
            for repo in reports
        ],
    }
    tasks = total("repeat_failed", "tasks")
    return {
        "schema": SCHEMA,
        "protocol": protocol,
        "protocol_identity": _identity(protocol),
        "summary": {
            "repositories": len(reports),
            "tasks": tasks,
            "injected_failed_edits": tasks,
            "repeat_correct_recoveries": total("repeat_failed", "correct_recoveries"),
            "repeat_repeated_failed_edits": total(
                "repeat_failed", "repeated_failed_edits"
            ),
            "fresh_correct_recoveries": total("fresh_research", "correct_recoveries"),
            "fresh_repeated_failed_edits": total(
                "fresh_research", "repeated_failed_edits"
            ),
            "fresh_different_wrong_edits": total(
                "fresh_research", "different_wrong_edits"
            ),
            "guided_correct_recoveries": total(
                "evidence_guided_recovery", "correct_recoveries"
            ),
            "guided_repeated_failed_edits": total(
                "evidence_guided_recovery", "repeated_failed_edits"
            ),
            "guided_different_wrong_edits": total(
                "evidence_guided_recovery", "different_wrong_edits"
            ),
            "guided_recovery_candidates_examined": total(
                "evidence_guided_recovery", "recovery_candidates_examined"
            ),
        },
        "repositories": reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure worker recovery after controlled failed verification."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(".hashmarks/benchmarks/worker-failed-verification-ab"),
    )
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--policy", choices=POLICIES)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--tasks", type=Path)
    args = parser.parse_args()
    if args.worker:
        if not args.policy or not args.workspace or not args.tasks or not args.output:
            parser.error("worker mode requires policy/workspace/tasks/output")
        run_worker(
            policy=args.policy,
            workspace=args.workspace,
            tasks_path=args.tasks,
            output=args.output,
            limit=args.limit,
        )
        return 0
    result = collect(args.root, limit=args.limit)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")  # noqa: T201 - intentional command output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
