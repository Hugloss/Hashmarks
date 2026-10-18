"""Lazy native SDK construction with Hashmarks-owned inspection metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server import MCPServer

    from .mcp_surface import HashmarksMcpSurface


@dataclass(frozen=True)
class McpServerBinding:
    surface: HashmarksMcpSurface
    tools: tuple[str, ...]
    query_surfaces: tuple[str, ...]
    query_projection_explicit: bool


def create_sdk_server(
    name: str,
    *,
    description: str,
    instructions: str,
    version: str,
    binding: McpServerBinding,
) -> MCPServer:
    from mcp.server import MCPServer

    class BoundMcpServer(MCPServer):
        _hashmarks_surface: HashmarksMcpSurface
        _hashmarks_projection_tools: tuple[str, ...]
        _hashmarks_projection_query_surfaces: tuple[str, ...]
        _hashmarks_query_surface_projection_explicit: bool

    server = BoundMcpServer(
        name, description=description, instructions=instructions, version=version
    )
    server._hashmarks_surface = binding.surface
    server._hashmarks_projection_tools = binding.tools
    server._hashmarks_projection_query_surfaces = binding.query_surfaces
    server._hashmarks_query_surface_projection_explicit = (
        binding.query_projection_explicit
    )
    return server


def close_sdk_server(server: MCPServer) -> None:
    """Close the repository surface owned by a Hashmarks-built native server."""
    from .mcp_surface import HashmarksMcpSurface

    surface = getattr(server, "_hashmarks_surface", None)
    if not isinstance(surface, HashmarksMcpSurface):
        raise RuntimeError("native MCP server has no Hashmarks surface binding")
    surface.close()
