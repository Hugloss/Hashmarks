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
_MAX_BODY_SITES = 16
_MAX_RETURN_KEYS = 32
_MAX_ACCESS_KEY_CHARS = 128


def _explicit_literal(node: ast.expr | None) -> tuple[str, str | None]:
    if node is None:
        return "not-supplied", None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        if len(node.value) > _MAX_LITERAL_CHARS:
            return "over-bound", None
        return "literal", node.value
    return "dynamic-or-unsupported", None


class _HandlerBodySyntax(ast.NodeVisitor):
    """Only direct handler-body syntax; nested scopes never belong to this handler."""

    def __init__(self) -> None:
        self.returns: list[tuple[int, int, dict[str, object]]] = []
        self.accesses: list[tuple[int, int, dict[str, object]]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return  # A nested handler is a different scope.

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return

    def visit_Return(self, node: ast.Return) -> None:
        value = node.value
        keys: list[str] | None = None
        if isinstance(value, ast.Dict) and len(value.keys) <= _MAX_RETURN_KEYS:
            if all(
                isinstance(key, ast.Constant)
                and type(key.value) is str
                and len(key.value) <= _MAX_ACCESS_KEY_CHARS
                for key in value.keys
            ):
                keys = [
                    key.value for key in value.keys if isinstance(key, ast.Constant)
                ]
        self.returns.append(
            (
                node.lineno,
                node.col_offset,
                {
                    "line": node.lineno,
                    "end_line": node.end_lineno or node.lineno,
                    "syntax": "literal-dict-return"
                    if keys is not None
                    else "unresolved-return",
                    "literal_keys_in_source_order": keys,
                },
            )
        )
        if len(self.returns) > _MAX_BODY_SITES:
            raise ValueError("handler return syntax site bound exceeded")
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if (
            isinstance(node.ctx, ast.Load)
            and isinstance(node.value, ast.Name)
            and isinstance(node.slice, ast.Constant)
            and type(node.slice.value) is str
            and len(node.slice.value) <= _MAX_ACCESS_KEY_CHARS
        ):
            self.accesses.append(
                (
                    node.lineno,
                    node.col_offset,
                    {
                        "line": node.lineno,
                        "end_line": node.end_lineno or node.lineno,
                        "receiver_syntax": node.value.id,
                        "literal_key": node.slice.value,
                    },
                )
            )
            if len(self.accesses) > _MAX_BODY_SITES:
                raise ValueError("handler literal access site bound exceeded")
        self.generic_visit(node)


def _handler_body_syntax(
    declaration: ast.FunctionDef | ast.AsyncFunctionDef,
) -> dict[str, object]:
    visitor = _HandlerBodySyntax()
    for statement in declaration.body:
        visitor.visit(statement)
    return {
        "authority": "direct-static-syntax-only",
        "coverage": "incomplete",
        "runtime_response_shape": "unknown",
        "cross_artifact_correspondence": "unresolved",
        # AST fields group dictionary keys/values and call args/keywords; their
        # traversal order is not physical source order, even on the same line.
        "literal_dictionary_returns": [
            site for _, _, site in sorted(visitor.returns, key=lambda row: row[:2])
        ],
        "literal_subscript_accesses": [
            site for _, _, site in sorted(visitor.accesses, key=lambda row: row[:2])
        ],
    }


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
    if (
        argument is None
        and call is not None
        and (
            any(keyword.arg is None for keyword in call.keywords)
            or (kind == "mcp-tool-decorator" and call.args)
        )
    ):
        state = "dynamic-or-unsupported"
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
    body_syntax = observed.get("static_body_syntax")
    extra_evidence: list[dict[str, object]] = []
    if body_syntax is not None:
        sites = [
            *body_syntax["literal_dictionary_returns"],
            *body_syntax["literal_subscript_accesses"],
        ]
        spans = sorted({(site["line"], site["end_line"]) for site in sites})
        extra_evidence = [
            {"path": path, "start_line": start, "end_line": end} for start, end in spans
        ]
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
                    },
                    *extra_evidence,
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
    include_literal_shape_syntax: bool = False,
    parsed: ast.Module | None = None,
) -> list[dict[str, object]]:
    groups: list[dict[str, object]] = []
    tree = parsed if parsed is not None else ast.parse(source, filename=path)
    for declaration in tree.body:
        if not isinstance(declaration, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body_syntax: dict[str, object] | None = None
        for ordinal, decorator in enumerate(declaration.decorator_list):
            observed = _observed_decorator(
                decorator, route_objects=route_objects, tool_objects=tool_objects
            )
            if observed is None:
                continue
            if include_literal_shape_syntax and body_syntax is None:
                body_syntax = _handler_body_syntax(declaration)
            groups.append(
                _declaration_group(
                    path,
                    declaration,
                    decorator,
                    ordinal,
                    {
                        **observed,
                        **(
                            {"static_body_syntax": body_syntax}
                            if body_syntax is not None
                            else {}
                        ),
                    },
                    provider=provider,
                )
            )
            if len(groups) > _MAX_GROUPS:
                raise ValueError("interface provider group bound exceeded")
    return groups


_MAX_CONSUMER_PAIRS = 16


def _validate_consumer_pairs(
    pairs: tuple[tuple[str, str, str, str, str], ...],
    paths: tuple[str, ...],
) -> None:
    """Admit only explicit same-scope source/function/receiver nominations."""
    if not isinstance(pairs, tuple) or len(pairs) > _MAX_CONSUMER_PAIRS:
        raise ValueError("consumer_pairs must be a tuple of at most 16 pairs")
    for pair in pairs:
        if not isinstance(pair, tuple) or len(pair) != 5:
            raise ValueError("consumer_pairs must contain five-field tuples")
        producer_path, producer_name, consumer_path, consumer_name, receiver = pair
        if (
            not isinstance(producer_path, str)
            or not isinstance(consumer_path, str)
            or producer_path not in paths
            or consumer_path not in paths
        ):
            raise ValueError("consumer_pairs paths must be explicitly selected")
        if any(
            not isinstance(value, str) or not value.isidentifier()
            for value in (producer_name, consumer_name, receiver)
        ):
            raise ValueError("consumer_pairs require exact Python identifiers")
    if len(set(pairs)) != len(pairs):
        raise ValueError("consumer_pairs must be unique")


def _unique_top_level(
    tree: ast.Module, name: str
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    matches = [
        row
        for row in tree.body
        if isinstance(row, (ast.FunctionDef, ast.AsyncFunctionDef))
        and row.name == name
    ]
    return matches[0] if len(matches) == 1 else None


def _direct_interface_decorator(
    declaration: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    route_objects: frozenset[str],
    tool_objects: frozenset[str],
) -> bool:
    return any(
        _observed_decorator(
            row, route_objects=route_objects, tool_objects=tool_objects
        ) is not None
        for row in declaration.decorator_list
    )


def _pair_declaration(
    path: str,
    declaration: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    role: str,
    value: dict[str, object],
    provider: str,
    sites: list[dict[str, object]],
) -> dict[str, object]:
    spans = {
        (declaration.lineno, declaration.lineno),
        *((site["line"], site["end_line"]) for site in sites),
    }
    return {
        "declaration_id": role,
        "semantic_role": {"kind": role},
        "value_state": "resolved",
        "value": value,
        "producer": {
            "provider": provider,
            "parser": "python-ast",
            "authority": "direct-static-syntax-only",
        },
        "evidence": [
            {"path": path, "start_line": start, "end_line": end}
            for start, end in sorted(spans)
        ],
    }


def _pair_group(
    index: int,
    pair: tuple[str, str, str, str, str],
    producer: ast.FunctionDef | ast.AsyncFunctionDef,
    consumer: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    provider_name: str,
) -> dict[str, object]:
    producer_path, producer_name, consumer_path, consumer_name, receiver = pair
    returns = _handler_body_syntax(producer)["literal_dictionary_returns"]
    reads = [
        site
        for site in _handler_body_syntax(consumer)["literal_subscript_accesses"]
        if site["receiver_syntax"] == receiver
    ]
    scope = {
        "producer_path": producer_path,
        "producer_function": producer_name,
        "consumer_path": consumer_path,
        "consumer_function": consumer_name,
        "consumer_receiver_syntax": receiver,
    }
    return {
        "group_id": f"caller-nominated-consumer-pair:{index}",
        "concept": {"kind": "nominated-python-interface-syntax-pair"},
        "scope": scope,
        "correspondence": {
            "state": "unresolved",
            "basis": {
                "provider": provider_name,
                "pair_authority": "explicit-caller-nomination-only",
                "runtime_correspondence": "unproven",
            },
        },
        "declarations": [
            _pair_declaration(
                producer_path,
                producer,
                role="producer-return-syntax",
                value={
                    "literal_dictionary_returns": returns,
                    "coverage": "incomplete",
                    "runtime_response_shape": "unknown",
                },
                provider=provider_name,
                sites=returns,
            ),
            _pair_declaration(
                consumer_path,
                consumer,
                role="consumer-subscript-read-syntax",
                value={
                    "receiver_syntax": receiver,
                    "literal_subscript_reads": reads,
                    "coverage": "incomplete",
                    "runtime_consumer_binding": "unknown",
                },
                provider=provider_name,
                sites=reads,
            ),
        ],
        "coverage": {
            "state": "incomplete",
            "truncation": "complete",
            "expected_declaration_ids": [],
            "scope": scope,
            "provenance": {
                "provider": provider_name,
                "reason": "explicit-pair-does-not-prove-runtime-correspondence",
            },
        },
    }


def _paired_groups(
    pairs: tuple[tuple[str, str, str, str, str], ...],
    trees: dict[str, ast.Module],
    *,
    provider: str,
    route_objects: frozenset[str],
    tool_objects: frozenset[str],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Retain only directly located nominees; everything else stays unresolved."""
    groups: list[dict[str, object]] = []
    unresolved: list[dict[str, object]] = []
    for index, pair in enumerate(sorted(pairs)):
        producer_path, producer_name, consumer_path, consumer_name, _ = pair
        producer_tree = trees.get(producer_path)
        consumer_tree = trees.get(consumer_path)
        producer_row = (
            _unique_top_level(producer_tree, producer_name)
            if producer_tree is not None
            else None
        )
        consumer_row = (
            _unique_top_level(consumer_tree, consumer_name)
            if consumer_tree is not None
            else None
        )
        if producer_row is None or consumer_row is None:
            unresolved.append({"pair": list(pair), "reason": "source-or-subject-unresolved"})
        elif not _direct_interface_decorator(
            producer_row,
            route_objects=route_objects,
            tool_objects=tool_objects,
        ):
            unresolved.append({"pair": list(pair), "reason": "producer-decorator-unresolved"})
        else:
            groups.append(
                _pair_group(
                    index, pair, producer_row, consumer_row, provider_name=provider
                )
            )
    return groups, unresolved


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
    include_literal_shape_syntax: bool = False
    consumer_pairs: tuple[tuple[str, str, str, str, str], ...] = ()

    def __post_init__(self) -> None:
        if type(self.include_literal_shape_syntax) is not bool:
            raise ValueError("include_literal_shape_syntax must be boolean")
        _validate_consumer_pairs(self.consumer_pairs, self.paths)
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
        trees: dict[str, ast.Module] = {}
        for path in sorted(self.paths):
            if not context.exists(path):
                unavailable.append(path)
                continue
            source = context.read_text(path)
            if len(source) > _MAX_SOURCE_CHARS:
                raise ValueError("interface provider source exceeds bounded AST input")
            if self.consumer_pairs:
                trees[path] = ast.parse(source, filename=path)
            groups.extend(
                _source_groups(
                    path,
                    source,
                    route_objects=frozenset(self.route_objects),
                    tool_objects=frozenset(self.tool_objects),
                    provider=self.name,
                    include_literal_shape_syntax=self.include_literal_shape_syntax,
                    parsed=trees.get(path),
                )
            )
            if len(groups) > _MAX_GROUPS:
                raise ValueError("interface provider group bound exceeded")
        unresolved_pairs: list[dict[str, object]] = []
        if self.consumer_pairs:
            paired, unresolved_pairs = _paired_groups(
                self.consumer_pairs,
                trees,
                provider=self.name,
                route_objects=frozenset(self.route_objects),
                tool_objects=frozenset(self.tool_objects),
            )
            groups.extend(paired)
            if len(groups) > _MAX_GROUPS:
                raise ValueError("interface provider group bound exceeded")
        return RepositoryDeclarationProviderResult(
            groups=tuple(groups),
            provenance={
                "provider": self.name,
                "parser": "python-ast",
                "file_scope": sorted(self.paths),
                "semantics": "direct-decorator-syntax-not-runtime-registration",
                **(
                    {"handler_body": "bounded-literal-syntax-not-response-contract"}
                    if self.include_literal_shape_syntax
                    else {}
                ),
                "missing_selected_paths": sorted(unavailable),
                **(
                    {
                        "consumer_pairs": "explicit-caller-nominations-only",
                        "unresolved_consumer_pairs": unresolved_pairs,
                    }
                    if self.consumer_pairs
                    else {}
                ),
            },
        )
