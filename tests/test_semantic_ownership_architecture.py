from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

from hashmarks.python_ast_cache import read_python_ast

ROOT = Path(__file__).resolve().parents[1]
CODEMAP = ROOT / "hashmarks" / "codemap"


def _tree(path: Path) -> ast.AST:
    return read_python_ast(path).tree


def test_codemap_cannot_import_dependency_adapters() -> None:
    violations: list[str] = []
    for path in sorted(CODEMAP.glob("*.py")):
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                module = (
                    importlib.util.resolve_name(
                        "." * node.level + (node.module or ""), "hashmarks.codemap"
                    )
                    if node.level
                    else node.module or ""
                )
                modules = [module, *(f"{module}.{alias.name}" for alias in node.names)]
            else:
                modules = []
            if any(
                module == "hashmarks.adapters"
                or module.startswith("hashmarks.adapters.")
                for module in modules
            ):
                violations.append(f"{path.name}:{node.lineno}:adapter import")
    assert violations == []


def test_dependency_core_cannot_branch_on_producer_format() -> None:
    forbidden = (
        "maven",
        "uv-lock",
        "gradle",
        "npm",
        "dependency-tree",
        "dependency-list",
        "classifier",
        "groupId",
        "artifactId",
    )
    violations: list[str] = []
    for path in sorted(CODEMAP.glob("dependency_resolution*.py")):
        for node in ast.walk(_tree(path)):
            if isinstance(node, (ast.Compare, ast.Match)):
                values = (
                    child.value
                    for child in ast.walk(node)
                    if isinstance(child, ast.Constant) and isinstance(child.value, str)
                )
                if any(any(term in value for term in forbidden) for value in values):
                    violations.append(f"{path.name}:{node.lineno}:producer branch")
    assert violations == []


def test_repository_member_observation_has_one_semantic_owner() -> None:
    definitions: list[str] = []
    for path in sorted(CODEMAP.glob("*.py")):
        for node in ast.walk(_tree(path)):
            if (
                isinstance(node, ast.FunctionDef)
                and node.name == "_repository_member_observation"
            ):
                definitions.append(f"{path.name}:{node.lineno}")
    assert len(definitions) == 1
    assert definitions[0].startswith("repository_delta.py:")


def test_evidence_binding_projection_does_not_read_repository_bytes_directly() -> None:
    path = CODEMAP / "repository_evidence_bindings.py"
    violations: list[str] = []
    for node in ast.walk(_tree(path)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr in {"read_bytes", "read_text"}:
            violations.append(f"{path.name}:{node.lineno}:{node.func.attr}")
    assert violations == [], (
        "repository evidence bindings must consume canonical member observation "
        "rather than create another repository byte-read authority: "
        + ", ".join(violations)
    )


def test_canonical_freshness_vocabulary_is_owned_once() -> None:
    owner = (CODEMAP / "evidence_freshness.py").read_text(encoding="utf-8")
    state_doc = (
        ROOT / "docs" / "reference" / "STATE_AND_SEMANTIC_OWNERS.md"
    ).read_text(encoding="utf-8")
    assert 'FRESHNESS_STATES = frozenset({"current", "stale", "unknown"})' in owner
    assert "current" in state_doc and "stale" in state_doc and "unknown" in state_doc

    freshness_map = (CODEMAP / "freshness_map.py").read_text(encoding="utf-8")
    context = (ROOT / "hashmarks" / "evidence_context.py").read_text(encoding="utf-8")
    assert '"invalidated"' not in freshness_map
    assert 'frozenset({"unknown", "current", "stale"})' in context


def test_binding_modules_are_projection_owners_not_second_change_authorities() -> None:
    bindings = (CODEMAP / "repository_evidence_bindings.py").read_text(encoding="utf-8")
    delta = (CODEMAP / "repository_evidence_binding_delta.py").read_text(
        encoding="utf-8"
    )
    coverage = (CODEMAP / "repository_evidence_coverage.py").read_text(encoding="utf-8")
    assert "_repository_member_observation(" in bindings
    assert "binding_definition_identity" in bindings
    assert "binding_observation_identity" in bindings
    assert "declared_dependencies" in delta
    assert "semantic_dependencies" not in delta
    assert '"source": "repository-observer"' in coverage
    assert '"source": "caller-asserted"' in coverage


def test_completeness_is_not_mixed_with_availability_or_freshness() -> None:
    delta = (CODEMAP / "repository_delta.py").read_text(encoding="utf-8")
    bindings = (CODEMAP / "repository_evidence_bindings.py").read_text(encoding="utf-8")
    state_doc = (
        ROOT / "docs" / "reference" / "STATE_AND_SEMANTIC_OWNERS.md"
    ).read_text(encoding="utf-8")

    assert "OBSERVATION_STATES" not in delta
    assert '"state": "complete"' in delta
    assert '"state": "complete"' in bindings
    assert "exactly `complete`, `incomplete`, or `unknown`" in state_doc


def test_declarations_reuse_repository_evidence_authorities() -> None:
    path = CODEMAP / "repository_declarations.py"
    source = path.read_text(encoding="utf-8")
    violations: list[str] = []
    for node in ast.walk(_tree(path)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr in {"read_bytes", "read_text"}:
            violations.append(f"{path.name}:{node.lineno}:{node.func.attr}")

    assert violations == []
    assert "self.repository_evidence_bindings(" in source
    assert "self.repository_evidence_binding_delta(" in source


def test_declaration_provider_context_has_no_raw_workspace_authority() -> None:
    provider_path = CODEMAP / "repository_declaration_provider.py"
    discovery_path = CODEMAP / "repository_declaration_discovery.py"
    provider_tree = _tree(provider_path)
    protocol = next(
        node
        for node in ast.walk(provider_tree)
        if isinstance(node, ast.ClassDef)
        and node.name == "RepositoryDeclarationProviderContext"
    )
    declared_names = {
        node.target.id
        for node in protocol.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert "workspace" not in declared_names

    discovery = discovery_path.read_text(encoding="utf-8")
    assert "self._iter_admitted_repository_files(" in discovery
    assert "MAX_PROVIDER_ENUMERATED_PATHS + 1" in discovery
    assert 'item.visibility.value != "deny"' in discovery
    assert (
        "collect_repository_declaration_providers(\n            self.workspace"
        not in discovery
    )



def test_repository_file_discovery_has_one_semantic_owner() -> None:
    owned = {
        "_path_admitted_for_analysis",
        "_iter_admitted_repository_files",
        "_walk_admitted_repository_files",
    }
    definitions: dict[str, list[str]] = {name: [] for name in owned}
    for path in sorted(CODEMAP.glob("*.py")):
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.FunctionDef) and node.name in definitions:
                definitions[node.name].append(f"{path.name}:{node.lineno}")

    for name in sorted(owned):
        assert len(definitions[name]) == 1
        assert definitions[name][0].startswith("repository_file_discovery.py:")

    indexing = (CODEMAP / "indexing_lifecycle.py").read_text(encoding="utf-8")
    declarations = (CODEMAP / "repository_declaration_discovery.py").read_text(
        encoding="utf-8"
    )
    owner = (CODEMAP / "repository_file_discovery.py").read_text(encoding="utf-8")
    assert "os.walk(" not in indexing
    assert "os.walk(" not in declarations
    assert "os.walk(" in owner
    assert "self.policy.decide(" in owner
