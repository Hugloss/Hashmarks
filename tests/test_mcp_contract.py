from __future__ import annotations

import copy

import pytest

from hashmarks.mcp_contract import (
    MCP_BASIC_HOST_QUALIFICATION_TOOLS,
    MCP_READ_ONLY_ANNOTATIONS,
    MCP_SERVER_INSTRUCTIONS,
    MCP_SERVER_NAME,
    MCP_TOOL_CONTRACTS,
    MCP_TOOL_NAMES,
    contract_summary,
    qualify_mcp_observation,
    qualification_response_schemas,
)


def _observation() -> dict[str, object]:
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
    assert first["schema"] == "hashmarks.mcp-contract.v1"
    assert first["contract_identity"].startswith("sha256:")
    assert first["server"]["name"] == MCP_SERVER_NAME
    assert first["server"]["version"] == "0.26.1"
    assert [row["name"] for row in first["tools"]] == list(MCP_TOOL_NAMES)
    assert first["tools"][5]["response_schemas"] == [
        "hashmarks.mcp-dependency-codemap.v1",
        "hashmarks.dependency-resolution-explain.v1",
        "hashmarks.dependency-resolution-delta.v3",
    ]

    summary = contract_summary(first)
    assert summary == {
        "schema": "hashmarks.mcp-contract.v1",
        "contract_identity": first["contract_identity"],
        "server_version": "0.26.1",
        "tools": list(MCP_TOOL_NAMES),
    }


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


def test_host_schema_expectations_derive_from_canonical_contract() -> None:
    plain = qualification_response_schemas(MCP_BASIC_HOST_QUALIFICATION_TOOLS)
    proxy = qualification_response_schemas(
        MCP_BASIC_HOST_QUALIFICATION_TOOLS,
        name_prefix="hashmarks_",
    )

    assert plain == {
        "repository_context": "hashmarks.repository-capsule.v1",
        "find": "hashmarks.mcp-find.v1",
    }
    assert proxy == {
        "hashmarks_repository_context": "hashmarks.repository-capsule.v1",
        "hashmarks_find": "hashmarks.mcp-find.v1",
    }
