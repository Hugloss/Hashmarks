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

SCHEMA = "hashmarks.agent-change-impact-qualification.v1"


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
        marker = f"# hashmarks change-impact probe {task_id}"
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
        marker = f"// hashmarks change-impact probe {task_id}"
    elif suffix == ".sql":
        marker = f"-- hashmarks change-impact probe {task_id}"
    else:
        raise ValueError(f"unsupported qualification edit suffix: {suffix or '<none>'}")
    original = path.read_text(encoding="utf-8")
    path.write_text(original.rstrip("\n") + "\n" + marker + "\n", encoding="utf-8")


def _task_owner_path(packet: dict[str, object]) -> str:
    ownership = packet.get("ownership")
    if not isinstance(ownership, dict) or ownership.get("status") != "resolved":
        return ""
    owner = ownership.get("owner")
    if not isinstance(owner, dict):
        return ""
    return str(owner.get("path") or "")


def _surface_paths(packet: dict[str, Any], role: str) -> set[str]:
    surfaces = (
        packet.get("surfaces") if isinstance(packet.get("surfaces"), dict) else {}
    )
    rows = surfaces.get(role) if isinstance(surfaces, dict) else []
    if not isinstance(rows, list):
        return set()
    return {
        str(row.get("path") or "")
        for row in rows
        if isinstance(row, dict) and row.get("path")
    }


