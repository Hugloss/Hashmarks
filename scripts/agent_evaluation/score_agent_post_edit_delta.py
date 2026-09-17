# Imports below follow the standalone script path bootstrap.
# ruff: noqa: E402
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from hashmarks.codemap import (
    CodeMap,
)
from scripts.agent_evaluation.economics import (
    verification_surface,
)

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

    frozen: list[dict[str, Any]] = []
    with CodeMap(repo) as codemap:
        sync_started = time.perf_counter()
        codemap.sync()
        sync_ms = (time.perf_counter() - sync_started) * 1000.0

        for task in tasks:
            task_id = str(task["id"])
            query = str(task["query"])
            previous = codemap.task_evidence(query, token_budget=token_budget)
            edit_path = str(previous.get("edit") or "")
            if not edit_path:
                raise ValueError(f"PUBLIC task {task_id} has no safe edit authority")
            _append_probe(repo / edit_path, task_id)

            started = time.perf_counter()
            delta = codemap.task_post_change_delta(
                query,
                [edit_path],
                previous_evidence=previous,
                token_budget=token_budget,
            )
            delta_ms = (time.perf_counter() - started) * 1000.0
            # This full refreshed start is measured only as the counterfactual
            # context cost.  The external-agent delta path does not need it.
            full_refreshed_start = codemap.task_evidence(
                query, token_budget=token_budget
            )
            frozen.append(
                {
                    "id": task_id,
                    "previous": previous,
                    "delta": delta,
                    "full_refreshed_start": full_refreshed_start,
                    "delta_bytes": _bytes(delta),
                    "full_refreshed_start_bytes": _bytes(full_refreshed_start),
                    "delta_ms": delta_ms,
                    "edit_path": edit_path,
                }
            )

    frozen_identity = _identity(
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

    # SECRET is opened only after every start packet, external edit, delta, and
    # counterfactual full refreshed packet is frozen.
    secret = json.loads(secret_path.read_text(encoding="utf-8"))
    expected = {str(row["id"]): row for row in secret.get("tasks") or []}
    if set(expected) != {row["id"] for row in frozen}:
        raise ValueError("SECRET task set does not match frozen PUBLIC task set")

    results: list[dict[str, Any]] = []
    categories: dict[str, list[dict[str, Any]]] = defaultdict(list)
    path_states: Counter[str] = Counter()
    freshness_states: Counter[str] = Counter()
    for row in frozen:
        truth = expected[row["id"]]
        previous = row["previous"]
        delta = row["delta"]
        refreshed = row["full_refreshed_start"]
        verify = refreshed.get("verify")
        verify_surface = verification_surface(
            verify if isinstance(verify, list) else ()
        )
        path_changes = (
            delta.get("path_changes")
            if isinstance(delta.get("path_changes"), list)
            else []
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
        path_states[state] += 1
        freshness_states[freshness] += 1
        graded = {
            "id": row["id"],
            "category": str(truth.get("category") or "unknown"),
            "previous_edit_correct": str(previous.get("edit") or "")
            == str(truth["expected_edit_path"]),
            "refreshed_edit_correct": str(refreshed.get("edit") or "")
            == str(truth["expected_edit_path"]),
            "refreshed_verify_correct": str(verify_surface.get("surface") or "")
            == str(truth["expected_verify_path"]),
            "path_change_detected": state == "changed"
            and str(path_change.get("path") or "") == str(truth["expected_edit_path"]),
            "revision_invalidated": "edit-source-revision" in invalidated,
            "generation_invalidated": "previous-evidence-generation" in invalidated,
            "edit_authority_reused": "edit-authority" in reused,
            "verification_surface_reused": "verification-surface" in reused,
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
                "previous_edit_correct",
                "refreshed_edit_correct",
                "refreshed_verify_correct",
                "path_change_detected",
                "revision_invalidated",
                "generation_invalidated",
                "edit_authority_reused",
                "verification_surface_reused",
                "selection_provenance_reused",
                "replacement_absent",
            )
        )
        results.append(graded)
        categories[graded["category"]].append(graded)

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
        "edit_authority_reused": sum(
            bool(row["edit_authority_reused"]) for row in results
        ),
        "verification_surface_reused": sum(
            bool(row["verification_surface_reused"]) for row in results
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
        "changed_paths_source": "exact path selected by the PUBLIC-only prior task-evidence packet",
        "source_budget_tokens": token_budget,
        "public_sha256": _sha(public_path),
        "secret_sha256": _sha(secret_path),
        "frozen_identity": frozen_identity,
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
    print(  # noqa: T201 - intentional command output
        json.dumps(
            {"summary": payload["summary"], "categories": payload["categories"]},
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
