"""Bounded direct Python function syntax, without runtime boundary inference.

The caller owns source/index/revision qualification. This source-only observer
uses that caller's cached AST and never reads files, resolves callees, follows
calls, or establishes task, message, transaction or execution ownership.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from typing import Any

MAX_BOUNDARY_FUNCTIONS = 4
MAX_BOUNDARY_SITES = 32


def _identifier(node: ast.expr) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute) and len(parts) < 8:
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    value = ".".join([node.id, *reversed(parts)])
    return value if len(value) <= 256 else None


def _callee(node: ast.expr) -> str | None:
    return _identifier(node.func) if isinstance(node, ast.Call) else None


class _BoundarySites(ast.NodeVisitor):
    def __init__(self) -> None:
        self.sites: list[dict[str, Any]] = []

    def _add(
        self, node: ast.expr | ast.stmt | ast.ExceptHandler, kind: str, **details: Any
    ) -> None:
        self.sites.append(
            {
                "syntax_kind": kind,
                "line": node.lineno,
                "end_line": node.end_lineno,
                "column": node.col_offset,
                "end_column": node.end_col_offset,
                **details,
            }
        )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # Nested definitions are outside the declared lexical body scope.
        pass

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        pass

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        pass

    def visit_Lambda(self, node: ast.Lambda) -> None:
        pass

    def visit_Await(self, node: ast.Await) -> None:
        self._add(
            node,
            "await",
            expression_kind=type(node.value).__name__,
            callee_identifier_syntax=_callee(node.value),
        )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        self._add(
            node,
            "call",
            callee_identifier_syntax=_identifier(node.func),
            callee_expression_kind=type(node.func).__name__,
            callee_member_syntax=(
                node.func.attr
                if isinstance(node.func, ast.Attribute) and len(node.func.attr) <= 256
                else None
            ),
            callee_member_state=(
                "over-bound"
                if isinstance(node.func, ast.Attribute) and len(node.func.attr) > 256
                else "literal-member-syntax"
                if isinstance(node.func, ast.Attribute)
                else "not-member-syntax"
            ),
            positional_argument_count=len(node.args),
            has_argument_expansion=any(
                isinstance(arg, ast.Starred) for arg in node.args
            )
            or any(keyword.arg is None for keyword in node.keywords),
        )
        self.generic_visit(node)

    def _context(self, node: ast.With | ast.AsyncWith, kind: str) -> None:
        self._add(
            node,
            kind,
            context_expressions=[
                {
                    "expression_kind": type(item.context_expr).__name__,
                    "callee_identifier_syntax": _callee(item.context_expr),
                    "binding_identifier_syntax": (
                        item.optional_vars.id
                        if isinstance(item.optional_vars, ast.Name)
                        else None
                    ),
                }
                for item in node.items[:8]
            ],
            omitted_context_expressions=max(0, len(node.items) - 8),
        )
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        self._context(node, "with")

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._context(node, "async-with")

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self._add(
            node,
            "exception-handler",
            exception_identifier_syntax=(
                _identifier(node.type) if node.type is not None else None
            ),
            exception_expression_kind=(
                type(node.type).__name__ if node.type is not None else "bare-except"
            ),
        )
        self.generic_visit(node)


def _function_sites(
    node: ast.FunctionDef | ast.AsyncFunctionDef, span: Mapping[str, Any]
) -> dict[str, Any]:
    visitor = _BoundarySites()
    for statement in node.body:
        visitor.visit(statement)
    # Prefer facts on caller-reported lines, without claiming an edit or an
    # execution sequence. The final emitted ordering is physical source order.
    sites = sorted(
        visitor.sites,
        key=lambda row: (
            not (
                row["line"] <= span["end_line"]
                and row["end_line"] >= span["start_line"]
            ),
            row["line"],
            row["column"],
            row["syntax_kind"],
        ),
    )[:MAX_BOUNDARY_SITES]
    return {
        "declaration_syntax": "async"
        if isinstance(node, ast.AsyncFunctionDef)
        else "sync",
        "sites": sorted(
            sites, key=lambda row: (row["line"], row["column"], row["syntax_kind"])
        ),
        "observed_site_count": len(visitor.sites),
        "omitted_site_count": max(0, len(visitor.sites) - len(sites)),
        "truncation": "truncated" if len(visitor.sites) > len(sites) else "complete",
    }


def observe_function_boundaries(
    tree: ast.Module,
    symbols: Sequence[Mapping[str, Any]],
    span: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind direct body syntax to exact already indexed declaration ranges."""
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    selected = [row for row in symbols if row.get("kind") in {"function", "method"}]
    observations: list[dict[str, Any]] = []
    for row in selected[:MAX_BOUNDARY_FUNCTIONS]:
        matches = [
            node
            for node in functions
            if node.lineno == row.get("start_line")
            and node.end_lineno == row.get("end_line")
            and node.name == row.get("name")
        ]
        bound = len(matches) == 1
        observations.append(
            {
                "subject": f"{span['path']}::{row['qualname']}",
                "state": "source-index-bound" if bound else "unresolved",
                "reason": None if bound else "unique-ast-index-correspondence-unproven",
                **(_function_sites(matches[0], span) if bound else {}),
            }
        )
    return {
        "state": "bounded-direct-function-syntax",
        "scope": "selected function bodies excluding nested def/class/lambda subtrees",
        "column_encoding": "utf8-byte-offset",
        "observations": observations,
        "omitted_function_count": max(0, len(selected) - MAX_BOUNDARY_FUNCTIONS),
        "bounds": {
            "functions": MAX_BOUNDARY_FUNCTIONS,
            "sites_per_function": MAX_BOUNDARY_SITES,
        },
        "authority": "direct-static-syntax-only",
        "callee_resolution": "not-established",
        "runtime_boundary_kind": "not-established",
        "task_ownership": "not-established",
        "execution_order": "not-established",
        "negative_evidence_admissible": False,
    }
