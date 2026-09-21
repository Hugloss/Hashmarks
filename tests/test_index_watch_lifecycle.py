from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

from hashmarks.codemap import CodeMap

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from hashmarks.observation import ChangeTracker


class _FakeWatcher:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def start(self) -> None:
        self._events.append("watcher-start")

    def synchronize(self) -> bool:
        self._events.append("watcher-synchronize")
        return True

    def stop(self) -> None:
        self._events.append("watcher-stop")


def _watch_owner(codemap: CodeMap):
    return importlib.import_module(codemap.watch_forever.__module__)


def test_watch_forever_starts_observer_before_initial_sync_and_stops_cleanly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    updates: list[tuple[object, list[str]]] = []

    with CodeMap(tmp_path, state_dir=tmp_path / ".codemap-state") as codemap:
        owner = _watch_owner(codemap)

        def fake_factory(
            root,
            callback,
            *,
            debounce_seconds,
            change_tracker,
            exclude_relative_paths,
        ):
            del root, callback, debounce_seconds, change_tracker
            excluded = set(exclude_relative_paths)
            assert ".codemap-state" in excluded
            assert ".git" in excluded
            assert ".fastidentity" in excluded
            events.append("watcher-factory")
            return _FakeWatcher(events)

        def fake_sync(paths=None):
            events.append("sync-full" if paths is None else f"sync:{paths}")
            return {"paths": paths}

        def stop_after_initial(_seconds: float) -> None:
            raise KeyboardInterrupt

        monkeypatch.setattr(owner, "create_default_watcher", fake_factory)
        monkeypatch.setattr(owner.time, "sleep", stop_after_initial)
        monkeypatch.setattr(codemap, "sync", fake_sync)

        codemap.watch_forever(
            debounce_seconds=0.01,
            on_update=lambda result, paths: updates.append((result, list(paths))),
        )

        assert events == [
            "watcher-factory",
            "watcher-start",
            "sync-full",
            "watcher-synchronize",
            "watcher-stop",
        ]
        assert updates == [({"paths": None}, [])]
        assert codemap.store.meta("watcher_state") == "stopped"
        assert codemap.store.meta("watcher_pid") == ""


def test_watch_forever_unknown_observation_forces_full_reconciliation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    updates: list[tuple[object, list[str]]] = []
    tracker: ChangeTracker | None = None

    with CodeMap(tmp_path, state_dir=tmp_path / ".codemap-state") as codemap:
        owner = _watch_owner(codemap)

        def fake_factory(
            root,
            callback,
            *,
            debounce_seconds,
            change_tracker,
            exclude_relative_paths,
        ):
            nonlocal tracker
            del root, callback, debounce_seconds, exclude_relative_paths
            tracker = change_tracker
            return _FakeWatcher(events)

        sync_calls: list[object] = []

        def fake_sync(paths=None):
            sync_calls.append(paths)
            return {"call": len(sync_calls), "paths": paths}

        sleeps = 0

        def drive_unknown_then_stop(_seconds: float) -> None:
            nonlocal sleeps
            sleeps += 1
            assert tracker is not None
            if sleeps == 1:
                tracker.mark_unknown("test observation gap")
                return
            raise KeyboardInterrupt

        monkeypatch.setattr(owner, "create_default_watcher", fake_factory)
        monkeypatch.setattr(owner.time, "sleep", drive_unknown_then_stop)
        monkeypatch.setattr(codemap, "sync", fake_sync)

        codemap.watch_forever(
            debounce_seconds=0.01,
            on_update=lambda result, paths: updates.append((result, list(paths))),
        )

        assert sync_calls == [None, None]
        assert updates == [
            ({"call": 1, "paths": None}, []),
            ({"call": 2, "paths": None}, []),
        ]
        assert codemap.store.meta("watcher_state") == "stopped"


def test_watch_forever_incremental_callback_reconciles_observed_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updates: list[tuple[object, list[str]]] = []
    callback = None
    external_state = tmp_path.parent / f"{tmp_path.name}-state"

    with CodeMap(tmp_path, state_dir=external_state) as codemap:
        owner = _watch_owner(codemap)

        def fake_factory(
            root,
            update_callback,
            *,
            debounce_seconds,
            change_tracker,
            exclude_relative_paths,
        ):
            nonlocal callback
            del root, debounce_seconds, change_tracker
            callback = update_callback
            assert set(exclude_relative_paths) == {".git", ".fastidentity"}
            return _FakeWatcher([])

        sync_calls: list[object] = []

        def fake_sync(paths=None):
            sync_calls.append(paths)
            return {"paths": paths}

        def drive_update_then_stop(_seconds: float) -> None:
            if len(sync_calls) == 1:
                assert callback is not None
                callback(["src/owner.py"])
                return
            raise KeyboardInterrupt

        monkeypatch.setattr(owner, "create_default_watcher", fake_factory)
        monkeypatch.setattr(owner.time, "sleep", drive_update_then_stop)
        monkeypatch.setattr(codemap, "sync", fake_sync)

        codemap.watch_forever(
            on_update=lambda result, paths: updates.append((result, list(paths)))
        )

    assert sync_calls == [None, ["src/owner.py"]]
    assert updates == [
        ({"paths": None}, []),
        ({"paths": ["src/owner.py"]}, ["src/owner.py"]),
    ]
