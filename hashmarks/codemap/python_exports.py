from __future__ import annotations

import ast
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


def python_export_binding(
    tree: ast.Module, exported_name: str
) -> tuple[str, list[str]]:
    """Preserve statement ordering without resolving competing re-exports."""
    bindings = [
        binding
        for node in tree.body
        if (binding := _statement_export_binding(node, exported_name)) is not None
    ]
    reexports = [values for kind, values in bindings if kind in {"reexport", "star"}]
    if len(reexports) > 1:
        targets = [target for values in reexports for target in values]
        return "ambiguous", list(dict.fromkeys(targets))
    return bindings[-1] if bindings else ("unknown", [])


def _statement_export_binding(
    node: ast.stmt, exported_name: str
) -> tuple[str, list[str]] | None:
    match node:
        case (
            ast.FunctionDef(name=name)
            | ast.AsyncFunctionDef(name=name)
            | ast.ClassDef(name=name)
        ) if name == exported_name:
            return "local", []
        case ast.Assign(targets=targets) if any(
            isinstance(item, ast.Name) and item.id == exported_name for item in targets
        ):
            return "local", []
        case ast.AnnAssign(target=ast.Name(id=name)) if name == exported_name:
            return "local", []
        case ast.ImportFrom():
            kind, targets = _import_from_binding(node, exported_name)
            if targets:
                return kind, targets
    return None


def _import_from_binding(
    node: ast.ImportFrom, exported_name: str
) -> tuple[str, list[str]]:
    prefix = "." * int(node.level) + (node.module or "")
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
        target = f"{prefix}.{name}" if prefix else name
        if target:
            targets.append(target)
    return "star" if star else "reexport", list(dict.fromkeys(targets))


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
