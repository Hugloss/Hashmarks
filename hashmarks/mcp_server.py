from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Any, TypeVar

from .errors import OptionalFeatureError, UserFacingError
from .mcp_surface import HashmarksMcpSurface, McpSurfaceError
from .paths import canonical_host_path

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_INSTALL_HINT = (
    'Hashmarks MCP support requires the optional extra: pip install "hashmarks[mcp]"'
)

_T = TypeVar("_T")


def _sdk():
    try:
        from mcp.server import MCPServer
        from mcp.server.mcpserver.exceptions import ToolError
        from mcp.types import ToolAnnotations
    except ImportError as exc:  # pragma: no cover - exercised through CLI boundary
        raise OptionalFeatureError(_INSTALL_HINT) from exc
    return MCPServer, ToolAnnotations, ToolError


def _call_surface(
    tool_error: type[Exception],
    operation: Callable[..., _T],
    /,
    *args: Any,
    **kwargs: Any,
) -> _T:
    """Translate Hashmarks consumer errors at the MCP transport boundary."""

    try:
        return operation(*args, **kwargs)
    except McpSurfaceError as exc:
        raise tool_error(str(exc)) from exc


def build_server(workspace: str | Path = ".", *, state_dir: str | Path | None = None):
    MCPServer, ToolAnnotations, ToolError = _sdk()
    surface = HashmarksMcpSurface(
        str(workspace), state_dir=None if state_dir is None else str(state_dir)
    )
    server = MCPServer("Hashmarks")
    annotations = ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )

    @server.tool(
        name="repository_context",
        description="Get compact repository orientation, generation/freshness, languages, areas, and project topology.",
        annotations=annotations,
    )
    def repository_context(max_areas: int = 12) -> dict[str, object]:
        return _call_surface(ToolError, surface.repository_context, max_areas=max_areas)

    @server.tool(
        name="find",
        description="Find bounded repository paths or symbols relevant to a query without reading full files.",
        annotations=annotations,
    )
    def find(query: str, limit: int = 20) -> dict[str, object]:
        return _call_surface(ToolError, surface.find, query, limit=limit)

    @server.tool(
        name="task_evidence",
        description="Get the compact pre-edit authority, edit, verification, freshness, ambiguity, and next-read evidence for a coding task.",
        annotations=annotations,
    )
    def task_evidence(
        task: str, limit: int = 20, per_role: int = 3, token_budget: int = 1536
    ) -> dict[str, object]:
        return _call_surface(
            ToolError,
            surface.task_evidence,
            task,
            limit=limit,
            per_role=per_role,
            token_budget=token_budget,
        )

    @server.tool(
        name="change_impact",
        description="Given a task and caller-reported changed repository paths, return bounded structural impact and verification relevance.",
        annotations=annotations,
    )
    def change_impact(
        task: str, changed_paths: list[str], max_depth: int = 4
    ) -> dict[str, object]:
        return _call_surface(
            ToolError, surface.change_impact, task, changed_paths, max_depth=max_depth
        )

    @server.tool(
        name="post_change",
        description="Refresh caller-reported changed paths against a previous task_evidence packet and return only invalidated/reused/replacement evidence.",
        annotations=annotations,
    )
    def post_change(
        task: str,
        changed_paths: list[str],
        previous_evidence: dict[str, Any],
        token_budget: int = 1536,
    ) -> dict[str, object]:
        return _call_surface(
            ToolError,
            surface.post_change,
            task,
            changed_paths,
            previous_evidence,
            token_budget=token_budget,
        )

    server._hashmarks_surface = surface
    return server


def run_stdio(
    workspace: str | Path = ".", *, state_dir: str | Path | None = None
) -> None:
    server = build_server(workspace, state_dir=state_dir)
    try:
        server.run(transport="stdio")
    finally:
        surface = getattr(server, "_hashmarks_surface", None)
        if surface is not None:
            surface.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="hashmarks mcp",
        description="Serve one Hashmarks workspace over local MCP stdio",
    )
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--state-dir", default=None)
    args = parser.parse_args(argv)
    workspace = canonical_host_path(args.workspace)
    state_dir = None if args.state_dir is None else canonical_host_path(args.state_dir)
    try:
        run_stdio(workspace, state_dir=state_dir)
    except (UserFacingError, McpSurfaceError) as exc:
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
