from __future__ import annotations

import ast
import os
import sys
from collections import OrderedDict
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import cached_property, lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from functools import _CacheInfo

_FileIdentity = tuple[int, int, int, int, int]
_MAX_SOURCE_TREES = 32
_MAX_SOURCE_BYTES = 8 * 1024 * 1024


@dataclass(slots=True)
class _SourceTrees:
    entries: OrderedDict[tuple[str, str], ast.Module] = field(
        default_factory=OrderedDict
    )
    size: int = 0
    active: bool = True

    def get(self, key: tuple[str, str]) -> ast.Module | None:
        if not self.active or key not in self.entries:
            return None
        self.entries.move_to_end(key)
        return self.entries[key]

    def retain(self, key: tuple[str, str], tree: ast.Module) -> None:
        size = len(key[1].encode("utf-8"))
        if not self.active or size > _MAX_SOURCE_BYTES:
            return
        self.entries[key] = tree
        self.size += size
        while len(self.entries) > _MAX_SOURCE_TREES or self.size > _MAX_SOURCE_BYTES:
            old, _ = self.entries.popitem(last=False)
            self.size -= len(old[1].encode("utf-8"))

    def clear(self) -> None:
        self.entries.clear()
        self.size = 0
        self.active = False


_source_trees: ContextVar[_SourceTrees | None] = ContextVar(
    "hashmarks_python_source_trees", default=None
)


def python_ast_signature() -> str:
    """Identify the canonical Python grammar and source parsing implementation."""
    version = ".".join(str(part) for part in sys.version_info[:3])
    return f"hashmarks.python-source.v1:{sys.implementation.name}:{version}"


def parse_python_ast(source: str | bytes, *, filename: str = "<unknown>") -> ast.Module:
    """Parse admitted UTF-8 source, reusing exact input within one observation.

    Consumers must treat returned trees as immutable. Filenames affect syntax
    diagnostics only; successful AST nodes contain coordinates in this source.
    Reuse never establishes repository identity or freshness.
    """
    text = source.decode("utf-8") if isinstance(source, bytes) else source
    key = (python_ast_signature(), text)
    trees = _source_trees.get()
    cached = trees.get(key) if trees is not None else None
    if cached is not None:
        return cached
    tree = ast.parse(text, filename=filename)
    if trees is not None:
        trees.retain(key, tree)
    return tree


@contextmanager
def python_ast_session() -> Iterator[None]:
    """Bound source-tree reuse to the existing outer observation lifetime."""
    existing = _source_trees.get()
    if existing is not None and existing.active:
        yield
        return
    trees = _SourceTrees()
    token = _source_trees.set(trees)
    try:
        yield
    finally:
        trees.clear()
        _source_trees.reset(token)


class UnstablePythonSourceError(OSError):
    """Raised when a Python source file changes while its parse snapshot is read."""


@dataclass(frozen=True)
class PythonAstSnapshot:
    source: str
    tree: ast.Module
    identity: _FileIdentity

    @property
    def size_bytes(self) -> int:
        """Describe physical size at the stable read, never content identity."""
        return self.identity[2]

    @cached_property
    def function_definitions_by_name(
        self,
    ) -> Mapping[str, tuple[ast.FunctionDef | ast.AsyncFunctionDef, ...]]:
        """Index declarations once in this snapshot, preserving duplicate names.

        This is syntax acceleration only. Callers still own scope qualification,
        ambiguity and repository freshness; the index is not symbol authority.
        """
        definitions: dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]] = {}
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                definitions.setdefault(node.name, []).append(node)
        return MappingProxyType(
            {name: tuple(nodes) for name, nodes in definitions.items()}
        )

    @cached_property
    def function_definitions_by_qualname(
        self,
    ) -> Mapping[str, tuple[ast.FunctionDef | ast.AsyncFunctionDef, ...]]:
        """Index exact lexical scopes, retaining duplicate declarations.

        Like the short-name index, this is acceleration within one stable AST
        snapshot. Consumers still qualify binding, ambiguity and freshness.
        """
        definitions: dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]] = {}

        def visit(node: ast.AST, scope: tuple[str, ...]) -> None:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                scope = (*scope, node.name)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    definitions.setdefault(".".join(scope), []).append(node)
            for child in ast.iter_child_nodes(node):
                visit(child, scope)

        visit(self.tree, ())
        return MappingProxyType(
            {name: tuple(nodes) for name, nodes in definitions.items()}
        )


def _metadata(path: Path) -> _FileIdentity:
    stat = path.stat()
    return (
        int(stat.st_dev),
        int(stat.st_ino),
        int(stat.st_size),
        int(stat.st_mtime_ns),
        int(stat.st_ctime_ns),
    )


@lru_cache(maxsize=4096)
def _cached_snapshot(
    absolute_path: str,
    identity: _FileIdentity,
    encoding: str,
    errors: str,
) -> PythonAstSnapshot:
    path = Path(absolute_path)
    source = path.read_text(encoding=encoding, errors=errors)
    if _metadata(path) != identity:
        raise UnstablePythonSourceError(f"Python source changed while reading: {path}")
    tree = parse_python_ast(source, filename=absolute_path)
    return PythonAstSnapshot(source=source, tree=tree, identity=identity)


def read_python_ast(
    path: str | Path,
    *,
    encoding: str = "utf-8",
    errors: str = "strict",
    max_attempts: int = 3,
) -> PythonAstSnapshot:
    """Return a freshness-bound source/AST snapshot for one Python file.

    Filesystem metadata is only a process-local acceleration key. The cache
    never becomes repository identity authority: callers still observe a miss
    whenever device/inode/size/mtime/ctime changes, and a concurrent edit
    during the read is retried rather than cached as a stable snapshot.
    """
    absolute = os.path.abspath(os.fspath(path))
    candidate = Path(absolute)
    last_error: UnstablePythonSourceError | None = None
    for _ in range(max_attempts):
        identity = _metadata(candidate)
        try:
            return _cached_snapshot(absolute, identity, encoding, errors)
        except UnstablePythonSourceError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise UnstablePythonSourceError(f"could not read stable Python source: {candidate}")


def ast_cache_info() -> _CacheInfo:
    return _cached_snapshot.cache_info()


def clear_ast_cache() -> None:
    _cached_snapshot.cache_clear()


__all__ = [
    "PythonAstSnapshot",
    "UnstablePythonSourceError",
    "ast_cache_info",
    "clear_ast_cache",
    "parse_python_ast",
    "python_ast_session",
    "python_ast_signature",
    "read_python_ast",
]
