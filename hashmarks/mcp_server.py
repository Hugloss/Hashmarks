from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING, Annotated, Any, Literal

from ._version import __version__
from .codemap.change_impact import CHANGE_IMPACT_DEFAULT_REQUEST
from .codemap.evidence_packet import TASK_EVIDENCE_DEFAULT_OPTIONS
from .codemap.evidence_profiles import ProfileName
from .codemap.find_engine import FIND_DEFAULT_OPTIONS
from .codemap.repository_intelligence_query import QUERY_SURFACES, QuerySurface
from .errors import OptionalFeatureError, UserFacingError
from .evidence_presentation import (
    FORMATS,
    PresentationFormat,
    present_repository_evidence,
    presentation_response,
    validate_presentation,
)
from .mcp_contract import (
    MCP_READ_ONLY_ANNOTATIONS,
    MCP_SERVER_DESCRIPTION,
    MCP_SERVER_INSTRUCTIONS,
    MCP_SERVER_NAME,
    MCP_TOOL_NAMES,
    McpToolContract,
    mcp_projection_instructions,
    normalize_mcp_query_surfaces,
    normalize_mcp_tool_names,
    tool_contract,
)
from .mcp_surface import HashmarksMcpSurface, McpSurfaceError
from .operation_contract import operation_modes
from .paths import canonical_host_path

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from mcp.server import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
    from mcp.types import CallToolResult, ToolAnnotations


_INSTALL_HINT = (
    'Hashmarks MCP support requires the optional extra: pip install "hashmarks[mcp]"'
)

_SERVER_INSTRUCTIONS = MCP_SERVER_INSTRUCTIONS

_Presentation = PresentationFormat
_QuerySurface = QuerySurface
_Profile = ProfileName

if TYPE_CHECKING:
    # Static checkers cannot evaluate computed Literal arguments. Runtime tool
    # schemas still derive their exact selectors from the operation owner.
    _DependencyCodemapResultMode = str
    _RepositoryDeclarationsResultMode = str
    _SourceObservationResultMode = str
    _RepositoryEvidenceResultMode = str
    _EvidenceComparisonResultMode = str
    _TaskEvidenceResultMode = str
else:
    _DependencyCodemapResultMode = Literal[
        *tuple(operation_modes("dependency_codemap"))
    ]
    _RepositoryDeclarationsResultMode = Literal[
        *tuple(operation_modes("repository_declarations"))
    ]
    _SourceObservationResultMode = Literal[
        *tuple(operation_modes("source_observation"))
    ]
    _RepositoryEvidenceResultMode = Literal[
        *tuple(operation_modes("repository_evidence"))
    ]
    _EvidenceComparisonResultMode = Literal[
        *tuple(operation_modes("evidence_comparison"))
    ]
    _TaskEvidenceResultMode = Literal[*tuple(operation_modes("task_evidence"))]


class _StrictSdkInteger:
    """Disable SDK coercion without importing its optional schema dependency."""

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: object, _handler: object
    ) -> object:
        # The native SDK evaluates this hook while registering the tool. Plain
        # module imports and catalog-only adapters never load Pydantic.
        from pydantic_core import core_schema

        return core_schema.int_schema(strict=True)


_SourceInteger = Annotated[int, _StrictSdkInteger]


def _sdk() -> tuple[type[MCPServer], type[ToolAnnotations], type[ToolError]]:
    try:
        from mcp.server import MCPServer
        from mcp.server.mcpserver.exceptions import ToolError
        from mcp.types import ToolAnnotations

    except ImportError as exc:  # pragma: no cover - exercised through CLI boundary
        raise OptionalFeatureError(_INSTALL_HINT) from exc
    return MCPServer, ToolAnnotations, ToolError


def _compact_json_tool_result(result: dict[str, object]) -> CallToolResult:
    """Mirror the validated native JSON without pretty-print amplification."""
    from mcp.types import CallToolResult, TextContent

    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=json.dumps(
                    result, separators=(",", ":"), ensure_ascii=False, allow_nan=False
                ),
            )
        ],
        structured_content=result,
    )


