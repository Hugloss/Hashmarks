from __future__ import annotations

from pathlib import Path

from hashmarks.client import RepositoryObservation
from hashmarks.codemap.engine import CodeMap
from hashmarks.observation import ObservationState
from hashmarks.daemon import IdentityDaemon


class _BarrierWatcher:
    def synchronize(self) -> bool:
        return True


def test_daemon_observe_exposes_complete_bounded_dirty_paths(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    daemon = IdentityDaemon(workspace, state_dir=tmp_path / "state")
    daemon._watcher = _BarrierWatcher()
    daemon.engine.changes.mark_reconciled(
        expected_generation=daemon.engine.changes.snapshot().generation
    )
    daemon.engine.changes.mark_dirty(["src/a.py", "src/b.py"])

    observed = daemon._observe_response({})

    assert observed["observation"] == "dirty"
    assert observed["dirty_paths"] == 2
    assert observed["paths"] == ["src/a.py", "src/b.py"]
    assert observed["paths_complete"] is True
    daemon.engine.close()


def test_daemon_observe_fails_closed_when_dirty_set_is_oversized(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    daemon = IdentityDaemon(workspace, state_dir=tmp_path / "state")
    daemon._watcher = _BarrierWatcher()
    daemon.engine.changes.mark_reconciled(
        expected_generation=daemon.engine.changes.snapshot().generation
    )
    daemon.engine.changes.mark_dirty(f"src/f{i}.py" for i in range(4097))

    observed = daemon._observe_response({})

    assert observed["dirty_paths"] == 4097
    assert observed["paths"] == []
    assert observed["paths_complete"] is False
    daemon.engine.close()


def _indexed_map(tmp_path: Path) -> CodeMap:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "a.py").write_text("def before():\n    return 1\n", encoding="utf-8")
    codemap = CodeMap(workspace, artifact_db=tmp_path / "artifacts.sqlite3")
    codemap.sync()
    codemap.store.set_meta("identity_generation", "1")
    return codemap


def _observation(
    *,
    state: ObservationState = ObservationState.DIRTY,
    generation: int = 2,
    paths: tuple[str, ...] = ("a.py",),
    paths_complete: bool = True,
    dirty_path_count: int | None = None,
) -> RepositoryObservation:
    return RepositoryObservation(
        state=state,
        generation=generation,
        dirty_paths=paths,
        paths_complete=paths_complete,
        dirty_path_count=len(paths) if dirty_path_count is None else dirty_path_count,
    )


def test_map_ready_reuses_one_atomic_complete_observation(tmp_path: Path, monkeypatch):
    codemap = _indexed_map(tmp_path)
    calls: list[object] = []
    observations = 0

    def sample() -> RepositoryObservation:
        nonlocal observations
        observations += 1
        return _observation()

    try:
        monkeypatch.setattr(codemap, "_daemon_observation", sample)
        monkeypatch.setattr(codemap, "sync", lambda paths=None: calls.append(paths))

        codemap._ensure_map_ready()

        assert calls == [("a.py",)]
        assert observations == 1
    finally:
        codemap.close()


def test_map_ready_falls_back_to_full_sync_without_authoritative_change_set(tmp_path: Path, monkeypatch):
    codemap = _indexed_map(tmp_path)
    calls: list[object] = []
    try:
        monkeypatch.setattr(
            codemap,
            "_daemon_observation",
            lambda: _observation(paths=(), paths_complete=False, dirty_path_count=1),
        )
        monkeypatch.setattr(codemap, "sync", lambda paths=None: calls.append(paths))

        codemap._ensure_map_ready()

        assert calls == [None]
    finally:
        codemap.close()


def test_map_ready_clean_matching_generation_does_not_sync(tmp_path: Path, monkeypatch):
    codemap = _indexed_map(tmp_path)
    calls: list[object] = []
    try:
        monkeypatch.setattr(
            codemap,
            "_daemon_observation",
            lambda: _observation(
                state=ObservationState.CLEAN, generation=1, paths=(), dirty_path_count=0
            ),
        )
        monkeypatch.setattr(codemap, "sync", lambda paths=None: calls.append(paths))

        codemap._ensure_map_ready()

        assert calls == []
    finally:
        codemap.close()


def test_map_ready_unknown_generation_change_falls_back_to_full_sync(tmp_path: Path, monkeypatch):
    codemap = _indexed_map(tmp_path)
    calls: list[object] = []
    try:
        monkeypatch.setattr(
            codemap,
            "_daemon_observation",
            lambda: _observation(
                state=ObservationState.UNKNOWN, generation=2, paths=(), paths_complete=False, dirty_path_count=0
            ),
        )
        monkeypatch.setattr(codemap, "sync", lambda paths=None: calls.append(paths))

        codemap._ensure_map_ready()

        assert calls == [None]
    finally:
        codemap.close()
