"""Static uv workspace candidate matching, shared by CodeMap observers.

The candidate universe is supplied by the repository admission owner. Matching
declared patterns never establishes native uv discovery or effective membership.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Sequence
from pathlib import PurePath


def uv_workspace_patterns(value: object) -> tuple[str, ...]:
    """Preserve the existing bounded observer's pattern normalization."""
    if not isinstance(value, list):
        return ()
    return tuple(
        item.strip().strip("/")
        for item in value
        if isinstance(item, str) and item.strip()
    )


def uv_workspace_member(
    pyproject: PurePath,
    workspace: PurePath,
    members: Sequence[str],
    excludes: Sequence[str],
) -> bool:
    """Apply one admitted workspace declaration to a nominated candidate."""
    if pyproject == workspace / "pyproject.toml":
        return True
    try:
        project = pyproject.parent.relative_to(workspace).as_posix()
    except ValueError:
        return False
    return any(
        fnmatch.fnmatchcase(project, pattern) for pattern in members
    ) and not any(fnmatch.fnmatchcase(project, pattern) for pattern in excludes)
