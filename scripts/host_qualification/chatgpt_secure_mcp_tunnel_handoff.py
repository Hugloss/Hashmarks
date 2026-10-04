from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from hashmarks._command_output import log_command_output

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from mcp_host_gate_common import (  # noqa: E402 - standalone script path setup
    HostGateError,
    completed_at,
    run,
    sha256,
    venv_executable,
)

logger = logging.getLogger(__name__)

EXPECTED_TOOLS = (
    "repository_context",
    "find",
    "task_evidence",
    "change_impact",
    "correlate_evidence",
    "dependency_codemap",
    "repository_declarations",
    "post_change",
)


def _command_argv(
    executable: Path,
    workspace: Path,
    state_dir: Path | None,
) -> list[str]:
    argv = [str(executable), "--workspace", str(workspace)]
    if state_dir is not None:
        argv.extend(("--state-dir", str(state_dir)))
    argv.append("mcp")
    return argv


def _command_text(argv: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(argv)
    return shlex.join(argv)


def _source_binding(
    executable: Path,
    source_root: Path | None,
    *,
    workspace: Path,
) -> dict[str, str] | None:
    if source_root is None:
        return None
    python = venv_executable(executable.parent.parent, "python")
    if not python.is_file():
        raise HostGateError(
            "source-root binding requires a Hashmarks virtual-environment executable "
            "with an adjacent Python interpreter"
        )
    code = (
        "from pathlib import Path; import hashmarks; "
        "print(Path(hashmarks.__file__).resolve().parents[1])"
    )
    imported_root = Path(
        run([str(python), "-I", "-c", code], cwd=workspace).stdout.strip()
    ).resolve()
    source_root = source_root.resolve()
    if imported_root != source_root:
        raise HostGateError(
            "Hashmarks executable imports a different source root: "
            f"expected {source_root}, got {imported_root}"
        )
    from hashmarks.test_shards import repository_content_identity

    excluded = (source_root / "dist",)
    before = repository_content_identity(
        source_root,
        excluded_paths=excluded,
    )
    after = repository_content_identity(
        source_root,
        excluded_paths=excluded,
    )
    if before != after:
        raise HostGateError(
            "Hashmarks source changed during handoff identity observation"
        )
    return {
        "root": str(source_root),
        "repository_content_identity": before,
    }


def _implementation_identity(
    executable: Path,
    source_root: Path | None,
    *,
    workspace: Path,
) -> dict[str, object]:
    try:
        before_sha256 = sha256(executable)
        version = run([str(executable), "--version"], cwd=workspace).stdout.strip()
        source = _source_binding(
            executable,
            source_root,
            workspace=workspace,
        )
        after_sha256 = sha256(executable)
    except OSError as exc:
        raise HostGateError(
            f"Hashmarks implementation identity became unreadable: {exc}"
        ) from exc
    if before_sha256 != after_sha256:
        raise HostGateError(
            "Hashmarks executable changed during handoff identity observation"
        )
    if not version.startswith("hashmarks version "):
        raise HostGateError(f"unexpected Hashmarks version output: {version!r}")
    return {
        "executable": str(executable),
        "executable_sha256": before_sha256,
        "version": version,
        "source": source,
    }


def _json_model(value: object | None) -> object | None:
    if value is None:
        return None
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json", by_alias=True)
    return value


async def _observe_mcp(
    executable: Path,
    workspace: Path,
    state_dir: Path | None,
) -> dict[str, Any]:
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError as exc:
        raise HostGateError(
            "ChatGPT tunnel handoff requires the MCP extra: uv sync --frozen --extra mcp"
        ) from exc

    command = _command_argv(executable, workspace, state_dir)
    params = StdioServerParameters(command=command[0], args=command[1:])
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                tools = await session.list_tools()
    except Exception as exc:
        raise HostGateError(
            f"Hashmarks stdio MCP command could not initialize: {exc}"
        ) from exc

    catalog = []
    for tool in tools.tools:
        catalog.append(
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "output_schema": tool.output_schema,
                "annotations": _json_model(tool.annotations),
            }
        )
    return {
        "protocol_version": str(initialized.protocol_version),
        "server": {
            "name": initialized.server_info.name,
            "version": initialized.server_info.version,
            "instructions": initialized.instructions,
        },
        "tools": catalog,
    }


