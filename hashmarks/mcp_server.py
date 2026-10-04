from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Any, Literal, TypeVar

from .errors import OptionalFeatureError, UserFacingError
from .mcp_surface import HashmarksMcpSurface, McpSurfaceError
from .paths import canonical_host_path

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_INSTALL_HINT = (
    'Hashmarks MCP support requires the optional extra: pip install "hashmarks[mcp]"'
)

_SERVER_INSTRUCTIONS = (
    "Hashmarks is read-only repository intelligence. For a task describing behavior "
    "without a unique known implementation path, call task_evidence before the first "
    "exploratory grep, glob, or read. This includes read-only questions asking which "
    "function implements a behavior. Use its bounded candidates, ambiguity, freshness, "
    "and next-read evidence to choose targeted native reads; retrieval ranking is "
    "evidence, not ownership authority. Read a unique known path directly. For a known "
    "exact symbol whose path is unknown, use find. "
    "After explicit changed paths exist, use change_impact or post_change when relevant. "
    "Hashmarks does not replace editing, shell, tests, or git."
)

_T = TypeVar("_T")

McpTransport = Literal["stdio", "streamable-http"]
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_DEFAULT_HTTP_HOST = "127.0.0.1"
_DEFAULT_HTTP_PORT = 8000
_DEFAULT_HTTP_PATH = "/mcp"


def add_transport_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help=(
            "stdio is the local subprocess transport; streamable-http serves the "
            "same read-only MCP surface on loopback for a secure tunnel or local client"
        ),
    )
    parser.add_argument("--host", default=_DEFAULT_HTTP_HOST)
    parser.add_argument("--port", type=int, default=_DEFAULT_HTTP_PORT)
    parser.add_argument("--path", default=_DEFAULT_HTTP_PATH)


def _validate_streamable_http(
    *, host: str, port: int, path: str
) -> tuple[str, int, str]:
    if host not in _LOOPBACK_HOSTS:
        raise UserFacingError(
            "Hashmarks streamable HTTP is loopback-only; use 127.0.0.1, ::1, "
            "or localhost and place an authenticated/tunneled boundary in front "
            "of Hashmarks when remote access is required"
        )
    if not 1 <= port <= 65535:
        raise UserFacingError("MCP HTTP port must be between 1 and 65535")
    if (
        not path.startswith("/")
        or path.startswith("//")
        or "?" in path
        or "#" in path
        or any(character.isspace() for character in path)
    ):
        raise UserFacingError(
            "MCP HTTP path must be one absolute URL path without query, fragment, "
            "whitespace, or a leading //"
        )
    return host, port, path


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


def _register_repository_declarations_tool(
    server: Any,
    surface: HashmarksMcpSurface,
    annotations: Any,
    tool_error: type[Exception],
) -> None:
    @server.tool(
        name="repository_declarations",
        description=(
            "Project correlated repository declarations as observation or explanation "
            "while preserving provenance, ambiguity, coverage, and freshness."
        ),
        annotations=annotations,
    )
    def repository_declarations(
        groups: list[dict[str, Any]],
        previous_observation: dict[str, Any] | None = None,
        result_mode: str = "observation",
    ) -> dict[str, object]:
        return _call_surface(
            tool_error,
            surface.repository_declarations,
            groups,
            previous_observation=previous_observation,
            result_mode=result_mode,
        )


