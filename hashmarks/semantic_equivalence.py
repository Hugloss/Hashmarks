from __future__ import annotations

import json
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal

from .python_ast_cache import clear_ast_cache

QueryKind = Literal["find_task", "task_action_map", "task_decision_packet"]

_DEFAULT_DIAGNOSTIC_KEYS = frozenset({
    "elapsed_ms",
    "duration_ms",
    "wall_ms",
    "wall_time_ms",
    "cache_hits",
    "cache_misses",
    "cache_state",
    "timing",
    "timings",
    "economics",
    "decision_metrics",
})


def _json_ready(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _json_ready(child)
            for key, child in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_ready(child) for child in value]
    as_dict = getattr(value, "as_dict", None)
    if callable(as_dict):
        return _json_ready(as_dict())
    return value


def _semantic_projection(
    value: object,
    diagnostic_keys: frozenset[str],
) -> object:
    ready = _json_ready(value)
    if isinstance(ready, dict):
        return {
            key: _semantic_projection(child, diagnostic_keys)
            for key, child in ready.items()
            if key not in diagnostic_keys
        }
    if isinstance(ready, list):
        return [
            _semantic_projection(child, diagnostic_keys)
            for child in ready
        ]
    return ready


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _run_query(codemap, query: QueryKind, task: str, limit: int) -> object:
    if query == "find_task":
        return codemap.find_task(task, limit=limit)
    if query == "task_action_map":
        return codemap.task_action_map(task, limit=limit)
    if query == "task_decision_packet":
        return codemap.task_decision_packet(task, limit=limit)
    raise ValueError(f"unsupported semantic-equivalence query: {query}")


def verify_cold_warm_semantic_equivalence(
    workspace: str | Path,
    *,
    query: QueryKind,
    task: str,
    limit: int = 20,
    diagnostic_keys: frozenset[str] = _DEFAULT_DIAGNOSTIC_KEYS,
) -> dict[str, object]:
    """Run one repository-intelligence query cold then warm and compare semantics.

    The helper deliberately owns no execution policy. It creates an isolated
    CodeMap state, clears the shared Python AST cache before the cold query, then
    immediately repeats the same query against the unchanged repository state.
    Diagnostic/performance-only keys are removed before comparison.
    """
    if limit < 1:
        raise ValueError("limit must be >= 1")
    if not task.strip():
        raise ValueError("task must be nonblank")

    from .codemap import CodeMap

    workspace_path = Path(workspace)
    with tempfile.TemporaryDirectory(prefix="hashmarks-semantic-equivalence-") as temp:
        state_dir = Path(temp)
        artifact_db = state_dir / "artifacts.sqlite3"
        with CodeMap(
            workspace_path,
            state_dir=state_dir,
            artifact_db=artifact_db,
        ) as codemap:
            codemap.sync()
            clear_ast_cache()
            cold = _run_query(codemap, query, task, limit)
            warm = _run_query(codemap, query, task, limit)

    cold_semantic = _semantic_projection(cold, diagnostic_keys)
    warm_semantic = _semantic_projection(warm, diagnostic_keys)
    cold_json = _canonical_json(cold_semantic)
    warm_json = _canonical_json(warm_semantic)
    return {
        "schema": "hashmarks.cold-warm-semantic-equivalence.v1",
        "query": query,
        "task": task,
        "limit": limit,
        "equivalent": cold_json == warm_json,
        "cold_semantic": cold_semantic,
        "warm_semantic": warm_semantic,
        "diagnostic_keys_ignored": sorted(diagnostic_keys),
    }
