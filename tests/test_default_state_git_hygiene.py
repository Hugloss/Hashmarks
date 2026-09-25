from __future__ import annotations

import subprocess
from pathlib import Path

from hashmarks.codemap import CodeMap


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _tracked_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    (repo / "source.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "source.py")
    _git(
        repo,
        "-c",
        "user.name=Hashmarks Test",
        "-c",
        "user.email=hashmarks@example.invalid",
        "commit",
        "-qm",
        "baseline",
    )
    return repo


def test_default_hashmarks_state_does_not_dirty_git_workspace(tmp_path: Path) -> None:
    repo = _tracked_repo(tmp_path)

    with CodeMap(repo) as codemap:
        codemap.sync()

    assert (repo / ".hashmarks" / ".gitignore").read_text(encoding="utf-8") == "*\n"
    assert _git(repo, "status", "--short").stdout == ""


def test_default_state_preserves_existing_ignore_policy(tmp_path: Path) -> None:
    repo = _tracked_repo(tmp_path)
    state = repo / ".hashmarks"
    state.mkdir()
    ignore = state / ".gitignore"
    ignore.write_text("custom-policy\n", encoding="utf-8")

    with CodeMap(repo):
        pass

    assert ignore.read_text(encoding="utf-8") == "custom-policy\n"


def test_custom_state_directory_is_not_given_git_policy(tmp_path: Path) -> None:
    repo = _tracked_repo(tmp_path)
    state = tmp_path / "external-state"

    with CodeMap(repo, state_dir=state):
        pass

    assert not (state / ".gitignore").exists()
