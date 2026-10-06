from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from typing import TYPE_CHECKING

import pytest

from hashmarks._version import __version__
from hashmarks.codemap.evidence_packet import TASK_EVIDENCE_DEFAULT_OPTIONS
from hashmarks.codemap.find_engine import FIND_DEFAULT_OPTIONS
from hashmarks.mcp_contract import (
    MCP_SERVER_INSTRUCTIONS,
    MCP_SERVER_NAME,
    MCP_TOOL_NAMES,
    contract_from_tool_models,
    tool_description,
)
from hashmarks.operation_contract import operation_default_mode, operation_modes

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.host_mcp_sdk

_MCP_AVAILABLE = importlib.util.find_spec("mcp") is not None
_NATIVE_REASON = "Hashmarks MCP interop requires the optional mcp extra"
_EXPECTED_TOOLS = list(MCP_TOOL_NAMES)


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


def _assert_canonical_result_mode_schemas(
    schemas: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    dependency = schemas["dependency_codemap"]["properties"]["result_mode"]
    declarations = schemas["repository_declarations"]["properties"]["result_mode"]
    assert dependency["enum"] == list(operation_modes("dependency_codemap"))
    assert dependency["default"] == operation_default_mode("dependency_codemap")
    assert declarations["enum"] == list(operation_modes("repository_declarations"))
    assert declarations["default"] == operation_default_mode("repository_declarations")
    return schemas


def _assert_find_defaults(
    schemas: dict[str, dict[str, object]],
) -> None:
    assert (
        schemas["find"]["properties"]["limit"]["default"] == FIND_DEFAULT_OPTIONS.limit
    )


def _assert_task_evidence_defaults(
    schemas: dict[str, dict[str, object]],
) -> None:
    defaults = TASK_EVIDENCE_DEFAULT_OPTIONS
    task_properties = schemas["task_evidence"]["properties"]
    assert task_properties["limit"]["default"] == defaults.limit
    assert task_properties["per_role"]["default"] == defaults.per_role
    assert task_properties["token_budget"]["default"] == defaults.token_budget
    assert (
        schemas["post_change"]["properties"]["token_budget"]["default"]
        == defaults.token_budget
    )


@pytest.mark.skipif(not _MCP_AVAILABLE, reason=_NATIVE_REASON)
def test_mcp_native_server_catalog_and_structured_call(tmp_path: Path) -> None:
    from hashmarks.mcp_server import build_server

    server = build_server(_repo(tmp_path), state_dir=tmp_path / "state")

    async def exercise() -> None:
        tools = await server.list_tools()
        assert [tool.name for tool in tools] == _EXPECTED_TOOLS
        descriptions = {tool.name: tool.description or "" for tool in tools}
        assert descriptions == {name: tool_description(name) for name in MCP_TOOL_NAMES}
        manifest = contract_from_tool_models(__version__, tools)
        identity = manifest["contract_identity"]
        contract_tools = manifest["tools"]
        assert isinstance(identity, str)
        assert isinstance(contract_tools, list)
        assert manifest["schema"] == "hashmarks.mcp-contract.v1"
        assert identity.startswith("sha256:")
        assert all(isinstance(row, dict) for row in contract_tools)
        assert [
            row["name"] for row in contract_tools if isinstance(row, dict)
        ] == _EXPECTED_TOOLS
        task_description = descriptions["task_evidence"]
        for phrase in (
            "Semantic first choice",
            "exploratory grep/read",
            "retrieval from ownership",
            "owner/ambiguity",
            "source/next-read",
            "verification",
            "freshness",
        ):
            assert phrase in task_description
        schemas = _assert_canonical_result_mode_schemas(
            {tool.name: tool.input_schema for tool in tools}
        )
        assert schemas["task_evidence"]["required"] == ["task"]
        assert schemas["find"]["required"] == ["query"]
        assert schemas["change_impact"]["required"] == ["task", "changed_paths"]
        _assert_find_defaults(schemas)
        _assert_task_evidence_defaults(schemas)
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
                assert initialized.server_info.name == MCP_SERVER_NAME
                assert initialized.server_info.version == __version__
                assert initialized.instructions == MCP_SERVER_INSTRUCTIONS

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
                assert result.structured_content["schema"] == "hashmarks.find.v2"
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
                payload_start = text.index("{")
                payload, _ = json.JSONDecoder().raw_decode(text[payload_start:])
                assert payload == {
                    "schema": "hashmarks.mcp-error.v1",
                    "reason": "invalid-request",
                    "message": "query must not be empty",
                    "recovery_authority": "consumer-owned",
                }

    asyncio.run(exercise())
