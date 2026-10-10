"""Direct, bounded Python decorator-to-declaration evidence for changed lines.

The canonical symbol range begins at the def/class line. Decorators precede
that range, so a changed decorator is not an indexed symbol overlap. This
request-local syntax observation preserves that distinction and never claims
route registration, runtime impact, or a relationship edge.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from typing import Protocol

MAX_DECORATOR_SOURCE_BYTES = 262_144
MAX_DECORATOR_ASSOCIATIONS = 16
MAX_DECLARATION_POINT_CANDIDATES = 33


class _SymbolRangeStore(Protocol):
    def symbols_overlapping_lines(
        self, path: str, start_line: int, end_line: int, *, limit: int
    ) -> list[dict[str, object]]: ...


def _unresolved(reason: str) -> dict[str, object]:
    return {
        "state": "unresolved",
        "reason": reason,
        "coverage": "unknown",
        "associations": [],
        "negative_evidence_admissible": False,
    }


def _decorator_hits(
    source: str, path: str, start_line: int, end_line: int
) -> list[tuple[int, str, list[dict[str, int]]]]:
    tree = ast.parse(source, filename=path)
    hits: list[tuple[int, str, list[dict[str, int]]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        matched = [
            {
                "start_line": decorator.lineno,
                "end_line": decorator.end_lineno or decorator.lineno,
            }
            for decorator in node.decorator_list
            if decorator.lineno <= end_line
            and (decorator.end_lineno or decorator.lineno) >= start_line
        ]
        if matched:
            hits.append((node.lineno, node.name, matched))
    return sorted(hits, key=lambda row: (row[2][0]["start_line"], row[0], row[1]))


def _qualified_declaration(
    store: _SymbolRangeStore, path: str, line: int, name: str
) -> Mapping[str, object] | None:
    candidates = store.symbols_overlapping_lines(
        path, line, line, limit=MAX_DECLARATION_POINT_CANDIDATES
    )
    # Do not use a truncated set to establish uniqueness, even if one row
    # happens to match the syntax. A distinct symbol is not an exact owner.
    if len(candidates) >= MAX_DECLARATION_POINT_CANDIDATES:
        return None
    matches = [
        row
        for row in candidates
        if row["start_line"] == line
        and row["name"] == name
        and row["kind"] in {"function", "method", "class"}
    ]
    return matches[0] if len(matches) == 1 else None


def observe_python_decorator_associations(
    store: _SymbolRangeStore,
    path: str,
    raw: bytes,
    span: Mapping[str, int],
) -> dict[str, object] | None:
    """Associate edited decorators with *current* indexed declarations only.

    Returns None for non-Python files; callers separately establish revision,
    visibility and read-after-observation stability.
    """
    if not path.endswith(".py"):
        return None
    if len(raw) > MAX_DECORATOR_SOURCE_BYTES:
        return _unresolved("python-decorator-source-over-bound")
    try:
        hits = _decorator_hits(
            raw.decode("utf-8"), path, span["start_line"], span["end_line"]
        )
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return _unresolved("python-decorator-syntax-unavailable")

    associations: list[dict[str, object]] = []
    unresolved = 0
    for declaration_line, name, decorators in hits[:MAX_DECORATOR_ASSOCIATIONS]:
        row = _qualified_declaration(store, path, declaration_line, name)
        if row is None:
            unresolved += 1
            continue
        subject = f"{path}::{row['qualname']}"
        associations.append(
            {
                "subject": subject,
                "path": path,
                "name": row["name"],
                "qualname": row["qualname"],
                "kind": row["kind"],
                "declaration_line": declaration_line,
                "indexed_symbol_range": {
                    "start_line": row["start_line"],
                    "end_line": row["end_line"],
                },
                "overlapping_decorator_ranges": decorators,
                "relationship_detail": {
                    "target": subject,
                    "result_mode": "relationships",
                },
                "basis": "direct-current-python-ast-decorator-and-indexed-declaration",
                "runtime_registration": "not-asserted",
                "semantic_impact": "not-asserted",
            }
        )
    return {
        "state": "bounded-python-decorator-syntax",
        "coverage": "observed-source-syntax-only",
        "matched_declaration_count": len(hits),
        "retained_count": len(associations),
        "unresolved_count": unresolved,
        "omitted_count": max(0, len(hits) - MAX_DECORATOR_ASSOCIATIONS),
        "association_limit": MAX_DECORATOR_ASSOCIATIONS,
        "associations": associations,
        "negative_evidence_admissible": False,
    }
