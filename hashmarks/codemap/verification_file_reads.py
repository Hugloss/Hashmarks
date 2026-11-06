"""Bounded structural observations of test inputs from repository-owned files.

Literal text only locates candidate sources. A qualified AST must prove an
unshadowed pathlib read or default shutil directory copy rooted at that source
file's repository ancestor. This observes an input relationship, never test
sufficiency or execution.
"""

from __future__ import annotations

import ast
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
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
        case (
            ast.Attribute(value=value, ctx=ast.Store() | ast.Del())
            | ast.Subscript(value=value, ctx=ast.Store() | ast.Del())
        ):
            while isinstance(value, (ast.Attribute, ast.Subscript)):
                value = value.value
            return value.id if isinstance(value, ast.Name) else None
    return None


def _name_uses(
    tree: ast.Module,
) -> tuple[Counter[str], Counter[str], Counter[str]]:
    counts: Counter[str] = Counter()
    loads: Counter[str] = Counter()
    iterations: Counter[str] = Counter()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            counts.update(
                alias.asname or alias.name.split(".", 1)[0] for alias in node.names
            )
        elif (name := _binding_name(node)) is not None:
            counts[name] += 1
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            loads[node.id] += 1
        elif isinstance(node, ast.For) and isinstance(node.iter, ast.Name):
            iterations[node.iter.id] += 1
    return counts, loads, iterations


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


def _copy_imports(
    tree: ast.Module, counts: Counter[str]
) -> tuple[frozenset[str], frozenset[str]]:
    modules: set[str] = set()
    functions: set[str] = set()
    for statement in tree.body:
        if isinstance(statement, ast.Import):
            modules.update(
                alias.asname or alias.name
                for alias in statement.names
                if alias.name == "shutil" and counts[alias.asname or alias.name] == 1
            )
        elif (
            isinstance(statement, ast.ImportFrom)
            and statement.module == "shutil"
            and not statement.level
        ):
            functions.update(
                alias.asname or alias.name
                for alias in statement.names
                if alias.name == "copytree" and counts[alias.asname or alias.name] == 1
            )
    return frozenset(modules), frozenset(functions)


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


def _has_loop_exit(node: ast.AST, *, nested_loop: bool = False) -> bool:
    if isinstance(
        node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
    ):
        return False
    if isinstance(node, (ast.Return, ast.Raise)):
        return True
    if isinstance(node, (ast.Break, ast.Continue)):
        return not nested_loop
    if isinstance(node, ast.Assert) and isinstance(node.test, ast.Constant):
        return not bool(node.test.value)
    if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
        return any(
            _has_loop_exit(child, nested_loop=True) for child in node.body
        ) or any(
            _has_loop_exit(child, nested_loop=nested_loop) for child in node.orelse
        )
    return any(
        _has_loop_exit(child, nested_loop=nested_loop)
        for child in ast.iter_child_nodes(node)
    )


@dataclass(frozen=True)
class _ReadSyntaxScope:
    tests_only: bool
    copy_imports: tuple[frozenset[str], frozenset[str]]
    copy_inputs_only: bool


