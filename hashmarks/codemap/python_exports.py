from __future__ import annotations

import ast
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from types import MappingProxyType


def static_string_names(value: ast.expr | None) -> list[str] | None:
    """Return a static string collection, or None when runtime evaluation is needed."""
    if not isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        return None
    names: list[str] = []
    for item in value.elts:
        if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
            return None
        names.append(item.value)
    return names


def python_reexport_targets(tree: ast.Module, exported_name: str) -> list[str]:
    """Return at most sixteen distinct top-level import targets in source order."""
    targets: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        _, candidates = _import_from_binding(node, exported_name)
        for target in candidates:
            if target not in targets:
                targets.append(target)
            if len(targets) >= 16:
                return targets
    return targets


@dataclass(frozen=True, slots=True)
class PythonExportBinding:
    kind: str
    targets: tuple[str, ...] = ()
    declaration: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | None = None


@dataclass(frozen=True, slots=True)
class PythonExportBindings:
    """Read-only binding syntax within one already parsed file snapshot."""

    body: tuple[ast.stmt, ...]
    writes: Mapping[ast.stmt, frozenset[str]]

    def binding(self, name: str) -> PythonExportBinding:
        return _export_binding(self.body, name, self.writes)


@lru_cache(maxsize=256)
def python_export_bindings(
    absolute_path: str,
    source_identity: tuple[int, int, int, int, int],
    tree: ast.Module,
) -> PythonExportBindings:
    """Index one stable, read-only AST; callers retain freshness/visibility authority.

    Path, full parser-snapshot identity and the actual tree bind this disposable
    acceleration. Source-only APIs remain uncached and observe their input tree.
    """
    return PythonExportBindings(
        tuple(tree.body),
        MappingProxyType(
            {
                statement: frozenset(_binding_writes(statement))
                for statement in tree.body
            }
        ),
    )


def _export_binding(
    body: Sequence[ast.stmt],
    name: str,
    writes: Mapping[ast.stmt, frozenset[str]] | None = None,
) -> PythonExportBinding:
    bindings: list[PythonExportBinding] = []
    for node in body:
        if isinstance(node, ast.AnnAssign) and node.value is None and bindings:
            continue
        binding = _statement_export_binding(
            node, name, None if writes is None else writes.get(node)
        )
        if binding is not None:
            bindings.append(binding)
    reexports = [row for row in bindings if row.kind in {"reexport", "star", "module"}]
    if len(reexports) > 1:
        targets = tuple(dict.fromkeys(t for row in reexports for t in row.targets))
        return PythonExportBinding("ambiguous", targets)
    return bindings[-1] if bindings else PythonExportBinding("unknown")


def python_export_binding(
    tree: ast.Module, exported_name: str
) -> tuple[str, list[str]]:
    """Preserve ordered binding qualification under the canonical syntax owner."""
    binding = _export_binding(tree.body, exported_name)
    return binding.kind, list(binding.targets)


def python_export_is_declaration(tree: ast.Module, exported_name: str) -> bool:
    return _export_binding(tree.body, exported_name).declaration is not None


def _binding_children(node: ast.AST) -> list[ast.AST]:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        body = set(node.body)
        return [child for child in ast.iter_child_nodes(node) if child not in body]
    if isinstance(node, ast.Lambda):
        return [node.args]
    if isinstance(node, ast.comprehension):
        return [node.iter, *node.ifs]
    return list(ast.iter_child_nodes(node))


def _binding_nodes(node: ast.AST) -> Iterator[ast.AST]:
    yield node
    for child in _binding_children(node):
        yield from _binding_nodes(child)


def _class_global_names(node: ast.ClassDef) -> frozenset[str]:
    return frozenset(
        name
        for statement in node.body
        for child in _binding_nodes(statement)
        if isinstance(child, ast.Global)
        for name in child.names
    )


def _class_global_writes(node: ast.ClassDef) -> Iterator[str]:
    names = _class_global_names(node)
    for statement in node.body:
        yield from _binding_writes(statement, names)


def _node_binding_writes(node: ast.AST) -> Iterator[str]:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        yield node.name
    if isinstance(node, ast.Name):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            yield node.id
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        yield from (alias.asname or alias.name.split(".")[0] for alias in node.names)
    if isinstance(
        node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar, ast.MatchMapping)
    ):
        bound_name = getattr(node, "name", getattr(node, "rest", None))
        if isinstance(bound_name, str):
            yield bound_name


def _binding_writes(
    node: ast.AST,
    names: frozenset[str] | None = None,
    *,
    include_class_globals: bool = True,
) -> Iterator[str]:
    # Nested bodies are local; definition headers and walrus expressions can
    # still bind the containing scope. Comprehension iteration targets are local.
    if isinstance(node, ast.ClassDef) and include_class_globals:
        # Class construction executes its body now. Explicit global writes
        # escape that namespace, including writes by immediately nested classes.
        yield from _class_global_writes(node)
    yield from (
        name for name in _node_binding_writes(node) if names is None or name in names
    )
    for child in _binding_children(node):
        yield from _binding_writes(
            child, names, include_class_globals=include_class_globals
        )


