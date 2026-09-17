from __future__ import annotations

import os
from dataclasses import dataclass, field
from hashlib import sha256
from typing import TYPE_CHECKING

from .digest import encode_field
from .paths import (
    canonical_host_path,
    has_glob,
    normalize_relative_path,
    normalize_relative_pattern,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
    from pathlib import Path

_MANIFEST_DOMAIN = b"fastidentity.input-manifest.v1\0"


@dataclass(frozen=True, slots=True)
class InputManifest:
    """Resolved, canonical Step input paths.

    Paths are validated once. The derived fingerprint is also computed once,
    so repeated identity reads can use O(1) manifest-cache lookup rather than
    re-hashing or re-normalizing a potentially huge path tuple.
    """

    paths: tuple[str, ...]
    fingerprint: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if tuple(sorted(set(self.paths))) != self.paths:
            raise ValueError("InputManifest paths must be sorted and unique")
        h = sha256()
        h.update(_MANIFEST_DOMAIN)
        for path in self.paths:
            if normalize_relative_path(path, allow_root=False) != path:
                raise ValueError(f"InputManifest path is not canonical: {path}")
            h.update(encode_field(path.encode("utf-8", errors="surrogateescape")))
        object.__setattr__(self, "fingerprint", h.hexdigest())

    @classmethod
    def resolve(
        cls,
        workspace: str | Path,
        patterns: Iterable[str],
        *,
        require_matches: bool = True,
    ) -> InputManifest:
        root = canonical_host_path(workspace)
        paths = resolve_inputs(
            root,
            patterns,
            require_matches=require_matches,
        )
        return cls(tuple(_remove_descendants_of_selected_dirs(root, paths)))

    def __iter__(self) -> Iterator[str]:
        return iter(self.paths)

    def __len__(self) -> int:
        return len(self.paths)


def _remove_descendants_of_selected_dirs(root: Path, rels: list[str]) -> list[str]:
    selected: list[str] = []
    selected_dirs: list[str] = []
    for rel in rels:
        if any(rel != d and rel.startswith(d.rstrip("/") + "/") for d in selected_dirs):
            continue
        selected.append(rel)
        absolute = root / rel
        if absolute.is_dir() and not absolute.is_symlink():
            selected_dirs.append(rel)
    return selected


def resolve_inputs(
    workspace: str | Path,
    patterns: Iterable[str],
    *,
    require_matches: bool = True,
) -> list[str]:
    """Resolve declared relative paths/globs into canonical relative paths."""
    root = canonical_host_path(workspace)
    found: set[str] = set()

    for raw_pattern in patterns:
        pattern = normalize_relative_pattern(raw_pattern)
        candidate = root / pattern

        if not has_glob(pattern):
            if os.path.lexists(candidate):
                found.add(pattern)
                continue
            if require_matches:
                raise FileNotFoundError(f"input pattern matched nothing: {pattern}")
            continue

        matched = False
        for match in root.glob(pattern):
            matched = True
            # Do not resolve the leaf: resolving would follow symlinks and
            # change canonical link semantics.
            found.add(match.relative_to(root).as_posix())
        if require_matches and not matched:
            raise FileNotFoundError(f"input pattern matched nothing: {pattern}")

    return sorted(found)
