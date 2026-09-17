from __future__ import annotations

import ast
import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from .python_ast_cache import ast_cache_info, clear_ast_cache, read_python_ast

_QUERY_KINDS = frozenset({"find_task", "task_action_map", "task_decision_packet"})


def _read_assignment_target_names(node: ast.AST) -> set[str]:
    if not isinstance(node, (ast.Assign, ast.AnnAssign)):
        return set()
    value = node.value
    if not isinstance(value, ast.Call):
        return set()
    func = value.func
    if not (
        isinstance(func, ast.Attribute) and func.attr in {"read_text", "read_bytes"}
    ):
        return set()
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return {target.id for target in targets if isinstance(target, ast.Name)}


def _file_read_assignment_names(function: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(function):
        names.update(_read_assignment_target_names(node))
    return names


def _is_ast_parse_call(call: ast.Call) -> bool:
    if not isinstance(call.func, ast.Attribute) or not call.args:
        return False
    owner = call.func.value
    return (
        call.func.attr == "parse" and isinstance(owner, ast.Name) and owner.id == "ast"
    )


def _source_is_file_read(source: ast.AST, read_names: set[str]) -> bool:
    if isinstance(source, ast.Name):
        return source.id in read_names
    if not isinstance(source, ast.Call):
        return False
    func = source.func
    return isinstance(func, ast.Attribute) and func.attr in {"read_text", "read_bytes"}


def _ast_parse_uses_file_read(call: ast.Call, read_names: set[str]) -> bool:
    return _is_ast_parse_call(call) and _source_is_file_read(call.args[0], read_names)


def _file_ast_parse_violations(path: Path) -> list[dict[str, object]]:
    tree = read_python_ast(path).tree
    violations: list[dict[str, object]] = []
    for function in [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]:
        read_names = _file_read_assignment_names(function)
        for node in ast.walk(function):
            if isinstance(node, ast.Call) and _ast_parse_uses_file_read(
                node, read_names
            ):
                violations.append(
                    {
                        "path": path.as_posix(),
                        "line": int(node.lineno),
                        "function": function.name,
                        "reason": "file-backed-ast-parse-bypasses-shared-cache",
                    }
                )
    return violations


def shared_python_ast_propagation_audit(
    repository_root: str | Path,
) -> dict[str, object]:
    """Detect production analyzers that re-read and directly parse Python files."""
    root = Path(repository_root)
    package = root / "hashmarks"
    violations: list[dict[str, object]] = []
    for path in sorted(package.rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        if relative == "hashmarks/python_ast_cache.py":
            continue
        violations.extend(_file_ast_parse_violations(path))
    return {
        "schema": "hashmarks.shared-python-ast-propagation-audit.v1",
        "valid": not violations,
        "cache_authority": "hashmarks.python_ast_cache.read_python_ast",
        "violations": violations,
        "files_scanned": sum(1 for _ in package.rglob("*.py")),
    }


def _run_query(codemap, query: str, task: str, limit: int) -> object:
    if query == "find_task":
        return codemap.find_task(task, limit=limit)
    if query == "task_action_map":
        return codemap.task_action_map(task, limit=limit)
    if query == "task_decision_packet":
        return codemap.task_decision_packet(task, limit=limit)
    raise ValueError(f"unsupported repository-intelligence query: {query}")


def _json_ready(value: object) -> object:
    as_dict = getattr(value, "as_dict", None)
    if callable(as_dict):
        return _json_ready(as_dict())
    if isinstance(value, Mapping):
        return {str(key): _json_ready(child) for key, child in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_ready(child) for child in value]
    return value


def _evidence_paths(value: object) -> set[str]:
    ready = _json_ready(value)
    paths: set[str] = set()
    if isinstance(ready, dict):
        path = ready.get("path")
        if isinstance(path, str) and path:
            paths.add(path)
        for child in ready.values():
            paths.update(_evidence_paths(child))
    elif isinstance(ready, list):
        for child in ready:
            paths.update(_evidence_paths(child))
    return paths


def _candidate_count(value: object) -> int:
    ready = _json_ready(value)
    if isinstance(ready, list):
        return len(ready)
    if not isinstance(ready, dict):
        return 0
    canonical = ready.get("canonical")
    if isinstance(canonical, list):
        return len(canonical)
    discrimination = ready.get("discrimination")
    if isinstance(discrimination, Mapping) and isinstance(
        discrimination.get("candidates"), list
    ):
        return len(discrimination["candidates"])
    return 0


def repository_query_runtime_diagnostics(
    workspace: str | Path,
    *,
    query: str,
    task: str,
    limit: int = 20,
) -> dict[str, object]:
    """Measure one isolated repository-intelligence query without execution telemetry."""
    if query not in _QUERY_KINDS:
        raise ValueError(f"unsupported repository-intelligence query: {query}")
    if limit < 1:
        raise ValueError("limit must be >= 1")
    if not task.strip():
        raise ValueError("task must be nonblank")

    from .codemap import CodeMap

    workspace_path = Path(workspace)
    with tempfile.TemporaryDirectory(prefix="hashmarks-economics-") as temp:
        state_dir = Path(temp)
        with CodeMap(
            workspace_path,
            state_dir=state_dir,
            artifact_db=state_dir / "artifacts.sqlite3",
        ) as codemap:
            sync = codemap.sync()
            clear_ast_cache()
            before = ast_cache_info()
            started_ns = time.perf_counter_ns()
            result = _run_query(codemap, query, task, limit)
            elapsed_ns = time.perf_counter_ns() - started_ns
            after = ast_cache_info()

    paths = sorted(_evidence_paths(result))
    existing = [
        workspace_path / path for path in paths if (workspace_path / path).is_file()
    ]
    return {
        "schema": "hashmarks.repository-query-runtime-diagnostics.v1",
        "query": query,
        "task": task,
        "limit": limit,
        "repository_scan": {
            "files": int(sync.discovered),
            "source_bytes": int(sync.economics.get("source_bytes") or 0),
            "parsed_artifacts": int(sync.parsed_artifacts),
            "reused_artifacts": int(sync.reused_artifacts),
            "seconds": float(sync.seconds),
        },
        "query_work": {
            "wall_time_ns": elapsed_ns,
            "wall_time_ms": elapsed_ns / 1_000_000,
            "ast_parses": int(after.misses - before.misses),
            "ast_cache_hits": int(after.hits - before.hits),
            "candidate_count": _candidate_count(result),
            "evidence_files": len(existing),
            "evidence_bytes": sum(path.stat().st_size for path in existing),
            "graph_nodes_traversed": None,
        },
        "availability": {
            "repository_scan_files": True,
            "repository_scan_bytes": True,
            "ast_parses": True,
            "ast_cache_hits": True,
            "candidate_count": True,
            "evidence_files": True,
            "evidence_bytes": True,
            "graph_nodes_traversed": False,
        },
        "boundary": "repository-intelligence-only",
    }


def _delta_stats(
    before: Mapping[str, int],
    after: Mapping[str, int],
) -> dict[str, int]:
    keys = set(before) | set(after)
    return {
        key: int(after.get(key, 0)) - int(before.get(key, 0)) for key in sorted(keys)
    }


def _related_query_session(
    codemap,
    task: str,
    limit: int,
) -> tuple[object, dict[str, object], dict[str, object], dict[str, dict[str, int]]]:
    with codemap.decision_session():
        start = codemap.decision_session_stats()
        found = codemap.find_task(task, limit=limit)
        after_find = codemap.decision_session_stats()
        action = codemap.task_action_map(task, limit=limit)
        after_action = codemap.decision_session_stats()
        packet = codemap.task_decision_packet(task, limit=limit)
        after_packet = codemap.decision_session_stats()
    deltas = {
        "find_task": _delta_stats(start, after_find),
        "task_action_map": _delta_stats(after_find, after_action),
        "task_decision_packet": _delta_stats(after_action, after_packet),
    }
    return found, action, packet, deltas


def _canonical_paths(action: Mapping[str, object]) -> list[str]:
    rows = action.get("canonical", [])
    if not isinstance(rows, list):
        return []
    return [
        str(row.get("path"))
        for row in rows
        if isinstance(row, Mapping) and row.get("path")
    ]


def _packet_role_paths(packet: Mapping[str, object]) -> dict[str, str | None]:
    return {
        role: (
            str(row.get("path"))
            if isinstance(row := packet.get(role), Mapping) and row.get("path")
            else None
        )
        for role in ("edit", "verify", "contract")
    }


def _action_role_paths(action: Mapping[str, object]) -> dict[str, str | None]:
    return {
        role: (
            str(row.get("path"))
            if isinstance(row := action.get(role), Mapping) and row.get("path")
            else None
        )
        for role in ("edit", "verify", "contract")
    }


def _related_query_semantics(
    found: object,
    action: Mapping[str, object],
    packet: Mapping[str, object],
) -> tuple[dict[str, object], bool]:
    found_paths = [hit.path for hit in found]
    action_paths = _canonical_paths(action)
    action_roles = _action_role_paths(action)
    packet_roles = _packet_role_paths(packet)
    semantics = {
        "find_task": found_paths,
        "task_action_map": action_paths,
        "action_roles": action_roles,
        "packet_roles": packet_roles,
    }
    equivalent = (
        found_paths[: len(action_paths)] == action_paths
        and action_roles == packet_roles
    )
    return semantics, equivalent


def related_query_reuse_receipt(
    workspace: str | Path,
    *,
    task: str,
    limit: int = 20,
) -> dict[str, object]:
    """Measure generation-bound evidence reuse across related query surfaces."""
    if limit < 1:
        raise ValueError("limit must be >= 1")
    if not task.strip():
        raise ValueError("task must be nonblank")

    from .codemap import CodeMap

    workspace_path = Path(workspace)
    with tempfile.TemporaryDirectory(prefix="hashmarks-related-query-reuse-") as temp:
        state_dir = Path(temp)
        with CodeMap(
            workspace_path,
            state_dir=state_dir,
            artifact_db=state_dir / "artifacts.sqlite3",
        ) as codemap:
            codemap.sync()
            found, action, packet, deltas = _related_query_session(codemap, task, limit)

    semantics, equivalent = _related_query_semantics(found, action, packet)
    return {
        "schema": "hashmarks.related-query-evidence-reuse.v1",
        "repository_generation_bound": True,
        "task": task,
        "limit": limit,
        "semantic_paths": semantics,
        "semantic_equivalent": equivalent,
        "stage_deltas": deltas,
        "reuse_observed": (
            deltas["task_action_map"].get("task_result_hit", 0) >= 1
            and (
                deltas["task_decision_packet"].get("task_action_hit", 0) >= 1
                or deltas["task_decision_packet"].get("task_result_hit", 0) >= 1
            )
        ),
        "boundary": "repository-intelligence-only",
    }


def _profile_limit(
    codemap,
    task: str,
    limit: int,
) -> dict[str, object]:
    started_ns = time.perf_counter_ns()
    rows = codemap.find_task(task, limit=limit)
    elapsed_ns = time.perf_counter_ns() - started_ns
    paths = [row.path for row in rows]
    return {
        "limit": limit,
        "result_count": len(rows),
        "bound_respected": len(rows) <= limit,
        "wall_time_ns": elapsed_ns,
        "paths": paths,
    }


def bounded_top_n_candidate_profile(
    workspace: str | Path,
    *,
    task: str,
    limits: Sequence[int] = (5, 10, 20),
) -> dict[str, object]:
    """Profile bounded top-N retrieval and prove stable prefix semantics."""
    normalized = tuple(sorted({int(limit) for limit in limits}))
    if not normalized or normalized[0] < 1:
        raise ValueError("limits must contain positive integers")
    if not task.strip():
        raise ValueError("task must be nonblank")

    from .codemap import CodeMap

    workspace_path = Path(workspace)
    with tempfile.TemporaryDirectory(prefix="hashmarks-top-n-profile-") as temp:
        state_dir = Path(temp)
        with CodeMap(
            workspace_path,
            state_dir=state_dir,
            artifact_db=state_dir / "artifacts.sqlite3",
        ) as codemap:
            codemap.sync()
            profiles = [_profile_limit(codemap, task, limit) for limit in normalized]

    largest = profiles[-1]["paths"]
    prefix_checks = {
        str(profile["limit"]): (profile["paths"] == largest[: profile["result_count"]])
        for profile in profiles
    }
    return {
        "schema": "hashmarks.bounded-top-n-candidate-profile.v1",
        "task": task,
        "profiles": profiles,
        "all_bounds_respected": all(
            bool(profile["bound_respected"]) for profile in profiles
        ),
        "prefix_semantics_equivalent": all(prefix_checks.values()),
        "prefix_checks": prefix_checks,
        "internal_operation_counts": {
            "sort_operations": None,
            "set_constructions": None,
            "string_normalizations": None,
        },
        "availability": {
            "top_n_result_count": True,
            "wall_time": True,
            "prefix_equivalence": True,
            "sort_operations": False,
            "set_constructions": False,
            "string_normalizations": False,
        },
        "boundary": "repository-intelligence-only",
    }


def ownership_graph_economics_receipt(
    workspace: str | Path,
    *,
    task: str,
    start_path: str,
    max_depth: int = 2,
) -> dict[str, object]:
    """Measure the bounded ownership graph using its authoritative graph projection."""
    if not task.strip():
        raise ValueError("task must be nonblank")
    if not start_path.strip():
        raise ValueError("start_path must be nonblank")

    from .codemap import CodeMap

    workspace_path = Path(workspace)
    with tempfile.TemporaryDirectory(prefix="hashmarks-graph-economics-") as temp:
        state_dir = Path(temp)
        with CodeMap(
            workspace_path,
            state_dir=state_dir,
            artifact_db=state_dir / "artifacts.sqlite3",
        ) as codemap:
            codemap.sync()
            started_ns = time.perf_counter_ns()
            graph = codemap.ownership_relation_graph(
                task,
                start_path,
                max_depth=max_depth,
            )
            elapsed_ns = time.perf_counter_ns() - started_ns

    nodes = graph.get("nodes")
    edges = graph.get("edges")
    candidates = graph.get("candidates")
    node_count = len(nodes) if isinstance(nodes, list) else 0
    edge_count = len(edges) if isinstance(edges, list) else 0
    candidate_count = len(candidates) if isinstance(candidates, list) else 0
    return {
        "schema": "hashmarks.ownership-graph-economics.v1",
        "task": task,
        "start_path": start_path,
        "max_depth": int(graph.get("max_depth") or max_depth),
        "graph_nodes_traversed": node_count,
        "graph_edges_observed": edge_count,
        "candidate_count": candidate_count,
        "wall_time_ns": elapsed_ns,
        "wall_time_ms": elapsed_ns / 1_000_000,
        "measurement_basis": "authoritative-ownership-graph-projection",
        "availability": {
            "graph_nodes_traversed": True,
            "graph_edges_observed": True,
            "candidate_count": True,
            "wall_time": True,
        },
        "boundary": "repository-intelligence-only",
    }


def low_level_operation_counter_decision() -> dict[str, object]:
    """Record why exact Python-operation counters are not product authority."""
    return {
        "schema": "hashmarks.low-level-operation-counter-decision.v1",
        "decision": "do-not-instrument",
        "metrics": {
            "sort_operations": False,
            "set_constructions": False,
            "string_normalizations": False,
        },
        "reason": (
            "Exact language-operation counts would couple repository intelligence "
            "to implementation details without improving selection correctness, "
            "freshness, ambiguity safety, or bounded top-N evidence."
        ),
        "preferred_evidence": [
            "bounded-top-n-result-count",
            "wall-time",
            "prefix-semantic-equivalence",
            "task-result-cache-hit-miss",
            "ast-cache-hit-miss",
            "ownership-graph-node-and-edge-count",
        ],
        "boundary": "repository-intelligence-only",
    }
