"""Index-owned Python packaging interpretation bound to exact manifest bytes.

The observations are operation-local contributors to Index publication. They do
not introduce another graph, persistent cache or repository identity authority.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from hashmarks.file_store import UnstableFileError

from .uv_workspace import uv_workspace_member, uv_workspace_patterns

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from hashmarks.file_store import FileDigestStore

    from .repository_file_discovery import RepositoryFiles


@dataclass(frozen=True)
class PythonImportRoots:
    roots: tuple[str, ...]
    revisions: tuple[tuple[str, str], ...]

    def recheck(self, files: RepositoryFiles, file_store: FileDigestStore) -> None:
        """Reject publication if current admitted bytes differ from interpreted bytes."""
        for rel, revision in self.revisions:
            admitted = files.visible_file(rel)
            if admitted is None:
                raise UnstableFileError(f"Python import-root input unavailable: {rel}")
            try:
                current = file_store.digest(
                    admitted.path,
                    workspace=files.workspace,
                    relative_path=rel,
                    force=True,
                ).hash
            except OSError as exc:
                raise UnstableFileError(
                    f"Python import-root input unavailable: {rel}"
                ) from exc
            if current != revision:
                raise UnstableFileError(f"Python import-root input changed: {rel}")


def _uv_workspace_pyprojects(
    workspace: Path, documents: Mapping[Path, object]
) -> tuple[Path, ...]:
    """Interpret workspace filtering from the same captured project bytes."""
    data = documents.get(workspace / "pyproject.toml")
    tool = data.get("tool") if isinstance(data, dict) else None
    uv = tool.get("uv") if isinstance(tool, dict) else None
    workspace_cfg = uv.get("workspace") if isinstance(uv, dict) else None
    if not isinstance(workspace_cfg, dict):
        return tuple(documents)
    members = workspace_cfg.get("members")
    if not isinstance(members, list):
        return tuple(documents)
    member_patterns = uv_workspace_patterns(members)
    exclude_patterns = uv_workspace_patterns(workspace_cfg.get("exclude"))
    return tuple(
        pyproject
        for pyproject in documents
        if uv_workspace_member(pyproject, workspace, member_patterns, exclude_patterns)
    )


def _setuptools_source_roots(tool: dict[str, object]) -> set[str]:
    configured: set[str] = set()
    setuptools = tool.get("setuptools")
    if not isinstance(setuptools, dict):
        return configured
    package_dir = setuptools.get("package-dir")
    if not isinstance(package_dir, dict):
        return configured
    root = package_dir.get("")
    if isinstance(root, str) and root.strip():
        configured.add(root.strip().strip("/"))
    return configured


def _hatch_source_roots(tool: dict[str, object]) -> set[str]:
    configured: set[str] = set()
    hatch = tool.get("hatch")
    if not isinstance(hatch, dict):
        return configured
    build = hatch.get("build")
    targets = build.get("targets") if isinstance(build, dict) else None
    wheel = targets.get("wheel") if isinstance(targets, dict) else None
    packages = wheel.get("packages") if isinstance(wheel, dict) else None
    if not isinstance(packages, list):
        return configured
    for package in packages:
        if isinstance(package, str) and "/" in package.strip("/"):
            configured.add(package.strip("/").split("/", 1)[0])
    return configured


def _poetry_source_roots(tool: dict[str, object]) -> set[str]:
    configured: set[str] = set()
    poetry = tool.get("poetry")
    packages = poetry.get("packages") if isinstance(poetry, dict) else None
    if not isinstance(packages, list):
        return configured
    for package in packages:
        if not isinstance(package, dict):
            continue
        root = package.get("from")
        if isinstance(root, str) and root.strip():
            configured.add(root.strip().strip("/"))
    return configured


def _project_source_roots(data: object) -> set[str]:
    tool = data.get("tool") if isinstance(data, dict) else None
    tool = tool if isinstance(tool, dict) else {}
    return {
        *_setuptools_source_roots(tool),
        *_hatch_source_roots(tool),
        *_poetry_source_roots(tool),
    }


def observe_python_import_roots(
    workspace: Path, pyprojects: Sequence[Path], file_store: FileDigestStore
) -> PythonImportRoots:
    """Reuse packaging semantics over one stable byte observation per contributor."""
    documents: dict[Path, object] = {}
    revisions: list[tuple[str, str]] = []
    for path in pyprojects:
        try:
            raw, digest = file_store.read_bytes_stable(path)
        except OSError as exc:
            raise UnstableFileError(
                f"Python import-root input unavailable: {path.relative_to(workspace)}"
            ) from exc
        revisions.append((path.relative_to(workspace).as_posix(), digest.hash))
        try:
            documents[path] = tomllib.loads(raw.decode("utf-8"))
        except (UnicodeError, tomllib.TOMLDecodeError):
            documents[path] = None
    roots: set[str] = set()
    for path in _uv_workspace_pyprojects(workspace, documents):
        prefix = path.parent.relative_to(workspace).as_posix()
        for root in _project_source_roots(documents[path]):
            combined = "/".join(part for part in (prefix, root) if part and part != ".")
            if combined:
                roots.add(combined)
    return PythonImportRoots(tuple(sorted(roots)), tuple(revisions))
