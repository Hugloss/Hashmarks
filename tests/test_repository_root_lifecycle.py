"""The construction root owns resource cleanup across partial construction."""

from collections.abc import Callable
from pathlib import Path
from typing import NoReturn, ParamSpec

import pytest

import hashmarks.codemap.engine as engine
from hashmarks.codemap.context_cache import ContextCache
from hashmarks.codemap.engine import CodeMap
from hashmarks.codemap.repository_index_store import ArtifactStore, WorkspaceMapStore
from hashmarks.file_store import FileDigestStore

_P = ParamSpec("_P")


def _recording_close(
    name: str,
    operation: Callable[_P, None],
    closed: list[str],
    *,
    fail: bool = False,
) -> Callable[_P, None]:
    def close(*args: _P.args, **kwargs: _P.kwargs) -> None:
        operation(*args, **kwargs)
        closed.append(name)
        if fail:
            raise RuntimeError("context close failed")

    return close


def _record_resources(
    monkeypatch: pytest.MonkeyPatch, *, fail_context: bool = False
) -> list[str]:
    closed: list[str] = []
    monkeypatch.setattr(
        WorkspaceMapStore,
        "close",
        _recording_close("workspace", WorkspaceMapStore.close, closed),
    )
    monkeypatch.setattr(
        FileDigestStore,
        "close",
        _recording_close("digests", FileDigestStore.close, closed),
    )
    monkeypatch.setattr(
        ArtifactStore,
        "close",
        _recording_close("artifacts", ArtifactStore.close, closed),
    )
    monkeypatch.setattr(
        ContextCache,
        "close",
        _recording_close("context", ContextCache.close, closed, fail=fail_context),
    )
    return closed


def test_failed_component_construction_closes_every_open_resource(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed = _record_resources(monkeypatch)

    def fail_search(*_args: object, **_kwargs: object) -> NoReturn:
        raise RuntimeError("search construction failed")

    monkeypatch.setattr(engine, "RepositorySearch", fail_search)
    with pytest.raises(RuntimeError, match="search construction failed"):
        CodeMap(
            tmp_path,
            state_dir=tmp_path / "state",
            artifact_db=tmp_path / "artifacts.sqlite3",
        )
    assert sorted(closed) == ["artifacts", "context", "digests", "workspace"]


def test_failed_workspace_binding_closes_the_new_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    state = tmp_path / "state"
    with CodeMap(first, state_dir=state, artifact_db=tmp_path / "artifacts.sqlite3"):
        pass
    closed = _record_resources(monkeypatch)
    with pytest.raises(ValueError, match="workspace"):
        CodeMap(second, state_dir=state, artifact_db=tmp_path / "artifacts.sqlite3")
    assert closed == ["workspace"]


def test_root_close_is_idempotent_for_owned_resources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed = _record_resources(monkeypatch)
    repository = CodeMap(
        tmp_path,
        state_dir=tmp_path / "state",
        artifact_db=tmp_path / "artifacts.sqlite3",
    )
    repository.close()
    repository.close()
    assert sorted(closed) == ["artifacts", "context", "digests", "workspace"]


def test_root_close_attempts_all_resources_when_one_close_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed = _record_resources(monkeypatch, fail_context=True)
    repository = CodeMap(
        tmp_path,
        state_dir=tmp_path / "state",
        artifact_db=tmp_path / "artifacts.sqlite3",
    )
    with pytest.raises(RuntimeError, match="context close failed"):
        repository.close()
    repository.close()
    assert sorted(closed) == ["artifacts", "context", "digests", "workspace"]
