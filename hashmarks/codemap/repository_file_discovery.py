from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from hashmarks.paths import canonical_host_path, normalize_relative_path

from .model import EvidenceVisibility
from .policy import ContextPolicy, PolicyDecision

_PRUNE_DIRS = {
    ".git",
    ".hashmarks",
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


class RepositoryFiles:
    """Own repository admission, visible traversal and the loaded context policy.

    Dependencies are canonical workspace/control paths, never a CodeMap facade,
    index, database, parser or consumer. This component owns its policy state;
    callers reconcile their derived evidence when refresh_policy reports change.
    """

    def __init__(
        self,
        workspace: str | Path,
        *,
        internal_state_path: str | None = None,
        policy_path: Path | None = None,
    ) -> None:
        self._workspace = canonical_host_path(workspace)
        self._internal_state_path = internal_state_path
        self._policy_path = (
            None
            if policy_path is None
            else canonical_host_path(self._workspace / policy_path)
        )
        self._policy = ContextPolicy.load(self._workspace, self._policy_path)

    @property
    def workspace(self) -> Path:
        return self._workspace

    @property
    def internal_state_path(self) -> str | None:
        return self._internal_state_path

    def decide(self, path: str) -> PolicyDecision:
        return self._policy.decide(path)

    def policy_fingerprint(self) -> str:
        return self._policy.fingerprint()

    def refresh_policy(self) -> bool:
        """Observe the configured policy; report semantic change without indexing."""
        current = ContextPolicy.load(self._workspace, self._policy_path)
        if current.fingerprint() == self._policy.fingerprint():
            return False
        self._policy = current
        return True

    def is_internal(self, rel: str) -> bool:
        clean = normalize_relative_path(rel, allow_root=True)
        state = self._internal_state_path
        return bool(state and (clean == state or clean.startswith(state + "/")))

    @staticmethod
    def discovery_coverage(admitted_count: int) -> dict[str, object]:
        """Project known admission scope without enumerating excluded members."""
        return {
            "scope": "discovered-policy-admitted-indexable-members",
            "admitted_member_count": admitted_count,
            "known_pruned_directory_classes": sorted(_PRUNE_DIRS),
            "pruned_member_count": None,
            "unreadable_member_count": None,
            "repository_wide_completeness": "not-claimed",
            "absence_outside_admitted_scope": "not-admissible",
            "basis": "canonical-repository-file-discovery",
        }

    def _inside_nested_repository(self, rel: str) -> bool:
        directory = self._workspace
        for part in PurePosixPath(rel).parts:
            directory /= part
            if (directory / ".git").exists():
                return True
        return False

    def is_admitted(self, rel: str) -> bool:
        rel = normalize_relative_path(rel, allow_root=True)
        return (
            not self.is_internal(rel)
            and not _is_pruned_relative_path(rel)
            and not self._inside_nested_repository(rel)
            and self.decide(rel).index
        )

    def relative_path(self, path: Path) -> str | None:
        try:
            value = path.relative_to(self._workspace).as_posix()
        except ValueError:
            return None
        return "" if value == "." else value

    def _prune_discovery_dirs(self, root_path: Path, dirs: list[str]) -> None:
        root_rel = self.relative_path(root_path) or ""
        dirs[:] = sorted(
            name
            for name in dirs
            if name not in _PRUNE_DIRS
            and not self.is_internal(f"{root_rel}/{name}".strip("/"))
            and not (root_path / name / ".git").exists()
        )

    def _admitted_repository_file(
        self,
        path: Path,
    ) -> _AdmittedRepositoryFile | None:
        if path.is_symlink() or not path.is_file():
            return None
        rel = self.relative_path(path)
        if rel is None or not rel or not self.is_admitted(rel):
            return None
        decision = self.decide(rel)
        return _AdmittedRepositoryFile(
            rel=rel,
            path=path,
            visibility=decision.evidence_visibility,
        )

    def _repository_walk_root(self, prefix: str) -> Path | None:
        rel = normalize_relative_path(prefix, allow_root=True)
        root = self._workspace if not rel else self._workspace / rel
        if root.is_symlink():
            return None
        if rel and not self.is_admitted(rel):
            return None
        return root

    def _iter_admitted_directory_files(
        self,
        root: Path,
    ) -> Iterator[_AdmittedRepositoryFile]:
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

    def iter_files(
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

    def visible_file(
        self,
        relpath: str,
    ) -> _AdmittedRepositoryFile | None:
        try:
            rel = normalize_relative_path(relpath, allow_root=False)
        except ValueError:
            return None
        item = self._admitted_repository_file(self._workspace / rel)
        if item is None or item.visibility is EvidenceVisibility.DENY:
            return None
        return item

    def visible_manifests(
        self,
        filename: str,
    ) -> tuple[Path, ...]:
        name = filename.strip()
        if not name or "/" in name or "\\" in name:
            raise ValueError("manifest filename must be a basename")
        return tuple(
            item.path
            for item in self.iter_files()
            if item.path.name == name and item.visibility is not EvidenceVisibility.DENY
        )

    def has_visible_file(self, prefix: str) -> bool:
        try:
            rel = normalize_relative_path(prefix, allow_root=True)
        except ValueError:
            return False
        for item in self.iter_files(rel):
            if item.visibility is not EvidenceVisibility.DENY:
                return True
        return False
