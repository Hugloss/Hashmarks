from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from dataclasses import dataclass
from typing import Any

from .operation_contract import (
    operation_contract_manifest,
    operation_default_mode,
    operation_modes,
    operation_schema,
    require_registered_operation,
    validate_operation_response,
)

MCP_CONTRACT_SCHEMA = "hashmarks.mcp-contract.v1"
MCP_ERROR_SCHEMA = "hashmarks.mcp-error.v1"
MCP_ERROR_REASONS = (
    "invalid-request",
    "stale-or-foreign-evidence",
    "continuity-mismatch",
    "unsupported-semantic",
    "transient-race-exhausted",
)
MCP_ERROR_RECOVERY_AUTHORITY = "consumer-owned"
MCP_SERVER_NAME = "Hashmarks"
MCP_SERVER_DESCRIPTION = (
    "Semantic read-only repository intelligence for behavior localization, "
    "ownership, impact, freshness, and verification evidence"
)
MCP_SERVER_INSTRUCTIONS = (
    "Hashmarks is the semantic repository-intelligence layer, not a text-search shortcut. "
    "For a task asking where behavior is implemented, which file or function owns it, "
    "what should be inspected next, or what verification is relevant when the exact "
    "implementation path is not already known, call task_evidence before exploratory "
    "grep, glob, or read. task_evidence can separate supporting retrieval from ownership "
    "authority, resolve a unique owner when admissible, preserve ambiguity when it cannot, "
    "return bounded source evidence or an exact next-read, select verification evidence "
    "and a verification plan, and report freshness. Prefer that semantic reduction over "
    "reconstructing ownership from repeated native search/read calls. Use native read for "
    "a unique known path or for the targeted next-read returned by Hashmarks. For a known "
    "exact symbol whose path is unknown, use find. After explicit changed paths exist, "
    "use change_impact or post_change when relevant. Caller-visible tool failures carry "
    "hashmarks.mcp-error.v1 JSON with consumer-owned recovery. Hashmarks does not replace "
    "editing, shell, tests, or git."
)
MCP_READ_ONLY_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}


@dataclass(frozen=True)
class McpToolContract:
    name: str
    description: str
    operation: str

    def __post_init__(self) -> None:
        require_registered_operation(self.operation)

    @property
    def response_modes(self) -> tuple[str, ...]:
        return tuple(operation_modes(self.operation))

    @property
    def response_schemas(self) -> tuple[str, ...]:
        return tuple(operation_modes(self.operation).values())

    @property
    def default_response_mode(self) -> str:
        return operation_default_mode(self.operation)

    @property
    def default_response_schema(self) -> str:
        return operation_schema(self.operation)

    def response_schema_for_mode(self, result_mode: str | None = None) -> str:
        return operation_schema(self.operation, result_mode)

    def validate_response(
        self,
        value: object,
        *,
        result_mode: str | None = None,
    ) -> dict[str, object]:
        return validate_operation_response(
            self.operation,
            value,
            mode=result_mode,
        )


MCP_TOOL_CONTRACTS = (
    McpToolContract(
        "repository_context",
        (
            "Broad orientation only: freshness, languages, areas, and topology. "
            "Do not use for behavior ownership; use task_evidence for owner, "
            "source/next-read, or verification evidence."
        ),
        "repository_context",
    ),
    McpToolContract(
        "find",
        (
            "Exact lookup for a path or symbol you already know by name. Do not use as a "
            "behavior-localization substitute: when the task describes behavior and the "
            "implementation path is unknown, use task_evidence first."
        ),
        "find",
    ),
    McpToolContract(
        "task_evidence",
        (
            "Semantic first choice for unknown-path behavior. Prefer before exploratory "
            "grep/read: separates retrieval from ownership, resolves owner/ambiguity, "
            "and returns source/next-read, verification, freshness."
        ),
        "task_evidence",
    ),
    McpToolContract(
        "change_impact",
        (
            "Use after explicit changed paths exist for bounded structural impact and "
            "verification relevance. For pre-edit evidence, use task_evidence."
        ),
        "change_impact",
    ),
    McpToolContract(
        "correlate_evidence",
        (
            "Correlate bounded external or derived observations to repository evidence "
            "while preserving ambiguity, provenance, completeness, and source equivalence."
        ),
        "correlate_evidence",
    ),
    McpToolContract(
        "dependency_codemap",
        (
            "Project dependency evidence as observation, explanation, or explicit "
            "endpoint comparison without executing a package manager."
        ),
        "dependency_codemap",
    ),
    McpToolContract(
        "repository_declarations",
        (
            "Project correlated repository declarations as observation or explanation "
            "while preserving provenance, ambiguity, coverage, and freshness."
        ),
        "repository_declarations",
    ),
    McpToolContract(
        "post_change",
        (
            "Refresh caller-reported changed paths against a previous task_evidence packet "
            "and return only invalidated/reused/replacement evidence."
        ),
        "post_change",
    ),
    McpToolContract(
        "repository_intelligence_query",
        (
            "Read-only bounded repository-intelligence facets: change description, "
            "profile, snapshot, delta, freshness, verification explanation, "
            "cross-repository and evidence economics. Previous snapshots are caller-supplied."
        ),
        "repository_intelligence_query",
    ),
    McpToolContract(
        "source_observation",
        (
            "Observe exact source occurrences for one member or an explicit bounded "
            "member set, with exact revisions, coverage and qualified absence."
        ),
        "source_observation",
    ),
    McpToolContract(
        "structural_locality",
        (
            "Observe bounded static calls, exact callers, unresolved targets, "
            "structural locality and related verifier paths for one exact symbol."
        ),
        "structural_locality",
    ),
)

