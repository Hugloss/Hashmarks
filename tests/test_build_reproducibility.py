from __future__ import annotations

import hashlib
import os
from typing import TYPE_CHECKING

import hashmarks_build

if TYPE_CHECKING:
    from pathlib import Path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_sdist_is_reproducible_across_source_mtime_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    release = tmp_path / "release"
    (release / "hashmarks").mkdir(parents=True)
    (release / "tests").mkdir()
    (release / "pyproject.toml").write_text(
        '[project]\nname = "hashmarks"\nversion = "1.2.3"\nrequires-python = ">=3.11"\n'
    )
    (release / "hashmarks" / "_version.py").write_text('__version__ = "1.2.3"\n')
    (release / "hashmarks" / "__init__.py").write_text("")
    (release / "README.md").write_text("# Hashmarks\n")
    (release / "tests" / "test_sample.py").write_text(
        "def test_sample():\n    assert True\n"
    )

    monkeypatch.setattr(hashmarks_build, "ROOT", release)
    first = tmp_path / "a"
    second = tmp_path / "b"
    name_a = hashmarks_build.build_sdist(first)

    for path in release.rglob("*"):
        if path.is_file():
            os.utime(path, (2_000_000_000, 2_000_000_000))

    name_b = hashmarks_build.build_sdist(second)
    assert name_a == name_b
    assert _sha(first / name_a) == _sha(second / name_b)


def test_wheel_is_reproducible_across_source_mtime_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    release = tmp_path / "release"
    (release / "hashmarks").mkdir(parents=True)
    (release / "pyproject.toml").write_text(
        '[project]\nname = "hashmarks"\nversion = "1.2.3"\nrequires-python = ">=3.11"\n'
    )
    (release / "hashmarks" / "_version.py").write_text('__version__ = "1.2.3"\n')
    (release / "hashmarks" / "__init__.py").write_text("")
    (release / "README.md").write_text("# Hashmarks 1.2.3\n")

    monkeypatch.setattr(hashmarks_build, "ROOT", release)
    first = tmp_path / "a"
    second = tmp_path / "b"
    name_a = hashmarks_build.build_wheel(first)

    for path in release.rglob("*"):
        if path.is_file():
            os.utime(path, (2_000_000_000, 2_000_000_000))

    name_b = hashmarks_build.build_wheel(second)
    assert name_a == name_b
    assert _sha(first / name_a) == _sha(second / name_b)
