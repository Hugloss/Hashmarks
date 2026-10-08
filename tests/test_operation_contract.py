from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path
from typing import get_args

import pytest

import hashmarks.codemap.change_impact as change_impact_module
import hashmarks.codemap.evidence_correlation as evidence_correlation_module
import hashmarks.codemap.evidence_packet as evidence_packet_module
import hashmarks.codemap.find_engine as find_engine_module
import hashmarks.codemap.post_change as post_change_module
import hashmarks.codemap.repository_context as repository_context_module
from hashmarks.codemap import CodeMap
from hashmarks.codemap.dependency_resolution_evidence import (
    DependencyResolutionEvidenceMixin,
)
from hashmarks.codemap.repository_declarations import RepositoryDeclarationsMixin
from hashmarks.mcp_contract import McpToolContract, tool_contract
from hashmarks.mcp_server import (
    _DependencyCodemapResultMode,
    _RepositoryDeclarationsResultMode,
)
from hashmarks.mcp_surface import HashmarksMcpSurface
from hashmarks.operation_contract import (
    OPERATION_CONTRACT_SCHEMA,
    OPERATION_CONTRACTS,
    operation_contract_manifest,
    operation_default_mode,
    operation_modes,
    operation_schema,
    registered_operations,
    require_operation_mode,
    require_registered_operation,
    validate_operation_response,
)

ROOT = Path(__file__).resolve().parents[1]

_EXPECTED = {
    "evidence_presentation": {
        "projection": "hashmarks.evidence-presentation.v1",
        "envelope": "hashmarks.evidence-presentation-envelope.v1",
    },
    "repository_context": {"default": "hashmarks.repository-capsule.v1"},
    "find": {"default": "hashmarks.find.v2"},
    "task_evidence": {"default": "hashmarks.task-evidence.v5"},
    "change_impact": {"default": "hashmarks.task-change-impact.v1"},
    "correlate_evidence": {"default": "hashmarks.evidence-correlation.v2"},
    "dependency_codemap": {
        "observation": "hashmarks.dependency-codemap.v1",
        "explain": "hashmarks.dependency-resolution-explain.v1",
        "compare": "hashmarks.dependency-resolution-delta.v3",
    },
    "repository_declarations": {
        "observation": "hashmarks.repository-declarations.v1",
        "explain": "hashmarks.repository-declaration-explain.v1",
    },
    "post_change": {"default": "hashmarks.task-post-change-delta.v2"},
    "source_observation": {
        "member": "hashmarks.source-observation.v1",
        "scope": "hashmarks.scoped-source-occurrences.v1",
    },
    "repository_evidence": {
        "observation": "hashmarks.repository-evidence-bindings.v1",
        "coverage": "hashmarks.repository-evidence-coverage.v1",
    },
    "projects": {"default": "hashmarks.codemap-projects.v1"},
    "outline": {"default": "hashmarks.outline.v1"},
    "grep": {"default": "hashmarks.grep.v1"},
    "structural": {"default": "hashmarks.structural-search.v1"},
    "symbol": {"default": "hashmarks.symbol.v1"},
    "source": {"default": "hashmarks.source.v1"},
    "affected": {"default": "hashmarks.codemap-affected.v1"},
    "tests": {"default": "hashmarks.codemap-tests.v1"},
    "structural_locality": {"default": "hashmarks.structural-locality.v1"},
    "structural_locality_delta": {"default": "hashmarks.structural-locality-delta.v1"},
    "context": {"default": "hashmarks.context-pack.v2"},
    "repository_findings": {"default": "hashmarks.repository-findings.v1"},
    "import_ownership": {"default": "hashmarks.import-ownership.v2"},
    "concurrency_risk": {"default": "hashmarks.concurrency-risk.v1"},
    "verification_ownership": {"default": "hashmarks.verification-ownership.v2"},
    "repository_ownership": {"default": "hashmarks.authority-ownership-graph.v3"},
    "cache_ownership": {"default": "hashmarks.cache-ownership.v1"},
    "cache_invalidation_ownership": {
        "default": "hashmarks.cache-invalidation-ownership.v1"
    },
    "task_action_map": {"default": "hashmarks.task-action-map.v1"},
    "verification_relevance": {"default": "hashmarks.verification-relevance.v1"},
    "ownership_relation_graph": {"default": "hashmarks.ownership-relation-graph.v1"},
    "task_decision_packet": {"default": "hashmarks.task-decision-packet.v2"},
    "task_decision_brief": {"default": "hashmarks.task-decision-brief.v1"},
    "task_action_brief": {"default": "hashmarks.task-action-brief.v1"},
    "task_decision_brief_budget_sweep": {
        "default": "hashmarks.task-decision-brief-budget-sweep.v1"
    },
    "repository_intelligence_query": {
        "default": "hashmarks.repository-intelligence-query.v1"
    },
    "refresh_after_change_delta": {"default": "hashmarks.refresh-delta.v1"},
    "refresh_after_change_brief": {"default": "hashmarks.post-change-refresh-brief.v1"},
    "refresh_after_change": {"default": "hashmarks.post-change-refresh.v1"},
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


_CLI_NON_SEMANTIC_CODEMAP_HANDLERS = {
    "_map_sync",
    "_map_clean",
    "_map_watch",
    "_map_status",
    "_map_enrich",
    "_map_import_scip",
    "_deps_code",
    "_refs_code",
}


def test_cli_codemap_exposure_is_exhaustively_classified() -> None:
    source = (ROOT / "hashmarks" / "repository_cli.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    non_semantic: set[str] = set()

    for function in (node for node in tree.body if isinstance(node, ast.FunctionDef)):
        codemap_calls = [
            node
            for node in ast.walk(function)
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "codemap"
            )
        ]
        if not codemap_calls:
            continue
        printers = [
            node
            for node in ast.walk(function)
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"_print", "_print_operation"}
            )
        ]
        if not printers:
            continue
        semantic = any(
            isinstance(node.func, ast.Name) and node.func.id == "_print_operation"
            for node in printers
        )
        if not semantic:
            non_semantic.add(function.name)

    assert non_semantic == _CLI_NON_SEMANTIC_CODEMAP_HANDLERS


