"""Native OpenCode registration inspection.

OpenCode owns configuration and precedence. This module only asks OpenCode for its
resolved configuration and compares the effective Hashmarks MCP command with the
installed executable.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .mcp_launch import mcp_server_args
from .paths import canonical_host_path


def _hashmarks_command_from_config(
    config: object,
) -> tuple[list[str] | None, str | None]:
    if not isinstance(config, dict):
        return None, "opencode debug config did not return an object"
    mcp = config.get("mcp")
    if not isinstance(mcp, dict):
        return None, "effective OpenCode config has no MCP object"
    servers = mcp.get("servers")
    entries = servers if isinstance(servers, dict) else mcp
    hashmarks = entries.get("hashmarks")
    if not isinstance(hashmarks, dict):
        return None, "effective OpenCode config has no hashmarks MCP server"
    command = hashmarks.get("command")
    if not (
        isinstance(command, list)
        and command
        and all(isinstance(value, str) and value for value in command)
    ):
        return None, "effective OpenCode hashmarks MCP command is not inspectable"
    return list(command), None


def inspect_effective_hashmarks_command(
    opencode: str,
) -> tuple[list[str] | None, str | None]:
    result = subprocess.run(
        [opencode, "debug", "config"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None, f"opencode debug config exited {result.returncode}"
    try:
        config = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None, "opencode debug config did not return JSON"
    return _hashmarks_command_from_config(config)


def effective_command_uses_executable(
    command: list[str],
    executable: Path,
) -> bool:
    if command[1:] != list(mcp_server_args(".")):
        return False
    configured = command[0]
    resolved = (
        shutil.which(configured)
        if "/" not in configured and "\\" not in configured
        else configured
    )
    if resolved is None:
        return False
    try:
        return canonical_host_path(resolved).samefile(executable)
    except OSError:
        return False
