"""Python verifier references over one caller-qualified AST snapshot."""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from functools import lru_cache

from .python_binding_scope import (
    PythonReferenceVisitor,
    annotated_assignment_expressions,
    annotations_are_deferred,
    definition_time_expressions,
    unfiltered_literal_comprehension,
)
from .python_bindings import PythonBindings

MAX_KEYWORD_IDENTIFIER_CHARS = 128


def _unnegated_test(test: ast.expr) -> tuple[ast.expr, bool]:
    negated = False
    while isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        negated = not negated
        test = test.operand
    return test, negated


def literal_truth(test: ast.expr) -> bool | None:
    """Identify an ordinary Python literal's truth, including explicit not."""
    operand, negated = _unnegated_test(test)
    if isinstance(operand, ast.Constant):
        return bool(operand.value) != negated
    return None


def empty_literal_iterable(node: ast.expr) -> bool:
    """Only literal iterables whose syntax guarantees zero members."""
    match node:
        case ast.List(elts=[]) | ast.Tuple(elts=[]) | ast.Dict(keys=[]):
            return True
        case ast.Constant(value="" | b""):
            return True
    return False


def empty_loop_else_exits(statement: ast.stmt) -> bool:
    """Only the sole reachable suite of an explicitly empty loop can prove this exit."""
    return (
        isinstance(statement, ast.For)
        and empty_literal_iterable(statement.iter)
        and any(
            isinstance(child, (ast.Return, ast.Raise)) for child in statement.orelse
        )
    )


def visit_suite_fields(
    node: ast.AST,
    visit: Callable[[ast.AST], object],
    visit_suite: Callable[[list[ast.stmt]], None],
) -> None:
    """Traverse sibling statement lists independently, including exception and final suites."""
    for field, value in ast.iter_fields(node):
        if isinstance(value, list):
            if field in {"body", "orelse", "finalbody"}:
                visit_suite(value)
            else:
                for child in value:
                    if isinstance(child, ast.AST):
                        visit(child)
        elif isinstance(value, ast.AST):
            visit(value)


def possible_boolean_operands(node: ast.BoolOp) -> Iterator[ast.expr]:
    """Yield possibly evaluated operands up to and including a decisive literal."""
    stop_if_true = isinstance(node.op, ast.Or)
    for operand in node.values:
        yield operand
        if literal_truth(operand) is stop_if_true:
            break


@dataclass(frozen=True)
class AttributeUse:
    imported: str
    suffix: str
    test: str | None


@dataclass(frozen=True)
class VerificationReferenceIndex:
    guards: dict[str, set[str | None]]
    uncertain_imports: set[str]
    name_uses: dict[str, set[str | None]]
    attributes: dict[tuple[str, int], set[AttributeUse]]
    flat_tests: set[str]
    used_typing_guard: bool
    keyword_arguments: tuple[tuple[str, int, int], ...]

    @staticmethod
    def strength(guards: set[str | None], used: bool) -> dict[str, object]:
        if used:
            strength = "reachable-symbol-use"
        elif None in guards:
            strength = "reachable-import"
        elif "type-checking-only" in guards:
            strength = "type-checking-only"
        elif guards:
            strength = "statically-dead"
        else:
            return {"syntactic_reference": True, "reference_strength": "syntactic"}
        return {
            "syntactic_reference": True,
            "reachable_import": used or None in guards,
            "reachable_symbol_use": used,
            "reference_strength": strength,
        }

    def imported_attribute(self, target: str, line: int) -> AttributeUse | None:
        """Retain the lexical binding at the indexed reference site."""
        uses = self.attributes.get((target, line), set())
        return next(iter(uses)) if len(uses) == 1 else None