def test_mcp_mode_types_derive_from_operation_contract() -> None:
    assert get_args(_DependencyCodemapResultMode) == tuple(
        operation_modes("dependency_codemap")
    )
    assert get_args(_RepositoryDeclarationsResultMode) == tuple(
        operation_modes("repository_declarations")
    )


def test_multimode_public_defaults_consume_canonical_operation_authority() -> None:
    expected = {
        "dependency_codemap": "observation",
        "repository_declarations": "observation",
    }
    assert {
        operation: operation_default_mode(operation) for operation in expected
    } == expected

    assert inspect.signature(
        DependencyResolutionEvidenceMixin.dependency_codemap
    ).parameters["result_mode"].default == operation_default_mode("dependency_codemap")
    assert inspect.signature(
        RepositoryDeclarationsMixin.repository_declarations_operation
    ).parameters["result_mode"].default == operation_default_mode(
        "repository_declarations"
    )
    assert inspect.signature(HashmarksMcpSurface.dependency_codemap).parameters[
        "result_mode"
    ].default == operation_default_mode("dependency_codemap")
    assert inspect.signature(HashmarksMcpSurface.repository_declarations).parameters[
        "result_mode"
    ].default == operation_default_mode("repository_declarations")
    assert tool_contract("dependency_codemap").default_response_mode == (
        operation_default_mode("dependency_codemap")
    )
    assert tool_contract("repository_declarations").default_response_mode == (
        operation_default_mode("repository_declarations")
    )

    server_source = (ROOT / "hashmarks" / "mcp_server.py").read_text(encoding="utf-8")
    assert (
        "result_mode: _RepositoryDeclarationsResultMode = "
        "contract.default_response_mode"
    ) in server_source
    assert "dependency_codemap_contract.default_response_mode" in server_source
    assert '_RepositoryDeclarationsResultMode = "observation"' not in server_source
    assert '_DependencyCodemapResultMode = "observation"' not in server_source


def test_operation_modes_fail_closed() -> None:
    assert require_operation_mode("dependency_codemap", "compare") == "compare"
    assert require_operation_mode("repository_declarations", "observation") == (
        "observation"
    )
    with pytest.raises(ValueError, match="unknown Hashmarks operation"):
        operation_modes("unknown")
    with pytest.raises(ValueError, match="unknown Hashmarks operation"):
        operation_default_mode("unknown")
    with pytest.raises(ValueError, match="result_mode must be one of"):
        require_operation_mode("dependency_codemap", "history")
    with pytest.raises(ValueError, match="unknown Hashmarks operation mode"):
        operation_schema("dependency_codemap", "history")


