from __future__ import annotations

import subprocess
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.parsers import artifact_key_for
from hashmarks.codemap.providers import TreeSitterRangeProvider
from hashmarks.codemap.repository_index_store import (
    default_base_snapshot,
    git_base_identity,
    git_overlay_paths,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.host_git


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "t@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True)
    (repo / "a.py").write_text("def alpha():\n    return 1\n")
    (repo / "b.py").write_text("def beta():\n    return 2\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    return repo


def test_clean_base_sync_publishes_shared_snapshot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    repo = _repo(tmp_path)
    with CodeMap(repo) as codemap:
        result = codemap.sync()
    base = git_base_identity(repo)
    assert base is not None
    snapshot = default_base_snapshot(repo, base)
    assert snapshot.is_file()
    assert result.overlay_paths == 0


def test_sibling_worktree_reuses_clean_base_snapshot_and_keeps_dirty_overlay_local(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    repo = _repo(tmp_path)
    with CodeMap(repo) as codemap:
        first = codemap.sync()
    sibling = tmp_path / "sibling"
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "worktree",
            "add",
            "-q",
            "--detach",
            str(sibling),
            "HEAD",
        ],
        check=True,
    )
    # The sibling uses a different workspace DB/state, but same common-dir artifact/base cache.
    with CodeMap(sibling) as codemap:
        reused = codemap.sync()
    assert reused.base_snapshot_reused == 2
    assert reused.parsed_artifacts == 0
    (sibling / "b.py").write_text("def beta():\n    return 3\n")
    with CodeMap(sibling) as codemap:
        dirty = codemap.sync()
    assert dirty.overlay_paths == 1
    assert dirty.base_snapshot_reused == 1
    assert codemap is not None


def test_assume_unchanged_path_must_match_snapshot_bytes_before_reuse(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    repo = _repo(tmp_path)
    with CodeMap(repo) as codemap:
        codemap.sync()

    subprocess.run(
        ["git", "-C", str(repo), "update-index", "--assume-unchanged", "a.py"],
        check=True,
    )
    (repo / "a.py").write_text("def omega():\n    return 1\n", encoding="utf-8")

    assert _git(repo, "status", "--porcelain") == ""
    assert git_overlay_paths(repo) == set()

    with CodeMap(repo) as codemap:
        result = codemap.sync()
        assert result.overlay_paths == 0
        assert result.base_snapshot_reused == 1
        assert result.parsed_artifacts == 1
        assert codemap.store.symbol("alpha") == []
        assert codemap.store.symbol("omega")


def _range_provider(version: str) -> TreeSitterRangeProvider:
    root = SimpleNamespace(named_children=())
    parser = SimpleNamespace(parse=lambda source: SimpleNamespace(root_node=root))
    return TreeSitterRangeProvider(lambda language: parser, version=version)


@pytest.mark.parametrize("next_provider", ["unavailable", "v2"])
def test_base_snapshot_requires_current_parser_provider_identity(
    tmp_path: Path, monkeypatch, next_provider: str
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    repo = _repo(tmp_path)
    with CodeMap(repo) as codemap:
        codemap.range_provider = _range_provider("v1")
        codemap.sync()
        before = {
            path: str(codemap.store.file_row(path)["artifact_key"])
            for path in ("a.py", "b.py")
        }

    with CodeMap(repo) as codemap:
        codemap.range_provider = (
            TreeSitterRangeProvider(None)
            if next_provider == "unavailable"
            else _range_provider(next_provider)
        )
        result = codemap.sync()
        assert result.base_snapshot_reused == 0
        assert result.parsed_artifacts == 2
        for path in ("a.py", "b.py"):
            row = codemap.store.file_row(path)
            assert row is not None
            assert str(row["artifact_key"]) != before[path]
            assert str(row["artifact_key"]) == artifact_key_for(
                str(row["file_digest"]),
                "python",
                range_provider=codemap.range_provider,
            )


def test_base_snapshot_reprojects_current_python_module_identity(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "t@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True)
    (repo / "src" / "pkg").mkdir(parents=True)
    source = repo / "src" / "pkg" / "mod.py"
    source.write_text("def run():\n    return 1\n", encoding="utf-8")
    manifest = repo / "pyproject.toml"
    manifest.write_text(
        "[project]\nname='fixture'\nversion='0.0.0'\n"
        "[tool.setuptools.package-dir]\n\"\"='src'\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)

    with CodeMap(repo) as codemap:
        codemap.sync()
        before = codemap.store.file_row("src/pkg/mod.py")
        assert before is not None
        assert before["module_name"] == "pkg.mod"

    manifest.write_text(
        "[project]\nname='fixture'\nversion='0.0.0'\n",
        encoding="utf-8",
    )
    assert git_overlay_paths(repo) == {"pyproject.toml"}

    with CodeMap(repo) as codemap:
        result = codemap.sync()
        after = codemap.store.file_row("src/pkg/mod.py")
        assert after is not None
        assert result.base_snapshot_reused == 1
        assert after["module_name"] == "src.pkg.mod"


def test_git_overlay_paths_includes_rename_origin_and_untracked_file(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    subprocess.run(["git", "-C", str(repo), "mv", "a.py", "renamed.py"], check=True)
    (repo / "new.py").write_text("value = 1\n", encoding="utf-8")

    assert git_overlay_paths(repo) == {"a.py", "renamed.py", "new.py"}


def test_fastidentity_overlay_is_visible_unless_it_is_the_active_state(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    directory = repo / ".fastidentity"
    directory.mkdir()
    (directory / "source.py").write_text("VALUE = 1\n", encoding="utf-8")

    assert git_overlay_paths(repo) == {".fastidentity/source.py"}
    assert git_overlay_paths(repo, state_rel=".fastidentity") == set()
