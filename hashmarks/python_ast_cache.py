from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_FileIdentity = tuple[int, int, int, int, int]


class UnstablePythonSourceError(OSError):
    """Raised when a Python source file changes while its parse snapshot is read."""


@dataclass(frozen=True)
class PythonAstSnapshot:
    source: str
    tree: ast.Module
    identity: _FileIdentity


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
    tree = ast.parse(source, filename=absolute_path)
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


def ast_cache_info():
    return _cached_snapshot.cache_info()


def clear_ast_cache() -> None:
    _cached_snapshot.cache_clear()


__all__ = [
    "PythonAstSnapshot",
    "UnstablePythonSourceError",
    "ast_cache_info",
    "clear_ast_cache",
    "read_python_ast",
]
