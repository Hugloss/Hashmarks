from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from hashmarks.mcp_contract import (
    MCP_BASIC_HOST_QUALIFICATION_TOOLS,
    MCP_ERROR_REASONS,
    MCP_ERROR_SCHEMA,
    MCP_READ_ONLY_ANNOTATIONS,
    MCP_SERVER_INSTRUCTIONS,
    MCP_SERVER_NAME,
    MCP_TOOL_CONTRACTS,
    MCP_TOOL_NAMES,
    contract_summary,
    qualification_response_schemas,
    qualify_mcp_observation,
    response_schema_for_mode,
    tool_contract,
    validate_tool_response,
)

ROOT = Path(__file__).resolve().parents[1]


def _observation() -> dict[str, Any]:
    return {
        "server": {
            "name": MCP_SERVER_NAME,
            "version": "0.26.1",
            "instructions": MCP_SERVER_INSTRUCTIONS,
        },
        "tools": [
            {
                "name": contract.name,
                "description": contract.description,
                "input_schema": {
                    "type": "object",
                    "properties": {"fixture": {"type": "string"}},
                },
                "output_schema": {"type": "object"},
                "annotations": dict(MCP_READ_ONLY_ANNOTATIONS),
            }
            for contract in MCP_TOOL_CONTRACTS
        ],
    }


def test_mcp_contract_manifest_is_deterministic_and_complete() -> None:
    first = qualify_mcp_observation(_observation())
    second = qualify_mcp_observation(copy.deepcopy(_observation()))

    assert first == second
    identity = first["contract_identity"]
    server = first["server"]
    tools = first["tools"]
    operation_contract = first["operation_contract"]
    assert isinstance(identity, str)
    assert isinstance(server, dict)
    assert isinstance(tools, list)
    assert isinstance(operation_contract, dict)
    assert first["schema"] == "hashmarks.mcp-contract.v1"
    assert operation_contract["schema"] == "hashmarks.operation-contract.v1"
    assert str(operation_contract["contract_identity"]).startswith("sha256:")
    assert first["errors"] == {
        "schema": MCP_ERROR_SCHEMA,
        "reasons": list(MCP_ERROR_REASONS),
        "recovery_authority": "consumer-owned",
    }
    assert identity.startswith("sha256:")
    assert server["name"] == MCP_SERVER_NAME
    assert server["version"] == "0.26.1"
    assert all(isinstance(row, dict) for row in tools)
    tool_rows = [row for row in tools if isinstance(row, dict)]
    assert [row["name"] for row in tool_rows] == list(MCP_TOOL_NAMES)
    assert tool_rows[5]["response_schemas"] == [
        "hashmarks.dependency-codemap.v1",
        "hashmarks.dependency-resolution-explain.v1",
        "hashmarks.dependency-resolution-delta.v3",
    ]
    assert tool_rows[5]["response_modes"] == {
        "observation": "hashmarks.dependency-codemap.v1",
        "explain": "hashmarks.dependency-resolution-explain.v1",
        "compare": "hashmarks.dependency-resolution-delta.v3",
    }
    assert tool_rows[7]["response_modes"] == {
        "default": "hashmarks.task-post-change-delta.v2"
    }

    summary = contract_summary(first)
    assert summary == {
        "schema": "hashmarks.mcp-contract.v1",
        "contract_identity": identity,
        "server_version": "0.26.1",
        "tools": list(MCP_TOOL_NAMES),
        "operation_contract_identity": operation_contract["contract_identity"],
        "error_schema": MCP_ERROR_SCHEMA,
        "error_reasons": list(MCP_ERROR_REASONS),
        "error_recovery_authority": "consumer-owned",
    }


def test_mcp_contract_summary_rejects_tampered_manifest() -> None:
    manifest = qualify_mcp_observation(_observation())
    server = manifest["server"]
    assert isinstance(server, dict)
    server["version"] = "forged"

    with pytest.raises(ValueError, match="contract identity mismatch"):
        contract_summary(manifest)