class _LiteralReadVisitor(ast.NodeVisitor):
    def __init__(
        self,
        roots: frozenset[str],
        names: frozenset[str],
        target: str,
        *,
        counts: Counter[str],
        iteration_only_names: frozenset[str],
        scope: _ReadSyntaxScope,
    ) -> None:
        self.roots = roots
        self.names = names
        self.target = target
        self.counts = counts
        self.iteration_only_names = iteration_only_names
        self.collections: dict[str, tuple[tuple[str, ...], ...]] = {}
        self.iterated_targets: set[str] = set()
        self.tests_only = scope.tests_only
        self.copy_modules, self.copy_functions = scope.copy_imports
        self.copy_inputs_only = scope.copy_inputs_only
        self.copy_scope = True
        self.test: str | None = None
        self.in_function = False
        self.terminated = False
        self.reads: list[dict[str, object]] = []

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if self.in_function:
            return
        self.in_function = True
        self.terminated = False
        self.test = (
            node.name if not self.tests_only or node.name.startswith("test_") else None
        )
        outer_collections = self.collections.copy()
        outer_targets = self.iterated_targets
        self.iterated_targets = set()
        for child in node.body:
            self.visit(child)
            if self.terminated:
                break
        self.test = None
        self.in_function = False
        self.collections = outer_collections
        self.iterated_targets = outer_targets

    def visit_Assign(self, node: ast.Assign) -> None:
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            paths = self._finite_paths(node.value)
            if (
                paths is not None
                and self.counts[name] == 1
                and name in self.iteration_only_names
            ):
                self.collections[name] = paths
        self.generic_visit(node)

    def _finite_paths(self, node: ast.expr) -> tuple[tuple[str, ...], ...] | None:
        if isinstance(node, ast.Name):
            return self.collections.get(node.id)
        if not isinstance(node, (ast.Tuple, ast.List)) or not (
            0
            < len(node.elts)
            <= VERIFICATION_RELEVANCE_DEFAULTS.literal_file_read_sites
        ):
            return None
        paths = tuple(_literal_path(item, self.roots, self.names) for item in node.elts)
        return (
            tuple(path for path in paths if path is not None)
            if all(path is not None for path in paths)
            else None
        )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        # Class-based/custom collection is outside this explicit syntax scope.
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return

    def _visit_comprehension(self, node: ast.expr) -> None:
        outer_targets = self.iterated_targets
        self.iterated_targets = set()
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp)) and all(
            not generator.is_async
            and not generator.ifs
            and isinstance(generator.iter, (ast.List, ast.Tuple, ast.Set))
            and bool(generator.iter.elts)
            and all(isinstance(item, ast.Constant) for item in generator.iter.elts)
            for generator in node.generators
        ):
            self.generic_visit(node)
        else:
            self._visit_copy_guarded(node)
        self.iterated_targets = outer_targets

    visit_ListComp = _visit_comprehension
    visit_SetComp = _visit_comprehension
    visit_DictComp = _visit_comprehension

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        # Python eagerly evaluates only the outermost iterator expression.
        # Merely constructing a generator does not read its deferred body.
        self.visit(node.generators[0].iter)

    @contextmanager
    def _copy_guard(self) -> Iterator[None]:
        previous = self.copy_scope
        self.copy_scope = False
        try:
            yield
        finally:
            self.copy_scope = previous

    def _visit_copy_guarded(self, node: ast.AST) -> None:
        with self._copy_guard():
            self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.visit(node.values[0])
        with self._copy_guard():
            for operand in node.values[1:]:
                self.visit(operand)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.visit(node.test)
        if isinstance(node.test, ast.Constant):
            self.visit(node.body if bool(node.test.value) else node.orelse)
        else:
            with self._copy_guard():
                self.visit(node.body)
                self.visit(node.orelse)

    visit_Try = _visit_copy_guarded
    visit_TryStar = _visit_copy_guarded
    visit_Match = _visit_copy_guarded

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

    def visit_Assert(self, node: ast.Assert) -> None:
        self.visit(node.test)
        if isinstance(node.test, ast.Constant):
            if not bool(node.test.value):
                if node.msg is not None:
                    self.visit(node.msg)
                self.terminated = True
        elif node.msg is not None:
            with self._copy_guard():
                self.visit(node.msg)

    def visit_While(self, node: ast.While) -> None:
        return

    def visit_For(self, node: ast.For) -> None:
        paths = self._finite_paths(node.iter)
        if (
            paths is None
            or not isinstance(node.target, ast.Name)
            or self.counts[node.target.id] != 1
            or any(_has_loop_exit(child) for child in node.body)
        ):
            return
        outer_targets = self.iterated_targets.copy()
        if any(PurePosixPath(*parts).as_posix() == self.target for parts in paths):
            self.iterated_targets.add(node.target.id)
        for child in node.body:
            self.visit(child)
        self.iterated_targets = outer_targets

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        return

    def visit_Call(self, node: ast.Call) -> None:
        reader_scope = (
            self.test is not None or not self.tests_only and not self.in_function
        )
        directory = self._copied_directory(node)
        observed_input = directory is not None or (
            not self.copy_inputs_only and self._reads_target(node)
        )
        if (
            reader_scope
            and not self.terminated
            and len(self.reads)
            < VERIFICATION_RELEVANCE_DEFAULTS.literal_file_read_sites
            and observed_input
        ):
            self.reads.append(
                {
                    "source_path": self.target,
                    "test_symbol" if self.tests_only else "reader_symbol": self.test,
                    "line": node.lineno,
                    "end_line": node.end_lineno or node.lineno,
                    "basis": "unshadowed-shutil-copytree-input"
                    if directory is not None
                    else "unshadowed-pathlib-literal-read",
                    **(
                        {"source_directory": directory} if directory is not None else {}
                    ),
                    **(
                        {
                            "line": node.func.value.lineno,
                            "end_line": node.func.value.end_lineno,
                            "start_byte_column": node.func.value.col_offset,
                            "end_byte_column": node.func.value.end_col_offset,
                        }
                        if not self.tests_only and isinstance(node.func, ast.Attribute)
                        else {}
                    ),
                }
            )
        self.generic_visit(node)

    def _copied_directory(self, node: ast.Call) -> str | None:
        # Only the default copy operation establishes this positive input
        # relationship. Filters, custom copy functions and computed sources
        # remain outside the observed syntax; runtime success is not inferred.
        function = node.func
        qualified = (
            isinstance(function, ast.Name)
            and function.id in self.copy_functions
            or isinstance(function, ast.Attribute)
            and function.attr == "copytree"
            and isinstance(function.value, ast.Name)
            and function.value.id in self.copy_modules
        )
        if not self.copy_scope or not qualified or len(node.args) != 2 or node.keywords:
            return None
        parts = _literal_path(node.args[0], self.roots, self.names)
        if not parts:
            return None
        source = PurePosixPath(*parts)
        target = PurePosixPath(self.target)
        return source.as_posix() if source in target.parents else None

    def _reads_target(self, node: ast.Call) -> bool:
        if not isinstance(node.func, ast.Attribute) or node.func.attr not in {
            "read_text",
            "read_bytes",
        }:
            return False
        parts = _literal_path(node.func.value, self.roots, self.names)
        if parts is not None:
            return PurePosixPath(*parts).as_posix() == self.target
        receiver = node.func.value
        while _is_call(receiver, self.names) and isinstance(receiver, ast.Call):
            receiver = receiver.args[0]
        return isinstance(receiver, ast.Name) and receiver.id in self.iterated_targets