_FIXED_MODE_CORE_BOUNDARIES = {
    "repository_context": ("hashmarks/codemap/repository_context.py", "orient"),
    "find": ("hashmarks/codemap/find_engine.py", "find_packet"),
    "task_evidence": ("hashmarks/codemap/evidence_packet.py", "task_evidence"),
    "change_impact": ("hashmarks/codemap/change_impact.py", "task_change_impact"),
    "correlate_evidence": (
        "hashmarks/codemap/evidence_correlation.py",
        "correlate_evidence",
    ),
    "post_change": ("hashmarks/codemap/post_change.py", "task_post_change_delta"),
    "projects": ("hashmarks/codemap/query_surface.py", "projects"),
    "outline": ("hashmarks/codemap/engine.py", "outline"),
    "grep": ("hashmarks/codemap/query_surface.py", "grep"),
    "structural": ("hashmarks/codemap/query_surface.py", "structural"),
    "symbol": ("hashmarks/codemap/query_surface.py", "symbol"),
    "source": ("hashmarks/codemap/query_surface.py", "source"),
    "affected": ("hashmarks/codemap/query_surface.py", "affected"),
    "tests": ("hashmarks/codemap/query_surface.py", "tests"),
    "structural_locality": (
        "hashmarks/codemap/structural_locality.py",
        "structural_locality",
    ),
    "structural_locality_delta": (
        "hashmarks/codemap/structural_locality.py",
        "structural_locality_delta",
    ),
    "context": ("hashmarks/codemap/model.py", "ContextPack.as_dict"),
    "repository_findings": (
        "hashmarks/codemap/ownership_analysis.py",
        "repository_findings",
    ),
    "import_ownership": (
        "hashmarks/codemap/ownership_analysis.py",
        "import_ownership_findings",
    ),
    "concurrency_risk": (
        "hashmarks/codemap/ownership_analysis.py",
        "concurrency_risk_findings",
    ),
    "verification_ownership": (
        "hashmarks/codemap/evidence_verification.py",
        "verification_ownership_graph",
    ),
    "repository_ownership": (
        "hashmarks/codemap/ownership_analysis.py",
        "repository_ownership_graph",
    ),
    "cache_ownership": (
        "hashmarks/codemap/ownership_analysis.py",
        "cache_ownership_findings",
    ),
    "cache_invalidation_ownership": (
        "hashmarks/codemap/ownership_analysis.py",
        "cache_invalidation_ownership_graph",
    ),
    "task_action_map": (
        "hashmarks/codemap/task_action_projection.py",
        "task_action_map",
    ),
    "verification_relevance": (
        "hashmarks/codemap/evidence_verification.py",
        "verification_relevance",
    ),
    "ownership_relation_graph": (
        "hashmarks/codemap/ownership_graph.py",
        "ownership_relation_graph",
    ),
    "task_decision_packet": (
        "hashmarks/codemap/evidence_decision_packet.py",
        "task_decision_packet",
    ),
    "task_decision_brief": (
        "hashmarks/codemap/evidence_packet.py",
        "task_decision_brief",
    ),
    "task_action_brief": (
        "hashmarks/codemap/evidence_packet.py",
        "task_action_brief",
    ),
    "task_decision_brief_budget_sweep": (
        "hashmarks/codemap/evidence_packet.py",
        "task_decision_brief_budget_sweep",
    ),
    "repository_intelligence_query": (
        "hashmarks/codemap/repository_intelligence_query.py",
        "repository_intelligence_query",
    ),
    "refresh_after_change_delta": (
        "hashmarks/codemap/post_change.py",
        "refresh_after_change_delta",
    ),
    "refresh_after_change_brief": (
        "hashmarks/codemap/post_change.py",
        "refresh_after_change_brief",
    ),
    "refresh_after_change": (
        "hashmarks/codemap/post_change.py",
        "refresh_after_change",
    ),
}


