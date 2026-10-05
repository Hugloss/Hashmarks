from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from hashmarks.codemap.dependency_resolution_evidence import (
    DependencyResolutionEvidenceMixin,
)
from hashmarks.codemap.repository_declarations import RepositoryDeclarationsMixin
from hashmarks.mcp_contract import McpToolContract
from hashmarks.operation_contract import (
    OPERATION_CONTRACT_SCHEMA,
    OPERATION_CONTRACTS,
    operation_contract_manifest,
    operation_modes,
    operation_schema,
    registered_operations,
    require_operation_mode,
    require_registered_operation,
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


def test_public_operation_admission_fails_before_projection() -> None:
    assert registered_operations() == tuple(_EXPECTED)
    assert require_registered_operation("find").operation == "find"

    with pytest.raises(ValueError, match="unknown Hashmarks operation"):
        require_registered_operation("unregistered_operation")
    with pytest.raises(ValueError, match="unknown Hashmarks operation"):
        validate_operation_response(
            "unregistered_operation",
            {"schema": "hashmarks.unregistered.v1"},
        )
    with pytest.raises(ValueError, match="unknown Hashmarks operation"):
        McpToolContract(
            "future_tool",
            "fixture",
            "unregistered_operation",
        )


def test_public_surfaces_do_not_mint_versioned_semantic_schemas() -> None:
    schema_literal = re.compile(r"hashmarks\.[a-z0-9_.-]+\.v\d+")
    for relative in (
        "hashmarks/mcp_surface.py",
        "hashmarks/mcp_server.py",
        "hashmarks/repository_cli.py",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert schema_literal.findall(source) == [], relative


def test_cli_operation_projection_names_are_registered_literals() -> None:
    source = (ROOT / "hashmarks" / "repository_cli.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    projected: list[str] = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_print_operation"
        ):
            continue
        assert node.args
        operation = node.args[0]
        assert isinstance(operation, ast.Constant)
        assert isinstance(operation.value, str)
        projected.append(operation.value)

    assert projected
    assert set(projected) <= set(registered_operations())


def test_operation_modes_fail_closed() -> None:
    assert require_operation_mode("dependency_codemap", "compare") == "compare"
    assert require_operation_mode("repository_declarations", "observation") == (
        "observation"
    )
    with pytest.raises(ValueError, match="unknown Hashmarks operation"):
        operation_modes("unknown")
    with pytest.raises(ValueError, match="result_mode must be one of"):
        require_operation_mode("dependency_codemap", "history")
    with pytest.raises(ValueError, match="unknown Hashmarks operation mode"):
        operation_schema("dependency_codemap", "history")


def test_core_operation_dispatchers_consume_canonical_mode_admission() -> None:
    dependency_source = (
        ROOT / "hashmarks" / "codemap" / "dependency_resolution_evidence.py"
    ).read_text(encoding="utf-8")
    declarations_source = (
        ROOT / "hashmarks" / "codemap" / "repository_declarations.py"
    ).read_text(encoding="utf-8")

    assert (
        'require_operation_mode("dependency_codemap", result_mode)' in dependency_source
    )
    assert (
        'require_operation_mode("repository_declarations", result_mode)'
        in declarations_source
    )
    assert 'allowed = ("observation", "explain", "compare")' not in dependency_source
    assert 'allowed = ("observation", "explain")' not in declarations_source


class _DependencyOperationHarness(DependencyResolutionEvidenceMixin):
    def dependency_resolution_evidence(self, _snapshot):
        return {"schema": "fixture"}

    def dependency_resolution_explain(self, _observation):
        return {"schema": "hashmarks.wrong.v1"}

    def dependency_resolution_delta(self, _before, _after):
        return {"schema": operation_schema("dependency_codemap", "compare")}


class _DeclarationOperationHarness(RepositoryDeclarationsMixin):
    def repository_declarations(self, _groups, *, previous_observation=None):
        del previous_observation
        return {
            "schema": operation_schema(
                "repository_declarations",
                "observation",
            )
        }

    def repository_declaration_explain(self, _packet):
        return {"schema": "hashmarks.wrong.v1"}


def test_core_dependency_operation_rejects_producer_schema_drift() -> None:
    harness = _DependencyOperationHarness()
    with pytest.raises(RuntimeError, match="operation response schema drift"):
        harness.dependency_codemap({}, result_mode="explain")


def test_core_declaration_operation_rejects_producer_schema_drift() -> None:
    harness = _DeclarationOperationHarness()
    with pytest.raises(RuntimeError, match="operation response schema drift"):
        harness.repository_declarations_operation([], result_mode="explain")