def _task_evidence_tool_result(
    result: dict[str, Any], mode: str, presentation: str
) -> CallToolResult:
    if mode != "initial":
        return _compact_json_tool_result(result)
    from mcp.types import CallToolResult, TextContent

    native = result.get("result", result)
    projection = result.get("presentation")
    if projection is None:
        projection = present_repository_evidence(native, format="text")
    if presentation in {"none", "text"}:
        text = str(projection["text"])
    else:
        text = json.dumps(
            projection, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
    return CallToolResult(
        content=[TextContent(type="text", text=text)], structured_content=native
    )


def _register_json_mirror_tool(
    server: MCPServer,
    contract: McpToolContract,
    annotations: ToolAnnotations,
    handler: Callable[..., object],
) -> None:
    from mcp.types import CallToolResult

    # Preserve structured-output validation and the object output schema while
    # accepting an explicit compact JSON mirror through the supported SDK API.
    handler.__annotations__["return"] = Annotated[CallToolResult, dict[str, object]]
    server.tool(
        name=contract.name,
        description=contract.description,
        annotations=annotations,
    )(handler)


def _call_surface(
    contract: McpToolContract,
    tool_error: type[Exception],
    operation: Callable[..., Mapping[str, object]],
    /,
    *args: object,
    response_mode: str | None = None,
    presentation: str = "none",
    **kwargs: object,
) -> dict[str, object]:
    """Translate consumer errors and enforce the canonical response contract."""

    try:
        if presentation not in FORMATS:
            raise McpSurfaceError(f"presentation must be one of: {', '.join(FORMATS)}")
        validate_presentation(presentation)
        if contract.operation == "repository_intelligence_query":
            kwargs["presentation"] = presentation
        result = dict(operation(*args, **kwargs))
        contract.validate_response(
            result,
            result_mode=response_mode,
            presentation=presentation
            if contract.operation == "repository_intelligence_query"
            else "none",
        )
        if contract.operation != "repository_intelligence_query":
            result = presentation_response(
                contract.operation,
                result,
                format=presentation,
                result_mode=response_mode,
            )
    except McpSurfaceError as exc:
        raise tool_error(exc.transport_message()) from exc
    return contract.validate_response(
        result, result_mode=response_mode, presentation=presentation
    )


def _register_repository_declarations_tool(
    server: MCPServer,
    surface: HashmarksMcpSurface,
    annotations: ToolAnnotations,
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
        presentation: _Presentation = "none",
        source_selection: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        return _call_surface(
            contract,
            tool_error,
            surface.repository_declarations,
            groups,
            previous_observation=previous_observation,
            result_mode=result_mode,
            response_mode=result_mode,
            presentation=presentation,
            **(
                {"source_selection": source_selection}
                if source_selection is not None
                else {}
            ),
        )


def _set_query_surface_annotation(
    handler: Callable[..., object], surfaces: tuple[str, ...] | list[str]
) -> None:
    if not TYPE_CHECKING:
        handler.__annotations__["surface_name"] = Literal.__getitem__(tuple(surfaces))


def _register_agent_evidence_tools(
    server: MCPServer,
    surface: HashmarksMcpSurface,
    annotations: ToolAnnotations,
    tool_error: type[Exception],
    query_surfaces: tuple[str, ...] | list[str] | None = None,
) -> None:
    """Expose existing producers while keeping MCP registration bounded."""
    intelligence_contract = tool_contract("repository_intelligence_query")
    selected_surfaces = QUERY_SURFACES if query_surfaces is None else query_surfaces

    query_description = intelligence_contract.description
    if query_surfaces is not None and query_surfaces != tuple(QUERY_SURFACES):
        query_description += (
            " This server projection permits only these surfaces: "
            + ", ".join(query_surfaces)
            + "."
        )

    def repository_intelligence_query(  # noqa: PLR0913 - explicit MCP query inputs
        surface_name: _QuerySurface,
        task: str,
        changed_paths: list[str] | None = None,
        profile: _Profile = "compact",
        presentation: _Presentation = "compact",
        member_path: str | None = None,
        previous_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        if surface_name not in selected_surfaces:
            error = McpSurfaceError(
                "repository_intelligence_query surface is unavailable in this "
                "server projection: " + str(surface_name)
            )
            raise tool_error(error.transport_message())
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

    # MCP derives the public input schema from this annotation. A projected
    # server must advertise the same allowlist enforced by the handler rather
    # than the complete canonical Literal used by an unprojected server.
    _set_query_surface_annotation(repository_intelligence_query, selected_surfaces)
    server.tool(
        name=intelligence_contract.name,
        description=query_description,
        annotations=annotations,
    )(repository_intelligence_query)

    source_contract = tool_contract("source_observation")

    @server.tool(
        name=source_contract.name,
        description=source_contract.description,
        annotations=annotations,
    )
    def source_observation(  # noqa: PLR0913 - stable selectors and explicit source byte bounds
        paths: list[str],
        literal: str | list[str] | None = None,
        result_mode: _SourceObservationResultMode = source_contract.default_response_mode,
        limit: _SourceInteger = 50,
        context_lines: int | dict[str, object] = 0,
        presentation: _Presentation = "none",
        *,
        byte_range: dict[str, object] | None = None,
        max_bytes: _SourceInteger = 1_048_576,
    ) -> dict[str, object]:
        return _call_surface(
            source_contract,
            tool_error,
            surface.source_observation,
            paths,
            literal=literal if isinstance(literal, str) else None,
            literals=literal if isinstance(literal, list) else None,
            result_mode=result_mode,
            response_mode=result_mode,
            limit=limit,
            context_lines=context_lines,
            byte_range=byte_range,
            max_bytes=max_bytes,
            presentation=presentation,
        )

    binding_contract = tool_contract("repository_evidence")

    @server.tool(
        name=binding_contract.name,
        description=binding_contract.description,
        annotations=annotations,
    )
    def repository_evidence(
        request: dict[str, Any],
        result_mode: _RepositoryEvidenceResultMode = binding_contract.default_response_mode,
        presentation: _Presentation = "none",
    ) -> dict[str, object]:
        return _call_surface(
            binding_contract,
            tool_error,
            surface.repository_evidence,
            request,
            result_mode=result_mode,
            response_mode=result_mode,
            presentation=presentation,
        )

    findings_contract = tool_contract("repository_findings")

    @server.tool(
        name=findings_contract.name,
        description=findings_contract.description,
        annotations=annotations,
    )
    def repository_findings(
        paths: list[str] | None = None, presentation: _Presentation = "none"
    ) -> dict[str, object]:
        return _call_surface(
            findings_contract,
            tool_error,
            surface.repository_findings,
            paths,
            presentation=presentation,
        )

    locality_contract = tool_contract("structural_locality")

    @server.tool(
        name=locality_contract.name,
        description=locality_contract.description,
        annotations=annotations,
    )
    def structural_locality(
        target: str,
        max_depth: int = 2,
        presentation: _Presentation = "none",
        result_mode: Literal["default", "relationships"] = "default",
        supplied_observations: list[dict[str, Any]] | None = None,
    ) -> dict[str, object]:
        return _call_surface(
            locality_contract,
            tool_error,
            surface.structural_locality,
            target,
            max_depth=max_depth,
            result_mode=result_mode,
            supplied_observations=supplied_observations,
            response_mode=result_mode,
            presentation=presentation,
        )


def _register_evidence_comparison_tool(
    server: MCPServer,
    surface: HashmarksMcpSurface,
    annotations: ToolAnnotations,
    tool_error: type[Exception],
) -> None:
    """Expose native two-endpoint comparisons with no history or execution state."""
    contract = tool_contract("evidence_comparison")

    @server.tool(
        name=contract.name,
        description=contract.description,
        annotations=annotations,
    )
    def evidence_comparison(  # noqa: PLR0913 - explicit diagnostic qualification inputs
        before: dict[str, Any],
        after: dict[str, Any],
        result_mode: _EvidenceComparisonResultMode = contract.default_response_mode,
        changed_paths: list[str] | None = None,
        change_set_complete: bool = False,
        relationship_evidence: dict[str, Any] | None = None,
        before_source: dict[str, Any] | None = None,
        after_source: dict[str, Any] | None = None,
        presentation: _Presentation = "none",
    ) -> dict[str, object]:
        return _call_surface(
            contract,
            tool_error,
            surface.evidence_comparison,
            before,
            after,
            result_mode=result_mode,
            response_mode=result_mode,
            changed_paths=changed_paths,
            change_set_complete=change_set_complete,
            relationship_evidence=relationship_evidence,
            before_source=before_source,
            after_source=after_source,
            presentation=presentation,
        )


def _apply_tool_projection(server: MCPServer, selected_tools: tuple[str, ...]) -> None:
    selected = set(selected_tools)
    for name in MCP_TOOL_NAMES:
        if name not in selected:
            server.remove_tool(name)


def _server_projection_selection(
    tool_names: tuple[str, ...] | list[str] | None,
    query_surfaces: tuple[str, ...] | list[str] | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    selected_tools = normalize_mcp_tool_names(tool_names)
    selected_query_surfaces = normalize_mcp_query_surfaces(query_surfaces)
    if (
        query_surfaces is not None
        and "repository_intelligence_query" not in selected_tools
    ):
        raise ValueError(
            "repository_intelligence_query surface projection requires "
            "repository_intelligence_query to be exposed"
        )
    return selected_tools, selected_query_surfaces


def build_server(
    workspace: str | Path = ".",
    *,
    state_dir: str | Path | None = None,
    tool_names: tuple[str, ...] | list[str] | None = None,
    query_surfaces: tuple[str, ...] | list[str] | None = None,
) -> MCPServer:
    _server_type, ToolAnnotations, ToolError = _sdk()
    from .mcp_sdk_server import McpServerBinding, create_sdk_server

    selected_tools, selected_query_surfaces = _server_projection_selection(
        tool_names,
        query_surfaces,
    )
    surface = HashmarksMcpSurface(
        str(workspace), state_dir=None if state_dir is None else str(state_dir)
    )
    server = create_sdk_server(
        MCP_SERVER_NAME,
        description=MCP_SERVER_DESCRIPTION,
        instructions=mcp_projection_instructions(
            selected_tools,
            query_surfaces=query_surfaces,
        ),
        version=__version__,
        binding=McpServerBinding(
            surface, selected_tools, selected_query_surfaces, query_surfaces is not None
        ),
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
    def repository_context(
        max_areas: int = 12, presentation: _Presentation = "none"
    ) -> dict[str, object]:
        return _call_surface(
            repository_context_contract,
            ToolError,
            surface.repository_context,
            max_areas=max_areas,
            presentation=presentation,
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
        presentation: _Presentation = "none",
    ) -> dict[str, object]:
        return _call_surface(
            find_contract,
            ToolError,
            surface.find,
            query,
            limit=limit,
            presentation=presentation,
        )

    task_evidence_contract = tool_contract("task_evidence")

    def task_evidence(  # noqa: PLR0913 - preserve explicit MCP inputs with disclosure mode
        task: str,
        *,
        limit: int = TASK_EVIDENCE_DEFAULT_OPTIONS.limit,
        per_role: int = TASK_EVIDENCE_DEFAULT_OPTIONS.per_role,
        token_budget: int = TASK_EVIDENCE_DEFAULT_OPTIONS.token_budget,
        presentation: _Presentation = "none",
        supplied_observations: list[dict[str, Any]] | None = None,
        result_mode: _TaskEvidenceResultMode = task_evidence_contract.default_response_mode,
    ) -> CallToolResult:
        result = _call_surface(
            task_evidence_contract,
            ToolError,
            surface.task_evidence,
            task,
            limit=limit,
            per_role=per_role,
            token_budget=token_budget,
            supplied_observations=supplied_observations,
            result_mode=result_mode,
            response_mode=result_mode,
            presentation=presentation,
        )
        return _task_evidence_tool_result(result, result_mode, presentation)

    _register_json_mirror_tool(
        server, task_evidence_contract, annotations, task_evidence
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
        changed_line_spans: list[dict[str, object]] | None = None,
        presentation: _Presentation = "none",
    ) -> dict[str, object]:
        return _call_surface(
            change_impact_contract,
            ToolError,
            surface.change_impact,
            task,
            changed_paths,
            max_depth=max_depth,
            changed_line_spans=changed_line_spans,
            presentation=presentation,
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
        presentation: _Presentation = "none",
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
            presentation=presentation,
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
        presentation: _Presentation = "none",
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
            presentation=presentation,
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
        presentation: _Presentation = "none",
    ) -> dict[str, object]:
        return _call_surface(
            post_change_contract,
            ToolError,
            surface.post_change,
            task,
            changed_paths,
            previous_evidence,
            token_budget=token_budget,
            presentation=presentation,
        )

    _register_agent_evidence_tools(
        server,
        surface,
        annotations,
        ToolError,
        query_surfaces=selected_query_surfaces,
    )
    _register_evidence_comparison_tool(server, surface, annotations, ToolError)

    _apply_tool_projection(server, selected_tools)

    return server


def run_stdio(
    workspace: str | Path = ".",
    *,
    state_dir: str | Path | None = None,
    tool_names: tuple[str, ...] | list[str] | None = None,
    query_surfaces: tuple[str, ...] | list[str] | None = None,
) -> None:
    server = build_server(
        workspace,
        state_dir=state_dir,
        tool_names=tool_names,
        query_surfaces=query_surfaces,
    )
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
    parser.add_argument(
        "--tool",
        action="append",
        choices=MCP_TOOL_NAMES,
        default=None,
        help="repeat to expose only the selected canonical MCP tools",
    )
    parser.add_argument(
        "--query-surface",
        action="append",
        choices=QUERY_SURFACES,
        default=None,
        help=(
            "repeat to restrict repository_intelligence_query to selected "
            "canonical query surfaces"
        ),
    )
    args = parser.parse_args(argv)
    workspace = canonical_host_path(args.workspace)
    state_dir = None if args.state_dir is None else canonical_host_path(args.state_dir)
    try:
        run_stdio(
            workspace,
            state_dir=state_dir,
            tool_names=args.tool,
            query_surfaces=args.query_surface,
        )
    except (UserFacingError, McpSurfaceError) as exc:
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
