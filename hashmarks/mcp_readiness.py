from __future__ import annotations

import asyncio
from pathlib import Path

from .mcp_contract import (
    MCP_TOOL_NAMES,
    current_contract_summary,
    mcp_projection_summary,
    normalize_mcp_tool_names,
)
from .mcp_launch import mcp_server_args
from .paths import canonical_host_path

MCP_READINESS_SCHEMA = "hashmarks.mcp-readiness.v1"


async def _observed_projection_tools(
    workspace: Path,
    *,
    state_dir: Path | None,
    tool_names: tuple[str, ...],
) -> tuple[str, ...]:
    from .mcp_server import build_server

    server = build_server(
        workspace,
        state_dir=state_dir,
        tool_names=tool_names,
    )
    try:
        tools = await server.list_tools()
        return tuple(str(tool.name) for tool in tools)
    finally:
        server._hashmarks_surface.close()


def mcp_readiness(
    workspace: str | Path,
    *,
    state_dir: str | Path | None = None,
    tool_names: tuple[str, ...] | list[str] | None = None,
) -> dict[str, object]:
    """Describe the local stdio MCP surface without claiming consumer admission.

    This is a product diagnostic for hosts and external benchmark harnesses.  A
    consumer must still independently prove executable identity, workspace
    binding, and the observed MCP catalog before treating a run as admitted.
    """

    workspace_path = canonical_host_path(workspace)
    resolved_state: Path | None = None
    if state_dir is not None:
        candidate = Path(state_dir)
        if not candidate.is_absolute():
            candidate = workspace_path / candidate
        resolved_state = canonical_host_path(candidate)

    summary = current_contract_summary(
        str(workspace_path),
        state_dir=None if resolved_state is None else str(resolved_state),
    )
    tools = summary.get("tools")
    normalized_tools = (
        tuple(str(value) for value in tools) if isinstance(tools, list) else ()
    )
    selected = normalize_mcp_tool_names(tool_names)
    observed = asyncio.run(
        _observed_projection_tools(
            workspace_path,
            state_dir=resolved_state,
            tool_names=selected,
        )
    )
    projection = (
        None
        if tool_names is None
        else {
            **mcp_projection_summary(summary, selected),
            "observed_tools": list(observed),
        }
    )
    ready = (
        normalized_tools == MCP_TOOL_NAMES
        and observed == selected
        and isinstance(summary.get("contract_identity"), str)
        and isinstance(summary.get("operation_contract_identity"), str)
        and isinstance(summary.get("server_version"), str)
    )
    return {
        "schema": MCP_READINESS_SCHEMA,
        "ready": ready,
        "authority": "diagnostic-only",
        "consumer_verification_required": True,
        "workspace": str(workspace_path),
        "transport": "stdio",
        "read_only": True,
        "server_version": summary.get("server_version"),
        "contract_identity": summary.get("contract_identity"),
        "operation_contract_identity": summary.get("operation_contract_identity"),
        "tool_count": len(normalized_tools),
        "tools": list(normalized_tools),
        "launch": {
            "args": list(
                mcp_server_args(
                    workspace_path,
                    state_dir=resolved_state,
                    tool_names=None if tool_names is None else selected,
                )
            ),
            "state_dir": None if resolved_state is None else str(resolved_state),
        },
        **({"projection": projection} if projection is not None else {}),
    }