def literal_repository_file_reads(
    tree: ast.Module,
    reader_path: str,
    target: str,
    *,
    tests_only: bool = True,
    include_directory_copies: bool = False,
) -> list[dict[str, object]]:
    counts, collection_uses, iteration_uses = _name_uses(tree)
    names = _path_imports(tree, counts)
    roots = _root_bindings(
        tree, names, counts, len(PurePosixPath(reader_path).parts) - 1
    )
    visitor = _LiteralReadVisitor(
        roots,
        names,
        target,
        counts=counts,
        iteration_only_names=frozenset(
            name
            for name, uses in collection_uses.items()
            if uses == iteration_uses[name]
        ),
        scope=_ReadSyntaxScope(
            tests_only=tests_only,
            copy_imports=_copy_imports(tree, counts)
            if include_directory_copies
            else (frozenset(), frozenset()),
            copy_inputs_only=tests_only
            and PurePosixPath(target).suffix in {".py", ".pyi"},
        ),
    )
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
        copied, ambiguous_copy = self.imports._resolve_import_owner_evidence(
            path, "shutil.copytree"
        )
        reads = literal_repository_file_reads(
            snapshot.tree,
            path,
            target,
            include_directory_copies=not copied and not ambiguous_copy,
        )
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
        # Bounded lexical discovery and deliberately limited syntax can establish
        # positive relationships, never complete absence of file readers.
        state.search_bound_reasons.add("literal-file-reader-syntax-scope")
        self.source.ensure_current(state.edit_path)
        target, _raw = self.source.member(state.edit_path)
        if target.get("state") != "known-present":
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
                path, state.edit_path, target.get("member_revision")
            )
            if reads:
                state.candidate_paths.add(path)
                state.file_read_references[path] = reads
        self.source.ensure_current(state.edit_path)
