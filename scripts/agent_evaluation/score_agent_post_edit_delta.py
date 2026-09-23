from __future__ import annotations

import argparse
import hashlib
import json
import logging
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from hashmarks._command_output import log_command_output
from hashmarks.codemap import (
    CodeMap,
)
from scripts.agent_evaluation.economics import (
    verification_surface,
)

logger = logging.getLogger(__name__)

SCHEMA = "hashmarks.agent-post-edit-delta-qualification.v1"


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _identity(value: object) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _bytes(value: object) -> int:
    return len(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    )


def _task_candidate(packet: dict[str, object]) -> dict[str, object] | None:
    ownership = packet.get("ownership")
    if not isinstance(ownership, dict):
        return None
    candidate = ownership.get("candidate")
    return candidate if isinstance(candidate, dict) else None


def _task_verification_argv(packet: dict[str, object]) -> list[str]:
    verification = packet.get("verification")
    if not isinstance(verification, dict):
        return []
    plan = verification.get("plan")
    if not isinstance(plan, dict):
        return []
    argv = plan.get("argv")
    return [str(value) for value in argv] if isinstance(argv, list) else []


def _append_probe(path: Path, task_id: str) -> None:
    suffix = path.suffix.lower()
    if suffix in {".py", ".toml", ".yaml", ".yml", ".sh"}:
        marker = f"# hashmarks post-edit delta probe {task_id}"
    elif suffix in {
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".go",
        ".rs",
        ".java",
        ".c",
        ".cc",
        ".cpp",
        ".h",
    }:
        marker = f"// hashmarks post-edit delta probe {task_id}"
    elif suffix == ".sql":
        marker = f"-- hashmarks post-edit delta probe {task_id}"
    else:
        # The qualification corpus currently resolves to Python/TOML owners.
        # Unknown formats fail closed rather than corrupting a fixture merely to
        # manufacture an edit event.
        raise ValueError(f"unsupported qualification edit suffix: {suffix or '<none>'}")
    original = path.read_text(encoding="utf-8")
    path.write_text(original.rstrip("\n") + "\n" + marker + "\n", encoding="utf-8")


def _freeze_task_evidence(
    repo: Path, tasks: list[object], token_budget: int
) -> tuple[list[dict[str, Any]], float]:
    frozen: list[dict[str, Any]] = []
    with CodeMap(repo) as codemap:
        sync_started = time.perf_counter()
        codemap.sync()
        sync_ms = (time.perf_counter() - sync_started) * 1000.0
        for task in tasks:
            task_id = str(task["id"])
            query = str(task["query"])
            previous = codemap.task_evidence(query, token_budget=token_budget)
            candidate = _task_candidate(previous)
            edit_path = (
                str(candidate.get("path") or "") if candidate is not None else ""
            )
            if not edit_path:
                raise ValueError(f"PUBLIC task {task_id} has no repository candidate")
            _append_probe(repo / edit_path, task_id)

            started = time.perf_counter()
            delta = codemap.task_post_change_delta(
                query,
                [edit_path],
                previous_evidence=previous,
                token_budget=token_budget,
            )
            delta_ms = (time.perf_counter() - started) * 1000.0
            refreshed = codemap.task_evidence(query, token_budget=token_budget)
            frozen.append(
                {
                    "id": task_id,
                    "previous": previous,
                    "delta": delta,
                    "full_refreshed_start": refreshed,
                    "delta_bytes": _bytes(delta),
                    "full_refreshed_start_bytes": _bytes(refreshed),
                    "delta_ms": delta_ms,
                    "edit_path": edit_path,
                }
            )
    return frozen, sync_ms


def _frozen_identity(frozen: list[dict[str, Any]]) -> str:
    return _identity(
        [
            {
                "id": row["id"],
                "previous": _identity(row["previous"]),
                "delta": _identity(row["delta"]),
                "full_refreshed_start": _identity(row["full_refreshed_start"]),
            }
            for row in frozen
        ]
    )


