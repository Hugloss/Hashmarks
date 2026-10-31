"""Bounded structural observations of test reads of repository-owned files.

Literal text only locates candidate sources. A qualified AST must prove an
unshadowed pathlib read rooted at that source file's repository ancestor. This
observes a read relationship, never test sufficiency or execution.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, cast

from hashmarks.paths import normalize_relative_path
from hashmarks.python_ast_cache import read_python_ast

from .model import EvidenceVisibility
from .verification_defaults import VERIFICATION_RELEVANCE_DEFAULTS

if TYPE_CHECKING:
    from .evidence_verification import (
        RepositoryVerification,
        _VerificationRelevanceState,
    )


def _binding_name(node: ast.AST) -> str | None:
    match node:
        case (
            ast.Name(id=name, ctx=ast.Store() | ast.Del())
            | ast.arg(arg=name)
            | ast.FunctionDef(name=name)
            | ast.AsyncFunctionDef(name=name)
            | ast.ClassDef(name=name)
            | ast.ExceptHandler(name=name)
            | ast.MatchAs(name=name)
            | ast.MatchStar(name=name)
            | ast.MatchMapping(rest=name)
        ):
            return name
        case ast.Attribute(value=value, ctx=ast.Store() | ast.Del()):
            while isinstance(value, ast.Attribute):
                value = value.value
            return value.id if isinstance(value, ast.Name) else None
    return None


def _bound_names(tree: ast.Module) -> Counter[str]:
    counts: Counter[str] = Counter()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            counts.update(
                alias.asname or alias.name.split(".", 1)[0] for alias in node.names
            )
        elif (name := _binding_name(node)) is not None:
            counts[name] += 1
    return counts


def _path_imports(tree: ast.Module, counts: Counter[str]) -> frozenset[str]:
    return frozenset(
        alias.asname or alias.name
        for statement in tree.body
        if isinstance(statement, ast.ImportFrom)
        and statement.module == "pathlib"
        and not statement.level
        for alias in statement.names
        if alias.name == "Path" and counts[alias.asname or alias.name] == 1
    )


def _is_call(node: ast.expr, names: frozenset[str]) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in names
        and len(node.args) == 1
        and not node.keywords
    )


def _repository_ancestor(node: ast.expr, names: frozenset[str], depth: int) -> bool:
    if not (
        isinstance(node, ast.Subscript)
        and isinstance(node.slice, ast.Constant)
        and type(node.slice.value) is int
        and node.slice.value == depth
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "parents"
    ):
        return False
    resolved = node.value.value
    return (
        isinstance(resolved, ast.Call)
        and not resolved.args
        and not resolved.keywords
        and isinstance(resolved.func, ast.Attribute)
        and resolved.func.attr == "resolve"
        and _is_call(resolved.func.value, names)
        and isinstance(resolved.func.value, ast.Call)
        and isinstance(resolved.func.value.args[0], ast.Name)
        and resolved.func.value.args[0].id == "__file__"
    )


def _root_bindings(
    tree: ast.Module, names: frozenset[str], counts: Counter[str], depth: int
) -> frozenset[str]:
    if counts["__file__"] or any(
        isinstance(node, ast.ImportFrom)
        and any(alias.name == "*" for alias in node.names)
        for node in ast.walk(tree)
    ):
        return frozenset()
    return frozenset(
        statement.targets[0].id
        for statement in tree.body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
        and counts[statement.targets[0].id] == 1
        and _repository_ancestor(statement.value, names, depth)
    )


def _literal_path(
    node: ast.expr, roots: frozenset[str], names: frozenset[str]
) -> tuple[str, ...] | None:
    if isinstance(node, ast.Name) and node.id in roots:
        return ()
    if _is_call(node, names) and isinstance(node, ast.Call):
        return _literal_path(node.args[0], roots, names)
    if not (
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Div)
        and isinstance(node.right, ast.Constant)
        and isinstance(node.right.value, str)
    ):
        return None
    parent = _literal_path(node.left, roots, names)
    literal = node.right.value
    if parent is None or "\\" in literal:
        return None
    try:
        normalized = normalize_relative_path(literal, allow_root=False)
    except ValueError:
        return None
    return (*parent, *PurePosixPath(normalized).parts)


class _LiteralReadVisitor(ast.NodeVisitor):
    def __init__(
        self, roots: frozenset[str], names: frozenset[str], target: str
    ) -> None:
        self.roots = roots
        self.names = names
        self.target = target
        self.test: str | None = None
        self.in_function = False
        self.terminated = False
        self.reads: list[dict[str, object]] = []

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if self.in_function:
            return
        self.in_function = True
        self.terminated = False
        self.test = node.name if node.name.startswith("test_") else None
        for child in node.body:
            self.visit(child)
            if self.terminated:
                break
        self.test = None
        self.in_function = False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # Class-based/custom collection is outside this explicit syntax scope.
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return

    def visit_If(self, node: ast.If) -> None:
        # Dynamic guards, including typing-only aliases, remain unqualified.
        if not isinstance(node.test, ast.Constant):
            return
        for child in node.body if bool(node.test.value) else node.orelse:
            self.visit(child)
            if self.terminated:
                break

    def visit_Return(self, node: ast.Return) -> None:
        self.generic_visit(node)
        self.terminated = True

    def visit_Raise(self, node: ast.Raise) -> None:
        self.generic_visit(node)
        self.terminated = True

    def visit_While(self, node: ast.While) -> None:
        return

    def visit_For(self, node: ast.For) -> None:
        return

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        return

    def visit_Call(self, node: ast.Call) -> None:
        if (
            self.test is not None
            and not self.terminated
            and len(self.reads)
            < VERIFICATION_RELEVANCE_DEFAULTS.literal_file_read_sites
            and self._reads_target(node)
        ):
            self.reads.append(
                {
                    "source_path": self.target,
                    "test_symbol": self.test,
                    "line": node.lineno,
                    "end_line": node.end_lineno or node.lineno,
                    "basis": "unshadowed-pathlib-literal-read",
                }
            )
        self.generic_visit(node)

    def _reads_target(self, node: ast.Call) -> bool:
        if not isinstance(node.func, ast.Attribute) or node.func.attr not in {
            "read_text",
            "read_bytes",
        }:
            return False
        parts = _literal_path(node.func.value, self.roots, self.names)
        return parts is not None and PurePosixPath(*parts).as_posix() == self.target


def literal_repository_file_reads(
    tree: ast.Module, reader_path: str, target: str
) -> list[dict[str, object]]:
    counts = _bound_names(tree)
    names = _path_imports(tree, counts)
    roots = _root_bindings(
        tree, names, counts, len(PurePosixPath(reader_path).parts) - 1
    )
    visitor = _LiteralReadVisitor(roots, names, target)
    visitor.visit(tree)
    return visitor.reads


class VerificationFileReadsMixin:
    def _verification_file_read_evidence(
        self, path: str, target: str, target_revision: object
    ) -> list[dict[str, object]]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        self.source.ensure_current(path)
        imported, ambiguous = self.imports._resolve_import_owner_evidence(
            path, "pathlib.Path"
        )
        if imported or ambiguous:
            return []
        try:
            snapshot = read_python_ast(self.workspace / path)
        except (OSError, SyntaxError, UnicodeError):
            return []
        reads = literal_repository_file_reads(snapshot.tree, path, target)
        self.source.ensure_current(path)
        member = self.reads.file_row(path)
        if member is None:
            return []
        for read in reads:
            read.update(
                reader_path=path,
                reader_revision=member.get("file_digest"),
                source_revision=target_revision,
            )
        return reads

    def _verification_collect_file_reads(
        self, state: _VerificationRelevanceState
    ) -> None:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        if PurePosixPath(state.edit_path).suffix in {".py", ".pyi"}:
            return
        # Bounded lexical discovery and deliberately limited syntax can establish
        # positive relationships, never complete absence of file readers.
        state.search_bound_reasons.add("literal-file-reader-syntax-scope")
        self.source.ensure_current(state.edit_path)
        target = self.reads.file_row(state.edit_path)
        if target is None or self.files.visible_file(state.edit_path) is None:
            return
        for row in self._verification_test_lexical_rows(state)[
            : VERIFICATION_RELEVANCE_DEFAULTS.literal_file_reader_paths
        ]:
            path = str(row["path"])
            if not path.endswith(".py") or not self._verification_ref_visible(row):
                continue
            if (
                self.files.decide(path).evidence_visibility
                is not EvidenceVisibility.SOURCE
            ):
                continue
            reads = self._verification_file_read_evidence(
                path, state.edit_path, target.get("file_digest")
            )
            if reads:
                state.candidate_paths.add(path)
                state.file_read_references[path] = reads
        self.source.ensure_current(state.edit_path)
