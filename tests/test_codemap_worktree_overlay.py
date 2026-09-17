from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.repository_index_store import default_base_snapshot, git_base_identity


pytestmark = pytest.mark.host_git


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"; repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@example.invalid"], check=True)
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
    base = git_base_identity(repo); assert base is not None
    snapshot = default_base_snapshot(repo, base)
    assert snapshot.is_file()
    assert result.overlay_paths == 0


def test_sibling_worktree_reuses_clean_base_snapshot_and_keeps_dirty_overlay_local(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    repo = _repo(tmp_path)
    with CodeMap(repo) as codemap:
        first = codemap.sync()
    sibling = tmp_path / "sibling"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", "--detach", str(sibling), "HEAD"], check=True)
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
