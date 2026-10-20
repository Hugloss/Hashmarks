from __future__ import annotations

import os
from contextlib import contextmanager
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
    from collections.abc import Callable, Iterable, Iterator
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


@contextmanager
def _input_match_scope(
    root: Path,
    pattern: str,
    *,
    bounded: bool,
) -> Iterator[Iterable[str]]:
    if bounded and pattern == "*":
        # pathlib glob implementations may buffer the whole directory. Direct
        # contents need no pattern engine, and this owner closes on interruption.
        with os.scandir(root) as entries:
            yield (entry.name for entry in entries)
    else:
        yield (match.relative_to(root).as_posix() for match in root.glob(pattern))


def _collect_input_match(
    found: set[str],
    relative: str,
    *,
    max_members: int | None,
    exclude_paths: tuple[str, ...],
    checkpoint: Callable[[], None] | None,
) -> None:
    if checkpoint is not None:
        checkpoint()
    if any(
        relative == path or relative.startswith(path + "/") for path in exclude_paths
    ):
        return
    if relative not in found and max_members is not None and len(found) >= max_members:
        raise ValueError("selected-input member limit exceeded")
    found.add(relative)


def resolve_inputs(
    workspace: str | Path,
    patterns: Iterable[str],
    *,
    require_matches: bool = True,
    max_members: int | None = None,
    exclude_paths: tuple[str, ...] = (),
    checkpoint: Callable[[], None] | None = None,
) -> list[str]:
    """Resolve declared relative paths/globs into canonical relative paths."""
    root = canonical_host_path(workspace)
    found: set[str] = set()
    if max_members is not None and (type(max_members) is not int or max_members < 1):
        raise ValueError("max_members must be a positive integer")

    for raw_pattern in patterns:
        pattern = normalize_relative_pattern(raw_pattern)
        candidate = root / pattern

        if not has_glob(pattern):
            if os.path.lexists(candidate):
                _collect_input_match(
                    found,
                    pattern,
                    max_members=max_members,
                    exclude_paths=exclude_paths,
                    checkpoint=checkpoint,
                )
                continue
            if require_matches:
                raise FileNotFoundError(f"input pattern matched nothing: {pattern}")
            continue

        matched = False
        with _input_match_scope(
            root, pattern, bounded=max_members is not None
        ) as matches:
            for relative in matches:
                matched = True
                _collect_input_match(
                    found,
                    relative,
                    max_members=max_members,
                    exclude_paths=exclude_paths,
                    checkpoint=checkpoint,
                )
        if require_matches and not matched:
            raise FileNotFoundError(f"input pattern matched nothing: {pattern}")

    return sorted(found)


@dataclass(frozen=True, slots=True)
class ResolvedInputScope:
    """One resolved selection shared by Merkle identity and member observation."""

    manifest: InputManifest
    excluded_paths: tuple[str, ...] = ()

    def excludes(self, relative_path: str) -> bool:
        return any(
            relative_path == excluded or relative_path.startswith(excluded + "/")
            for excluded in self.excluded_paths
        )

    @classmethod
    def directory_contents(
        cls,
        workspace: str | Path,
        excluded_paths: tuple[str, ...],
        *,
        max_members: int,
        checkpoint: Callable[[], None] | None = None,
    ) -> ResolvedInputScope:
        """Resolve bounded direct contents with literal selected exclusions."""
        paths = _collapse_exclusions(
            normalize_relative_path(path, allow_root=False) for path in excluded_paths
        )
        selected = resolve_inputs(
            workspace,
            ("*",),
            require_matches=False,
            max_members=max_members,
            exclude_paths=paths,
            checkpoint=checkpoint,
        )
        return cls(InputManifest(tuple(selected)), paths)

    @classmethod
    def resolve(
        cls,
        workspace: str | Path,
        patterns: Iterable[str],
        exclude: Iterable[str],
        *,
        require_matches: bool = True,
    ) -> ResolvedInputScope:
        included = InputManifest.resolve(
            workspace, patterns, require_matches=require_matches
        )
        excluded = _resolve_exclusions(workspace, exclude)
        scope = cls(included, excluded)
        return cls(
            InputManifest(tuple(path for path in included if not scope.excludes(path))),
            excluded,
        )


def _resolve_exclusions(
    workspace: str | Path, patterns: Iterable[str]
) -> tuple[str, ...]:
    resolved: set[str] = set()
    for value in patterns:
        pattern = normalize_relative_pattern(value)
        if has_glob(pattern):
            resolved.update(
                resolve_inputs(workspace, (pattern,), require_matches=False)
            )
        else:
            # Literal exclusions apply even when the named entry is absent.
            resolved.add(pattern)
    return _collapse_exclusions(resolved)


def _collapse_exclusions(paths: Iterable[str]) -> tuple[str, ...]:
    selected: list[str] = []
    for path in sorted(set(paths)):
        if not any(path.startswith(parent + "/") for parent in selected):
            selected.append(path)
    return tuple(selected)
