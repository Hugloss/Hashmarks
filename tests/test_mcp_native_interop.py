from __future__ import annotations

import asyncio
import importlib.util
import socket
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.host_mcp_sdk

_MCP_AVAILABLE = importlib.util.find_spec("mcp") is not None
_NATIVE_REASON = "Hashmarks MCP interop requires the optional mcp extra"
_EXPECTED_TOOLS = [
    "repository_context",
    "find",
    "task_evidence",
    "change_impact",
    "correlate_evidence",
    "dependency_codemap",
    "repository_declarations",
    "post_change",
]


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src" / "feature.py").write_text(
        "def flare041(value: int) -> int:\n    return value + 1\n", encoding="utf-8"
    )
    (repo / "tests" / "test_feature.py").write_text(
        "from src.feature import flare041\n\ndef test_flare041():\n    assert flare041(1) == 2\n",
        encoding="utf-8",
    )
    return repo


@pytest.mark.skipif(not _MCP_AVAILABLE, reason=_NATIVE_REASON)
def test_mcp_native_server_catalog_and_structured_call(tmp_path: Path) -> None:
    from hashmarks.mcp_server import build_server

    server = build_server(_repo(tmp_path), state_dir=tmp_path / "state")

    async def exercise() -> None:
        tools = await server.list_tools()
        assert [tool.name for tool in tools] == _EXPECTED_TOOLS
        descriptions = {tool.name: tool.description or "" for tool in tools}
        selection_contract = {
            "repository_context": (
                "Use only for initial repository orientation: freshness, languages, areas, "
                "and topology. For a coding task needing ownership, edit, verification, or "
                "next-read evidence, use task_evidence instead."
            ),
            "find": (
                "Look up a known exact path or symbol. If the task only describes behavior "
                "and its implementation path is unknown, call task_evidence first."
            ),
            "task_evidence": (
                "First discovery tool for a behavior description with unknown implementation "
                "path. Call before exploratory grep, glob, or read, including read-only "
                "'which function?' tasks. Returns bounded candidates and next reads."
            ),
            "change_impact": (
                "Use after explicit changed paths exist for bounded structural impact and "
                "verification relevance. For pre-edit evidence, use task_evidence."
            ),
            "post_change": (
                "Refresh caller-reported changed paths against a previous task_evidence "
                "packet and return only invalidated/reused/replacement evidence."
            ),
        }
        assert {
            name: descriptions[name] for name in selection_contract
        } == selection_contract
        schemas = {tool.name: tool.input_schema for tool in tools}
        assert schemas["task_evidence"]["required"] == ["task"]
        assert schemas["find"]["required"] == ["query"]
        assert schemas["change_impact"]["required"] == ["task", "changed_paths"]
        assert schemas["task_evidence"]["properties"]["limit"]["default"] == 20
        assert schemas["task_evidence"]["properties"]["per_role"]["default"] == 3
        assert schemas["task_evidence"]["properties"]["token_budget"]["default"] == 1536
        for tool in tools:
            assert tool.annotations is not None
            assert tool.annotations.read_only_hint is True
            assert tool.annotations.destructive_hint is False
            assert tool.annotations.idempotent_hint is True
            assert tool.annotations.open_world_hint is False
            assert tool.output_schema is not None

        result = await server.call_tool("repository_context", {})
        assert result.is_error is not True
        assert result.structured_content is not None
        assert result.structured_content["schema"] == "hashmarks.repository-capsule.v1"

    try:
        asyncio.run(exercise())
    finally:
        server._hashmarks_surface.close()


@pytest.mark.skipif(not _MCP_AVAILABLE, reason=_NATIVE_REASON)
def test_mcp_native_stdio_initialize_catalog_call_and_error(tmp_path: Path) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    repo = _repo(tmp_path)
    state = tmp_path / "stdio-state"

    async def exercise() -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "hashmarks.mcp_server",
                "--workspace",
                str(repo),
                "--state-dir",
                str(state),
            ],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                assert initialized.server_info.name == "Hashmarks"
                assert initialized.instructions is not None
                assert "call task_evidence before the first" in initialized.instructions
                assert "exploratory grep, glob, or read" in initialized.instructions

                prompts = await session.list_prompts()
                resources = await session.list_resources()
                assert prompts.prompts == []
                assert resources.resources == []

                tools = await session.list_tools()
                assert [tool.name for tool in tools.tools] == _EXPECTED_TOOLS

                result = await session.call_tool(
                    "find", arguments={"query": "flare041", "limit": 5}
                )
                assert result.is_error is not True
                assert result.structured_content is not None
                assert result.structured_content["schema"] == "hashmarks.mcp-find.v1"
                assert any(
                    row["path"] == "src/feature.py"
                    for row in result.structured_content["results"]
                )

                invalid = await session.call_tool(
                    "find", arguments={"query": "", "limit": 5}
                )
                assert invalid.is_error is True
                text = "\n".join(
                    getattr(block, "text", "") for block in invalid.content
                )
                assert "query must not be empty" in text
                assert "Traceback" not in text

    asyncio.run(exercise())


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@pytest.mark.skipif(not _MCP_AVAILABLE, reason=_NATIVE_REASON)
def test_mcp_native_streamable_http_initialize_catalog_and_call(tmp_path: Path) -> None:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    repo = _repo(tmp_path)
    state = tmp_path / "http-state"
    port = _free_loopback_port()
    endpoint = f"http://127.0.0.1:{port}/mcp"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "hashmarks.mcp_server",
            "--workspace",
            str(repo),
            "--state-dir",
            str(state),
            "--transport",
            "streamable-http",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--path",
            "/mcp",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    async def exercise() -> None:
        last_error: Exception | None = None
        for _ in range(100):
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                raise AssertionError(
                    "Hashmarks HTTP MCP exited before readiness: "
                    f"stdout={stdout!r} stderr={stderr!r}"
                )
            try:
                async with streamable_http_client(endpoint) as (read, write):
                    async with ClientSession(read, write) as session:
                        initialized = await session.initialize()
                        assert initialized.server_info.name == "Hashmarks"
                        assert initialized.instructions is not None
                        assert "call task_evidence before the first" in initialized.instructions

                        tools = await session.list_tools()
                        assert [tool.name for tool in tools.tools] == _EXPECTED_TOOLS

                        result = await session.call_tool(
                            "find",
                            arguments={"query": "flare041", "limit": 5},
                        )
                        assert result.is_error is not True
                        assert result.structured_content is not None
                        assert result.structured_content["schema"] == "hashmarks.mcp-find.v1"
                        assert any(
                            row["path"] == "src/feature.py"
                            for row in result.structured_content["results"]
                        )
                        return
            except Exception as exc:  # server startup is the only retried boundary
                last_error = exc
                await asyncio.sleep(0.05)
        raise AssertionError(f"Hashmarks HTTP MCP did not become ready: {last_error}")

    try:
        asyncio.run(exercise())
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