def _writes_name(node: ast.AST, name: str) -> bool:
    return any(bound == name for bound in _binding_writes(node))


def _arguments_bind(arguments: ast.arguments, name: str) -> bool:
    positional = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
    positional.extend(
        arg for arg in (arguments.vararg, arguments.kwarg) if arg is not None
    )
    return any(argument.arg == name for argument in positional)


def _call_uses_name(node: ast.Call, name: str) -> bool:
    target = node.func
    while isinstance(target, ast.Attribute):
        target = target.value
    return isinstance(target, ast.Name) and target.id == name


def _expression_bound_call(
    node: ast.AST, name: str, line: int, bound: bool = False
) -> bool:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        # Headers execute before their declaration publishes its binding. The
        # final file binding therefore cannot qualify a self-named header call.
        # Decorators may precede the declaration's own lineno.
        return any(
            _expression_bound_call(child, name, line, bound or node.name == name)
            for child in _binding_children(node)
        )
    start = getattr(node, "lineno", None)
    if start is not None and not start <= line <= (
        getattr(node, "end_lineno", None) or start
    ):
        return False
    if (
        isinstance(node, ast.Call)
        and bound
        and node.lineno == line
        and _call_uses_name(node, name)
    ):
        return True
    if isinstance(node, ast.Lambda):
        defaults = [
            *node.args.defaults,
            *(value for value in node.args.kw_defaults if value is not None),
        ]
        return any(
            _expression_bound_call(value, name, line, bound) for value in defaults
        ) or _expression_bound_call(
            node.body,
            name,
            line,
            bound or _arguments_bind(node.args, name) or _writes_name(node.body, name),
        )
    if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
        local = bound or any(
            _writes_name(generator.target, name) for generator in node.generators
        )
        inside = [generator.iter for generator in node.generators[1:]]
        inside.extend(
            condition for generator in node.generators for condition in generator.ifs
        )
        inside.extend(
            (node.key, node.value) if isinstance(node, ast.DictComp) else (node.elt,)
        )
        return _expression_bound_call(
            node.generators[0].iter, name, line, bound
        ) or any(_expression_bound_call(value, name, line, local) for value in inside)
    return any(
        _expression_bound_call(child, name, line, bound)
        for child in _binding_children(node)
    )


def python_expression_call_binds(
    body: Sequence[ast.stmt], name: str, line: int
) -> bool:
    """Observe call-site shadowing without leaking expression locals into their parent.

    The compact call index has line coordinates only. A same-line collision
    therefore preserves uncertainty for every call with that receiver spelling.
    """
    return any(_expression_bound_call(statement, name, line) for statement in body)


def python_function_scope_binds(
    definitions: Mapping[str, tuple[ast.FunctionDef | ast.AsyncFunctionDef, ...]],
    qualname: str,
    name: str,
) -> bool:
    """Preserve local/closure shadowing before admitting module import identity.

    Unrelated methods and nested bodies cannot rebind this callable's names.
    Duplicate declarations or an unknown callable scope remain unresolved.
    """
    parts = qualname.split(".")
    for depth in range(1, len(parts) + 1):
        functions = definitions.get(".".join(parts[:depth]), ())
        if not functions and depth < len(parts):
            continue
        if len(functions) != 1:
            return True
        function = functions[0]
        if _arguments_bind(function.args, name) or any(
            _writes_name(statement, name) for statement in function.body
        ):
            return True
    return False


def _statement_export_binding(
    node: ast.stmt, name: str, writes: frozenset[str] | None = None
) -> PythonExportBinding | None:
    if (
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name == name
    ):
        return PythonExportBinding("local", declaration=node)
    if isinstance(node, ast.ImportFrom):
        kind, targets = _import_from_binding(node, name)
        return PythonExportBinding(kind, tuple(targets)) if targets else None
    if isinstance(node, ast.Import):
        targets = tuple(
            alias.name if alias.asname else alias.name.split(".")[0]
            for alias in node.names
            if (alias.asname or alias.name.split(".")[0]) == name
        )
        return PythonExportBinding("module", targets) if targets else None
    if not (_writes_name(node, name) if writes is None else name in writes):
        return None
    if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        return PythonExportBinding("local")
    return PythonExportBinding("ambiguous")


def _class_export_binding(node: ast.ClassDef, name: str) -> PythonExportBinding:
    if name in _class_global_names(node):
        return PythonExportBinding("ambiguous")
    writes = {
        statement: frozenset(_binding_writes(statement, include_class_globals=False))
        for statement in node.body
    }
    return _export_binding(node.body, name, writes)


