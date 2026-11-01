from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.python_ast_cache import read_python_ast

ROOT = Path(__file__).resolve().parents[1]
CODEMAP = ROOT / "hashmarks" / "codemap"


def _tree(path: Path) -> ast.Module:
    return read_python_ast(path).tree


def _syntax_import_bindings(
    node: ast.Import | ast.ImportFrom, package: str
) -> list[tuple[str, str]]:
    if isinstance(node, ast.Import):
        return [
            (
                alias.asname or alias.name.split(".")[0],
                alias.name if alias.asname else alias.name.split(".")[0],
            )
            for alias in node.names
        ]
    module = node.module or ""
    if node.level:
        module = importlib.util.resolve_name("." * node.level + module, package)
    return [
        (alias.asname or alias.name, f"{module}.{alias.name}") for alias in node.names
    ]


def _owns_raw_source_parser(target: str) -> bool:
    root = target.split(".")[0]
    return (
        root == "tree_sitter"
        or root.startswith("tree_sitter_")
        or root == "esprima"
        or target == "hashmarks.codemap.providers.StructuralParser"
    )


def _syntax_call_target(node: ast.AST, bindings: dict[str, str]) -> str:
    if isinstance(node, ast.Name):
        return bindings.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        return f"{_syntax_call_target(node.value, bindings)}.{node.attr}"
    return ""


def _source_parser_call(
    node: ast.Call,
    bindings: dict[str, str],
    package: str,
    allow_provider_construction: bool,
) -> str | None:
    target = _syntax_call_target(node.func, bindings)
    if not allow_provider_construction and target == (
        "hashmarks.codemap.providers.TreeSitterRangeProvider"
    ):
        return target
    if target not in {"importlib.import_module", "__import__", "builtins.__import__"}:
        return None
    if not node.args or not isinstance(node.args[0], ast.Constant):
        return None
    value = node.args[0].value
    if not isinstance(value, str):
        return None
    if value.startswith("."):
        value = importlib.util.resolve_name(value, package)
    return value if _owns_raw_source_parser(value) else None


