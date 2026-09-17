from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class NxNodeData:
    name: str
    type: str
    root: str
    source_root: str | None
    targets: tuple[str, ...]
    tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NxEdgeData:
    source: str
    target: str
    kind: str


@dataclass(frozen=True, slots=True)
class NxGraphData:
    executable: str | None
    nodes: tuple[NxNodeData, ...] = ()
    edges: tuple[NxEdgeData, ...] = ()
    warnings: tuple[str, ...] = ()


def find_nx(workspace: Path) -> str | None:
    local = workspace / "node_modules" / ".bin" / "nx"
    if local.is_file():
        return str(local)
    return shutil.which("nx")


def _nx_environment() -> dict[str, str]:
    env = dict(os.environ)
    env["NX_DAEMON"] = "false"
    env["NX_CACHE_PROJECT_GRAPH"] = "false"
    return env


def _run_nx_graph(nx: str, workspace: Path, timeout: float) -> tuple[subprocess.CompletedProcess[str] | None, str | None]:
    try:
        completed = subprocess.run(
            [nx, "graph", "--print"],
            cwd=workspace,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
            env=_nx_environment(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"nx graph failed: {exc}"
    if completed.returncode == 0:
        return completed, None
    detail = completed.stderr.strip().splitlines()[-1] if completed.stderr.strip() else f"exit {completed.returncode}"
    return None, f"nx graph failed: {detail}"


def _nx_payload(stdout: str) -> tuple[dict[str, object] | None, str | None]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return None, "nx graph returned invalid JSON"
    graph = payload.get("graph", payload) if isinstance(payload, dict) else {}
    if not isinstance(graph, dict):
        return None, "nx graph JSON is missing project nodes/dependencies"
    raw_nodes = graph.get("nodes")
    raw_deps = graph.get("dependencies")
    if not isinstance(raw_nodes, dict) or not isinstance(raw_deps, dict):
        return None, "nx graph JSON is missing project nodes/dependencies"
    return {"nodes": raw_nodes, "dependencies": raw_deps}, None


def _nx_data(raw: dict[str, object]) -> dict[str, object]:
    data = raw.get("data")
    return data if isinstance(data, dict) else {}


def _safe_nx_root(data: dict[str, object]) -> str | None:
    root = str(data.get("root") or ".").replace("\\", "/").strip("/") or "."
    unsafe = root == ".." or root.startswith("../") or "/../" in root
    return None if unsafe else root


def _nx_targets(data: dict[str, object]) -> tuple[str, ...]:
    raw = data.get("targets")
    values = raw if isinstance(raw, dict) else {}
    return tuple(sorted(str(value) for value in values))


def _nx_tags(data: dict[str, object]) -> tuple[str, ...]:
    raw = data.get("tags")
    values = raw if isinstance(raw, list) else []
    return tuple(str(value) for value in values)


def _nx_source_root(data: dict[str, object]) -> str | None:
    value = data.get("sourceRoot")
    return None if value is None else str(value)


def _nx_node(key: object, raw: object) -> NxNodeData | None:
    if not isinstance(raw, dict):
        return None
    data = _nx_data(raw)
    root = _safe_nx_root(data)
    if root is None:
        return None
    return NxNodeData(
        name=str(raw.get("name") or key),
        type=str(raw.get("type") or "project"),
        root=root,
        source_root=_nx_source_root(data),
        targets=_nx_targets(data),
        tags=_nx_tags(data),
    )


def _nx_nodes(raw_nodes: dict[object, object]) -> tuple[list[NxNodeData], set[str]]:
    nodes = [node for key, raw in raw_nodes.items() if (node := _nx_node(key, raw)) is not None]
    return nodes, {node.name for node in nodes}


def _nx_dependency_edge(source: str, raw: object, known: set[str]) -> NxEdgeData | None:
    if not isinstance(raw, dict):
        return None
    target = str(raw.get("target") or "")
    if target not in known or target == source:
        return None
    return NxEdgeData(source, target, str(raw.get("type") or "dependency"))


def _nx_edges(raw_deps: dict[object, object], known: set[str]) -> list[NxEdgeData]:
    edges: list[NxEdgeData] = []
    for source, values in raw_deps.items():
        source_name = str(source)
        if source_name not in known or not isinstance(values, list):
            continue
        edges.extend(
            edge for raw in values
            if (edge := _nx_dependency_edge(source_name, raw, known)) is not None
        )
    return edges


def _collect_nx_payload(nx: str, workspace: Path, timeout: float) -> tuple[dict[str, object] | None, str | None]:
    completed, error = _run_nx_graph(nx, workspace, timeout)
    if completed is None:
        return None, error or "nx graph failed"
    return _nx_payload(completed.stdout)


def collect_nx_graph(workspace: Path, *, executable: str | None = None, timeout: float = 30.0) -> NxGraphData:
    nx = executable or find_nx(workspace)
    if nx is None:
        return NxGraphData(None, warnings=("nx.json detected but repo-local/global nx executable is unavailable",))
    graph, error = _collect_nx_payload(nx, workspace, timeout)
    if graph is None:
        return NxGraphData(nx, warnings=(error or "nx graph unavailable",))
    nodes, known = _nx_nodes(graph["nodes"])
    return NxGraphData(nx, tuple(nodes), tuple(_nx_edges(graph["dependencies"], known)))