def _validate_observation(observation: dict[str, Any]) -> None:
    server = observation.get("server")
    if not isinstance(server, dict) or server.get("name") != "Hashmarks":
        raise HostGateError("MCP handoff did not initialize the Hashmarks server")
    instructions = server.get("instructions")
    if not isinstance(instructions, str) or (
        "call task_evidence before exploratory" not in instructions
        or "supporting retrieval from ownership authority" not in instructions
        or "unique known path" not in instructions
    ):
        raise HostGateError(
            "Hashmarks MCP routing instructions are unavailable or stale"
        )
    tools = observation.get("tools")
    if not isinstance(tools, list):
        raise HostGateError("Hashmarks MCP tool catalog is unavailable")
    names = tuple(str(row.get("name")) for row in tools if isinstance(row, dict))
    if names != EXPECTED_TOOLS:
        raise HostGateError(
            "Hashmarks MCP tool catalog differs from the tunnel handoff contract: "
            f"{names!r}"
        )
    for row in tools:
        if not isinstance(row, dict):
            raise HostGateError("Hashmarks MCP catalog contains a malformed tool")
        annotations = row.get("annotations")
        if not isinstance(annotations, dict) or (
            annotations.get("readOnlyHint") is not True
            or annotations.get("destructiveHint") is not False
            or annotations.get("idempotentHint") is not True
            or annotations.get("openWorldHint") is not False
        ):
            raise HostGateError(
                f"Hashmarks MCP tool annotations are not read-only: {row.get('name')}"
            )


def build_handoff(
    *,
    executable: Path,
    workspace: Path,
    state_dir: Path | None,
    implementation: dict[str, object],
    observation: dict[str, Any],
) -> dict[str, Any]:
    _validate_observation(observation)
    command = _command_argv(executable, workspace, state_dir)
    version = implementation.get("version")
    if not isinstance(version, str) or not version.startswith("hashmarks version "):
        raise HostGateError("qualified Hashmarks implementation version is unavailable")
    expected_server_version = version.removeprefix("hashmarks version ")
    server = observation.get("server")
    server_version = server.get("version") if isinstance(server, dict) else None
    if server_version != expected_server_version:
        raise HostGateError(
            "Hashmarks CLI/MCP version authority differs: "
            f"cli={expected_server_version!r} mcp={server_version!r}"
        )
    return {
        "schema": "hashmarks.chatgpt-secure-mcp-tunnel-handoff.v1",
        "status": "READY",
        "completed_at": completed_at(),
        "authority": {
            "hashmarks_transport": "stdio",
            "remote_transport_owner": "openai-secure-mcp-tunnel",
            "chatgpt_configuration_owner": "external",
            "credentials_owner": "external",
        },
        "workspace": str(workspace),
        "state_dir": None if state_dir is None else str(state_dir),
        "source": implementation.get("source"),
        "hashmarks": {
            "executable": implementation.get("executable"),
            "executable_sha256": implementation.get("executable_sha256"),
            "version": version,
        },
        "mcp_command_argv": command,
        "mcp_command": _command_text(command),
        "mcp": observation,
    }


async def qualify_handoff(
    *,
    executable: Path,
    workspace: Path,
    state_dir: Path | None,
    source_root: Path | None,
) -> dict[str, Any]:
    before = _implementation_identity(
        executable,
        source_root,
        workspace=workspace,
    )
    observation = await _observe_mcp(executable, workspace, state_dir)
    after = _implementation_identity(
        executable,
        source_root,
        workspace=workspace,
    )
    if before != after:
        raise HostGateError(
            "Hashmarks implementation changed while MCP handoff was being qualified"
        )
    return build_handoff(
        executable=executable,
        workspace=workspace,
        state_dir=state_dir,
        implementation=before,
        observation=observation,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Qualify one exact local Hashmarks stdio MCP command for handoff to "
            "OpenAI Secure MCP Tunnel without creating or mutating the tunnel."
        )
    )
    parser.add_argument("--hashmarks", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--state-dir")
    parser.add_argument(
        "--source-root",
        help=(
            "optional clean/source-managed Hashmarks root to bind when the executable "
            "is a virtual-environment console script"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("dist/chatgpt-secure-mcp-tunnel-handoff.json"),
    )
    args = parser.parse_args(argv)

    executable = Path(args.hashmarks).expanduser().resolve()
    workspace = Path(args.workspace).expanduser().resolve()
    if not executable.is_file():
        raise SystemExit(f"Hashmarks executable does not exist: {executable}")
    if not workspace.is_dir():
        raise SystemExit(f"Hashmarks workspace does not exist: {workspace}")
    state_dir = None
    if args.state_dir is not None:
        state_dir = Path(args.state_dir).expanduser()
        if not state_dir.is_absolute():
            state_dir = workspace / state_dir
        state_dir = state_dir.resolve()
    source_root = (
        None
        if args.source_root is None
        else Path(args.source_root).expanduser().resolve()
    )
    if source_root is not None and not source_root.is_dir():
        raise SystemExit(f"Hashmarks source root does not exist: {source_root}")

    try:
        receipt = asyncio.run(
            qualify_handoff(
                executable=executable,
                workspace=workspace,
                state_dir=state_dir,
                source_root=source_root,
            )
        )
    except HostGateError as exc:
        raise SystemExit(f"ChatGPT MCP tunnel handoff unavailable: {exc}") from exc

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    log_command_output(logger, str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