class _VerificationReferenceIndexVisitor(PythonReferenceVisitor):
    def __init__(
        self,
        bindings: PythonBindings,
        typing_guards: bool,
        *,
        deferred_annotations: bool,
    ) -> None:
        self.deferred_annotations = deferred_annotations
        self.bindings = bindings
        self.typing_guards = typing_guards
        self.used_typing_guard = False
        self.guard: str | None = None
        self.imports: dict[ast.alias, str] = {}
        self.by_name: dict[str, set[str]] = {}
        self.guards: dict[str, set[str | None]] = {}
        self.uncertain_imports: set[str] = set()
        self.loads: list[ast.Name | ast.Attribute] = []
        self.keyword_arguments: dict[str, tuple[int, int]] = {}
        self.flat_tests = {
            name
            for name, binding in bindings.syntax.root.bindings.items()
            if name.startswith("test_")
            and binding.kind == "declaration"
            and isinstance(binding.node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        self.eager_test_scopes = {
            scope
            for scope in bindings.syntax.scopes
            if unfiltered_literal_comprehension(scope.node, simple_targets=True)
            or (
                isinstance(scope.node, ast.ClassDef)
                and not scope.node.bases
                and not scope.node.keywords
            )
        }

    def _visit_suite(self, statements: list[ast.stmt]) -> None:
        """Keep direct exits local to this suite, including their evaluated operands."""
        previous = self.guard
        for statement in statements:
            self.visit(statement)
            if isinstance(
                statement, (ast.Return, ast.Raise, ast.Break, ast.Continue)
            ) or empty_loop_else_exits(statement):
                self.guard = self.guard or "statically-dead"
        self.guard = previous

    def generic_visit(self, node: ast.AST) -> None:
        visit_suite_fields(node, self.visit, self._visit_suite)

    def _guarded_branches(self, test: ast.expr) -> tuple[str | None, str | None]:
        truth = literal_truth(test)
        reason = "statically-dead"
        if truth is None:
            operand, negated = _unnegated_test(test)
            if not self.typing_guards or not self.bindings.references_import_member(
                operand, "typing", "TYPE_CHECKING"
            ):
                return None, None
            self.used_typing_guard = True
            reason = "type-checking-only"
            truth = negated
        return (None, reason) if truth else (reason, None)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        for operand in possible_boolean_operands(node):
            self.visit(operand)

    def visit_For(self, node: ast.For) -> None:
        self.visit(node.iter)
        previous = self.guard
        if empty_literal_iterable(node.iter):
            self.guard = previous or "statically-dead"
        self.visit(node.target)
        self._visit_suite(node.body)
        self.guard = previous
        self._visit_suite(node.orelse)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.visit(node.test)
        body_guard, else_guard = self._guarded_branches(node.test)
        if body_guard is None:
            self.visit(node.body)
        if else_guard is None:
            self.visit(node.orelse)

    def visit_If(self, node: ast.If) -> None:
        previous = self.guard
        self.visit(node.test)
        body, otherwise = self._guarded_branches(node.test)
        self.guard = previous or body
        self._visit_suite(node.body)
        self.guard = previous or otherwise
        self._visit_suite(node.orelse)
        self.guard = previous

    def _import(self, node: ast.Import | ast.ImportFrom, prefix: str) -> None:
        syntax = self.bindings.syntax
        for alias in node.names:
            target = prefix + alias.name
            self.guards.setdefault(target, set()).add(self.guard)
            if self.guard is not None:
                continue
            self.imports[alias] = target
            bound = alias.asname or alias.name.split(".")[0]
            self.by_name.setdefault(bound, set()).add(target)
            binding = syntax.lookup(bound, syntax.owners[node])
            if binding is None or binding.node is not alias:
                self.uncertain_imports.add(target)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module + "." if node.module else ""
        self._import(node, "." * node.level + module)

    def visit_Import(self, node: ast.Import) -> None:
        self._import(node, "")

    def _visit_definition(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
    ) -> None:
        for expression in definition_time_expressions(
            node, deferred=self.deferred_annotations
        ):
            self.visit(expression)
        self._visit_suite(node.body)

    visit_FunctionDef = _visit_definition
    visit_AsyncFunctionDef = _visit_definition
    visit_ClassDef = _visit_definition

    def visit_TypeAlias(self, node: ast.stmt) -> None:
        # The parameters and RHS of a type statement are lazy source expressions.
        return

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        scope = self.bindings.syntax.owners.get(node)
        for expression in annotated_assignment_expressions(
            node, scope.node if scope else None, deferred=self.deferred_annotations
        ):
            self.visit(expression)

    def visit_keyword(self, node: ast.keyword) -> None:
        if (
            self.guard is None
            and node.arg is not None
            and len(node.arg) <= MAX_KEYWORD_IDENTIFIER_CHARS
        ):
            self.keyword_arguments.setdefault(
                node.arg, (node.lineno, node.end_lineno or node.lineno)
            )
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if self.guard is None and isinstance(node.ctx, ast.Load):
            self.loads.append(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if self.guard is None and isinstance(node.ctx, ast.Load):
            self.loads.append(node)
        self.generic_visit(node)

    def _test(self, node: ast.AST, *, qualified_use: bool = False) -> str | None:
        scope = self.bindings.syntax.owners.get(node)
        # A qualified import use can carry its test identity through an eager
        # comprehension or plain class suite, including method headers.
        # Crossing a function body would lose that witness.
        while qualified_use and scope is not None and scope in self.eager_test_scopes:
            scope = scope.defining
        if (
            scope is not None
            and scope.defining is self.bindings.syntax.root
            and scope.name in self.flat_tests
        ):
            return scope.name
        return None

    @staticmethod
    def _attribute(
        node: ast.Attribute, alias: ast.alias, imported: str
    ) -> tuple[str, str] | None:
        parts: list[str] = []
        value: ast.expr = node
        while isinstance(value, ast.Attribute):
            parts.append(value.attr)
            value = value.value
        if not isinstance(value, ast.Name):
            return None
        suffix = ".".join(reversed(parts))
        target = f"{value.id}.{suffix}"
        if imported.startswith(value.id + ".") and not alias.asname:
            if not target.startswith(imported + "."):
                return None
            suffix = target[len(imported) + 1 :]
        return target, suffix

    def _unresolved_use(self, node: ast.Name | ast.Attribute) -> None:
        if isinstance(node, ast.Name) and self._test(node) is not None:
            self.uncertain_imports.update(self.by_name.get(node.id, ()))

    def index(self) -> VerificationReferenceIndex:
        names: dict[str, set[str | None]] = {}
        attributes: dict[tuple[str, int], set[AttributeUse]] = {}
        for node in self.loads:
            alias = self.bindings.imported_alias(node)
            if alias is None or alias not in self.imports:
                self._unresolved_use(node)
                continue
            imported = self.imports[alias]
            test = self._test(node, qualified_use=True)
            if isinstance(node, ast.Name):
                names.setdefault(imported, set()).add(test)
            elif pair := self._attribute(node, alias, imported):
                target, suffix = pair
                attributes.setdefault((target, node.lineno), set()).add(
                    AttributeUse(imported, suffix, test)
                )
        return VerificationReferenceIndex(
            self.guards,
            self.uncertain_imports,
            names,
            attributes,
            self.flat_tests,
            self.used_typing_guard,
            tuple(
                (name, start, end)
                for name, (start, end) in self.keyword_arguments.items()
            ),
        )


@lru_cache(maxsize=4096)
def verification_reference_index(
    absolute_path: str,
    identity: tuple[int, int, int, int, int],
    tree: ast.Module,
    source: str,
    typing_guards: bool = True,
) -> VerificationReferenceIndex:
    """Project the existing source snapshot without rereading or reparsing the member."""
    visitor = _VerificationReferenceIndexVisitor(
        PythonBindings(tree, source.encode("utf-8")),
        typing_guards,
        deferred_annotations=annotations_are_deferred(tree),
    )
    visitor.visit(tree)
    return visitor.index()