def _source_syntax_bypasses(
    tree: ast.Module,
    package: str = "hashmarks.codemap",
    *,
    allow_provider_construction: bool = False,
) -> list[tuple[int, str]]:
    bindings: dict[str, str] = {}
    violations: set[tuple[int, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports = _syntax_import_bindings(node, package)
            bindings.update(imports)
            violations.update(
                (node.lineno, target)
                for _, target in imports
                if _owns_raw_source_parser(target)
            )
    for node in ast.walk(tree):
        target = _syntax_call_target(node, bindings)
        if isinstance(node, (ast.Name, ast.Attribute)) and (
            _owns_raw_source_parser(target)
            or (
                not allow_provider_construction
                and target == "hashmarks.codemap.providers.TreeSitterRangeProvider.auto"
            )
        ):
            violations.add((node.lineno, target))
        if isinstance(node, ast.Call):
            target = _source_parser_call(
                node, bindings, package, allow_provider_construction
            )
            if target is not None:
                violations.add((node.lineno, target))
        if isinstance(node, ast.Attribute) and node.attr in {
            "_parser",
            "_parser_factory",
            "_syntax_reuse",
        }:
            violations.add((node.lineno, f"provider-private:{node.attr}"))
    return sorted(violations)


def test_native_source_parser_construction_stays_with_its_owner() -> None:
    violations = []
    for path in sorted(CODEMAP.rglob("*.py")):
        if path == CODEMAP / "providers.py":
            continue
        package = ".".join(path.relative_to(ROOT).parent.parts)
        violations.extend(
            f"{path.relative_to(CODEMAP)}:{line}:{target}"
            for line, target in _source_syntax_bypasses(
                _tree(path),
                package,
                allow_provider_construction=path == CODEMAP / "engine.py",
            )
        )
    assert violations == [], (
        "source consumers must use the configured syntax provider, not acquire "
        "another parser: " + ", ".join(violations)
    )


@pytest.mark.parametrize(
    "source",
    [
        "import tree_sitter as alternate\nalternate.Parser()\n",
        "from tree_sitter_language_pack import get_parser as renamed\n"
        "renamed('typescript').parse(raw)\n",
        "from tree_sitter_typescript import language_typescript as grammar\n",
        "from esprima import tokenize as lexical_observer\n",
        "from .providers import StructuralParser as OtherOwner\n",
        "from ..codemap.providers import StructuralParser as OtherOwner\n",
        "from . import providers as native\nnative.StructuralParser()\n",
        "from .providers import TreeSitterRangeProvider as Other\nOther()\n",
        "from .providers import TreeSitterRangeProvider as Other\nOther.auto()\n",
        "from . import providers as native\n"
        "factory = native.TreeSitterRangeProvider.auto\nfactory()\n",
        "import importlib as modules\nmodules.import_module('tree_sitter')\n",
        "import importlib.util\nimportlib.import_module('tree_sitter')\n",
        "from importlib import import_module as load\n"
        "load('tree_sitter_language_pack')\n",
        "from builtins import __import__ as load\nload('tree_sitter')\n",
        "__import__('tree_sitter_languages')\n",
        "def observe(configured, raw):\n"
        "    return configured._parser('javascript').parse(raw)\n",
        "def observe(configured, raw):\n"
        "    factory = configured._parser_factory\n"
        "    return factory('tsx').parse(raw)\n",
        "def observe(configured):\n    configured._syntax_reuse.set(None)\n",
    ],
)
def test_native_source_parser_guard_detects_renamed_and_relative_bypasses(
    source: str,
) -> None:
    assert _source_syntax_bypasses(ast.parse(source))


def test_native_source_parser_guard_preserves_qualified_projections() -> None:
    source = (
        "from .providers import SourceSyntaxProvider, StructuralTree, source_grammar\n"
        "from .ecmascript_syntax import module_declarations\n"
        "from .python_ast import identifier_terms, estimate_tokens\n"
        "def observe(provider, raw, path):\n"
        "    tree = provider.syntax_tree(raw, source_grammar(path))\n"
        "    return module_declarations(tree, raw)\n"
    )
    assert _source_syntax_bypasses(ast.parse(source)) == []


def test_source_composition_may_construct_the_configured_provider_only() -> None:
    source = (
        "from .providers import TreeSitterRangeProvider as Native\n"
        "provider = Native.auto()\n"
    )
    assert (
        _source_syntax_bypasses(ast.parse(source), allow_provider_construction=True)
        == []
    )
    assert _source_syntax_bypasses(ast.parse(source))
    assert _source_syntax_bypasses(
        ast.parse("from tree_sitter_language_pack import get_parser as alternative\n"),
        allow_provider_construction=True,
    )


def _python_module_parse_bypasses(tree: ast.Module) -> list[int]:
    bindings = dict(
        pair
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for pair in _syntax_import_bindings(node, "hashmarks.codemap")
    )
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _syntax_call_target(node.func, bindings) == "ast.parse"
        and not any(
            keyword.arg == "mode"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value == "eval"
            for keyword in node.keywords
        )
    ]


def test_python_member_parsing_uses_the_existing_ast_owner() -> None:
    violations = [
        f"{path.relative_to(CODEMAP)}:{line}"
        for path in sorted(CODEMAP.rglob("*.py"))
        for line in _python_module_parse_bypasses(_tree(path))
    ]
    assert violations == [], (
        "whole-member Python parsers bypass their owner: " + ", ".join(violations)
    )


@pytest.mark.parametrize(
    "source",
    [
        "import ast as syntax\nsyntax.parse(raw)\n",
        "from ast import parse as another\nanother(raw)\n",
        "import ast\nast.parse(raw, mode='exec')\n",
    ],
)
def test_python_member_guard_detects_renamed_parser_calls(source: str) -> None:
    assert _python_module_parse_bypasses(ast.parse(source))


def test_annotation_expression_parse_is_distinct_from_member_parsing() -> None:
    assert (
        _python_module_parse_bypasses(
            ast.parse("import ast\nast.parse(annotation, mode='eval')\n")
        )
        == []
    )


def test_binding_interpreters_consume_supplied_syntax_without_source_io() -> None:
    forbidden = {
        "open",
        "read_text",
        "read_bytes",
        "parse",
        "parse_python_ast",
        "syntax_tree",
        "tokenize",
    }
    paths = [
        *CODEMAP.glob("python_binding*.py"),
        *CODEMAP.glob("ecmascript_binding*.py"),
    ]
    violations = [
        f"{path.name}:{node.lineno}"
        for path in paths
        for node in ast.walk(_tree(path))
        if isinstance(node, ast.Call)
        and (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in forbidden
            or isinstance(node.func, ast.Name)
            and node.func.id in forbidden
        )
    ]
    assert violations == [], (
        "binding projectors must use admitted syntax: " + ", ".join(violations)
    )


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
            if path.name == "evidence_graph.py" and cls == "RepositoryRelationships":
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
    state_doc = (
        ROOT / "docs" / "reference" / "STATE_AND_SEMANTIC_OWNERS.md"
    ).read_text(encoding="utf-8")
    assert 'FRESHNESS_STATES = frozenset({"current", "stale", "unknown"})' in owner
    assert "def freshness_state(" in owner
    for name in (
        "repository_evidence_bindings.py",
        "freshness_map.py",
        "evidence_packet.py",
        "change_intelligence.py",
    ):
        consumer = (CODEMAP / name).read_text(encoding="utf-8")
        assert "from hashmarks.freshness import freshness_state" in consumer
        assert "from .evidence_freshness import freshness_state" not in consumer
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
    assert "self.bindings.observe(" in source
    assert "self.bindings.delta(" in source


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
    native = (CODEMAP / "native_evidence.py").read_text(encoding="utf-8")
    freshness = (CODEMAP / "evidence_freshness.py").read_text(encoding="utf-8")

    assert '.rglob("pyproject.toml")' not in indexing
    assert 'self.files.visible_manifests("pyproject.toml")' in indexing
    assert "default_project_graph_providers(self.files.visible_manifests)" in native
    assert "def _manifest_admitted(" in freshness
    assert "self.files.is_admitted(relpath)" in freshness
    assert "self.files.decide(relpath)" in freshness
    assert "self._admit_project_graph(" in native
    assert native.index("self._admit_project_graph(") < native.index(
        "self.store.replace_project_graph("
    )