def run(
    repo: Path, public_path: Path, secret_path: Path, output: Path
) -> dict[str, Any]:
    public = json.loads(public_path.read_text(encoding="utf-8"))
    tasks = public.get("tasks")
    if (
        not isinstance(tasks, list)
        or not tasks
        or any(set(row) != {"id", "query"} for row in tasks)
    ):
        raise ValueError("PUBLIC tasks must contain exactly id/query")

    frozen: list[dict[str, Any]] = []
    with CodeMap(repo) as codemap:
        started = time.perf_counter()
        codemap.sync()
        sync_ms = (time.perf_counter() - started) * 1000.0
        for task in tasks:
            task_id = str(task["id"])
            query = str(task["query"])
            start = codemap.task_evidence(query)
            edit_path = _task_owner_path(start)
            if not edit_path:
                raise ValueError(
                    f"PUBLIC task {task_id} has no resolved repository owner"
                )
            _append_probe(repo / edit_path, task_id)
            impact_started = time.perf_counter()
            impact = codemap.task_change_impact(query, [edit_path])
            impact_ms = (time.perf_counter() - impact_started) * 1000.0
            frozen.append(
                {
                    "id": task_id,
                    "query": query,
                    "start": start,
                    "impact": impact,
                    "edit_path": edit_path,
                    "impact_bytes": _bytes(impact),
                    "impact_ms": impact_ms,
                }
            )

    frozen_identity = _identity(
        [
            {
                "id": row["id"],
                "start": _identity(row["start"]),
                "impact": _identity(row["impact"]),
            }
            for row in frozen
        ]
    )

    # SECRET is opened only after all start packets, external edit probes, and
    # impact packets have been frozen.
    secret = json.loads(secret_path.read_text(encoding="utf-8"))
    expected = {str(row["id"]): row for row in secret.get("tasks") or []}
    if set(expected) != {row["id"] for row in frozen}:
        raise ValueError("SECRET task set does not match frozen PUBLIC task set")

    results: list[dict[str, Any]] = []
    categories: dict[str, list[dict[str, Any]]] = defaultdict(list)
    reason_counts: Counter[str] = Counter()
    for row in frozen:
        truth = expected[row["id"]]
        impact = row["impact"]
        start = row["start"]
        verification_rows = (
            ((impact.get("surfaces") or {}).get("verification") or [])
            if isinstance(impact.get("surfaces"), dict)
            else []
        )
        implementation_rows = (
            ((impact.get("surfaces") or {}).get("implementation") or [])
            if isinstance(impact.get("surfaces"), dict)
            else []
        )
        for surface_rows in (verification_rows, implementation_rows):
            if isinstance(surface_rows, list):
                for item in surface_rows:
                    if isinstance(item, dict):
                        reason_counts[str(item.get("via") or "unknown")] += 1
        changed = (
            impact.get("changed") if isinstance(impact.get("changed"), list) else []
        )
        changed_row = (
            changed[0] if len(changed) == 1 and isinstance(changed[0], dict) else {}
        )
        changed_roles = {str(value) for value in (changed_row.get("roles") or [])}
        provenance = (
            start.get("provenance") if isinstance(start.get("provenance"), dict) else {}
        )
        structural = str(provenance.get("why") or "").startswith("structural-")
        verification_paths = _surface_paths(impact, "verification")
        implementation_paths = _surface_paths(impact, "implementation")
        serialized = json.dumps(
            impact, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        graded = {
            "id": row["id"],
            "category": str(truth.get("category") or "unknown"),
            "edit_correct": row["edit_path"] == str(truth["expected_edit_path"]),
            "verify_relevant": str(truth["expected_verify_path"]) in verification_paths,
            "structural_dependency_relevant": (not structural)
            or bool(implementation_paths),
            "contract_root_typed": ("contract" in changed_roles)
            if str(truth.get("category")) == "configuration-ownership"
            else True,
            "external_execution_owner": impact.get("owner") == "external",
            "advisory_authority": impact.get("authority") == "advisory",
            "no_source_or_argv_replay": '"content"' not in serialized
            and '"argv"' not in serialized,
            "impact_bytes": int(row["impact_bytes"]),
            "impact_ms": float(row["impact_ms"]),
        }
        graded["fully_correct"] = all(
            bool(graded[key])
            for key in (
                "edit_correct",
                "verify_relevant",
                "structural_dependency_relevant",
                "contract_root_typed",
                "external_execution_owner",
                "advisory_authority",
                "no_source_or_argv_replay",
            )
        )
        results.append(graded)
        categories[graded["category"]].append(graded)

    count = len(results)
    summary = {
        "tasks": count,
        "fully_correct": sum(bool(row["fully_correct"]) for row in results),
        "verify_relevant": sum(bool(row["verify_relevant"]) for row in results),
        "structural_dependency_relevant": sum(
            bool(row["structural_dependency_relevant"]) for row in results
        ),
        "contract_root_typed": sum(bool(row["contract_root_typed"]) for row in results),
        "no_source_or_argv_replay": sum(
            bool(row["no_source_or_argv_replay"]) for row in results
        ),
        "visible_bytes": sum(int(row["impact_bytes"]) for row in results),
        "visible_bytes_per_task": sum(int(row["impact_bytes"]) for row in results)
        / count,
        "mean_impact_ms": sum(float(row["impact_ms"]) for row in results) / count,
        "reason_counts": dict(sorted(reason_counts.items())),
        "initial_sync_ms": sync_ms,
    }
    category_summary = {
        name: {
            "tasks": len(rows),
            "fully_correct": sum(bool(row["fully_correct"]) for row in rows),
            "verify_relevant": sum(bool(row["verify_relevant"]) for row in rows),
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
        "secret_join_after_start_external_edit_and_impact_freeze": True,
        "external_edit": "syntax-preserving comment appended to PUBLIC-only selected edit path",
        "changed_paths_source": "exact PUBLIC-only task_evidence ownership authority",
        "impact_authority": "existing reverse/project impact plus proven task ownership path and selected verification authority",
        "solution_loop_owner": "external-agent",
        "public_sha256": _sha(public_path),
        "secret_sha256": _sha(secret_path),
        "frozen_identity": frozen_identity,
    }
    payload = {
        "schema": SCHEMA,
        "summary": summary,
        "categories": category_summary,
        "results": results,
        "protocol": protocol,
    }
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--secret", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = run(args.repo, args.public, args.secret, args.output)
    print(json.dumps(payload["summary"], sort_keys=True))  # noqa: T201 - intentional command output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
