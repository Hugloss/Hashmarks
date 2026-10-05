from __future__ import annotations

from pathlib import Path

import pytest

from hashmarks.operation_contract import (
    OPERATION_CONTRACT_SCHEMA,
    OPERATION_CONTRACTS,
    operation_contract_manifest,
    operation_modes,
    operation_schema,
    validate_operation_response,
)

ROOT = Path(__file__).resolve().parents[1]

_EXPECTED = {
    "repository_context": {
        "default": "hashmarks.repository-capsule.v1",
    },
    "find": {
        "default": "hashmarks.find.v2",
    },
    "task_evidence": {
        "default": "hashmarks.task-evidence.v2",
    },
    "change_impact": {
        "default": "hashmarks.task-change-impact.v1",
    },
    "correlate_evidence": {
        "default": "hashmarks.evidence-correlation.v2",
    },
    "dependency_codemap": {
        "observation": "hashmarks.dependency-codemap.v1",
        "explain": "hashmarks.dependency-resolution-explain.v1",
        "compare": "hashmarks.dependency-resolution-delta.v3",
    },
    "repository_declarations": {
        "observation": "hashmarks.repository-declarations.v1",
        "explain": "hashmarks.repository-declaration-explain.v1",
    },
    "post_change": {
        "default": "hashmarks.task-post-change-delta.v2",
    },
}


def test_operation_contract_is_one_exact_mapping() -> None:
    assert {
        contract.operation: contract.mode_map() for contract in OPERATION_CONTRACTS
    } == _EXPECTED

    manifest = operation_contract_manifest()
    assert manifest["schema"] == OPERATION_CONTRACT_SCHEMA
    assert str(manifest["contract_identity"]).startswith("sha256:")
    assert manifest["mappings"] == [
        {"operation": operation, "modes": modes}
        for operation, modes in _EXPECTED.items()
    ]


@pytest.mark.parametrize(
    ("operation", "mode", "schema"),
    [
        (operation, mode, schema)
        for operation, modes in _EXPECTED.items()
        for mode, schema in modes.items()
    ],
)
def test_operation_contract_validates_exact_operation_mode_schema(
    operation: str,
    mode: str,
    schema: str,
) -> None:
    selected_mode = None if mode == "default" else mode
    assert operation_schema(operation, selected_mode) == schema
    packet = {"schema": schema}
    assert validate_operation_response(operation, packet, mode=selected_mode) is packet

    with pytest.raises(RuntimeError, match="operation response schema drift"):
        validate_operation_response(
            operation,
            {"schema": "hashmarks.wrong.v1"},
            mode=selected_mode,
        )


def test_operation_schema_versions_have_one_source_owner() -> None:
    owner = ROOT / "hashmarks" / "operation_contract.py"
    schema_strings = {
        schema for modes in _EXPECTED.values() for schema in modes.values()
    }

    duplicates: list[str] = []
    for path in sorted((ROOT / "hashmarks").rglob("*.py")):
        if path == owner:
            continue
        source = path.read_text(encoding="utf-8")
        for schema in sorted(schema_strings):
            if schema in source:
                duplicates.append(f"{path.relative_to(ROOT).as_posix()}: {schema}")

    assert duplicates == []


def test_transports_do_not_own_semantic_find_or_dependency_schema() -> None:
    mcp_source = (ROOT / "hashmarks" / "mcp_surface.py").read_text(encoding="utf-8")
    cli_source = (ROOT / "hashmarks" / "repository_cli.py").read_text(encoding="utf-8")

    assert "self._map.find_packet(" in mcp_source
    assert "codemap.find_packet(" in cli_source
    assert "hashmarks.mcp-find.v1" not in mcp_source
    assert "hashmarks.find.v1" not in cli_source
    assert "hashmarks.mcp-dependency-codemap.v1" not in mcp_source


def test_operation_modes_fail_closed() -> None:
    with pytest.raises(ValueError, match="unknown Hashmarks operation"):
        operation_modes("unknown")
    with pytest.raises(ValueError, match="unknown Hashmarks operation mode"):
        operation_schema("dependency_codemap", "history")
