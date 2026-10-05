from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Any, Literal

from ._version import __version__
from .errors import OptionalFeatureError, UserFacingError
from .mcp_contract import (
    MCP_READ_ONLY_ANNOTATIONS,
    MCP_SERVER_DESCRIPTION,
    MCP_SERVER_INSTRUCTIONS,
    MCP_SERVER_NAME,
    tool_description,
    validate_tool_response,
)
from .mcp_surface import HashmarksMcpSurface, McpSurfaceError
from .operation_contract import operation_modes
from .paths import canonical_host_path

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_INSTALL_HINT = (
    'Hashmarks MCP support requires the optional extra: pip install "hashmarks[mcp]"'
)

_SERVER_INSTRUCTIONS = MCP_SERVER_INSTRUCTIONS

_DependencyCodemapResultMode = Literal[*tuple(operation_modes("dependency_codemap"))]
_RepositoryDeclarationsResultMode = Literal[
    *tuple(operation_modes("repository_declarations"))
]


def _sdk():
    try:
        from mcp.server import MCPServer
        from mcp.server.mcpserver.exceptions import ToolError
        from mcp.types import ToolAnnotations
    except ImportError as exc:  # pragma: no cover - exercised through CLI boundary
        raise OptionalFeatureError(_INSTALL_HINT) from exc
    return MCPServer, ToolAnnotations, ToolError


def _call_surface(
    tool_name: str,
    tool_error: type[Exception],
    operation: Callable[..., dict[str, object]],
    /,
    *args: Any,
    response_mode: str | None = None,
    **kwargs: Any,
) -> dict[str, object]:
    """Translate consumer errors and enforce the canonical response contract."""

    try:
        result = operation(*args, **kwargs)
    except McpSurfaceError as exc:
        raise tool_error(exc.transport_message()) from exc
    return validate_tool_response(tool_name, result, result_mode=response_mode)


def _register_repository_declarations_tool(
    server: Any,
    surface: HashmarksMcpSurface,
    annotations: Any,
    tool_error: type[Exception],
) -> None:
    @server.tool(
        name="repository_declarations",
        description=tool_description("repository_declarations"),
        annotations=annotations,
    )
    def repository_declarations(
        groups: list[dict[str, Any]],
        previous_observation: dict[str, Any] | None = None,
        result_mode: _RepositoryDeclarationsResultMode = "observation",
    ) -> dict[str, object]:
        return _call_surface(
            "repository_declarations",
            tool_error,
            surface.repository_declarations,
            groups,
            previous_observation=previous_observation,
            result_mode=result_mode,
            response_mode=result_mode,
        )


def build_server(workspace: str | Path = ".", *, state_dir: str | Path | None = None):
    MCPServer, ToolAnnotations, ToolError = _sdk()
    surface = HashmarksMcpSurface(
        str(workspace), state_dir=None if state_dir is None else str(state_dir)
    )
    server = MCPServer(
        MCP_SERVER_NAME,
        description=MCP_SERVER_DESCRIPTION,
        instructions=MCP_SERVER_INSTRUCTIONS,
        version=__version__,
    )
    annotations = ToolAnnotations(
        read_only_hint=MCP_READ_ONLY_ANNOTATIONS["readOnlyHint"],
        destructive_hint=MCP_READ_ONLY_ANNOTATIONS["destructiveHint"],
        idempotent_hint=MCP_READ_ONLY_ANNOTATIONS["idempotentHint"],
        open_world_hint=MCP_READ_ONLY_ANNOTATIONS["openWorldHint"],
    )

    @server.tool(
        name="repository_context",
        description=tool_description("repository_context"),
        annotations=annotations,
    )
    def repository_context(max_areas: int = 12) -> dict[str, object]:
        return _call_surface(
            "repository_context",
            ToolError,
            surface.repository_context,
            max_areas=max_areas,
        )

    @server.tool(
        name="find",
        description=tool_description("find"),
        annotations=annotations,
    )
    def find(query: str, limit: int = 20) -> dict[str, object]:
        return _call_surface("find", ToolError, surface.find, query, limit=limit)

    @server.tool(
        name="task_evidence",
        description=tool_description("task_evidence"),
        annotations=annotations,
    )
    def task_evidence(
        task: str, limit: int = 20, per_role: int = 3, token_budget: int = 1536
    ) -> dict[str, object]:
        return _call_surface(
            "task_evidence",
            ToolError,
            surface.task_evidence,
            task,
            limit=limit,
            per_role=per_role,
            token_budget=token_budget,
        )

    @server.tool(
        name="change_impact",
        description=tool_description("change_impact"),
        annotations=annotations,
    )
    def change_impact(
        task: str, changed_paths: list[str], max_depth: int = 4
    ) -> dict[str, object]:
        return _call_surface(
            "change_impact",
            ToolError,
            surface.change_impact,
            task,
            changed_paths,
            max_depth=max_depth,
        )

    @server.tool(
        name="correlate_evidence",
        description=tool_description("correlate_evidence"),
        annotations=annotations,
    )
    def correlate_evidence(
        bundles: list[dict[str, Any]],
        path_mappings: list[dict[str, Any]] | None = None,
        previous_correlation: dict[str, Any] | None = None,
        include_relationships: bool = True,
        relationship_limit_per_path: int = 100,
    ) -> dict[str, object]:
        return _call_surface(
            "correlate_evidence",
            ToolError,
            surface.correlate_evidence,
            bundles,
            path_mappings=path_mappings,
            previous_correlation=previous_correlation,
            include_relationships=include_relationships,
            relationship_limit_per_path=relationship_limit_per_path,
        )

    @server.tool(
        name="dependency_codemap",
        description=tool_description("dependency_codemap"),
        annotations=annotations,
    )
    def dependency_codemap(
        snapshot: dict[str, object],
        queries: list[dict[str, object]] | None = None,
        previous_observation: dict[str, object] | None = None,
        result_mode: _DependencyCodemapResultMode = "observation",
    ) -> dict[str, object]:
        return _call_surface(
            "dependency_codemap",
            ToolError,
            surface.dependency_codemap,
            snapshot,
            queries,
            previous_observation=previous_observation,
            result_mode=result_mode,
            response_mode=result_mode,
        )

    _register_repository_declarations_tool(server, surface, annotations, ToolError)

    @server.tool(
        name="post_change",
        description=tool_description("post_change"),
        annotations=annotations,
    )
    def post_change(
        task: str,
        changed_paths: list[str],
        previous_evidence: dict[str, Any],
        token_budget: int = 1536,
    ) -> dict[str, object]:
        return _call_surface(
            "post_change",
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
