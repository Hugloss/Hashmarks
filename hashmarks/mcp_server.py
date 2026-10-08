from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Any, Literal

from ._version import __version__
from .codemap.change_impact import CHANGE_IMPACT_DEFAULT_REQUEST
from .codemap.evidence_packet import TASK_EVIDENCE_DEFAULT_OPTIONS
from .codemap.find_engine import FIND_DEFAULT_OPTIONS
from .errors import OptionalFeatureError, UserFacingError
from .mcp_contract import (
    MCP_READ_ONLY_ANNOTATIONS,
    MCP_SERVER_DESCRIPTION,
    MCP_SERVER_INSTRUCTIONS,
    MCP_SERVER_NAME,
    McpToolContract,
    tool_contract,
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
_SourceObservationResultMode = Literal[*tuple(operation_modes("source_observation"))]


def _sdk():
    try:
        from mcp.server import MCPServer
        from mcp.server.mcpserver.exceptions import ToolError
        from mcp.types import ToolAnnotations
    except ImportError as exc:  # pragma: no cover - exercised through CLI boundary
        raise OptionalFeatureError(_INSTALL_HINT) from exc
    return MCPServer, ToolAnnotations, ToolError


def _call_surface(
    contract: McpToolContract,
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
    return contract.validate_response(result, result_mode=response_mode)


def _register_repository_declarations_tool(
    server: Any,
    surface: HashmarksMcpSurface,
    annotations: Any,
    tool_error: type[Exception],
) -> None:
    contract = tool_contract("repository_declarations")

    @server.tool(
        name=contract.name,
        description=contract.description,
        annotations=annotations,
    )
    def repository_declarations(
        groups: list[dict[str, Any]],
        previous_observation: dict[str, Any] | None = None,
        result_mode: _RepositoryDeclarationsResultMode = contract.default_response_mode,
    ) -> dict[str, object]:
        return _call_surface(
            contract,
            tool_error,
            surface.repository_declarations,
            groups,
            previous_observation=previous_observation,
            result_mode=result_mode,
            response_mode=result_mode,
        )


def _register_agent_evidence_tools(
    server: Any,
    surface: HashmarksMcpSurface,
    annotations: Any,
    tool_error: type[Exception],
) -> None:
    """Expose existing producers while keeping MCP registration bounded."""
    intelligence_contract = tool_contract("repository_intelligence_query")

    @server.tool(
        name=intelligence_contract.name,
        description=intelligence_contract.description,
        annotations=annotations,
    )
    def repository_intelligence_query(  # noqa: PLR0913 - explicit MCP query inputs
        surface_name: str,
        task: str,
        changed_paths: list[str] | None = None,
        profile: str = "compact",
        presentation: str = "compact",
        member_path: str | None = None,
        previous_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        return _call_surface(
            intelligence_contract,
            tool_error,
            surface.repository_intelligence_query,
            surface_name,
            task,
            changed_paths,
            profile=profile,
            presentation=presentation,
            member_path=member_path,
            previous_snapshot=previous_snapshot,
        )

    source_contract = tool_contract("source_observation")

    @server.tool(
        name=source_contract.name,
        description=source_contract.description,
        annotations=annotations,
    )
    def source_observation(
        paths: list[str],
        literal: str | None = None,
        result_mode: _SourceObservationResultMode = source_contract.default_response_mode,
        limit: int = 50,
    ) -> dict[str, object]:
        return _call_surface(
            source_contract,
            tool_error,
            surface.source_observation,
            paths,
            literal=literal,
            result_mode=result_mode,
            response_mode=result_mode,
            limit=limit,
        )

    locality_contract = tool_contract("structural_locality")

    @server.tool(
        name=locality_contract.name,
        description=locality_contract.description,
        annotations=annotations,
    )
    def structural_locality(target: str, max_depth: int = 2) -> dict[str, object]:
        return _call_surface(
            locality_contract,
            tool_error,
            surface.structural_locality,
            target,
            max_depth=max_depth,
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

    repository_context_contract = tool_contract("repository_context")

    @server.tool(
        name=repository_context_contract.name,
        description=repository_context_contract.description,
        annotations=annotations,
    )
    def repository_context(max_areas: int = 12) -> dict[str, object]:
        return _call_surface(
            repository_context_contract,
            ToolError,
            surface.repository_context,
            max_areas=max_areas,
        )

    find_contract = tool_contract("find")

    @server.tool(
        name=find_contract.name,
        description=find_contract.description,
        annotations=annotations,
    )
    def find(
        query: str,
        limit: int = FIND_DEFAULT_OPTIONS.limit,
    ) -> dict[str, object]:
        return _call_surface(find_contract, ToolError, surface.find, query, limit=limit)

    task_evidence_contract = tool_contract("task_evidence")

    @server.tool(
        name=task_evidence_contract.name,
        description=task_evidence_contract.description,
        annotations=annotations,
    )
    def task_evidence(
        task: str,
        limit: int = TASK_EVIDENCE_DEFAULT_OPTIONS.limit,
        per_role: int = TASK_EVIDENCE_DEFAULT_OPTIONS.per_role,
        token_budget: int = TASK_EVIDENCE_DEFAULT_OPTIONS.token_budget,
    ) -> dict[str, object]:
        return _call_surface(
            task_evidence_contract,
            ToolError,
            surface.task_evidence,
            task,
            limit=limit,
            per_role=per_role,
            token_budget=token_budget,
        )

    change_impact_contract = tool_contract("change_impact")

    @server.tool(
        name=change_impact_contract.name,
        description=change_impact_contract.description,
        annotations=annotations,
    )
    def change_impact(
        task: str,
        changed_paths: list[str],
        max_depth: int = CHANGE_IMPACT_DEFAULT_REQUEST.options.max_depth,
    ) -> dict[str, object]:
        return _call_surface(
            change_impact_contract,
            ToolError,
            surface.change_impact,
            task,
            changed_paths,
            max_depth=max_depth,
        )

    correlate_evidence_contract = tool_contract("correlate_evidence")

    @server.tool(
        name=correlate_evidence_contract.name,
        description=correlate_evidence_contract.description,
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
            correlate_evidence_contract,
            ToolError,
            surface.correlate_evidence,
            bundles,
            path_mappings=path_mappings,
            previous_correlation=previous_correlation,
            include_relationships=include_relationships,
            relationship_limit_per_path=relationship_limit_per_path,
        )

    dependency_codemap_contract = tool_contract("dependency_codemap")

    @server.tool(
        name=dependency_codemap_contract.name,
        description=dependency_codemap_contract.description,
        annotations=annotations,
    )
    def dependency_codemap(
        snapshot: dict[str, object],
        queries: list[dict[str, object]] | None = None,
        previous_observation: dict[str, object] | None = None,
        result_mode: _DependencyCodemapResultMode = (
            dependency_codemap_contract.default_response_mode
        ),
    ) -> dict[str, object]:
        return _call_surface(
            dependency_codemap_contract,
            ToolError,
            surface.dependency_codemap,
            snapshot,
            queries,
            previous_observation=previous_observation,
            result_mode=result_mode,
            response_mode=result_mode,
        )

    _register_repository_declarations_tool(server, surface, annotations, ToolError)

    post_change_contract = tool_contract("post_change")

    @server.tool(
        name=post_change_contract.name,
        description=post_change_contract.description,
        annotations=annotations,
    )
    def post_change(
        task: str,
        changed_paths: list[str],
        previous_evidence: dict[str, Any],
        token_budget: int = TASK_EVIDENCE_DEFAULT_OPTIONS.token_budget,
    ) -> dict[str, object]:
        return _call_surface(
            post_change_contract,
            ToolError,
            surface.post_change,
            task,
            changed_paths,
            previous_evidence,
            token_budget=token_budget,
        )

    _register_agent_evidence_tools(server, surface, annotations, ToolError)

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
