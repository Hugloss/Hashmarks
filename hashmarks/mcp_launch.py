"""Canonical Hashmarks stdio MCP launch semantics."""

from __future__ import annotations

from pathlib import Path

SOURCE_MCP_PREFIX = ("uv", "run", "--frozen", "--no-sync", "hashmarks")


def mcp_server_args(
    workspace: str | Path,
    *,
    state_dir: str | Path | None = None,
    tool_names: tuple[str, ...] | list[str] | None = None,
) -> tuple[str, ...]:
    args = ["--workspace", str(workspace)]
    if state_dir is not None:
        args.extend(("--state-dir", str(state_dir)))
    args.append("mcp")
    for name in tool_names or ():
        args.extend(("--tool", str(name)))
    return tuple(args)


def installed_mcp_command(
    executable: str | Path,
    workspace: str | Path,
    *,
    state_dir: str | Path | None = None,
) -> tuple[str, ...]:
    return (
        str(executable),
        *mcp_server_args(workspace, state_dir=state_dir),
    )


def source_mcp_command(
    workspace: str | Path = ".",
) -> tuple[str, ...]:
    return (
        *SOURCE_MCP_PREFIX,
        *mcp_server_args(workspace),
    )
