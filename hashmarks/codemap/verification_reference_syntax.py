"""Immutable Python reference syntax over one caller-qualified AST snapshot.

This process-local projection owns no file reads, repository identity, import
resolution or verification selection. The caller retains freshness authority.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from functools import lru_cache

MAX_KEYWORD_IDENTIFIER_CHARS = 128


@dataclass(frozen=True)
class VerificationReferenceIndex:
    bindings: tuple[tuple[str, str, str | None], ...]
    module_bindings: tuple[tuple[str, str, str | None], ...]
    reachable_names: frozenset[str]
    reachable_attributes: frozenset[str]
    reachable_attribute_chains: frozenset[str]
    bound_names: frozenset[str]
    star_import: bool
    keyword_arguments: tuple[tuple[str, int, int], ...]

    def imported_attribute(self, target: str) -> tuple[str, str] | None:
        """Expand one unshadowed import alias, without resolving its owner."""
        if target not in self.reachable_attribute_chains:
            return None
        alias, suffix = target.split(".", 1)
        if alias in self.bound_names or self.star_import:
            return None
        targets = {
            imported
            for imported, bound, guard in self.module_bindings
            if bound == alias and guard is None
        }
        if len(targets) != 1:
            return None
        imported = next(iter(targets))
        tail = imported.removeprefix(alias + ".")
        if imported.startswith(alias + ".") and suffix.startswith(tail + "."):
            suffix = suffix.removeprefix(tail + ".")
        return imported, suffix


class _VerificationReferenceIndexVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.guard: str | None = None
        self.bindings: list[tuple[str, str, str | None]] = []
        self.module_bindings: list[tuple[str, str, str | None]] = []
        self.reachable_names: set[str] = set()
        self.reachable_attributes: set[str] = set()
        self.reachable_attribute_chains: set[str] = set()
        self.bound_names: set[str] = set()
        self.star_import = False
        self.keyword_arguments: dict[str, tuple[int, int]] = {}

    def visit(self, node: ast.AST) -> None:
        match node:
            case (
                ast.FunctionDef(name=name)
                | ast.AsyncFunctionDef(name=name)
                | ast.ClassDef(name=name)
                | ast.arg(arg=name)
                | ast.ExceptHandler(name=name)
                | ast.MatchAs(name=name)
                | ast.MatchStar(name=name)
                | ast.MatchMapping(rest=name)
            ) if name is not None:
                self.bound_names.add(name)
        super().visit(node)

    @staticmethod
    def _guard_kind(test: ast.expr) -> str | None:
        if isinstance(test, ast.Constant) and test.value is False:
            return "statically-dead"
        if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
            return "type-checking-only"
        if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
            return "type-checking-only"
        return None

    def visit_If(self, node: ast.If) -> None:
        previous = self.guard
        self.guard = previous or self._guard_kind(node.test)
        for child in node.body:
            self.visit(child)
        self.guard = previous
        for child in node.orelse:
            self.visit(child)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if self.guard is None and any(alias.name == "*" for alias in node.names):
            self.star_import = True
        self.bindings.extend(
            (alias.name, alias.asname or alias.name, self.guard) for alias in node.names
        )
        prefix = "." * int(node.level or 0)
        module = str(node.module or "")
        self.module_bindings.extend(
            (
                f"{prefix}{module + '.' if module else ''}{alias.name}",
                alias.asname or alias.name,
                self.guard,
            )
            for alias in node.names
        )

    def visit_Import(self, node: ast.Import) -> None:
        self.module_bindings.extend(
            (
                alias.name,
                alias.asname or alias.name.split(".", 1)[0],
                self.guard,
            )
            for alias in node.names
        )

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

    @staticmethod
    def _attribute_chain(node: ast.Attribute) -> str | None:
        parts = [node.attr]
        value: ast.expr = node.value
        while isinstance(value, ast.Attribute):
            parts.append(value.attr)
            value = value.value
        if not isinstance(value, ast.Name):
            return None
        parts.append(value.id)
        return ".".join(reversed(parts))

    def visit_Name(self, node: ast.Name) -> None:
        if self.guard is None and isinstance(node.ctx, ast.Load):
            self.reachable_names.add(node.id)
        elif isinstance(node.ctx, (ast.Store, ast.Del)):
            self.bound_names.add(node.id)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if self.guard is None and isinstance(node.ctx, ast.Load):
            self.reachable_attributes.add(node.attr)
            chain = self._attribute_chain(node)
            if chain:
                self.reachable_attribute_chains.add(chain)
        elif isinstance(node.ctx, (ast.Store, ast.Del)):
            chain = self._attribute_chain(node)
            if chain:
                self.bound_names.add(chain.split(".", 1)[0])
        self.generic_visit(node)


@lru_cache(maxsize=4096)
def verification_reference_index(
    absolute_path: str,
    identity: tuple[int, int, int, int, int],
    tree: ast.Module,
) -> VerificationReferenceIndex:
    """Project one already freshness-bound AST snapshot into reference evidence.

    ``tree`` is part of the process-local cache key so a new snapshot can never
    reuse a projection from an older source identity.  The caller obtains the
    snapshot through ``read_python_ast``; do not re-read the same file here.
    """
    visitor = _VerificationReferenceIndexVisitor()
    visitor.visit(tree)
    imported_targets: dict[str, set[str]] = {}
    for imported, bound, guard in visitor.module_bindings:
        if guard is None:
            imported_targets.setdefault(bound, set()).add(imported)
    visitor.bound_names.update(
        bound for bound, targets in imported_targets.items() if len(targets) > 1
    )
    return VerificationReferenceIndex(
        bindings=tuple(visitor.bindings),
        module_bindings=tuple(visitor.module_bindings),
        reachable_names=frozenset(visitor.reachable_names),
        reachable_attributes=frozenset(visitor.reachable_attributes),
        reachable_attribute_chains=frozenset(visitor.reachable_attribute_chains),
        bound_names=frozenset(visitor.bound_names),
        star_import=visitor.star_import,
        keyword_arguments=tuple(
            (name, start, end)
            for name, (start, end) in visitor.keyword_arguments.items()
        ),
    )
