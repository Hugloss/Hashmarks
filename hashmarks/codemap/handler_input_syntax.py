"""Bounded Python handler input syntax, shared by existing declaration observers.

Only AST syntax from an already admitted source member. No framework binding,
Pydantic validation, runtime dependency injection or callable resolution.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence
from typing import TypedDict

MAX_HANDLER_PARAMETERS = 16
MAX_ANNOTATION_CHARS = 192
MAX_DEFAULT_KEYWORDS = 8
MAX_ANNOTATED_METADATA = 4
MAX_DIRECT_NAME_CHARS = 128


class HandlerParameter(TypedDict):
    name: str
    kind: str
    start_line: int
    end_line: int
    annotation: dict[str, object]
    annotated_metadata: dict[str, object]
    default: dict[str, object]


def _annotation(node: ast.expr | None) -> dict[str, object]:
    if node is None:
        return {"state": "not-supplied"}
    try:
        value = ast.unparse(node)
    except (RecursionError, ValueError):
        return {"state": "dynamic-or-unsupported"}
    if len(value) > MAX_ANNOTATION_CHARS or "\n" in value:
        return {"state": "over-bound"}
    return {
        "state": "direct-annotation-syntax",
        "text": value,
        "start_line": node.lineno,
        "end_line": node.end_lineno or node.lineno,
    }


def _callee(node: ast.expr) -> dict[str, object]:
    if isinstance(node, ast.Name):
        if len(node.id) > MAX_DIRECT_NAME_CHARS:
            return {"state": "over-bound"}
        return {"state": "name-syntax", "name": node.id}
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        if (
            len(node.value.id) > MAX_DIRECT_NAME_CHARS
            or len(node.attr) > MAX_DIRECT_NAME_CHARS
        ):
            return {"state": "over-bound"}
        return {
            "state": "member-syntax",
            "receiver": node.value.id,
            "name": node.attr,
        }
    return {"state": "dynamic-or-unsupported"}


def _reference(node: ast.expr) -> dict[str, object]:
    """Direct literal target expression only: never an inferred object binding."""
    return _callee(node)


def _keyword_references(
    keywords: Sequence[tuple[str, ast.expr]],
) -> dict[str, object]:
    """Retain direct identifier syntax within the already returned keyword bound."""
    references = [(name, _reference(value)) for name, value in keywords]
    if not any(
        reference["state"] in {"name-syntax", "member-syntax"}
        for _name, reference in references
    ):
        return {}
    return {
        "keyword_references": [
            {"keyword": name, "reference": reference} for name, reference in references
        ],
        "keyword_reference_scope": "returned-direct-keyword-values",
    }


def _default(node: ast.expr | None) -> dict[str, object]:
    if node is None:
        return {"state": "not-supplied"}
    if isinstance(node, ast.Constant):
        return {
            "state": "literal-kind-only",
            "kind": (
                "none"
                if node.value is None
                else "bool"
                if type(node.value) is bool
                else "string"
                if type(node.value) is str
                else "integer"
                if type(node.value) is int
                else "float"
                if type(node.value) is float
                else "other-literal"
            ),
        }
    if not isinstance(node, ast.Call):
        return {"state": "dynamic-or-unsupported"}
    keywords = [
        (kw.arg if len(kw.arg) <= MAX_DIRECT_NAME_CHARS else "<over-bound>", kw.value)
        for kw in node.keywords
        if kw.arg is not None
    ]
    return {
        "state": "direct-call-syntax",
        "callee": _callee(node.func),
        "positional_count": len(node.args),
        "first_argument_reference": (
            _reference(node.args[0]) if node.args else {"state": "not-supplied"}
        ),
        "keyword_names": [name for name, _value in keywords[:MAX_DEFAULT_KEYWORDS]],
        "keyword_names_omitted": max(0, len(keywords) - MAX_DEFAULT_KEYWORDS),
        **_keyword_references(keywords[:MAX_DEFAULT_KEYWORDS]),
        "has_argument_expansion": any(isinstance(arg, ast.Starred) for arg in node.args)
        or any(kw.arg is None for kw in node.keywords),
        "runtime_binding": "not-established",
    }


def _metadata(annotation: ast.expr | None) -> dict[str, object]:
    if not isinstance(annotation, ast.Subscript):
        return {"state": "not-observed"}
    root = _callee(annotation.value)
    if root not in (
        {"state": "name-syntax", "name": "Annotated"},
        {"state": "member-syntax", "receiver": "typing", "name": "Annotated"},
    ):
        return {"state": "not-observed"}
    parts: Sequence[ast.expr] = (
        annotation.slice.elts
        if isinstance(annotation.slice, ast.Tuple)
        else (annotation.slice,)
    )
    if len(parts) < 2:
        return {"state": "unresolved"}
    values = parts[1:]
    return {
        "state": "direct-annotated-metadata-syntax",
        "observed_count": len(values),
        "omitted_count": max(0, len(values) - MAX_ANNOTATED_METADATA),
        "sites": [_default(part) for part in values[:MAX_ANNOTATED_METADATA]],
        "dependency_resolution": "not-established",
    }


def _parameter(node: ast.arg, kind: str, default: ast.expr | None) -> HandlerParameter:
    if len(node.arg) > MAX_DIRECT_NAME_CHARS:
        raise ValueError("handler parameter name exceeds identifier bound")
    return {
        "name": node.arg,
        "kind": kind,
        "start_line": node.lineno,
        "end_line": max(
            node.end_lineno or node.lineno,
            default.end_lineno or default.lineno
            if default is not None
            else node.lineno,
        ),
        "annotation": _annotation(node.annotation),
        "annotated_metadata": _metadata(node.annotation),
        "default": _default(default),
    }


def _all_parameters(
    declaration: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[HandlerParameter]:
    args = declaration.args
    count = (
        len(args.posonlyargs)
        + len(args.args)
        + len(args.kwonlyargs)
        + int(args.vararg is not None)
        + int(args.kwarg is not None)
    )
    if count > MAX_HANDLER_PARAMETERS:
        raise ValueError("handler parameter syntax exceeds site bound")
    positional = [*args.posonlyargs, *args.args]
    padding = len(positional) - len(args.defaults)
    defaults: list[ast.expr | None] = [None] * padding + list(args.defaults)
    records: list[HandlerParameter] = []
    for index, (arg, default) in enumerate(zip(positional, defaults, strict=True)):
        kind = (
            "positional-only"
            if index < len(args.posonlyargs)
            else "positional-or-keyword"
        )
        records.append(_parameter(arg, kind, default))
    if args.vararg is not None:
        records.append(_parameter(args.vararg, "variadic-positional", None))
    records.extend(
        _parameter(arg, "keyword-only", default)
        for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=True)
    )
    if args.kwarg is not None:
        records.append(_parameter(args.kwarg, "variadic-keyword", None))
    return records


def handler_input_syntax(
    declaration: ast.FunctionDef | ast.AsyncFunctionDef,
) -> dict[str, object]:
    """Observe explicit signature and direct DI-call syntax, not API contracts."""
    parameters = _all_parameters(declaration)
    source_end = max(
        (item["end_line"] for item in parameters),
        default=declaration.lineno,
    )
    return {
        "state": "bounded-direct-handler-input-syntax",
        "authority": "direct-static-syntax-only",
        "coverage": "incomplete",
        "parameters_observed": len(parameters),
        "parameters": parameters,
        "return_annotation": _annotation(declaration.returns),
        "signature_source_range": {
            "start_line": declaration.lineno,
            "end_line": max(
                source_end,
                declaration.returns.end_lineno
                if declaration.returns is not None and declaration.returns.end_lineno
                else declaration.lineno,
            ),
        },
        "runtime_request_validation": "unknown",
        "dependency_resolution": "not-established",
        "cross_artifact_correspondence": "unresolved",
        "negative_evidence_admissible": False,
    }
