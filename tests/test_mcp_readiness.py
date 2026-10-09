from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import hashmarks.cli as cli
import hashmarks.mcp_readiness as readiness
from hashmarks.mcp_contract import MCP_TOOL_NAMES
from hashmarks.mcp_readiness import MCP_READINESS_SCHEMA, mcp_readiness


def test_native_server_advertises_restricted_query_surface(
    tmp_path: Path,
) -> None:
    from hashmarks.mcp_server import build_server

    server = build_server(
        tmp_path,
        tool_names=("repository_intelligence_query",),
        query_surfaces=("verification-explanation",),
    )
    try:
        tools = asyncio.run(server.list_tools())
        assert [tool.name for tool in tools] == ["repository_intelligence_query"]
        assert "verification-explanation" in str(tools[0].description)
        assert server._hashmarks_projection_query_surfaces == (
            "verification-explanation",
        )
        assert server._hashmarks_query_surface_projection_explicit is True
    finally:
        server._hashmarks_surface.close()


def test_mcp_readiness_projects_contract_and_launch(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = workspace / ".state"
    monkeypatch.setattr(
        readiness,
        "current_contract_summary",
        lambda _workspace, *, state_dir=None: {
            "schema": "hashmarks.mcp-contract.v1",
            "contract_identity": "sha256:contract",
            "server_version": "0.test",
            "tools": list(MCP_TOOL_NAMES),
            "operation_contract_identity": "sha256:operations",
            "error_schema": "hashmarks.mcp-error.v1",
            "error_reasons": [],
            "error_recovery_authority": "consumer-owned",
        },
    )

    async def observed(*_args, **_kwargs):
        return MCP_TOOL_NAMES

    monkeypatch.setattr(readiness, "_observed_projection_tools", observed)

    result = mcp_readiness(workspace, state_dir=state)

    assert result == {
        "schema": MCP_READINESS_SCHEMA,
        "ready": True,
        "authority": "diagnostic-only",
        "consumer_verification_required": True,
        "workspace": str(workspace.resolve()),
        "transport": "stdio",
        "read_only": True,
        "server_version": "0.test",
        "contract_identity": "sha256:contract",
        "operation_contract_identity": "sha256:operations",
        "tool_count": len(MCP_TOOL_NAMES),
        "tools": list(MCP_TOOL_NAMES),
        "repository_intelligence_query_surfaces": [
            "change-intelligence",
            "verification-explanation",
            "freshness",
            "snapshot",
            "profile",
            "delta",
            "cross-repository",
            "economics",
        ],
        "launch": {
            "args": [
                "--workspace",
                str(workspace.resolve()),
                "--state-dir",
                str(state.resolve()),
                "mcp",
            ],
            "state_dir": str(state.resolve()),
        },
    }


def test_doctor_mcp_is_opt_in_and_machine_readable(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    class Identity:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def doctor(self) -> dict[str, object]:
            return {"identity": "ready"}

    monkeypatch.setattr(cli, "RepositoryIdentity", Identity)
    monkeypatch.setattr(
        readiness,
        "mcp_readiness",
        lambda *_args, **_kwargs: {
            "schema": MCP_READINESS_SCHEMA,
            "ready": True,
        },
    )

    args = argparse.Namespace(
        workspace=tmp_path,
        state_dir=None,
        mode="auto",
        timeout=1.0,
        mcp=True,
        mcp_tool=None,
    )
    assert cli._doctor(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "identity": "ready",
        "mcp": {
            "schema": MCP_READINESS_SCHEMA,
            "ready": True,
        },
    }


def test_mcp_readiness_qualifies_explicit_tool_projection(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    canonical = {
        "schema": "hashmarks.mcp-contract.v1",
        "contract_identity": "sha256:contract",
        "server_version": "0.test",
        "tools": list(MCP_TOOL_NAMES),
        "operation_contract_identity": "sha256:operations",
        "error_schema": "hashmarks.mcp-error.v1",
        "error_reasons": [],
        "error_recovery_authority": "consumer-owned",
    }
    monkeypatch.setattr(
        readiness,
        "current_contract_summary",
        lambda *_args, **_kwargs: canonical,
    )

    async def observed(*_args, **_kwargs):
        return ("task_evidence",)

    monkeypatch.setattr(readiness, "_observed_projection_tools", observed)

    result = mcp_readiness(
        workspace,
        tool_names=("task_evidence",),
    )

    assert result["ready"] is True
    assert result["tools"] == list(MCP_TOOL_NAMES)
    assert result["projection"]["tools"] == ["task_evidence"]
    assert result["projection"]["observed_tools"] == ["task_evidence"]
    assert str(result["projection"]["projection_identity"]).startswith("sha256:")
    assert result["launch"]["args"][-3:] == [
        "mcp",
        "--tool",
        "task_evidence",
    ]


def test_mcp_readiness_qualifies_query_surface_projection(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    canonical = {
        "schema": "hashmarks.mcp-contract.v1",
        "contract_identity": "sha256:contract",
        "server_version": "0.test",
        "tools": list(MCP_TOOL_NAMES),
        "operation_contract_identity": "sha256:operations",
        "error_schema": "hashmarks.mcp-error.v1",
        "error_reasons": [],
        "error_recovery_authority": "consumer-owned",
    }
    monkeypatch.setattr(
        readiness,
        "current_contract_summary",
        lambda *_args, **_kwargs: canonical,
    )

    async def observed_tools(*_args, **_kwargs):
        return ("repository_intelligence_query",)

    async def observed_surfaces(*_args, **_kwargs):
        return ("verification-explanation",)

    monkeypatch.setattr(
        readiness,
        "_observed_projection_tools",
        observed_tools,
    )
    monkeypatch.setattr(
        readiness,
        "_observed_projection_query_surfaces",
        observed_surfaces,
    )

    result = mcp_readiness(
        workspace,
        tool_names=("repository_intelligence_query",),
        query_surfaces=("verification-explanation",),
    )

    projection = result["projection"]
    assert result["ready"] is True
    assert projection["tools"] == ["repository_intelligence_query"]
    assert projection["repository_intelligence_query_surfaces"] == [
        "verification-explanation"
    ]
    assert projection["observed_repository_intelligence_query_surfaces"] == [
        "verification-explanation"
    ]
    assert result["launch"]["args"][-5:] == [
        "mcp",
        "--tool",
        "repository_intelligence_query",
        "--query-surface",
        "verification-explanation",
    ]


def test_mcp_readiness_fails_closed_on_query_surface_observation_drift(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    canonical = {
        "schema": "hashmarks.mcp-contract.v1",
        "contract_identity": "sha256:contract",
        "server_version": "0.test",
        "tools": list(MCP_TOOL_NAMES),
        "operation_contract_identity": "sha256:operations",
        "error_schema": "hashmarks.mcp-error.v1",
        "error_reasons": [],
        "error_recovery_authority": "consumer-owned",
    }
    monkeypatch.setattr(
        readiness,
        "current_contract_summary",
        lambda *_args, **_kwargs: canonical,
    )

    async def observed_tools(*_args, **_kwargs):
        return ("repository_intelligence_query",)

    async def observed_surfaces(*_args, **_kwargs):
        return ("freshness",)

    monkeypatch.setattr(
        readiness,
        "_observed_projection_tools",
        observed_tools,
    )
    monkeypatch.setattr(
        readiness,
        "_observed_projection_query_surfaces",
        observed_surfaces,
    )

    result = mcp_readiness(
        workspace,
        tool_names=("repository_intelligence_query",),
        query_surfaces=("verification-explanation",),
    )

    assert result["ready"] is False
    assert result["projection"]["observed_repository_intelligence_query_surfaces"] == [
        "freshness"
    ]


def test_doctor_parser_exposes_mcp_projection_tools() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    cli._add_identity_cli(sub)

    parsed = parser.parse_args(["doctor", "--mcp", "--mcp-tool", "task_evidence"])

    assert parsed.mcp is True
    assert parsed.mcp_tool == ["task_evidence"]


def test_doctor_parser_exposes_mcp_query_surface_projection() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    cli._add_identity_cli(sub)

    parsed = parser.parse_args(
        [
            "doctor",
            "--mcp",
            "--mcp-tool",
            "repository_intelligence_query",
            "--mcp-query-surface",
            "verification-explanation",
        ]
    )

    assert parsed.mcp is True
    assert parsed.mcp_tool == ["repository_intelligence_query"]
    assert parsed.mcp_query_surface == ["verification-explanation"]


def test_doctor_parser_exposes_explicit_mcp_probe() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    cli._add_identity_cli(sub)

    plain = parser.parse_args(["doctor"])
    probed = parser.parse_args(["doctor", "--mcp"])

    assert plain.mcp is False
    assert probed.mcp is True
