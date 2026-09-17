from __future__ import annotations

import os
from pathlib import Path, PurePosixPath, PureWindowsPath

_GLOB_CHARS = frozenset("*?[")


def _raw_path(value: str | Path) -> str:
    raw = os.fspath(value)
    if "\x00" in raw:
        raise ValueError("input path contains NUL byte")
    return raw.replace("\\", "/")


def canonical_host_path(value: str | Path) -> Path:
    """Return one stable host/control-path spelling.

    Host/control paths identify filesystem objects owned or observed by the
    process (workspace roots, cache roots, SQLite files, watcher roots). They
    are canonicalized exactly once so later ``chdir()`` calls, ``..`` segments,
    and symlinked ancestors cannot change their meaning.

    This helper must *not* be used for workspace identity leaves: identity
    paths are lexical and relative so final symlinks remain symlinks rather
    than being replaced by their targets.
    """
    raw = os.fspath(value)
    if "\x00" in raw:
        raise ValueError("host path contains NUL byte")
    return Path(raw).expanduser().resolve(strict=False)


def sqlite_identity_exclusions(db_path: str | Path) -> tuple[Path, ...]:
    """Canonical paths owned by one SQLite database, including sidecars."""
    db = canonical_host_path(db_path)
    return tuple(
        canonical_host_path(candidate)
        for candidate in (
            db,
            Path(str(db) + "-wal"),
            Path(str(db) + "-shm"),
            Path(str(db) + "-journal"),
        )
    )


def canonical_event_relative_path(
    root: str | Path,
    event_path: str | Path,
) -> str | None:
    """Map a watcher event to a canonical relative path without following leaf.

    Watcher paths are observations, not identity authority. Canonicalize the
    event parent so symlink aliases of the workspace collapse, but preserve the
    final path component so a symlink leaf is still identified as the link.
    Events whose canonical parent is outside ``root`` are ignored.
    """
    canonical_root = canonical_host_path(root)
    raw = Path(event_path)
    if not raw.is_absolute():
        raw = canonical_root / raw

    candidate = canonical_host_path(raw.parent) / raw.name
    try:
        rel = candidate.relative_to(canonical_root).as_posix()
    except ValueError:
        return None
    return normalize_relative_path(rel)


def _reject_absolute(raw: str) -> None:
    if (
        Path(raw).is_absolute()
        or PureWindowsPath(raw).is_absolute()
        or PureWindowsPath(raw).drive
    ):
        raise ValueError(f"input path must be relative to workspace: {raw}")


def _reject_parent_escape(raw: str) -> None:
    if ".." in PurePosixPath(raw).parts:
        raise ValueError(f"input path must not contain '..': {raw}")


def normalize_relative_path(value: str | Path, *, allow_root: bool = True) -> str:
    """Normalize a non-glob workspace-relative path without following symlinks."""
    raw = _raw_path(value)
    _reject_absolute(raw)
    _reject_parent_escape(raw)

    parts = tuple(part for part in PurePosixPath(raw).parts if part not in ("", "."))
    normalized = "/".join(parts)
    if not normalized and not allow_root:
        raise ValueError("input path must not be empty")
    return normalized


def normalize_relative_pattern(value: str | Path) -> str:
    """Validate and normalize a workspace-relative literal/glob pattern."""
    raw = _raw_path(value)
    _reject_absolute(raw)
    _reject_parent_escape(raw)
    parts = tuple(part for part in PurePosixPath(raw).parts if part not in ("", "."))
    normalized = "/".join(parts)
    if not normalized:
        raise ValueError("input pattern must not be empty")
    return normalized


def has_glob(pattern: str) -> bool:
    return any(ch in pattern for ch in _GLOB_CHARS)
