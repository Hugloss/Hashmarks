from __future__ import annotations

import concurrent.futures
from typing import TYPE_CHECKING

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.repository_index_store import (
    WorkspaceMapStore,
    WorkspaceStateMismatchError,
)

if TYPE_CHECKING:
    from pathlib import Path


def _repo(path: Path, *, symbol: str) -> None:
    path.mkdir(parents=True)
    (path / "pyproject.toml").write_text(
        f'[project]\nname="{path.name}"\nversion="0"\n', encoding="utf-8"
    )
    (path / "source.py").write_text(
        f"def {symbol}():\n    return 1\n", encoding="utf-8"
    )


def test_external_state_dir_is_bound_to_exactly_one_workspace(tmp_path: Path) -> None:
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    state = tmp_path / "shared-state"
    _repo(repo_a, symbol="alpha_only")
    _repo(repo_b, symbol="beta_only")

    with CodeMap(
        repo_a, state_dir=state, artifact_db=tmp_path / "a-artifacts.sqlite3"
    ) as codemap:
        codemap.sync()
        assert codemap.find("alpha_only")

    with pytest.raises(
        WorkspaceStateMismatchError, match="already bound to a different workspace"
    ):
        CodeMap(repo_b, state_dir=state, artifact_db=tmp_path / "b-artifacts.sqlite3")

    with CodeMap(
        repo_a, state_dir=state, artifact_db=tmp_path / "a-artifacts.sqlite3"
    ) as codemap:
        assert codemap.find("alpha_only")
        assert not any(hit.name == "beta_only" for hit in codemap.find("beta_only"))


def test_concurrent_external_state_first_claim_has_one_workspace_owner(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()

    def claim(workspace: Path) -> str:
        store = WorkspaceMapStore(state / "codemap.sqlite3")
        try:
            store.bind_workspace(workspace)
            return "claimed"
        except WorkspaceStateMismatchError:
            return "rejected"
        finally:
            store.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(claim, (repo_a, repo_b)))

    assert sorted(results) == ["claimed", "rejected"]


def test_external_unbound_existing_state_fails_closed(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    state = tmp_path / "external-state"
    store = WorkspaceMapStore(state / "codemap.sqlite3")
    store.set_meta("generation", "1")
    store.close()

    with pytest.raises(WorkspaceStateMismatchError, match="not workspace-bound"):
        CodeMap(workspace, state_dir=state, artifact_db=tmp_path / "artifacts.sqlite3")


def test_in_workspace_unbound_existing_state_can_adopt_its_owner(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    state = workspace / "custom-state"
    store = WorkspaceMapStore(state / "codemap.sqlite3")
    store.set_meta("generation", "1")
    store.close()

    with CodeMap(
        workspace, state_dir=state, artifact_db=tmp_path / "artifacts.sqlite3"
    ) as codemap:
        assert codemap.store.meta("state.workspace") == str(workspace.resolve())


def test_clean_preserves_external_workspace_binding(tmp_path: Path) -> None:
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    state = tmp_path / "external-state"
    _repo(repo_a, symbol="alpha_only")
    _repo(repo_b, symbol="beta_only")

    with CodeMap(
        repo_a, state_dir=state, artifact_db=tmp_path / "a-artifacts.sqlite3"
    ) as codemap:
        codemap.sync()
        codemap.clean()
        assert codemap.store.meta("state.workspace") == str(repo_a.resolve())

    with CodeMap(
        repo_a, state_dir=state, artifact_db=tmp_path / "a-artifacts.sqlite3"
    ) as codemap:
        codemap.sync()
        assert codemap.find("alpha_only")

    with pytest.raises(
        WorkspaceStateMismatchError, match="already bound to a different workspace"
    ):
        CodeMap(repo_b, state_dir=state, artifact_db=tmp_path / "b-artifacts.sqlite3")