def _grade_task(
    row: dict[str, Any], truth: dict[str, Any]
) -> tuple[dict[str, Any], str, str]:
    previous = row["previous"]
    delta = row["delta"]
    refreshed = row["full_refreshed_start"]
    verify_surface = verification_surface(_task_verification_argv(refreshed))
    path_changes = (
        delta.get("path_changes") if isinstance(delta.get("path_changes"), list) else []
    )
    path_change = (
        path_changes[0]
        if len(path_changes) == 1 and isinstance(path_changes[0], dict)
        else {}
    )
    invalidated = {str(value) for value in (delta.get("invalidated") or [])}
    reused = {str(value) for value in (delta.get("reused") or [])}
    state = str(path_change.get("state") or "missing")
    freshness = str(delta.get("freshness") or "missing")
    graded = {
        "id": row["id"],
        "category": str(truth.get("category") or "unknown"),
        "previous_candidate_correct": str(
            (_task_candidate(previous) or {}).get("path") or ""
        )
        == str(truth["expected_edit_path"]),
        "refreshed_candidate_correct": str(
            (_task_candidate(refreshed) or {}).get("path") or ""
        )
        == str(truth["expected_edit_path"]),
        "refreshed_verify_correct": str(verify_surface.get("surface") or "")
        == str(truth["expected_verify_path"]),
        "path_change_detected": state == "changed"
        and str(path_change.get("path") or "") == str(truth["expected_edit_path"]),
        "revision_invalidated": "candidate-source-revision" in invalidated,
        "generation_invalidated": "previous-evidence-generation" in invalidated,
        "candidate_reused": "owner" in reused or "task-candidate" in reused,
        "verification_surface_reused": "verification-surface" in reused,
        "verification_plan_reused": "verification-plan" in reused,
        "selection_provenance_reused": "selection-provenance" in reused,
        "replacement_absent": "replacement" not in delta,
        "delta_bytes": int(row["delta_bytes"]),
        "full_refreshed_start_bytes": int(row["full_refreshed_start_bytes"]),
        "delta_ms": float(row["delta_ms"]),
        "freshness": freshness,
        "semantic_shields": int(
            (delta.get("semantic_invalidation") or {}).get("shields", 0)
        )
        if isinstance(delta.get("semantic_invalidation"), dict)
        else 0,
    }
    graded["fully_correct"] = all(
        bool(graded[key])
        for key in (
            "previous_candidate_correct",
            "refreshed_candidate_correct",
            "refreshed_verify_correct",
            "path_change_detected",
            "revision_invalidated",
            "generation_invalidated",
            "candidate_reused",
            "verification_surface_reused",
            "verification_plan_reused",
            "selection_provenance_reused",
            "replacement_absent",
        )
    )
    return graded, state, freshness


