from __future__ import annotations

import ast


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
