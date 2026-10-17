"""Bounded direct Python function syntax, without runtime boundary inference.

The caller owns source/index/revision qualification. This source-only observer
uses that caller's cached AST and never reads files, resolves callees, follows
calls, or establishes task, message, transaction or execution ownership.
"""

from __future__ import annotations

import ast
import math
from collections.abc import Mapping, Sequence
from typing import Any

MAX_BOUNDARY_FUNCTIONS = 4
MAX_BOUNDARY_SITES = 32
MAX_BOUNDARY_ARGUMENTS = 8
MAX_BOUNDARY_LITERAL_CHARS = 128


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


def _argument_value(node: ast.expr) -> dict[str, object]:
    identifier = _identifier(node)
    if identifier is not None:
        return {"state": "identifier-syntax", "identifier": identifier}
    if not isinstance(node, ast.Constant):
        return {
            "state": "expression-unestablished",
            "expression_kind": type(node).__name__,
        }
    value = node.value
    kinds = {
        type(None): "none",
        bool: "bool",
        str: "string",
        int: "integer",
        float: "float",
    }
    kind = kinds.get(type(value))
    if kind is None:
        return {"state": "unsupported-literal", "kind": type(value).__name__}
    over_bound = (
        isinstance(value, str)
        and len(value) > MAX_BOUNDARY_LITERAL_CHARS
        or type(value) is int
        and value.bit_length() > 256
        or isinstance(value, float)
        and not math.isfinite(value)
    )
    if over_bound:
        return {"state": "literal-over-bound", "kind": kind}
    if type(value) is int:
        # JSON consumers may decode numbers as binary64. Keep the exact Python
        # literal without asking a transport to preserve arbitrary precision.
        return {
            "state": "literal-syntax",
            "kind": kind,
            "value": str(value),
            "encoding": "decimal-text",
        }
    return {"state": "literal-syntax", "kind": kind, "value": value}


def _keyword_argument(node: ast.keyword) -> dict[str, object]:
    name = node.arg
    over_bound = name is not None and len(name) > 256
    return {
        "name": None if over_bound else name,
        "name_state": "over-bound"
        if over_bound
        else "mapping-expansion"
        if name is None
        else "literal",
        "expansion": name is None,
        "value": _argument_value(node.value),
    }


def _call_arguments(node: ast.Call) -> dict[str, object]:
    """Describe source arguments without evaluating values or binding a call."""
    positional = [
        {
            "position": position,
            "expansion": isinstance(argument, ast.Starred),
            "value": _argument_value(
                argument.value if isinstance(argument, ast.Starred) else argument
            ),
        }
        for position, argument in enumerate(node.args[:MAX_BOUNDARY_ARGUMENTS])
    ]
    keywords = [
        _keyword_argument(argument)
        for argument in node.keywords[:MAX_BOUNDARY_ARGUMENTS]
    ]
    omitted_positional = max(0, len(node.args) - len(positional))
    omitted_keywords = max(0, len(node.keywords) - len(keywords))
    return {
        "positional": positional,
        "keywords": keywords,
        "omitted_positional_count": omitted_positional,
        "omitted_keyword_count": omitted_keywords,
        "truncation": "truncated"
        if omitted_positional or omitted_keywords
        else "complete",
        "runtime_binding": "not-established",
    }


class _BoundarySites(ast.NodeVisitor):
    def __init__(self) -> None:
        self.sites: list[dict[str, Any]] = []

    def _add(
        self,
        node: ast.expr | ast.stmt | ast.ExceptHandler,
        kind: str,
        **details: object,
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
            awaited_identifier_syntax=_identifier(node.value),
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
            **(
                {"argument_syntax": _call_arguments(node)}
                if node.args or node.keywords
                else {}
            ),
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
                    "context_identifier_syntax": _identifier(item.context_expr),
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

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._add(
            node,
            "async-for",
            iterator_expression_kind=type(node.iter).__name__,
            callee_identifier_syntax=_callee(node.iter),
            iterator_identifier_syntax=_identifier(node.iter),
            target_expression_kind=type(node.target).__name__,
            target_identifier_syntax=_identifier(node.target),
        )
        self.generic_visit(node)

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
            "positional_arguments_per_call": MAX_BOUNDARY_ARGUMENTS,
            "keyword_arguments_per_call": MAX_BOUNDARY_ARGUMENTS,
            "literal_chars": MAX_BOUNDARY_LITERAL_CHARS,
        },
        "authority": "direct-static-syntax-only",
        "callee_resolution": "not-established",
        "runtime_boundary_kind": "not-established",
        "task_ownership": "not-established",
        "execution_order": "not-established",
        "negative_evidence_admissible": False,
    }