def _summaries(
    results: list[dict[str, Any]],
    result_states: list[tuple[str, str]],
    sync_ms: float,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    categories: dict[str, list[dict[str, Any]]] = defaultdict(list)
    path_states: Counter[str] = Counter()
    freshness_states: Counter[str] = Counter()
    for row, (path_state, freshness_state) in zip(results, result_states, strict=True):
        categories[row["category"]].append(row)
        path_states[path_state] += 1
        freshness_states[freshness_state] += 1
    count = len(results)
    delta_bytes = sum(int(row["delta_bytes"]) for row in results)
    full_bytes = sum(int(row["full_refreshed_start_bytes"]) for row in results)
    summary = {
        "tasks": count,
        "fully_correct": sum(bool(row["fully_correct"]) for row in results),
        "path_change_detected": sum(
            bool(row["path_change_detected"]) for row in results
        ),
        "revision_invalidated": sum(
            bool(row["revision_invalidated"]) for row in results
        ),
        "generation_invalidated": sum(
            bool(row["generation_invalidated"]) for row in results
        ),
        "candidate_reused": sum(bool(row["candidate_reused"]) for row in results),
        "verification_surface_reused": sum(
            bool(row["verification_surface_reused"]) for row in results
        ),
        "verification_plan_reused": sum(
            bool(row["verification_plan_reused"]) for row in results
        ),
        "selection_provenance_reused": sum(
            bool(row["selection_provenance_reused"]) for row in results
        ),
        "replacement_absent": sum(bool(row["replacement_absent"]) for row in results),
        "path_states": dict(sorted(path_states.items())),
        "freshness_states": dict(sorted(freshness_states.items())),
        "semantic_shields": sum(int(row["semantic_shields"]) for row in results),
        "delta_visible_bytes": delta_bytes,
        "delta_visible_bytes_per_task": delta_bytes / count,
        "full_refreshed_start_visible_bytes": full_bytes,
        "full_refreshed_start_visible_bytes_per_task": full_bytes / count,
        "visible_reduction_pct": 100.0 * (1.0 - delta_bytes / full_bytes),
        "mean_delta_ms": sum(float(row["delta_ms"]) for row in results) / count,
        "initial_sync_ms": sync_ms,
    }
    category_summary = {
        name: {
            "tasks": len(rows),
            "fully_correct": sum(bool(row["fully_correct"]) for row in rows),
            "mean_delta_bytes": sum(int(row["delta_bytes"]) for row in rows)
            / len(rows),
        }
        for name, rows in sorted(categories.items())
    }
    return summary, category_summary


def run(
    repo: Path,
    public_path: Path,
    secret_path: Path,
    output: Path,
    *,
    token_budget: int = 1536,
) -> dict[str, Any]:
    public = json.loads(public_path.read_text(encoding="utf-8"))
    tasks = public.get("tasks")
    if (
        not isinstance(tasks, list)
        or not tasks
        or any(set(row) != {"id", "query"} for row in tasks)
    ):
        raise ValueError("PUBLIC tasks must contain exactly id/query")
    if token_budget < 1:
        raise ValueError("token_budget must be >= 1")

    frozen, sync_ms = _freeze_task_evidence(repo, tasks, token_budget)

    # SECRET is opened only after every start packet, external edit, delta, and
    # counterfactual full refreshed packet is frozen.
    secret = json.loads(secret_path.read_text(encoding="utf-8"))
    expected = {str(row["id"]): row for row in secret.get("tasks") or []}
    if set(expected) != {row["id"] for row in frozen}:
        raise ValueError("SECRET task set does not match frozen PUBLIC task set")

    results: list[dict[str, Any]] = []
    result_states: list[tuple[str, str]] = []
    for row in frozen:
        graded, state, freshness = _grade_task(row, expected[row["id"]])
        results.append(graded)
        result_states.append((state, freshness))
    summary, category_summary = _summaries(results, result_states, sync_ms)
    protocol = {
        "public_fields": ["id", "query"],
        "secret_fields": [
            "expected_edit_path",
            "expected_verify_path",
            "expected_safe",
            "category",
        ],
        "secret_join_after_start_edit_delta_and_counterfactual_freeze": True,
        "external_edit": "syntax-preserving comment appended to the selected edit path before delta refresh",
        "changed_paths_source": "repository candidate from the PUBLIC-only prior task-evidence packet; mutation remains external",
        "source_budget_tokens": token_budget,
        "public_sha256": _sha(public_path),
        "secret_sha256": _sha(secret_path),
        "frozen_identity": _frozen_identity(frozen),
        "exact_model_token_telemetry": False,
        "visible_measurement": "UTF-8 serialized packet bytes",
        "solution_loop": "external; qualification mutator only simulates the already-completed external edit event",
    }
    payload = {
        "schema": SCHEMA,
        "protocol": protocol,
        "protocol_identity": _identity(protocol),
        "summary": summary,
        "categories": category_summary,
        "results": results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--secret", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--token-budget", type=int, default=1536)
    args = parser.parse_args()
    payload = run(
        args.repo, args.public, args.secret, args.output, token_budget=args.token_budget
    )
    log_command_output(
        logger,
        json.dumps(
            {"summary": payload["summary"], "categories": payload["categories"]},
            indent=2,
            sort_keys=True,
        ),
    )


if __name__ == "__main__":
    main()
