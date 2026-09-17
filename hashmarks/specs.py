from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, TypeAlias

from .paths import has_glob, normalize_relative_pattern

if TYPE_CHECKING:
    from collections.abc import Iterable


class InputSpec(Protocol):
    def as_pattern(self) -> str: ...


@dataclass(frozen=True, slots=True)
class File:
    path: str | Path

    def as_pattern(self) -> str:
        value = normalize_relative_pattern(str(self.path))
        if has_glob(value):
            raise ValueError(f"File input must not contain glob syntax: {value}")
        return value


@dataclass(frozen=True, slots=True)
class Directory:
    path: str | Path

    def as_pattern(self) -> str:
        value = normalize_relative_pattern(str(self.path))
        if has_glob(value):
            raise ValueError(f"Directory input must not contain glob syntax: {value}")
        return value


@dataclass(frozen=True, slots=True)
class Glob:
    pattern: str

    def as_pattern(self) -> str:
        value = normalize_relative_pattern(self.pattern)
        if not has_glob(value):
            raise ValueError(f"Glob input must contain glob syntax: {value}")
        return value


InputValue: TypeAlias = str | Path | InputSpec


def patterns_from_inputs(values: Iterable[InputValue]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if isinstance(value, (str, Path)):
            result.append(normalize_relative_pattern(str(value)))
        else:
            result.append(value.as_pattern())
    return tuple(result)


def _missing_input(pattern: str, kind: str, require_matches: bool) -> None:
    if require_matches:
        raise FileNotFoundError(f"{kind} input matched nothing: {pattern}")


def _validate_file_input(root: Path, value: File, require_matches: bool) -> str:
    pattern = value.as_pattern()
    target = root / pattern
    if not os.path.lexists(target):
        _missing_input(pattern, "file", require_matches)
    elif not target.is_symlink() and not target.is_file():
        raise ValueError(f"File input is not a file: {pattern}")
    return pattern


def _validate_directory_input(
    root: Path, value: Directory, require_matches: bool
) -> str:
    pattern = value.as_pattern()
    target = root / pattern
    if not os.path.lexists(target):
        _missing_input(pattern, "directory", require_matches)
    elif target.is_symlink() or not target.is_dir():
        raise ValueError(f"Directory input is not a real directory: {pattern}")
    return pattern


def _validated_input_pattern(
    root: Path, value: InputValue, require_matches: bool
) -> str:
    if isinstance(value, File):
        return _validate_file_input(root, value, require_matches)
    if isinstance(value, Directory):
        return _validate_directory_input(root, value, require_matches)
    if isinstance(value, (str, Path)):
        return normalize_relative_pattern(str(value))
    return value.as_pattern()


def validate_input_values(
    workspace: str | Path,
    values: Iterable[InputValue],
    *,
    require_matches: bool = True,
) -> tuple[str, ...]:
    root = Path(workspace)
    return tuple(
        _validated_input_pattern(root, value, require_matches) for value in values
    )
