"""Lexical scope qualification over an already admitted Python AST.

The existing export owner supplies Python's binding-write semantics. This
operation-local index does not parse, read files, or resolve repository imports.
"""

from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass, field

from .python_exports import _binding_children, _binding_writes
from .source_binding_contract import (
    MAX_ALIAS_DEPTH,
    MAX_BINDING_NODES,
    BindingObservationBound,
)

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


@dataclass(eq=False)
class PythonScope:
    node: ast.AST
    kind: str
    name: str | None
    parent: PythonScope | None = None
    defining: PythonScope | None = None
    bindings: dict[str, PythonBinding] = field(default_factory=dict)
    globals: set[str] = field(default_factory=set)
    nonlocals: set[str] = field(default_factory=set)
    external_writes: set[str] = field(default_factory=set)
    star_import: bool = False
    dynamic_namespace: bool = False
    invalid_declarations: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class PythonBinding:
    name: str
    node: ast.AST
    scope: PythonScope
    kind: str
    value: ast.AST | None = None
    imported: ast.Import | ast.ImportFrom | None = None
    reason: str | None = None


def function_parameters(node: FunctionNode) -> list[ast.arg]:
    arguments = node.args
    return [
        *arguments.posonlyargs,
        *arguments.args,
        *arguments.kwonlyargs,
        *(arg for arg in (arguments.vararg, arguments.kwarg) if arg is not None),
    ]


def function_defaults(node: FunctionNode) -> list[tuple[ast.arg, ast.expr]]:
    arguments = node.args
    positional = [*arguments.posonlyargs, *arguments.args]
    defaults = list(
        zip(
            positional[len(positional) - len(arguments.defaults) :],
            arguments.defaults,
            strict=True,
        )
    )
    defaults.extend(
        (parameter, value)
        for parameter, value in zip(
            arguments.kwonlyargs, arguments.kw_defaults, strict=True
        )
        if value is not None
    )
    return defaults


def _enclosing(scope: PythonScope) -> PythonScope:
    """Functions, lambdas and comprehensions never close over class namespaces."""
    while scope.kind == "class" and scope.parent is not None:
        scope = scope.parent
    return scope


def _scope_body(scope: PythonScope) -> list[ast.AST]:
    node = scope.node
    if isinstance(
        node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    ):
        return list(node.body)
    if isinstance(node, ast.Lambda):
        return [node.body]
    if isinstance(node, _COMPREHENSIONS):
        return [
            *(generator.iter for generator in node.generators[1:]),
            *(
                condition
                for generator in node.generators
                for condition in generator.ifs
            ),
            *(
                (node.key, node.value)
                if isinstance(node, ast.DictComp)
                else (node.elt,)
            ),
        ]
    return []


def _statement_candidates(node: ast.AST, scope: PythonScope) -> list[PythonBinding]:
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return [
            PythonBinding(
                alias.asname or alias.name.split(".")[0],
                alias,
                scope,
                "import",
                imported=node,
            )
            for alias in node.names
            if alias.name != "*"
        ]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [PythonBinding(node.name, node, scope, "declaration")]
    if isinstance(node, ast.Assign):
        return [
            PythonBinding(target.id, target, scope, "alias", value=node.value)
            for target in node.targets
            if isinstance(target, ast.Name)
        ]
    if (
        isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.value is not None
    ):
        return [
            PythonBinding(node.target.id, node.target, scope, "alias", value=node.value)
        ]
    return []


def _scope_parameters(scope: PythonScope) -> list[PythonBinding]:
    if isinstance(scope.node, _FUNCTIONS):
        return [
            PythonBinding(arg.arg, arg, scope, "parameter")
            for arg in function_parameters(scope.node)
        ]
    if isinstance(scope.node, _COMPREHENSIONS):
        return [
            PythonBinding(name, generator.target, scope, "parameter")
            for generator in scope.node.generators
            for name in _binding_writes(generator.target)
        ]
    return []


