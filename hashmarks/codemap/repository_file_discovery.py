from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, cast

from hashmarks.paths import normalize_relative_path

if TYPE_CHECKING:
    from .engine import CodeMap

_PRUNE_DIRS = {
    ".git",
    ".hashmarks",
    ".fastidentity",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".next",
    "target",
    ".tox",
    ".nox",
    "coverage",
    ".coverage",
}


def _is_pruned_relative_path(rel: str) -> bool:
    """Return whether repository discovery must stop at any path segment."""
    normalized = rel.replace("\\", "/").strip("/")
    if not normalized:
        return False
    return any(part in _PRUNE_DIRS for part in PurePosixPath(normalized).parts)


@dataclass(frozen=True)
class _AdmittedRepositoryFile:
    rel: str
    path: Path
    visibility: EvidenceVisibility


class RepositoryFileDiscoveryMixin:
    """Canonical admission and traversal for repository-owned file surfaces."""

    def _path_admitted_for_analysis(self, rel: str) -> bool:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        return (
            not self._internal_path(rel)
            and not _is_pruned_relative_path(rel)
            and self.policy.decide(rel).index
        )

    def _workspace_relative_path(self, path: Path) -> str | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        try:
            value = path.relative_to(self.workspace).as_posix()
        except ValueError:
            return None
        return "" if value == "." else value

    def _prune_discovery_dirs(self, root_path: Path, dirs: list[str]) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        root_rel = self._workspace_relative_path(root_path) or ""
        dirs[:] = sorted(
            name
            for name in dirs
            if name not in _PRUNE_DIRS
            and not self._internal_path(f"{root_rel}/{name}".strip("/"))
        )

    def _admitted_repository_file(
        self,
        path: Path,
    ) -> _AdmittedRepositoryFile | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if path.is_symlink() or not path.is_file():
            return None
        rel = self._workspace_relative_path(path)
        if rel is None or not rel or not self._path_admitted_for_analysis(rel):
            return None
        decision = self.policy.decide(rel)
        return _AdmittedRepositoryFile(
            rel=rel,
            path=path,
            visibility=decision.evidence_visibility,
        )

    def _repository_walk_root(self, prefix: str) -> Path | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        rel = normalize_relative_path(prefix, allow_root=True)
        root = self.workspace if not rel else self.workspace / rel
        if root.is_symlink():
            return None
        if rel and not self._path_admitted_for_analysis(rel):
            return None
        return root

    def _iter_admitted_directory_files(
        self,
        root: Path,
    ) -> Iterator[_AdmittedRepositoryFile]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        for current_root, dirs, files in os.walk(
            root,
            topdown=True,
            followlinks=False,
        ):
            root_path = Path(current_root)
            self._prune_discovery_dirs(root_path, dirs)
            for name in sorted(files):
                item = self._admitted_repository_file(root_path / name)
                if item is not None:
                    yield item

    def _iter_admitted_repository_files(
        self,
        prefix: str = "",
    ) -> Iterator[_AdmittedRepositoryFile]:
        root = self._repository_walk_root(prefix)
        if root is None:
            return
        if root.is_file():
            item = self._admitted_repository_file(root)
            if item is not None:
                yield item
            return
        if root.is_dir():
            yield from self._iter_admitted_directory_files(root)
