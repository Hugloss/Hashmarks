from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

from hashmarks.codemap import CodeMap
from hashmarks.python_ast_cache import read_python_ast

ROOT = Path(__file__).resolve().parents[1]
CODEMAP = ROOT / "hashmarks" / "codemap"


def _tree(path: Path) -> ast.Module:
    return read_python_ast(path).tree


def _relationship_cache_writers(tree: ast.Module) -> list[tuple[str, str, int]]:
    writers = []
    for cls in (node for node in tree.body if isinstance(node, ast.ClassDef)):
        for method in (node for node in cls.body if isinstance(node, ast.FunctionDef)):
            for node in ast.walk(method):
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.ctx, ast.Store)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "self"
                    and node.attr == "_reverse_file_graph_cache"
                ):
                    writers.append((cls.name, method.name, node.lineno))
    return writers


def test_relationship_cache_writes_stay_with_its_owner() -> None:
    violations = []
    for path in sorted(CODEMAP.glob("*.py")):
        for cls, method, line in _relationship_cache_writers(_tree(path)):
            if path.name == "evidence_graph.py" and cls == "EvidenceGraphMixin":
                continue
            if (path.name, cls, method) == ("engine.py", "CodeMap", "__init__"):
                continue
            violations.append(f"{path.name}:{method}:{line}")
    assert violations == [], violations


def test_relationship_cache_guard_detects_all_direct_assignment_forms() -> None:
    tree = ast.parse(
        "class ForeignOwner:\n"
        "    def publish(self):\n"
        "        self._reverse_file_graph_cache = None\n"
        "        self._reverse_file_graph_cache: object = None\n"
        "        self._reverse_file_graph_cache += other\n"
    )
    assert _relationship_cache_writers(tree) == [
        ("ForeignOwner", "publish", 3),
        ("ForeignOwner", "publish", 4),
        ("ForeignOwner", "publish", 5),
    ]


def _effective_method_collisions(cls: type[object]) -> dict[str, list[str]]:
    definitions: dict[str, list[str]] = {}
    for owner in cls.__mro__:
        for name, value in vars(owner).items():
            if name.startswith("__"):
                continue
            if callable(value) or isinstance(
                value, (staticmethod, classmethod, property)
            ):
                definitions.setdefault(name, []).append(owner.__qualname__)
    return {name: owners for name, owners in definitions.items() if len(owners) > 1}


def test_codemap_has_no_accidental_effective_method_shadowing() -> None:
    assert _effective_method_collisions(CodeMap) == {}


def test_effective_method_guard_detects_a_mixin_collision() -> None:
    class First:
        def resolve_owner(self) -> str:
            return "first"

    class Second:
        def resolve_owner(self) -> str:
            return "second"

    class Colliding(First, Second):
        pass

    assert _effective_method_collisions(Colliding) == {
        "resolve_owner": [First.__qualname__, Second.__qualname__]
    }


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
                continue
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
    retired: list[str] = []
    for path in sorted(CODEMAP.glob("*.py")):
        tree = _tree(path)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.FunctionDef)
                and node.name == "_repository_member_observation"
            ):
                retired.append(f"{path.name}:{node.lineno}")
        for cls in (node for node in tree.body if isinstance(node, ast.ClassDef)):
            if cls.name != "RepositorySource":
                continue
            definitions.extend(
                f"{path.name}:{node.lineno}"
                for node in cls.body
                if isinstance(node, ast.FunctionDef) and node.name == "member"
            )

    assert len(definitions) == 1
    assert definitions[0].startswith("repository_source.py:")
    assert retired == []


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
    owner = (ROOT / "hashmarks" / "freshness.py").read_text(encoding="utf-8")
    codemap_freshness = (CODEMAP / "evidence_freshness.py").read_text(encoding="utf-8")
    state_doc = (
        ROOT / "docs" / "reference" / "STATE_AND_SEMANTIC_OWNERS.md"
    ).read_text(encoding="utf-8")
    assert 'FRESHNESS_STATES = frozenset({"current", "stale", "unknown"})' in owner
    assert "def freshness_state(" in owner
    assert "from hashmarks.freshness import FRESHNESS_STATES, freshness_state" in (
        codemap_freshness
    )
    assert "current" in state_doc and "stale" in state_doc and "unknown" in state_doc

    freshness_map = (CODEMAP / "freshness_map.py").read_text(encoding="utf-8")
    context = (ROOT / "hashmarks" / "evidence_context.py").read_text(encoding="utf-8")
    find_engine = (CODEMAP / "find_engine.py").read_text(encoding="utf-8")
    assert '"invalidated"' not in freshness_map
    assert 'frozenset({"unknown", "current", "stale"})' not in context
    assert "from .freshness import FRESHNESS_STATES" in context
    assert "def _find_freshness_state(" not in find_engine
    assert "from hashmarks.freshness import freshness_state" in find_engine


def test_binding_modules_are_projection_owners_not_second_change_authorities() -> None:
    bindings = (CODEMAP / "repository_evidence_bindings.py").read_text(encoding="utf-8")
    delta = (CODEMAP / "repository_evidence_binding_delta.py").read_text(
        encoding="utf-8"
    )
    coverage = (CODEMAP / "repository_evidence_coverage.py").read_text(encoding="utf-8")
    assert "self.source.member(" in bindings
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
    assert "self.files.iter_files(" in discovery
    assert "MAX_PROVIDER_ENUMERATED_PATHS + 1" in discovery
    assert 'item.visibility.value != "deny"' in discovery
    assert (
        "collect_repository_declaration_providers(\n            self.workspace"
        not in discovery
    )


def test_repository_file_discovery_has_one_semantic_owner() -> None:
    owned = {
        "is_admitted",
        "iter_files",
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
    assert "self.decide(" in owner
    assert "from .engine import CodeMap" not in owner
    assert "RepositoryFileDiscoveryMixin" not in owner


def test_repository_derived_file_evidence_uses_canonical_admission_owner() -> None:
    indexing = (CODEMAP / "indexing_lifecycle.py").read_text(encoding="utf-8")
    engine = (CODEMAP / "engine.py").read_text(encoding="utf-8")
    freshness = (CODEMAP / "evidence_freshness.py").read_text(encoding="utf-8")
    graph = (CODEMAP / "evidence_graph.py").read_text(encoding="utf-8")

    assert '.rglob("pyproject.toml")' not in indexing
    assert 'self.files.visible_manifests("pyproject.toml")' in indexing
    assert (
        "default_project_graph_providers(\n            self.files.visible_manifests"
        in engine
    )
    assert "def _manifest_admitted(" in freshness
    assert "self.files.is_admitted(relpath)" in freshness
    assert "self.files.decide(relpath)" in freshness
    assert "self._admit_project_graph(" in graph
    assert graph.index("self._admit_project_graph(") < graph.index(
        "self.store.replace_project_graph("
    )
