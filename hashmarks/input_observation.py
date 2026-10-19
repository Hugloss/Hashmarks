from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from .observation import UnstableObservationError
from .snapshot import InputCounts, InputMember

if TYPE_CHECKING:
    from collections.abc import Callable

    from .digest import Digest
    from .inputs import ResolvedInputScope
    from .merkle import _Node

DEFAULT_MAX_INPUT_MEMBERS = 100_000


@dataclass(frozen=True, slots=True)
class _EntryState:
    device: int
    inode: int
    mode: int
    size: int
    mtime_ns: int
    ctime_ns: int

    @classmethod
    def read(cls, path: Path) -> _EntryState:
        observed = path.lstat()
        return cls(
            observed.st_dev,
            observed.st_ino,
            observed.st_mode,
            observed.st_size,
            observed.st_mtime_ns,
            observed.st_ctime_ns,
        )

    def same_directory(self, other: _EntryState) -> bool:
        return (
            stat.S_ISDIR(self.mode)
            and stat.S_ISDIR(other.mode)
            and self.device == other.device
            and self.inode == other.inode
        )


class InputCapture:
    """Request-local inventory and stability checks for the existing Merkle walk.

    This object never hashes bytes, resolves a second membership set, or retains
    cache state. Every member digest is supplied by the canonical Merkle owner.
    """

    def __init__(
        self,
        workspace: Path,
        scope: ResolvedInputScope,
        *,
        max_members: int,
        directory_members: Callable[[str], tuple[str, ...]],
    ) -> None:
        self.workspace = workspace
        self.scope = scope
        self.max_members = max_members
        self._directory_members = directory_members
        self._states: dict[str, _EntryState] = {}
        self._ancestors: dict[str, _EntryState] = {}
        self._directories: dict[str, tuple[str, ...]] = {}
        self._members: dict[str, InputMember] = {}

    def begin(self, relative_path: str) -> None:
        if relative_path in self._states:
            return
        if len(self._states) >= self.max_members:
            raise ValueError("selected-input member limit exceeded")
        state = _EntryState.read(self.workspace / relative_path)
        if not any(
            predicate(state.mode)
            for predicate in (stat.S_ISREG, stat.S_ISDIR, stat.S_ISLNK)
        ):
            raise ValueError(f"unsupported selected-input entry: {relative_path}")
        self._states[relative_path] = state

    def bind_ancestors(self, relative_path: str) -> None:
        for parent in Path(relative_path).parents:
            key = "" if parent.as_posix() == "." else parent.as_posix()
            if key in self._ancestors:
                continue
            state = _EntryState.read(self.workspace / key)
            if not stat.S_ISDIR(state.mode):
                raise ValueError(
                    f"selected input has a non-directory or symlink ancestor: {key}"
                )
            self._ancestors[key] = state

    def directory(self, relative_path: str, members: tuple[str, ...]) -> None:
        self._directories[relative_path] = members

    def record(self, relative_path: str, node: _Node, revision: Digest) -> None:
        modes = {b"F": stat.S_ISREG, b"D": stat.S_ISDIR, b"L": stat.S_ISLNK}
        if not modes[node.kind](self._states[relative_path].mode):
            raise UnstableObservationError(
                f"selected-input kind changed during observation: {relative_path}"
            )
        kinds: dict[bytes, Literal["file", "directory", "symlink"]] = {
            b"F": "file",
            b"D": "directory",
            b"L": "symlink",
        }
        self._members[relative_path] = InputMember(
            path=relative_path,
            kind=kinds[node.kind],
            revision=revision.hash,
            regular_file_bytes=revision.size if node.kind == b"F" else 0,
            executable=node.executable if node.kind == b"F" else None,
            link_target=(
                node.target.decode("utf-8", errors="surrogateescape")
                if node.target is not None
                else None
            ),
        )

    def _validate_entry(self, relative_path: str, before: _EntryState) -> None:
        after = _EntryState.read(self.workspace / relative_path)
        if before == after:
            return
        expected = self._directories.get(relative_path)
        if (
            expected is not None
            and before.same_directory(after)
            and expected == self._directory_members(relative_path)
        ):
            # An excluded entry can change directory metadata without changing
            # the resolved member set. Selected members have their own checks.
            return
        raise UnstableObservationError(
            f"selected input changed during observation: {relative_path}"
        )

    def validate(self) -> None:
        try:
            for relative_path, before in self._states.items():
                self._validate_entry(relative_path, before)
            for relative_path, before in self._ancestors.items():
                after = _EntryState.read(self.workspace / relative_path)
                if not before.same_directory(after):
                    raise UnstableObservationError(
                        f"selected-input ancestor changed: {relative_path}"
                    )
        except (FileNotFoundError, NotADirectoryError) as exc:
            raise UnstableObservationError(
                "selected input disappeared during observation"
            ) from exc

    def result(self) -> tuple[tuple[InputMember, ...], InputCounts]:
        members = tuple(
            self._members[path]
            for path in sorted(
                self._members,
                key=lambda item: item.encode("utf-8", errors="surrogateescape"),
            )
        )
        return members, InputCounts(
            file_count=sum(member.kind == "file" for member in members),
            directory_count=sum(member.kind == "directory" for member in members),
            symlink_count=sum(member.kind == "symlink" for member in members),
            regular_file_bytes=sum(member.regular_file_bytes for member in members),
        )