def _function_node(source: str, name: str) -> ast.FunctionDef:
    tree = ast.parse(source)
    if "." not in name:
        matches = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == name
        ]
        assert len(matches) == 1
        return matches[0]

    class_name, method_name = name.split(".", 1)
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    ]
    assert len(classes) == 1
    matches = [
        node
        for node in classes[0].body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    ]
    assert len(matches) == 1
    return matches[0]


def test_fixed_mode_operations_self_prove_at_canonical_core_boundary() -> None:
    fixed_modes = {
        contract.operation
        for contract in OPERATION_CONTRACTS
        if len(contract.modes) == 1
    }
    assert set(_FIXED_MODE_CORE_BOUNDARIES) == fixed_modes

    for operation, (relative, function_name) in _FIXED_MODE_CORE_BOUNDARIES.items():
        source = (ROOT / relative).read_text(encoding="utf-8")
        function = _function_node(source, function_name)
        validated = [
            node
            for node in ast.walk(function)
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "validate_operation_response"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == operation
            )
        ]
        decorated = [
            node
            for node in function.decorator_list
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "operation_response"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == operation
            )
        ]
        assert validated or decorated, f"{operation} must self-prove at {function_name}"


def _fixed_mode_repo(root: Path) -> tuple[Path, str]:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    source = root / "src" / "owner.py"
    source.write_text("def widget(): return 'old'\n", encoding="utf-8")
    (root / "tests" / "test_owner.py").write_text(
        "from src.owner import widget\ndef test_widget(): assert widget() == 'new'\n",
        encoding="utf-8",
    )
    return source, "change widget implementation and verify widget test"


def test_core_repository_context_rejects_its_own_schema_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixed_mode_repo(tmp_path)
    monkeypatch.setattr(
        repository_context_module,
        "operation_schema",
        lambda _operation: "hashmarks.wrong.v1",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(RuntimeError, match="operation response schema drift"):
            codemap.orient()


def test_core_find_rejects_its_own_schema_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixed_mode_repo(tmp_path)
    monkeypatch.setattr(
        find_engine_module,
        "operation_schema",
        lambda _operation: "hashmarks.wrong.v1",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(RuntimeError, match="operation response schema drift"):
            codemap.find_packet("widget")


def test_core_task_evidence_rejects_its_own_schema_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source, task = _fixed_mode_repo(tmp_path)
    monkeypatch.setattr(
        evidence_packet_module,
        "operation_schema",
        lambda _operation: "hashmarks.wrong.v1",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(RuntimeError, match="operation response schema drift"):
            codemap.task_evidence(task)


def test_core_change_impact_rejects_its_own_schema_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source, task = _fixed_mode_repo(tmp_path)
    monkeypatch.setattr(
        change_impact_module,
        "operation_schema",
        lambda _operation: "hashmarks.wrong.v1",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(RuntimeError, match="operation response schema drift"):
            codemap.task_change_impact(task, ["src/owner.py"])


def test_core_correlation_rejects_its_own_schema_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixed_mode_repo(tmp_path)
    monkeypatch.setattr(
        evidence_correlation_module,
        "_CORRELATION_SCHEMA",
        "hashmarks.wrong.v1",
    )
    bundles = [
        {
            "bundle_id": "fixture:1",
            "producer": {"kind": "test-fixture"},
            "completeness": "complete",
            "scope": {"kind": "test-fixture"},
            "truncation": "complete",
            "anchors": [
                {
                    "anchor_id": "frame:0",
                    "path": "/app/src/owner.py",
                    "line": 1,
                    "symbol": "widget",
                    "metadata": {},
                }
            ],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(RuntimeError, match="operation response schema drift"):
            codemap.correlate_evidence(
                bundles,
                path_mappings=[{"external_prefix": "/app", "repository_prefix": ""}],
            )


def test_core_post_change_rejects_its_own_schema_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, task = _fixed_mode_repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        previous = codemap.task_evidence(task)
        source.write_text("def widget(): return 'new'\n", encoding="utf-8")

        def drifted_schema(operation: str, mode: str | None = None) -> str:
            if operation == "post_change":
                return "hashmarks.wrong.v1"
            return operation_schema(operation, mode)

        monkeypatch.setattr(post_change_module, "operation_schema", drifted_schema)
        with pytest.raises(RuntimeError, match="operation response schema drift"):
            codemap.task_post_change_delta(
                task,
                ["src/owner.py"],
                previous_evidence=previous,
            )


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
