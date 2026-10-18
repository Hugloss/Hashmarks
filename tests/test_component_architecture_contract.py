"""Closed, test-only checks for component direction and state ownership.

The controls attack the same checks used on production source. This inventory
has no runtime role and grants no repository or execution authority.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

from hashmarks.python_ast_cache import read_python_ast

ROOT = Path(__file__).resolve().parents[1]
CODEMAP = ROOT / "hashmarks/codemap"

# Exact constructor edges. Other imported component types may only be lower
# owners reachable through these edges, or the importing component itself.
COMPONENTS: dict[str, tuple[str, frozenset[str]]] = {
    "RepositoryFiles": ("repository_file_discovery", frozenset()),
    "RepositoryObservationSource": ("repository_observation", frozenset()),
    "RepositoryIndex": (
        "indexing_lifecycle",
        frozenset({"RepositoryFiles", "RepositoryObservationSource"}),
    ),
    "DecisionScope": ("decision_session", frozenset({"RepositoryIndex"})),
    "RepositorySource": (
        "repository_source",
        frozenset({"RepositoryIndex", "DecisionScope"}),
    ),
    "RepositoryImports": ("import_resolution", frozenset({"RepositorySource"})),
    "RepositoryNativeEvidence": ("native_evidence", frozenset({"RepositorySource"})),
    "RepositoryRelationships": (
        "evidence_graph",
        frozenset({"RepositoryImports", "RepositoryNativeEvidence"}),
    ),
    "RepositoryStructure": (
        "structural_locality",
        frozenset(
            {
                "RepositorySource",
                "RepositoryImports",
                "RepositoryNativeEvidence",
                "RepositoryRelationships",
            }
        ),
    ),
    "RepositorySearch": ("find_engine", frozenset({"RepositoryNativeEvidence"})),
    "RepositoryContext": (
        "repository_context",
        frozenset({"RepositorySource", "RepositorySearch", "RepositoryRelationships"}),
    ),
    "RepositoryOwnership": (
        "ownership_graph",
        frozenset(
            {
                "RepositorySource",
                "RepositoryImports",
                "RepositoryStructure",
                "RepositorySearch",
            }
        ),
    ),
    "RepositoryVerification": (
        "evidence_verification",
        frozenset({"RepositoryImports"}),
    ),
    "RepositoryTasks": (
        "repository_tasks",
        frozenset(
            {
                "RepositorySearch",
                "RepositoryOwnership",
                "RepositoryVerification",
                "RepositoryRelationships",
                "RepositoryContext",
            }
        ),
    ),
    "RepositoryBindings": (
        "repository_evidence_bindings",
        frozenset({"RepositorySource"}),
    ),
    "RepositoryCorrelation": (
        "evidence_correlation",
        frozenset({"RepositoryBindings"}),
    ),
    "RepositoryDeclarations": (
        "repository_declarations",
        frozenset({"RepositoryBindings"}),
    ),
    "RepositoryDependencies": (
        "repository_dependencies",
        frozenset({"RepositorySource", "RepositoryImports", "RepositoryCorrelation"}),
    ),
    "RepositoryChanges": (
        "repository_changes",
        frozenset({"RepositoryTasks", "RepositoryRelationships"}),
    ),
    "RepositoryCrossRepository": (
        "cross_repository_evidence",
        frozenset({"RepositoryChanges"}),
    ),
    "RepositoryEconomics": ("intelligence_economics", frozenset({"RepositoryChanges"})),
    "RepositoryViews": (
        "repository_intelligence_query",
        frozenset(
            {
                "RepositoryChanges",
                "RepositoryCrossRepository",
                "RepositoryEconomics",
                "RepositoryStructure",
            }
        ),
    ),
    "WorktreeOverlay": (
        "worktree_overlay",
        frozenset({"RepositoryIndex", "RepositorySearch", "DecisionScope"}),
    ),
}
QUALIFIED_COMPONENTS = {
    f"hashmarks.codemap.{module}.{name}": name
    for name, (module, _) in COMPONENTS.items()
}
ROOT_SYMBOLS = {
    "hashmarks.CodeMap",
    "hashmarks.codemap.CodeMap",
    "hashmarks.codemap.engine.CodeMap",
}
ROOT_IMPORT_SITES = {"engine.py", "service.py", "worktree_overlay.py", "__init__.py"}
INTERNAL_COMPONENTS = {
    "RepositoryObservationSource",
    "RepositoryImports",
    "WorktreeOverlay",
}

CACHE_OWNERS = {
    "_snapshot_reuse": "RepositoryChanges",
    "_impact_owner_reuse": "RepositoryChanges",
    "_ownership_import_reuse": "RepositoryOwnership",
    "_reverse_file_graph_cache": "RepositoryRelationships",
    "_context_flight": "RepositoryContext",
    "_find_flight": "RepositorySearch",
    "_task_result_cache": "RepositorySearch",
    "_task_recent_retrieval_paths": "RepositorySearch",
    "_task_authority_paths_cache": "RepositoryTasks",
    "_task_recent_authority_paths": "RepositoryTasks",
    "_task_action_reuse": "RepositoryTasks",
    "_task_observation_reuse": "RepositoryTasks",
    **{
        name: "DecisionScope"
        for name in (
            "_symbols_cache",
            "_file_row_cache",
            "_module_paths_cache",
            "_exact_symbols_cache",
            "_refs_cache",
            "_edges_from_cache",
            "_edges_for_path_cache",
            "_df_cache",
            "_candidates_cache",
            "_repository_identity_cache",
        )
    },
}
FAMILY_MODULES = {
    **{module: name for name, (module, _) in COMPONENTS.items()},
    **{
        module: "RepositoryChanges"
        for module in (
            "repository_delta",
            "change_impact",
            "post_change",
            "change_intelligence",
            "freshness_map",
        )
    },
    **{
        module: "RepositorySearch"
        for module in (
            "task_retrieval",
            "retrieval_diagnostics",
        )
    },
    **{
        module: "RepositoryTasks"
        for module in (
            "task_freshness",
            "task_action_projection",
            "task_entry_points",
            "task_verification",
            "task_receipts",
            "relationships",
            "evidence_packet",
            "evidence_decision_packet",
            "task_evidence_retrieval",
            "task_evidence_scoped_method",
            "configuration_evidence",
        )
    },
    **{
        module: "RepositoryOwnership"
        for module in (
            "ownership_analysis",
            "ownership_candidates",
            "ownership_candidate_evidence",
            "ownership_candidate_resolution",
            "ownership_nomination",
        )
    },
    "work_context": "RepositoryContext",
}


def _imports(tree: ast.Module, package: str = "hashmarks.codemap") -> dict[str, str]:
    result: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = (
                importlib.util.resolve_name(
                    "." * node.level + (node.module or ""), package
                )
                if node.level
                else node.module or ""
            )
            result.update(
                {
                    alias.asname or alias.name: f"{module}.{alias.name}"
                    for alias in node.names
                }
            )
        elif isinstance(node, ast.Import):
            result.update(
                {
                    alias.asname or alias.name.split(".")[0]: alias.name
                    if alias.asname
                    else alias.name.split(".")[0]
                    for alias in node.names
                }
            )
    return result


def _qualified(node: ast.AST, imports: dict[str, str]) -> str:
    if isinstance(node, ast.Name):
        return imports.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        return _qualified(node.value, imports) + "." + node.attr
    return ""


def _constructor_edges(tree: ast.Module, name: str) -> frozenset[str]:
    owner = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == name
    )
    constructor = next(
        node
        for node in owner.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    imports = _imports(tree)
    arguments = [
        *constructor.args.posonlyargs,
        *constructor.args.args,
        *constructor.args.kwonlyargs,
    ]
    edges: set[str] = set()
    for argument in arguments:
        if argument.annotation is None:
            assert argument.arg == "self", (
                name,
                argument.arg,
                "untyped constructor input",
            )
            continue
        annotation = argument.annotation
        if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
            annotation = ast.parse(annotation.value, mode="eval").body
        edges.update(
            QUALIFIED_COMPONENTS[value]
            for node in ast.walk(annotation)
            if (value := _qualified(node, imports)) in QUALIFIED_COMPONENTS
        )
    return frozenset(edges)


def _lower_owners(
    name: str, edges: dict[str, frozenset[str]], trail: tuple[str, ...] = ()
) -> set[str]:
    if name in trail:
        raise AssertionError("component cycle: " + " -> ".join((*trail, name)))
    lower: set[str] = set()
    for child in edges[name]:
        lower.add(child)
        lower.update(_lower_owners(child, edges, (*trail, name)))
    return lower


def _root_imports(tree: ast.Module, package: str = "hashmarks.codemap") -> set[str]:
    imports = _imports(tree, package)
    found = set(imports.values()) & ROOT_SYMBOLS
    found.update(
        value
        for node in ast.walk(tree)
        if (value := _qualified(node, imports)) in ROOT_SYMBOLS
    )
    return found


def _cache_writes(tree: ast.Module, module: str) -> list[str]:
    mutations = {
        "clear",
        "update",
        "setdefault",
        "pop",
        "popitem",
        "append",
        "extend",
        "add",
        "discard",
        "remove",
        "__setitem__",
    }
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
            target: ast.AST = node
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store):
            target = node.value
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in mutations
        ):
            target = node.func.value
        else:
            continue
        slots = {
            child.attr
            for child in ast.walk(target)
            if isinstance(child, ast.Attribute) and child.attr in CACHE_OWNERS
        }
        violations.extend(
            f"{module}:{node.lineno}:{slot}"
            for slot in sorted(slots)
            if FAMILY_MODULES.get(module) != CACHE_OWNERS[slot]
        )
    return violations


def _root_callbacks(
    owner: ast.ClassDef, imports: dict[str, str], methods: set[str]
) -> list[str]:
    problems: list[str] = []
    for node in ast.walk(owner):
        if (
            not isinstance(node, ast.Call)
            or _qualified(node.func, imports) not in QUALIFIED_COMPONENTS
        ):
            continue
        for argument in [*node.args, *(keyword.value for keyword in node.keywords)]:
            if isinstance(argument, ast.Name) and argument.id == "self":
                problems.append("borrowed root")
            if any(
                isinstance(child, ast.Lambda)
                and any(
                    isinstance(value, ast.Name) and value.id == "self"
                    for value in ast.walk(child)
                )
                for child in ast.walk(argument)
            ):
                problems.append("root callback")
            if (
                isinstance(argument, ast.Attribute)
                and isinstance(argument.value, ast.Name)
                and argument.value.id == "self"
                and argument.attr in methods
            ):
                problems.append("bound root callback")
    return problems


def _root_contract(tree: ast.Module) -> list[str]:
    owner = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "CodeMap"
    )
    methods = {node.name for node in owner.body if isinstance(node, ast.FunctionDef)}
    imports = _imports(tree)
    properties = {
        node.name: node
        for node in owner.body
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(decorator, ast.Name) and decorator.id == "property"
            for decorator in node.decorator_list
        )
    }
    allowed = {
        "__init__",
        "_open_resources",
        "_compose_components",
        "__enter__",
        "__exit__",
        "close",
        *properties,
    }
    problems = [f"root method:{name}" for name in sorted(methods - allowed)]
    if owner.bases:
        problems.append("root domain inheritance")
    if any(isinstance(node, (ast.Assign, ast.AnnAssign)) for node in owner.body):
        problems.append("root class alias")
    exposed = {
        QUALIFIED_COMPONENTS.get(_qualified(node.returns, imports), "")
        for node in properties.values()
        if node.returns is not None
    }
    if exposed != set(COMPONENTS) - INTERNAL_COMPONENTS:
        problems.append("root component property inventory")
    problems.extend(_root_callbacks(owner, imports, methods - properties.keys()))
    return problems


def _missing_family_modules(modules: dict[str, str]) -> list[str]:
    return sorted(
        module for module in modules if not (CODEMAP / f"{module}.py").is_file()
    )


def test_component_family_inventory_resolves_current_source_modules() -> None:
    assert _missing_family_modules(FAMILY_MODULES) == []


def test_nonexistent_family_control_is_rejected_by_the_same_inventory_check() -> None:
    assert _missing_family_modules(
        {**FAMILY_MODULES, "_missing_component_family": "RepositorySearch"}
    ) == ["_missing_component_family"]


def test_real_component_constructor_and_import_directions_are_closed() -> None:
    trees = {
        name: read_python_ast(CODEMAP / f"{module}.py").tree
        for name, (module, _) in COMPONENTS.items()
    }
    edges = {name: _constructor_edges(tree, name) for name, tree in trees.items()}
    assert edges == {name: expected for name, (_, expected) in COMPONENTS.items()}
    for name, tree in trees.items():
        lower = _lower_owners(name, edges) | {name}
        imported = set(_imports(tree).values()) & QUALIFIED_COMPONENTS.keys()
        assert {QUALIFIED_COMPONENTS[value] for value in imported} <= lower, name


def test_domain_modules_do_not_import_or_cast_the_composition_root() -> None:
    violations: list[str] = []
    for path in sorted(CODEMAP.rglob("*.py")):
        if path.parent == CODEMAP and path.name in ROOT_IMPORT_SITES:
            continue
        package = "hashmarks." + ".".join(
            path.parent.relative_to(ROOT / "hashmarks").parts
        )
        if _root_imports(read_python_ast(path).tree, package):
            violations.append(path.relative_to(ROOT).as_posix())
    assert violations == []


def test_reserved_cache_writes_belong_to_one_component() -> None:
    violations = [
        finding
        for path in sorted(CODEMAP.glob("*.py"))
        for finding in _cache_writes(read_python_ast(path).tree, path.stem)
    ]
    assert violations == []


def test_construction_root_exposes_only_named_component_and_lifetime_operations() -> (
    None
):
    assert _root_contract(read_python_ast(CODEMAP / "engine.py").tree) == []


def test_root_back_reference_control_resolves_alias_and_type_only_import() -> None:
    tree = ast.parse(
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n from .engine import CodeMap as Root\nclass Fake:\n def __init__(self, root: Root): self.codemap = root\n"
    )
    assert _root_imports(tree) == {"hashmarks.codemap.engine.CodeMap"}


@pytest.mark.parametrize(
    "statement",
    [
        "self._snapshot_reuse = {}",
        "self.changes._snapshot_reuse.entries.clear()",
        "self._snapshot_reuse.entries[key] = value",
        "self._snapshot_reuse.entries |= other",
    ],
)
def test_wrong_owner_write_controls_use_the_real_state_guard(statement: str) -> None:
    tree = ast.parse(
        "class RepositoryTasks:\n def mutate(self):\n  " + statement + "\n"
    )
    assert _cache_writes(tree, "repository_tasks")
    assert _cache_writes(tree, "repository_changes") == []


def test_dependency_cycle_control_is_rejected_by_the_real_graph_check() -> None:
    edges = {name: expected for name, (_, expected) in COMPONENTS.items()}
    edges["RepositorySource"] |= {"RepositoryTasks"}
    with pytest.raises(AssertionError, match="component cycle"):
        _lower_owners("RepositoryTasks", edges)


@pytest.mark.parametrize(
    "argument,reason",
    [
        ("self", "borrowed root"),
        ("lambda: self.source", "root callback"),
        ("self._compose_components", "bound root callback"),
    ],
)
def test_root_callback_controls_use_the_same_construction_guard(
    argument: str, reason: str
) -> None:
    real = read_python_ast(CODEMAP / "engine.py").source
    tree = ast.parse(
        real.replace(
            "RepositoryBindings(self.source)", f"RepositoryBindings({argument})"
        )
    )
    assert reason in _root_contract(tree)


def test_retired_alias_control_is_rejected_by_the_same_root_guard() -> None:
    real = read_python_ast(CODEMAP / "engine.py").source
    tree = ast.parse(
        real.replace(
            "class CodeMap:",
            "class CodeMap:\n    task_evidence = RepositoryTasks.evidence",
        )
    )
    assert "root class alias" in _root_contract(tree)
