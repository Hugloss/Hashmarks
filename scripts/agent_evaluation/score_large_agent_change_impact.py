from __future__ import annotations

import argparse
import json
import logging
import statistics
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hashmarks._command_output import log_command_output
from hashmarks.codemap import (
    CodeMap,
)
from scripts.generate_large_impact_corpus import (
    KINDS,
    generate,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Iterable

SCHEMA = "hashmarks.large-agent-change-impact-economics.v1"


def _bytes(value: object) -> int:
    return len(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    )


def _append_probe(path: Path) -> None:
    marker = (
        "# external edit probe\n"
        if path.suffix == ".py"
        else "// external edit probe\n"
    )
    path.write_text(
        path.read_text(encoding="utf-8").rstrip("\n") + "\n" + marker, encoding="utf-8"
    )


def _task_candidate_path(packet: dict[str, object]) -> str:
    ownership = packet.get("ownership")
    if not isinstance(ownership, dict):
        return ""
    candidate = ownership.get("candidate")
    if not isinstance(candidate, dict):
        return ""
    return str(candidate.get("path") or "")


def _surface_paths(packet: dict[str, Any], role: str) -> set[str]:
    surfaces = (
        packet.get("surfaces") if isinstance(packet.get("surfaces"), dict) else {}
    )
    rows = surfaces.get(role) if isinstance(surfaces, dict) else []
    return (
        {
            str(row.get("path"))
            for row in rows
            if isinstance(row, dict) and row.get("path")
        }
        if isinstance(rows, list)
        else set()
    )


def _freeze_scenario(
    repo: Path, tasks: list[dict[str, object]]
) -> tuple[list[dict], float]:
    frozen = []
    with CodeMap(repo) as codemap:
        started = time.perf_counter()
        codemap.sync()
        sync_ms = (time.perf_counter() - started) * 1000.0
        for task in tasks:
            query = str(task["query"])
            start_started = time.perf_counter()
            start = codemap.task_evidence(query)
            start_ms = (time.perf_counter() - start_started) * 1000.0
            edit_path = _task_candidate_path(start)
            if edit_path:
                _append_probe(repo / edit_path)
                impact_started = time.perf_counter()
                impact = codemap.task_change_impact(query, [edit_path])
                impact_ms = (time.perf_counter() - impact_started) * 1000.0
            else:
                impact = {}
                impact_ms = 0.0
            frozen.append(
                {
                    "id": str(task["id"]),
                    "query": query,
                    "start": start,
                    "edit": edit_path,
                    "impact": impact,
                    "impact_bytes": _bytes(impact),
                    "start_ms": start_ms,
                    "impact_ms": impact_ms,
                }
            )
    return frozen, sync_ms


def _grade_scenario(
    frozen: list[dict[str, Any]], expected: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    graded = []
    for row in frozen:
        truth = expected[row["id"]]
        impact = row["impact"]
        verify = _surface_paths(impact, "verification")
        implementation = _surface_paths(impact, "implementation")
        encoded = json.dumps(
            impact, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        result = {
            "id": row["id"],
            "candidate_correct": row["edit"] == str(truth["expected_edit_path"]),
            "candidate_available": bool(row["edit"]),
            "verify_relevant": str(truth["expected_verify_path"]) in verify,
            "dependency_relevant": str(truth["expected_dependency_path"])
            in implementation,
            "no_source_or_argv_replay": '"content"' not in encoded
            and '"argv"' not in encoded,
            "impact_bytes": int(row["impact_bytes"]),
            "start_ms": float(row["start_ms"]),
            "impact_ms": float(row["impact_ms"]),
        }
        result["fully_correct"] = all(
            bool(result[key])
            for key in (
                "candidate_correct",
                "candidate_available",
                "verify_relevant",
                "dependency_relevant",
                "no_source_or_argv_replay",
            )
        )
        graded.append(result)
    return graded


def run_scenario(
    root: Path, *, kind: str, noise_files: int, tasks: int
) -> dict[str, Any]:
    scenario = f"{kind}-{noise_files}"
    repo = root / "repos" / scenario
    public_path = root / "public" / f"{scenario}.json"
    secret_path = root / "secret" / f"{scenario}.json"
    manifest = generate(
        repo, public_path, secret_path, kind=kind, noise_files=noise_files, tasks=tasks
    )
    public = json.loads(public_path.read_text(encoding="utf-8"))

    frozen, sync_ms = _freeze_scenario(repo, public["tasks"])

    # SECRET is opened only after every task-local start, caller edit probe, and
    # changed-impact packet for this scenario has been frozen.
    secret = json.loads(secret_path.read_text(encoding="utf-8"))
    expected = {str(row["id"]): row for row in secret["tasks"]}
    graded = _grade_scenario(frozen, expected)

    return {
        "scenario": scenario,
        "kind": kind,
        "noise_files": noise_files,
        "repository_files": sum(1 for path in repo.rglob("*") if path.is_file()),
        "manifest": manifest,
        "tasks": tasks,
        "sync_ms": sync_ms,
        "fully_correct": sum(bool(row["fully_correct"]) for row in graded),
        "candidate_correct": sum(bool(row["candidate_correct"]) for row in graded),
        "verify_relevant": sum(bool(row["verify_relevant"]) for row in graded),
        "dependency_relevant": sum(bool(row["dependency_relevant"]) for row in graded),
        "no_source_or_argv_replay": sum(
            bool(row["no_source_or_argv_replay"]) for row in graded
        ),
        "mean_impact_bytes": statistics.fmean(row["impact_bytes"] for row in graded),
        "mean_start_ms": statistics.fmean(row["start_ms"] for row in graded),
        "mean_impact_ms": statistics.fmean(row["impact_ms"] for row in graded),
        "max_impact_ms": max(row["impact_ms"] for row in graded),
        "results": graded,
        "protocol": {
            "secret_join_after_scenario_freeze": True,
            "external_edit": "syntax-preserving comment applied to a repository candidate; no ownership claim",
            "solution_loop_owner": "external-agent",
        },
    }


def run_matrix(
    root: Path,
    *,
    sizes: Iterable[int] = (250, 1000, 3000, 10000),
    kinds: Iterable[str] = KINDS,
    regular_tasks: int = 8,
    largest_tasks: int = 4,
) -> dict[str, Any]:
    sizes = tuple(int(size) for size in sizes)
    kinds = tuple(kinds)
    scenarios: list[dict[str, Any]] = []
    largest = max(sizes)
    for size in sizes:
        for kind in kinds:
            scenarios.append(
                run_scenario(
                    root,
                    kind=kind,
                    noise_files=size,
                    tasks=largest_tasks
                    if size == largest and size >= 10000
                    else regular_tasks,
                )
            )
    total_tasks = sum(row["tasks"] for row in scenarios)
    payload = {
        "schema": SCHEMA,
        "summary": {
            "scenarios": len(scenarios),
            "tasks": total_tasks,
            "fully_correct": sum(row["fully_correct"] for row in scenarios),
            "candidate_correct": sum(row["candidate_correct"] for row in scenarios),
            "verify_relevant": sum(row["verify_relevant"] for row in scenarios),
            "dependency_relevant": sum(row["dependency_relevant"] for row in scenarios),
            "no_source_or_argv_replay": sum(
                row["no_source_or_argv_replay"] for row in scenarios
            ),
            "max_repository_files": max(row["repository_files"] for row in scenarios),
            "mean_impact_bytes": statistics.fmean(
                row["mean_impact_bytes"] for row in scenarios
            ),
        },
        "scenarios": scenarios,
        "scientific_boundary": [
            "Deterministic repository-intelligence/context/latency stress, not a model-directed experiment.",
            "SECRET grading metadata remains outside worker repositories and is opened only after scenario packets are frozen.",
            "Hashmarks does not edit the solution, choose follow-up work, execute verification, or own recovery.",
            "UTF-8 serialized bytes are measured directly and are not relabeled as model tokens.",
        ],
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sizes", default="250,1000,3000,10000")
    parser.add_argument("--regular-tasks", type=int, default=8)
    parser.add_argument("--largest-tasks", type=int, default=4)
    args = parser.parse_args()
    sizes = tuple(int(value) for value in args.sizes.split(",") if value.strip())
    payload = run_matrix(
        args.root,
        sizes=sizes,
        regular_tasks=args.regular_tasks,
        largest_tasks=args.largest_tasks,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    log_command_output(logger, json.dumps(payload["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
