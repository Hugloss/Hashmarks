"""Caller-selected, syntax-only Python route and MCP-tool declaration evidence.

This is an explicit repository_declarations provider, not a runtime framework
analyzer. It executes no repository code, does not infer route registration,
consumer behavior or handler reachability, and retains no separate index.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from hashmarks.paths import normalize_relative_path

from .repository_declaration_provider import (
    RepositoryDeclarationProviderContext,
    RepositoryDeclarationProviderResult,
)

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})
_MAX_PATHS = 32
_MAX_GROUPS = 128
_MAX_SOURCE_CHARS = 262_144
_MAX_LITERAL_CHARS = 1_024


def _explicit_literal(node: ast.expr | None) -> tuple[str, str | None]:
    if node is None:
        return "not-supplied", None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        if len(node.value) > _MAX_LITERAL_CHARS:
            return "over-bound", None
        return "literal", node.value
    return "dynamic-or-unsupported", None


def _observed_decorator(
    expression: ast.expr,
    *,
    route_objects: frozenset[str],
    tool_objects: frozenset[str],
) -> dict[str, object] | None:
    call = expression if isinstance(expression, ast.Call) else None
    target = call.func if call is not None else expression
    if not (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)):
        return None
    obj, member = target.value.id, target.attr
    if obj in route_objects and member in _HTTP_METHODS:
        kind = "http-route-decorator"
        argument = (
            next(
                (kw.value for kw in call.keywords if kw.arg == "path"),
                call.args[0] if call.args else None,
            )
            if call is not None
            else None
        )
    elif obj in tool_objects and member == "tool":
        kind = "mcp-tool-decorator"
        argument = (
            next(
                (kw.value for kw in call.keywords if kw.arg == "name"),
                None,
            )
            if call is not None
            else None
        )
    else:
        return None
    state, literal = _explicit_literal(argument)
    return {
        "kind": kind,
        "object_name": obj,
        "decorator_method": member,
        "argument_state": state,
        "literal_argument": literal,
        "form": "call" if call is not None else "bare",
    }


def _declaration_group(
    path: str,
    declaration: ast.FunctionDef | ast.AsyncFunctionDef,
    decorator: ast.expr,
    ordinal: int,
    observed: dict[str, object],
    *,
    provider: str,
) -> dict[str, object]:
    group_id = f"{path}:{declaration.lineno}:{decorator.lineno}:{ordinal}"
    scope = {
        "path": path,
        "handler_syntax": declaration.name,
        "decorator_line": decorator.lineno,
    }
    return {
        "group_id": group_id,
        "concept": {"kind": observed["kind"], "syntax": "python-decorator"},
        "scope": scope,
        "correspondence": {
            "state": "unresolved",
            "basis": {
                "producer": provider,
                "reason": "syntax-does-not-prove-runtime-registration",
            },
        },
        "declarations": [
            {
                "declaration_id": "direct-decorator",
                "semantic_role": {"kind": "syntactic-handler-declaration"},
                "value_state": "resolved",
                "value": {
                    **observed,
                    "handler_declared_name": declaration.name,
                    "handler_kind": (
                        "async"
                        if isinstance(declaration, ast.AsyncFunctionDef)
                        else "sync"
                    ),
                },
                "producer": {
                    "provider": provider,
                    "parser": "python-ast",
                    "authority": "direct-static-syntax-only",
                },
                "evidence": [
                    {
                        "path": path,
                        "start_line": decorator.lineno,
                        "end_line": declaration.lineno,
                    }
                ],
            }
        ],
        "coverage": {
            "state": "incomplete",
            "truncation": "complete",
            "expected_declaration_ids": [],
            "scope": scope,
            "provenance": {
                "producer": provider,
                "reason": "selected-top-level-decorators-only",
            },
        },
    }


def _source_groups(
    path: str,
    source: str,
    *,
    route_objects: frozenset[str],
    tool_objects: frozenset[str],
    provider: str,
) -> list[dict[str, object]]:
    groups: list[dict[str, object]] = []
    for declaration in ast.parse(source, filename=path).body:
        if not isinstance(declaration, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for ordinal, decorator in enumerate(declaration.decorator_list):
            observed = _observed_decorator(
                decorator, route_objects=route_objects, tool_objects=tool_objects
            )
            if observed is None:
                continue
            groups.append(
                _declaration_group(
                    path, declaration, decorator, ordinal, observed, provider=provider
                )
            )
            if len(groups) > _MAX_GROUPS:
                raise ValueError("interface provider group bound exceeded")
    return groups


@dataclass(frozen=True, slots=True)
class StaticPythonInterfaceDeclarations:
    """Selected-file AST observations for static decorator syntax only.

    A consumer explicitly instantiates and passes this provider to
    CodeMap.discover_repository_declarations([provider]). No implicit loading,
    filesystem scanning, process launch or persistent provider state occurs.
    """

    paths: tuple[str, ...]
    name: str = "static-python-interface"
    route_objects: tuple[str, ...] = ("app", "router")
    tool_objects: tuple[str, ...] = ("mcp", "server")

    def __post_init__(self) -> None:
        if not 1 <= len(self.paths) <= _MAX_PATHS:
            raise ValueError("interface provider requires 1..32 exact paths")
        if any(
            not isinstance(path, str)
            or not path.endswith(".py")
            or normalize_relative_path(path, allow_root=False) != path
            for path in self.paths
        ):
            raise ValueError("interface provider requires canonical .py paths")
        if len(set(self.paths)) != len(self.paths):
            raise ValueError("interface provider paths must be unique")
        for values in (self.route_objects, self.tool_objects):
            if (
                not values
                or len(values) > 16
                or any(not isinstance(x, str) or not x.isidentifier() for x in values)
                or len(set(values)) != len(values)
            ):
                raise ValueError("interface provider object identifiers invalid")

    def detect(self, context: RepositoryDeclarationProviderContext) -> bool:
        return any(context.exists(path) for path in self.paths)

    def discover(
        self, context: RepositoryDeclarationProviderContext
    ) -> RepositoryDeclarationProviderResult:
        groups: list[dict[str, object]] = []
        unavailable: list[str] = []
        for path in sorted(self.paths):
            if not context.exists(path):
                unavailable.append(path)
                continue
            source = context.read_text(path)
            if len(source) > _MAX_SOURCE_CHARS:
                raise ValueError("interface provider source exceeds bounded AST input")
            groups.extend(
                _source_groups(
                    path,
                    source,
                    route_objects=frozenset(self.route_objects),
                    tool_objects=frozenset(self.tool_objects),
                    provider=self.name,
                )
            )
            if len(groups) > _MAX_GROUPS:
                raise ValueError("interface provider group bound exceeded")
        return RepositoryDeclarationProviderResult(
            groups=tuple(groups),
            provenance={
                "provider": self.name,
                "parser": "python-ast",
                "file_scope": sorted(self.paths),
                "semantics": "direct-decorator-syntax-not-runtime-registration",
                "missing_selected_paths": sorted(unavailable),
            },
        )
