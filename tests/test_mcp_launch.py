from __future__ import annotations

import json
import tomllib
from pathlib import Path

from hashmarks.mcp_launch import installed_mcp_command, mcp_server_args, source_mcp_command

ROOT = Path(__file__).resolve().parents[1]


def test_mcp_launch_owner_resolves_source_and_installed_commands() -> None:
    workspace = Path("/workspace")
    executable = Path("/opt/hashmarks/bin/hashmarks")
    state = workspace / ".state"

    assert installed_mcp_command(executable, workspace) == (
        str(executable),
        "--workspace",
        str(workspace),
        "mcp",
    )
    assert installed_mcp_command(executable, workspace, state_dir=state) == (
        str(executable),
        "--workspace",
        str(workspace),
        "--state-dir",
        str(state),
        "mcp",
    )
    assert source_mcp_command(".") == (
        "uv",
        "run",
        "--frozen",
        "--no-sync",
        "hashmarks",
        "--workspace",
        ".",
        "mcp",
    )


def test_checked_in_host_configs_are_exact_source_launch_projections() -> None:
    expected = list(source_mcp_command("."))

    opencode = json.loads((ROOT / "opencode.json").read_text(encoding="utf-8"))
    assert opencode["mcp"]["hashmarks"]["command"] == expected

    shared = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    shared_entry = shared["mcpServers"]["hashmarks"]
    assert [shared_entry["command"], *shared_entry["args"]] == expected

    codex = tomllib.loads((ROOT / ".codex" / "config.toml").read_text(encoding="utf-8"))
    codex_entry = codex["mcp_servers"]["hashmarks"]
    assert [codex_entry["command"], *codex_entry["args"]] == expected


def test_mcp_launch_consumers_do_not_reconstruct_launch_semantics() -> None:
    consumers = {
        "hashmarks/cli.py": "installed_mcp_command",
        "hashmarks/opencode_registration.py": "mcp_server_args",
        "scripts/mcp_host_status.py": "source_mcp_command",
        "scripts/host_qualification/opencode_mcp_host_gate.py": "installed_mcp_command",
        "scripts/host_qualification/claude_mcp_host_gate.py": "installed_mcp_command",
        "scripts/host_qualification/codex_mcp_host_gate.py": "installed_mcp_command",
        "scripts/host_qualification/pi_mcp_host_gate.py": "installed_mcp_command",
        "scripts/host_qualification/chatgpt_secure_mcp_tunnel_handoff.py": (
            "installed_mcp_command"
        ),
    }
    stale_owners = (
        '["--workspace", ".", "mcp"]',
        '["--workspace", str(repo), "mcp"]',
        'argv = [str(executable), "--workspace", str(workspace)]',
        "EXPECTED_UV_ARGS",
    )

    for relative, owner in consumers.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert owner in text
        for stale in stale_owners:
            assert stale not in text


def test_mcp_launch_can_project_tools_without_changing_default() -> None:
    assert mcp_server_args(
        "/workspace",
        tool_names=("task_evidence",),
    ) == (
        "--workspace",
        "/workspace",
        "mcp",
        "--tool",
        "task_evidence",
    )