MCP_TOOL_NAMES = tuple(contract.name for contract in MCP_TOOL_CONTRACTS)
MCP_BASIC_HOST_QUALIFICATION_TOOLS = ("repository_context", "find")
MCP_WORKFLOW_HOST_QUALIFICATION_TOOLS = (
    "repository_context",
    "find",
    "task_evidence",
    "change_impact",
    "post_change",
)
_TOOL_BY_NAME = {contract.name: contract for contract in MCP_TOOL_CONTRACTS}


def tool_contract(name: str) -> McpToolContract:
    try:
        return _TOOL_BY_NAME[name]
    except KeyError as exc:
        raise ValueError(f"unknown Hashmarks MCP tool: {name}") from exc


def default_response_schema(name: str) -> str:
    return tool_contract(name).default_response_schema


def response_schemas(name: str) -> tuple[str, ...]:
    return tool_contract(name).response_schemas


def response_schema_for_mode(name: str, result_mode: str | None = None) -> str:
    return tool_contract(name).response_schema_for_mode(result_mode)


def validate_tool_response(
    name: str,
    value: object,
    *,
    result_mode: str | None = None,
) -> dict[str, object]:
    return tool_contract(name).validate_response(
        value,
        result_mode=result_mode,
    )


def tool_description(name: str) -> str:
    return tool_contract(name).description


def qualification_response_schemas(
    names: tuple[str, ...],
    *,
    name_prefix: str = "",
) -> dict[str, str]:
    return {f"{name_prefix}{name}": default_response_schema(name) for name in names}


def _json_model(value: object | None) -> object | None:
    if value is None:
        return None
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json", by_alias=True)
    return value


def _canonical_annotations(value: object) -> dict[str, bool]:
    raw = _json_model(value)
    if not isinstance(raw, dict):
        raise ValueError("Hashmarks MCP tool annotations are unavailable")
    normalized = {key: raw.get(key) for key in MCP_READ_ONLY_ANNOTATIONS}
    if normalized != MCP_READ_ONLY_ANNOTATIONS:
        raise ValueError("Hashmarks MCP tool annotations are not read-only")
    return dict(MCP_READ_ONLY_ANNOTATIONS)


def _canonical_schema(value: object, *, label: str) -> dict[str, Any]:
    raw = _json_model(value)
    if not isinstance(raw, dict):
        raise ValueError(f"Hashmarks MCP {label} is unavailable")
    return raw


def _canonical_tool_input_schema(
    expected: McpToolContract,
    value: object,
) -> dict[str, Any]:
    schema = _canonical_schema(value, label=f"{expected.name} input schema")
    if len(expected.response_modes) <= 1:
        return schema

    properties = schema.get("properties")
    if not isinstance(properties, dict):
        raise ValueError(
            f"Hashmarks MCP {expected.name} result_mode schema is unavailable"
        )
    result_mode = properties.get("result_mode")
    if not isinstance(result_mode, dict):
        raise ValueError(
            f"Hashmarks MCP {expected.name} result_mode schema is unavailable"
        )
    if result_mode.get("enum") != list(expected.response_modes):
        raise ValueError(
            f"Hashmarks MCP {expected.name} result_mode enum differs from "
            "the operation contract"
        )
    if result_mode.get("default") != expected.default_response_mode:
        raise ValueError(
            f"Hashmarks MCP {expected.name} result_mode default differs from "
            "the operation contract"
        )
    required = schema.get("required", [])
    if isinstance(required, list) and "result_mode" in required:
        raise ValueError(
            f"Hashmarks MCP {expected.name} result_mode default is not omittable"
        )
    return schema


def _contract_identity(value: dict[str, object]) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    digest = hashlib.sha256(
        MCP_CONTRACT_SCHEMA.encode("utf-8") + b"\0" + encoded
    ).hexdigest()
    return f"sha256:{digest}"


def _qualified_server(observation: dict[str, Any]) -> str:
    server = observation.get("server")
    if not isinstance(server, dict) or server.get("name") != MCP_SERVER_NAME:
        raise ValueError("MCP observation did not initialize the Hashmarks server")
    version = server.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("Hashmarks MCP server version is unavailable")
    if server.get("instructions") != MCP_SERVER_INSTRUCTIONS:
        raise ValueError("Hashmarks MCP routing instructions differ from the contract")
    return version


