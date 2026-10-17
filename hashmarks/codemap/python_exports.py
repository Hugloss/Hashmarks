from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum


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
class _ExportBinding:
    kind: str
    targets: tuple[str, ...] = ()
    declaration: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | None = None


def _export_binding(tree: ast.Module, name: str) -> _ExportBinding:
    bindings: list[_ExportBinding] = []
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and node.value is None and bindings:
            continue
        binding = _statement_export_binding(node, name)
        if binding is not None:
            bindings.append(binding)
    reexports = [row for row in bindings if row.kind in {"reexport", "star", "module"}]
    if len(reexports) > 1:
        targets = tuple(dict.fromkeys(t for row in reexports for t in row.targets))
        return _ExportBinding("ambiguous", targets)
    return bindings[-1] if bindings else _ExportBinding("unknown")


def python_export_binding(
    tree: ast.Module, exported_name: str
) -> tuple[str, list[str]]:
    """Preserve ordered binding qualification under the canonical syntax owner."""
    binding = _export_binding(tree, exported_name)
    return binding.kind, list(binding.targets)


def python_export_is_declaration(tree: ast.Module, exported_name: str) -> bool:
    return _export_binding(tree, exported_name).declaration is not None


def _binding_children(node: ast.AST) -> list[ast.AST]:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        body = set(node.body)
        return [child for child in ast.iter_child_nodes(node) if child not in body]
    if isinstance(node, ast.Lambda):
        return [node.args]
    if isinstance(node, ast.comprehension):
        return [node.iter, *node.ifs]
    return list(ast.iter_child_nodes(node))


def _writes_name(node: ast.AST, name: str) -> bool:
    # Nested bodies are local; definition headers and walrus expressions can
    # still bind the containing scope. Comprehension iteration targets are local.
    if (
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name == name
    ):
        return True
    if isinstance(node, ast.Name):
        return node.id == name and isinstance(node.ctx, (ast.Store, ast.Del))
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return any((a.asname or a.name.split(".")[0]) == name for a in node.names)
    if (
        isinstance(
            node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar, ast.MatchMapping)
        )
        and getattr(node, "name", getattr(node, "rest", None)) == name
    ):
        return True
    return any(_writes_name(child, name) for child in _binding_children(node))


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
        arguments = [
            *function.args.posonlyargs,
            *function.args.args,
            *function.args.kwonlyargs,
        ]
        arguments.extend(
            arg
            for arg in (function.args.vararg, function.args.kwarg)
            if arg is not None
        )
        if any(argument.arg == name for argument in arguments) or any(
            _writes_name(statement, name) for statement in function.body
        ):
            return True
    return False


def _statement_export_binding(node: ast.stmt, name: str) -> _ExportBinding | None:
    if (
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name == name
    ):
        return _ExportBinding("local", declaration=node)
    if isinstance(node, ast.ImportFrom):
        kind, targets = _import_from_binding(node, name)
        return _ExportBinding(kind, tuple(targets)) if targets else None
    if isinstance(node, ast.Import):
        targets = tuple(
            alias.name if alias.asname else alias.name.split(".")[0]
            for alias in node.names
            if (alias.asname or alias.name.split(".")[0]) == name
        )
        return _ExportBinding("module", targets) if targets else None
    if not _writes_name(node, name):
        return None
    if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        return _ExportBinding("local")
    return _ExportBinding("ambiguous")


def python_class_node(tree: ast.Module, qualname: str) -> ast.ClassDef | None:
    """Qualify every class component with the same ordered binding analysis."""
    body = tree.body
    selected: ast.ClassDef | None = None
    for part in qualname.split("."):
        binding = _export_binding(ast.Module(body=body, type_ignores=[]), part)
        if not isinstance(binding.declaration, ast.ClassDef):
            return None
        selected = binding.declaration
        body = selected.body
    return selected


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