def python_class_node(tree: ast.Module, qualname: str) -> ast.ClassDef | None:
    """Qualify every class component with the same ordered binding analysis."""
    selected: ast.ClassDef | None = None
    for part in qualname.split("."):
        binding = (
            _export_binding(tree.body, part)
            if selected is None
            else _class_export_binding(selected, part)
        )
        if not isinstance(binding.declaration, ast.ClassDef):
            return None
        selected = binding.declaration
    return selected


def python_class_member_binding(
    node: ast.ClassDef, name: str
) -> tuple[str, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | None]:
    """Expose the same ordered binding rule inside one declared class scope."""
    binding = _class_export_binding(node, name)
    return binding.kind, binding.declaration


def python_function_body_binds(
    node: ast.FunctionDef | ast.AsyncFunctionDef, name: str
) -> bool:
    """Observe writes in the body separately from formal argument bindings."""
    return any(_writes_name(statement, name) for statement in node.body)


def python_import_target(node: ast.ImportFrom, name: str) -> str:
    """One spelling for indexed and qualified relative import evidence."""
    prefix = "." * node.level + (node.module or "")
    return f"{prefix}.{name}" if node.module else f"{prefix}{name}"


def _import_from_binding(
    node: ast.ImportFrom, exported_name: str
) -> tuple[str, list[str]]:
    targets: list[str] = []
    star = False
    for alias in node.names:
        if alias.name == "*":
            star = True
            name = exported_name
        elif (alias.asname or alias.name) == exported_name:
            name = alias.name
        else:
            continue
        target = python_import_target(node, name)
        if target:
            targets.append(target)
    return "star" if star else "reexport", list(dict.fromkeys(targets))


def python_import_alias_targets(tree: ast.Module, name: str) -> list[tuple[str, str]]:
    """Nominate at most seventeen explicit top-level imported alias bindings."""
    rows: list[tuple[str, str]] = []
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        for alias in node.names:
            if alias.name == name:
                rows.append(
                    (alias.asname or alias.name, python_import_target(node, name))
                )
                if len(rows) == 17:
                    return rows
    return rows


class AllExportStatus(Enum):
    """Distinguish implicit exports from an explicitly unprovable declaration."""

    ABSENT = "absent"
    UNKNOWN = "unknown"


def static_all_exports(tree: ast.Module) -> list[str] | AllExportStatus:
    """Interpret supported top-level ``__all__`` declarations in source order.

    Unknown declarations and deletion are terminal: a later assignment cannot
    restore authority. Only ABSENT permits the caller's implicit-symbol fallback.
    This parser reads syntax only; the caller owns repository identity/freshness.
    """
    exports: list[str] | AllExportStatus = AllExportStatus.ABSENT
    for node in tree.body:
        exports = _all_statement_exports(node, exports)
        if exports is AllExportStatus.UNKNOWN:
            break
    return exports


def _targets_all(targets: list[ast.expr]) -> bool:
    return any(isinstance(item, ast.Name) and item.id == "__all__" for item in targets)


def _all_assignment(node: ast.stmt) -> ast.expr | None:
    match node:
        case ast.Assign(targets=targets, value=value) if _targets_all(targets):
            return value
        case ast.AnnAssign(target=ast.Name(id="__all__"), value=value):
            return value
    return None


def _all_statement_exports(
    node: ast.stmt, exports: list[str] | AllExportStatus
) -> list[str] | AllExportStatus:
    assigned = _all_assignment(node)
    if assigned is not None:
        names = static_string_names(assigned)
        return AllExportStatus.UNKNOWN if names is None else names
    match node:
        case ast.AugAssign(target=ast.Name(id="__all__"), op=op, value=value):
            if not isinstance(op, ast.Add):
                return AllExportStatus.UNKNOWN
            return _extend_all_exports(exports, value)
        case ast.Expr(
            value=ast.Call(
                func=ast.Attribute(value=ast.Name(id="__all__"), attr=method)
            ) as call
        ) if method in {"append", "extend"}:
            return _call_all_exports(exports, call, method)
        case ast.Delete(targets=targets) if _targets_all(targets):
            return AllExportStatus.UNKNOWN
    return exports


def _extend_all_exports(
    exports: list[str] | AllExportStatus, value: ast.expr
) -> list[str] | AllExportStatus:
    names = static_string_names(value)
    if not isinstance(exports, list) or names is None:
        return AllExportStatus.UNKNOWN
    exports.extend(names)
    return exports


def _call_all_exports(
    exports: list[str] | AllExportStatus, call: ast.Call, method: str
) -> list[str] | AllExportStatus:
    if not isinstance(exports, list) or call.keywords or len(call.args) != 1:
        return AllExportStatus.UNKNOWN
    if method == "extend":
        return _extend_all_exports(exports, call.args[0])
    arg = call.args[0]
    if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
        return AllExportStatus.UNKNOWN
    exports.append(arg.value)
    return exports