def _qualified_tool(
    expected: McpToolContract,
    raw: object,
) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise ValueError("Hashmarks MCP catalog contains a malformed tool")
    if raw.get("description") != expected.description:
        raise ValueError(
            f"Hashmarks MCP tool description differs from the contract: {expected.name}"
        )
    return {
        "name": expected.name,
        "description": expected.description,
        "input_schema": _canonical_tool_input_schema(
            expected,
            raw.get("input_schema"),
        ),
        "output_schema": _canonical_schema(
            raw.get("output_schema"), label=f"{expected.name} output schema"
        ),
        "annotations": _canonical_annotations(raw.get("annotations")),
        "operation": expected.operation,
        "response_schemas": list(expected.response_schemas),
        "response_modes": operation_modes(expected.operation),
    }


def _qualified_tools(observation: dict[str, Any]) -> list[dict[str, object]]:
    raw_tools = observation.get("tools")
    if not isinstance(raw_tools, list):
        raise ValueError("Hashmarks MCP tool catalog is unavailable")
    names = tuple(str(row.get("name")) for row in raw_tools if isinstance(row, dict))
    if names != MCP_TOOL_NAMES:
        raise ValueError(
            f"Hashmarks MCP tool catalog differs from the contract: {names!r}"
        )
    if len(raw_tools) != len(MCP_TOOL_CONTRACTS):
        raise ValueError("Hashmarks MCP tool catalog contains malformed entries")
    return [
        _qualified_tool(expected, raw)
        for expected, raw in zip(MCP_TOOL_CONTRACTS, raw_tools, strict=True)
    ]


def qualify_mcp_observation(observation: dict[str, Any]) -> dict[str, object]:
    version = _qualified_server(observation)
    tools = _qualified_tools(observation)
    manifest: dict[str, object] = {
        "schema": MCP_CONTRACT_SCHEMA,
        "server": {
            "name": MCP_SERVER_NAME,
            "version": version,
            "description": MCP_SERVER_DESCRIPTION,
            "instructions": MCP_SERVER_INSTRUCTIONS,
        },
        "operation_contract": operation_contract_manifest(),
        "tools": tools,
        "errors": {
            "schema": MCP_ERROR_SCHEMA,
            "reasons": list(MCP_ERROR_REASONS),
            "recovery_authority": MCP_ERROR_RECOVERY_AUTHORITY,
        },
    }
    manifest["contract_identity"] = _contract_identity(manifest)
    return manifest


def contract_from_tool_models(
    version: str,
    tools: list[object] | tuple[object, ...],
) -> dict[str, object]:
    catalog: list[dict[str, object | None]] = []
    for tool in tools:
        catalog.append(
            {
                "name": getattr(tool, "name", None),
                "description": getattr(tool, "description", None),
                "input_schema": getattr(tool, "input_schema", None),
                "output_schema": getattr(tool, "output_schema", None),
                "annotations": getattr(tool, "annotations", None),
            }
        )
    return qualify_mcp_observation(
        {
            "server": {
                "name": MCP_SERVER_NAME,
                "version": version,
                "instructions": MCP_SERVER_INSTRUCTIONS,
            },
            "tools": catalog,
        }
    )


def contract_summary(manifest: dict[str, object]) -> dict[str, object]:
    server = manifest.get("server")
    tools = manifest.get("tools")
    operation_contract = manifest.get("operation_contract")
    errors = manifest.get("errors")
    identity = manifest.get("contract_identity")
    if manifest.get("schema") != MCP_CONTRACT_SCHEMA:
        raise ValueError("invalid Hashmarks MCP contract manifest")
    if not all(
        (
            isinstance(server, dict),
            isinstance(tools, list),
            isinstance(operation_contract, dict),
            isinstance(errors, dict),
            isinstance(identity, str),
        )
    ):
        raise ValueError("invalid Hashmarks MCP contract manifest")
    identity_payload = {
        key: value for key, value in manifest.items() if key != "contract_identity"
    }
    if identity != _contract_identity(identity_payload):
        raise ValueError("Hashmarks MCP contract identity mismatch")
    return {
        "schema": MCP_CONTRACT_SCHEMA,
        "contract_identity": identity,
        "server_version": server.get("version"),
        "tools": [str(row.get("name")) for row in tools if isinstance(row, dict)],
        "operation_contract_identity": operation_contract.get("contract_identity"),
        "error_schema": errors.get("schema"),
        "error_reasons": errors.get("reasons"),
        "error_recovery_authority": errors.get("recovery_authority"),
    }


async def _current_contract_summary(workspace: str) -> dict[str, object]:
    from ._version import __version__
    from .mcp_server import build_server

    server = build_server(workspace)
    try:
        tools = await server.list_tools()
        return contract_summary(contract_from_tool_models(__version__, tools))
    finally:
        server._hashmarks_surface.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit the canonical contract identity for one installed Hashmarks MCP server."
    )
    parser.add_argument("--workspace", default=".")
    args = parser.parse_args(argv)
    sys.stdout.write(
        json.dumps(
            asyncio.run(_current_contract_summary(args.workspace)),
            sort_keys=True,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
