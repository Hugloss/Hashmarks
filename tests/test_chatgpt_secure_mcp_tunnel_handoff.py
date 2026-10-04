from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from scripts.host_qualification.chatgpt_secure_mcp_tunnel_handoff import (
    EXPECTED_TOOLS,
    _command_argv,
    _observe_mcp,
    _validate_observation,
    build_handoff,
)
from scripts.mcp_host_gate_common import HostGateError

_MCP_AVAILABLE = importlib.util.find_spec("mcp") is not None


def _observation() -> dict[str, object]:
    annotations = {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
    return {
        "protocol_version": "2026-07-28",
        "server": {
            "name": "Hashmarks",
            "version": "0.26.1",
            "instructions": (
                "For unknown behavior call task_evidence before the first "
                "exploratory grep, glob, or read."
            ),
        },
        "tools": [
            {
                "name": name,
                "description": f"{name} description",
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "annotations": annotations,
            }
            for name in EXPECTED_TOOLS
        ],
    }


def test_handoff_command_is_exact_workspace_bound_stdio(tmp_path: Path) -> None:
    executable = tmp_path / "bin" / "hashmarks"
    workspace = tmp_path / "repo"
    state = workspace / ".state"
    assert _command_argv(executable, workspace, None) == [
        str(executable),
        "--workspace",
        str(workspace),
        "mcp",
    ]
    assert _command_argv(executable, workspace, state) == [
        str(executable),
        "--workspace",
        str(workspace),
        "--state-dir",
        str(state),
        "mcp",
    ]


def test_handoff_receipt_preserves_external_tunnel_authority(tmp_path: Path) -> None:
    executable = tmp_path / "hashmarks"
    executable.write_bytes(b"candidate")
    workspace = tmp_path / "repo"
    workspace.mkdir()
    with (
        mock.patch(
            "scripts.host_qualification.chatgpt_secure_mcp_tunnel_handoff.run",
            return_value=SimpleNamespace(stdout="hashmarks version 0.26.1\n"),
        ),
        mock.patch(
            "scripts.host_qualification.chatgpt_secure_mcp_tunnel_handoff.sha256",
            return_value="a" * 64,
        ),
        mock.patch(
            "scripts.host_qualification.chatgpt_secure_mcp_tunnel_handoff.completed_at",
            return_value="2026-10-04T15:00:00Z",
        ),
    ):
        receipt = build_handoff(
            executable=executable,
            workspace=workspace,
            state_dir=None,
            source={
                "root": "/source",
                "repository_content_identity": "sha256:" + "b" * 64 + ":10",
            },
            observation=_observation(),
        )

    assert receipt["status"] == "READY"
    assert receipt["authority"] == {
        "hashmarks_transport": "stdio",
        "remote_transport_owner": "openai-secure-mcp-tunnel",
        "chatgpt_configuration_owner": "external",
        "credentials_owner": "external",
    }
    assert receipt["mcp_command_argv"] == [
        str(executable),
        "--workspace",
        str(workspace),
        "mcp",
    ]
    assert receipt["hashmarks"]["executable_sha256"] == "a" * 64
    assert receipt["source"]["repository_content_identity"].startswith("sha256:")
    assert receipt["mcp"]["tools"][0]["name"] == "repository_context"


def test_handoff_rejects_cli_mcp_version_split_brain(tmp_path: Path) -> None:
    executable = tmp_path / "hashmarks"
    executable.write_bytes(b"candidate")
    workspace = tmp_path / "repo"
    workspace.mkdir()
    observation = _observation()
    observation["server"]["version"] = "0.25.0"
    with mock.patch(
        "scripts.host_qualification.chatgpt_secure_mcp_tunnel_handoff.run",
        return_value=SimpleNamespace(stdout="hashmarks version 0.26.1\n"),
    ), mock.patch(
        "scripts.host_qualification.chatgpt_secure_mcp_tunnel_handoff.sha256",
        return_value="a" * 64,
    ):
        with pytest.raises(HostGateError, match="CLI/MCP version authority differs"):
            build_handoff(
                executable=executable,
                workspace=workspace,
                state_dir=None,
                source=None,
                observation=observation,
            )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda value: value["server"].update({"name": "Other"}),
            "did not initialize the Hashmarks server",
        ),
        (
            lambda value: value["server"].update({"instructions": "generic"}),
            "routing instructions",
        ),
        (
            lambda value: value["tools"].pop(),
            "tool catalog differs",
        ),
        (
            lambda value: value["tools"][0]["annotations"].update(
                {"readOnlyHint": False}
            ),
            "annotations are not read-only",
        ),
    ],
)
def test_handoff_rejects_unqualified_catalog(
    mutation,
    message: str,
) -> None:
    value = _observation()
    mutation(value)
    with pytest.raises(HostGateError, match=message):
        _validate_observation(value)


@pytest.mark.host_mcp_sdk
@pytest.mark.skipif(not _MCP_AVAILABLE, reason="MCP extra is not installed")
def test_native_handoff_observes_project_stdio_catalog(tmp_path: Path) -> None:
    suffix = ".exe" if sys.platform == "win32" else ""
    executable = Path(sys.executable).parent / f"hashmarks{suffix}"
    if not executable.is_file():
        pytest.skip("project Hashmarks console script is not installed")

    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "owner.py").write_text(
        "def owner() -> int:\n    return 1\n",
        encoding="utf-8",
    )
    observation = asyncio.run(_observe_mcp(executable, workspace, None))
    _validate_observation(observation)

    assert observation["server"]["name"] == "Hashmarks"
    assert tuple(row["name"] for row in observation["tools"]) == EXPECTED_TOOLS