def build_server(workspace: str | Path = ".", *, state_dir: str | Path | None = None):
    MCPServer, ToolAnnotations, ToolError = _sdk()
    surface = HashmarksMcpSurface(
        str(workspace), state_dir=None if state_dir is None else str(state_dir)
    )
    server = MCPServer(
        "Hashmarks",
        description="Read-only repository intelligence for coding agents",
        instructions=_SERVER_INSTRUCTIONS,
    )
    annotations = ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )

    @server.tool(
        name="repository_context",
        description=(
            "Use only for initial repository orientation: freshness, languages, areas, "
            "and topology. For a coding task needing ownership, edit, verification, or "
            "next-read evidence, use task_evidence instead."
        ),
        annotations=annotations,
    )
    def repository_context(max_areas: int = 12) -> dict[str, object]:
        return _call_surface(ToolError, surface.repository_context, max_areas=max_areas)

    @server.tool(
        name="find",
        description=(
            "Look up a known exact path or symbol. If the task only describes behavior "
            "and its implementation path is unknown, call task_evidence first."
        ),
        annotations=annotations,
    )
    def find(query: str, limit: int = 20) -> dict[str, object]:
        return _call_surface(ToolError, surface.find, query, limit=limit)

    @server.tool(
        name="task_evidence",
        description=(
            "First discovery tool for a behavior description with unknown implementation "
            "path. Call before exploratory grep, glob, or read, including read-only "
            "'which function?' tasks. Returns bounded candidates and next reads."
        ),
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
        description=(
            "Use after explicit changed paths exist for bounded structural impact and "
            "verification relevance. For pre-edit evidence, use task_evidence."
        ),
        annotations=annotations,
    )
    def change_impact(
        task: str, changed_paths: list[str], max_depth: int = 4
    ) -> dict[str, object]:
        return _call_surface(
            ToolError, surface.change_impact, task, changed_paths, max_depth=max_depth
        )

    @server.tool(
        name="correlate_evidence",
        description="Correlate bounded external or derived observations to repository evidence while preserving ambiguity, provenance, completeness, and source equivalence.",
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
        description=(
            "Project dependency evidence as observation, explanation, or explicit "
            "endpoint comparison without executing a package manager."
        ),
        annotations=annotations,
    )
    def dependency_codemap(
        snapshot: dict[str, object],
        queries: list[dict[str, object]] | None = None,
        previous_observation: dict[str, object] | None = None,
        result_mode: str = "observation",
    ) -> dict[str, object]:
        return _call_surface(
            ToolError,
            surface.dependency_codemap,
            snapshot,
            queries,
            previous_observation=previous_observation,
            result_mode=result_mode,
        )

    _register_repository_declarations_tool(server, surface, annotations, ToolError)

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


def run_server(
    workspace: str | Path = ".",
    *,
    state_dir: str | Path | None = None,
    transport: McpTransport = "stdio",
    host: str = _DEFAULT_HTTP_HOST,
    port: int = _DEFAULT_HTTP_PORT,
    path: str = _DEFAULT_HTTP_PATH,
) -> None:
    if transport == "streamable-http":
        host, port, path = _validate_streamable_http(
            host=host,
            port=port,
            path=path,
        )
    elif transport != "stdio":
        raise UserFacingError(f"unsupported MCP transport: {transport}")

    server = build_server(workspace, state_dir=state_dir)
    try:
        if transport == "stdio":
            server.run(transport="stdio")
            return
        server.run(
            transport="streamable-http",
            host=host,
            port=port,
            streamable_http_path=path,
            json_response=True,
            stateless_http=True,
        )
    finally:
        surface = getattr(server, "_hashmarks_surface", None)
        if surface is not None:
            surface.close()


def run_stdio(
    workspace: str | Path = ".", *, state_dir: str | Path | None = None
) -> None:
    run_server(workspace, state_dir=state_dir, transport="stdio")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="hashmarks mcp",
        description=(
            "Serve one Hashmarks workspace over local MCP stdio or loopback "
            "Streamable HTTP"
        ),
    )
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--state-dir", default=None)
    add_transport_arguments(parser)
    args = parser.parse_args(argv)
    workspace = canonical_host_path(args.workspace)
    state_dir = None if args.state_dir is None else canonical_host_path(args.state_dir)
    try:
        run_server(
            workspace,
            state_dir=state_dir,
            transport=args.transport,
            host=args.host,
            port=args.port,
            path=args.path,
        )
    except (UserFacingError, McpSurfaceError) as exc:
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