def test_mcp_contract_identity_binds_wire_schema_and_server_version() -> None:
    original = qualify_mcp_observation(_observation())

    changed_schema = _observation()
    changed_schema["tools"][0]["input_schema"]["properties"]["fixture"] = {
        "type": "integer"
    }
    schema_manifest = qualify_mcp_observation(changed_schema)

    changed_version = _observation()
    changed_version["server"]["version"] = "0.26.2"
    version_manifest = qualify_mcp_observation(changed_version)

    assert schema_manifest["contract_identity"] != original["contract_identity"]
    assert version_manifest["contract_identity"] != original["contract_identity"]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda value: value["tools"].reverse(),
            "tool catalog differs",
        ),
        (
            lambda value: value["tools"][0].update({"description": "drifted"}),
            "tool description differs",
        ),
        (
            lambda value: value["tools"][0].update({"output_schema": None}),
            "output schema is unavailable",
        ),
        (
            lambda value: value["tools"][0]["annotations"].update(
                {"openWorldHint": True}
            ),
            "annotations are not read-only",
        ),
    ],
)
def test_mcp_contract_rejects_independent_catalog_drift(
    mutation,
    message: str,
) -> None:
    observation = _observation()
    mutation(observation)
    with pytest.raises(ValueError, match=message):
        qualify_mcp_observation(observation)


def test_response_schema_authority_is_mode_specific() -> None:
    assert response_schema_for_mode("find") == "hashmarks.find.v2"
    assert (
        response_schema_for_mode("dependency_codemap", "observation")
        == "hashmarks.dependency-codemap.v1"
    )
    assert (
        response_schema_for_mode("dependency_codemap", "explain")
        == "hashmarks.dependency-resolution-explain.v1"
    )
    assert (
        response_schema_for_mode("dependency_codemap", "compare")
        == "hashmarks.dependency-resolution-delta.v3"
    )
    assert (
        response_schema_for_mode("repository_declarations", "explain")
        == "hashmarks.repository-declaration-explain.v1"
    )
    assert (
        response_schema_for_mode("post_change") == "hashmarks.task-post-change-delta.v2"
    )


def test_response_schema_authority_rejects_runtime_drift() -> None:
    packet = {"schema": "hashmarks.task-post-change-delta.v2", "change": "unchanged"}
    assert validate_tool_response("post_change", packet) is packet

    with pytest.raises(RuntimeError, match="response schema drift"):
        validate_tool_response(
            "post_change",
            {"schema": "hashmarks.task-post-change-delta.v1"},
        )
    with pytest.raises(RuntimeError, match="response schema drift"):
        validate_tool_response(
            "dependency_codemap",
            {"schema": "hashmarks.dependency-resolution-explain.v1"},
            result_mode="compare",
        )
    with pytest.raises(RuntimeError, match="non-object response"):
        validate_tool_response("find", ["not", "an", "object"])


def test_tool_contract_owns_response_validation() -> None:
    contract = tool_contract("post_change")
    packet = {"schema": "hashmarks.task-post-change-delta.v2"}
    assert contract.validate_response(packet) is packet

    with pytest.raises(RuntimeError, match="response schema drift"):
        contract.validate_response({"schema": "hashmarks.task-post-change-delta.v1"})


def test_mcp_server_consumes_one_contract_object_per_tool() -> None:
    source = (ROOT / "hashmarks" / "mcp_server.py").read_text(encoding="utf-8")

    assert "tool_description(" not in source
    assert "validate_tool_response(" not in source
    for name in MCP_TOOL_NAMES:
        assert source.count(f'tool_contract("{name}")') == 1
        assert f'name="{name}"' not in source
        assert f'_call_surface("{name}"' not in source


def test_host_schema_expectations_derive_from_canonical_contract() -> None:
    plain = qualification_response_schemas(MCP_BASIC_HOST_QUALIFICATION_TOOLS)
    proxy = qualification_response_schemas(
        MCP_BASIC_HOST_QUALIFICATION_TOOLS,
        name_prefix="hashmarks_",
    )

    assert plain == {
        "repository_context": "hashmarks.repository-capsule.v1",
        "find": "hashmarks.find.v2",
    }
    assert proxy == {
        "hashmarks_repository_context": "hashmarks.repository-capsule.v1",
        "hashmarks_find": "hashmarks.find.v2",
    }