def _scope_bindings(scope: PythonScope) -> None:
    body = _scope_body(scope)
    writes = Counter(
        name
        for statement in body
        for name in _binding_writes(
            statement, annotation_targets_bind=scope.kind not in {"module", "class"}
        )
    )
    candidates: dict[str, list[PythonBinding]] = {}
    for statement in body:
        for binding in _statement_candidates(statement, scope):
            candidates.setdefault(binding.name, []).append(binding)
    for binding in _scope_parameters(scope):
        writes[binding.name] += 1
        candidates.setdefault(binding.name, []).append(binding)
    for name, count in writes.items():
        selected = candidates.get(name, [])
        scope.bindings[name] = (
            selected[0]
            if count == 1 and len(selected) == 1
            else PythonBinding(
                name,
                selected[0].node if selected else scope.node,
                scope,
                "unknown",
                reason="competing-bindings"
                if count > 1
                else "conditional-or-unsupported-binding",
            )
        )


class PythonScopes(ast.NodeVisitor):
    """Index one syntax tree, preserving definition and body scope separately."""

    def __init__(self, tree: ast.Module) -> None:
        self.root = PythonScope(tree, "module", None)
        self.current = self.root
        self.scopes = [self.root]
        self.nodes: list[ast.AST] = []
        self.owners: dict[ast.AST, PythonScope] = {}
        self.function_scopes: dict[FunctionNode, PythonScope] = {}
        self.type_nodes: set[ast.AST] = set()
        self._in_type = False
        self.visit(tree)
        for scope in self.scopes:
            _scope_bindings(scope)
        self._qualify_scope_declarations()
        self._qualify_external_writes()
        self._qualify_dynamic_namespace_writes()

    def visit(self, node: ast.AST) -> None:
        if len(self.nodes) >= MAX_BINDING_NODES:
            raise BindingObservationBound("Python syntax node bound")
        self.nodes.append(node)
        self.owners[node] = self.current
        if self._in_type:
            self.type_nodes.add(node)
        super().visit(node)

    def _visit_type(self, node: ast.AST | None) -> None:
        if node is None:
            return
        before = self._in_type
        self._in_type = True
        self.visit(node)
        self._in_type = before

    def visit_arg(self, node: ast.arg) -> None:
        self._visit_type(node.annotation)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.visit(node.target)
        self._visit_type(node.annotation)
        if node.value is not None:
            self.visit(node.value)

    def _enter(self, node: ast.AST, kind: str, name: str | None) -> PythonScope:
        before = self.current
        self.current = PythonScope(node, kind, name, _enclosing(before), before)
        self.scopes.append(self.current)
        return before

    def _function(self, node: FunctionNode) -> None:
        for child in _binding_children(node):
            if child is getattr(node, "returns", None):
                self._visit_type(child)
            else:
                self.visit(child)
        before = self._enter(node, "function", getattr(node, "name", "<lambda>"))
        self.function_scopes[node] = self.current
        for statement in _scope_body(self.current):
            self.visit(statement)
        self.current = before

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._function(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for child in _binding_children(node):
            self.visit(child)
        before = self._enter(node, "class", node.name)
        for statement in node.body:
            self.visit(statement)
        self.current = before

    def _comprehension(
        self, node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp
    ) -> None:
        self.visit(node.generators[0].iter)
        before = self._enter(node, "comprehension", None)
        for generator in node.generators:
            self.visit(generator.target)
        for expression in _scope_body(self.current):
            self.visit(expression)
        self.current = before

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._comprehension(node)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._comprehension(node)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._comprehension(node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._comprehension(node)

    def visit_Global(self, node: ast.Global) -> None:
        self.current.globals.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.current.nonlocals.update(node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.current.star_import |= any(alias.name == "*" for alias in node.names)
        self.generic_visit(node)

    def _qualify_external_writes(self) -> None:
        for scope in self.scopes:
            for name in scope.globals & scope.bindings.keys():
                if scope.bindings[name].kind != "parameter":
                    self.root.external_writes.add(name)
            for name in scope.nonlocals & scope.bindings.keys():
                outer = self._nonlocal_scope(name, scope)
                if outer is not None and scope.bindings[name].kind != "parameter":
                    outer.external_writes.add(name)

    def _qualify_scope_declarations(self) -> None:
        """AST parsing alone does not reject declarations after lexical use."""
        seen: dict[PythonScope, set[str]] = {}
        for node in self.nodes:
            scope = self.owners[node]
            names = seen.setdefault(scope, set())
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, (ast.Global, ast.Nonlocal)):
                scope.invalid_declarations.update(names.intersection(node.names))

    def _nonlocal_scope(self, name: str, scope: PythonScope) -> PythonScope | None:
        current = scope.parent
        while current is not None and current.kind != "module":
            if name in current.globals:
                return None
            if name in current.bindings and name not in current.nonlocals:
                return current
            current = current.parent
        return None

    def _lookup_scope(
        self, name: str, scope: PythonScope
    ) -> tuple[PythonScope | None, str | None]:
        if name in scope.invalid_declarations:
            return None, "scope-declaration-after-use"
        if name not in scope.globals | scope.nonlocals:
            return scope, None
        if name in scope.globals & scope.nonlocals:
            return None, "conflicting-scope-declarations"
        binding = scope.bindings.get(name)
        if binding is not None and binding.kind == "parameter":
            return None, "parameter-scope-declaration-conflict"
        if name in scope.globals:
            return self.root, None
        outer = self._nonlocal_scope(name, scope)
        return outer, "nonlocal-binding-unqualified" if outer is None else None

    def lookup(self, name: str, scope: PythonScope) -> PythonBinding | None:
        current: PythonScope | None = scope
        while current is not None:
            redirected, reason = self._lookup_scope(name, current)
            if reason is not None:
                return PythonBinding(
                    name, current.node, current, "unknown", reason=reason
                )
            assert redirected is not None
            current = redirected
            if current.dynamic_namespace:
                return PythonBinding(
                    name,
                    current.node,
                    current,
                    "unknown",
                    reason="dynamic-namespace-write",
                )
            if current.star_import or name in current.external_writes:
                return PythonBinding(
                    name,
                    current.node,
                    current,
                    "unknown",
                    reason="dynamic-or-external-binding-write",
                )
            if name in current.bindings:
                return current.bindings[name]
            current = current.parent
        return None

    def _namespace_owner(
        self, node: ast.AST | None, scope: PythonScope, depth: int = 0
    ) -> PythonScope | None:
        if depth >= MAX_ALIAS_DEPTH:
            return None
        if isinstance(node, ast.Name):
            binding = self.lookup(node.id, scope)
            return (
                self._namespace_owner(binding.value, binding.scope, depth + 1)
                if binding is not None and binding.kind == "alias"
                else None
            )
        if not isinstance(node, ast.Call) or node.args or node.keywords:
            return None
        if (
            not isinstance(node.func, ast.Name)
            or self.lookup(node.func.id, scope) is not None
        ):
            return None
        if node.func.id == "globals":
            return self.root
        return scope if node.func.id in {"locals", "vars"} else None

    def _namespace_write(self, node: ast.AST) -> PythonScope | None:
        if isinstance(node, ast.Subscript) and isinstance(
            node.ctx, (ast.Store, ast.Del)
        ):
            return self._namespace_owner(node.value, self.owners[node])
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr
            in {
                "update",
                "clear",
                "pop",
                "popitem",
                "setdefault",
                "__setitem__",
                "__delitem__",
                "__ior__",
            }
        ):
            return self._namespace_owner(node.func.value, self.owners[node])
        return None

    def _qualify_dynamic_namespace_writes(self) -> None:
        changed: set[PythonScope] = set()
        for node in self.nodes:
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "exec"
                and self.lookup("exec", self.owners[node]) is None
            ):
                changed.update((self.root, self.owners[node]))
            owner = self._namespace_write(node)
            if owner is not None:
                changed.add(owner)
        for scope in changed:
            scope.dynamic_namespace = True
