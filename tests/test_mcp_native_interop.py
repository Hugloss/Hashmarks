from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.host_mcp_sdk

_MCP_AVAILABLE = importlib.util.find_spec("mcp") is not None
_NATIVE_REASON = "Hashmarks MCP interop requires the optional mcp extra"
_EXPECTED_TOOLS = [
    "repository_context",
    "find",
    "task_evidence",
    "change_impact",
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

                prompts = await session.list_prompts()
                resources = await session.list_resources()
                assert prompts.prompts == []
                assert resources.resources == []

                tools = await session.list_tools()
                assert [tool.name for tool in tools.tools] == _EXPECTED_TOOLS

                result = await session.call_tool("find", arguments={"query": "flare041", "limit": 5})
                assert result.is_error is not True
                assert result.structured_content is not None
                assert result.structured_content["schema"] == "hashmarks.mcp-find.v1"
                assert any(row["path"] == "src/feature.py" for row in result.structured_content["results"])

                invalid = await session.call_tool("find", arguments={"query": "", "limit": 5})
                assert invalid.is_error is True
                text = "\n".join(getattr(block, "text", "") for block in invalid.content)
                assert "query must not be empty" in text
                assert "Traceback" not in text

    asyncio.run(exercise())
