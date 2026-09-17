from __future__ import annotations

import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from .product_acceptance import scale_class_contract
from .qualification_economics import qualification_classification_economics
from .repository_diagnostics import (
    bounded_top_n_candidate_profile,
    related_query_reuse_receipt,
    repository_query_runtime_diagnostics,
)

RESIDUAL_ECONOMICS_SCHEMA = "hashmarks.residual-repository-economics.v1"
CHANGED_IMPACT_ECONOMICS_SCHEMA = "hashmarks.changed-impact-economics.v1"
_QUERY_SURFACES = ("find_task", "task_action_map", "task_decision_packet")


def _nested_path_count(value: object) -> int:
    if isinstance(value, Mapping):
        own = int(isinstance(value.get("path"), str) and bool(value.get("path")))
        return own + sum(_nested_path_count(child) for child in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return sum(_nested_path_count(child) for child in value)
    return 0


def changed_impact_economics_receipt(
    workspace: str | Path,
    *,
    task: str,
    changed_paths: Sequence[str],
) -> dict[str, object]:
    """Measure changed-impact repository intelligence without mutating or executing work."""
    if not task.strip():
        raise ValueError("task must be nonblank")
    normalized = tuple(
        dict.fromkeys(path.strip() for path in changed_paths if path.strip())
    )
    if not normalized:
        raise ValueError("changed_paths must be nonempty")
    from .codemap import CodeMap

    workspace_path = Path(workspace)
    with tempfile.TemporaryDirectory(prefix="hashmarks-residual-impact-") as temp:
        state = Path(temp)
        with CodeMap(
            workspace_path, state_dir=state, artifact_db=state / "artifacts.sqlite3"
        ) as codemap:
            sync = codemap.sync()
            started = time.perf_counter_ns()
            result = codemap.task_change_impact(task, normalized)
            elapsed = time.perf_counter_ns() - started
    project = result.get("project_impact") if isinstance(result, Mapping) else None
    total_affected = (
        project.get("total_affected") if isinstance(project, Mapping) else None
    )
    return {
        "schema": CHANGED_IMPACT_ECONOMICS_SCHEMA,
        "task": task,
        "changed_paths": list(normalized),
        "wall_time_ns": elapsed,
        "wall_time_ms": elapsed / 1_000_000,
        "evidence_path_occurrences": _nested_path_count(result),
        "project_total_affected": total_affected,
        "repository_scan_files": int(sync.discovered),
        "repository_scan_bytes": int(sync.economics.get("source_bytes") or 0),
        "authority": "repository-intelligence-economics-only",
        "execution_layout": "external",
    }


def _isolated_query_receipts(
    workspace: Path, task: str, limit: int
) -> dict[str, dict[str, object]]:
    return {
        query: repository_query_runtime_diagnostics(
            workspace, query=query, task=task, limit=limit
        )
        for query in _QUERY_SURFACES
    }


def _isolated_totals(
    receipts: Mapping[str, Mapping[str, object]],
) -> dict[str, int | float]:
    query_work = [row["query_work"] for row in receipts.values()]
    return {
        "wall_time_ns": sum(int(row["wall_time_ns"]) for row in query_work),
        "ast_parses": sum(int(row["ast_parses"]) for row in query_work),
        "ast_cache_hits": sum(int(row["ast_cache_hits"]) for row in query_work),
        "candidate_count": sum(int(row["candidate_count"]) for row in query_work),
        "evidence_files": sum(int(row["evidence_files"]) for row in query_work),
        "evidence_bytes": sum(int(row["evidence_bytes"]) for row in query_work),
    }


def residual_repository_economics_report(
    workspace: str | Path,
    *,
    task: str,
    changed_paths: Sequence[str] = (),
    limit: int = 20,
    qualification_root: str | Path | None = None,
) -> dict[str, object]:
    """Aggregate existing economics surfaces into one post-feature residual receipt."""
    workspace_path = Path(workspace).resolve()
    isolated = _isolated_query_receipts(workspace_path, task, limit)
    scan = isolated["find_task"]["repository_scan"]
    scale = scale_class_contract(
        files=int(scan["files"]),
        source_bytes=int(scan["source_bytes"]),
    )
    qualification = (
        qualification_classification_economics(Path(qualification_root).resolve())
        if qualification_root is not None
        else None
    )
    impact = (
        changed_impact_economics_receipt(
            workspace_path, task=task, changed_paths=changed_paths
        )
        if changed_paths
        else None
    )
    return {
        "schema": RESIDUAL_ECONOMICS_SCHEMA,
        "task": task,
        "limit": limit,
        "scale": scale,
        "isolated_queries": isolated,
        "isolated_query_totals": _isolated_totals(isolated),
        "related_query_reuse": related_query_reuse_receipt(
            workspace_path, task=task, limit=limit
        ),
        "bounded_top_n": bounded_top_n_candidate_profile(
            workspace_path, task=task, limits=(5, 10, limit)
        ),
        "changed_impact": impact,
        "qualification_classification": qualification,
        "boundary": "repository-intelligence-economics-only",
        "execution_authority": "external",
        "result_authority": "external",
        "certification_authority": "external",
    }
