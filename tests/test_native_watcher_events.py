from __future__ import annotations

from typing import TYPE_CHECKING

from hashmarks.watcher import (
    _IN_CREATE,
    _IN_DELETE,
    _IN_IGNORED,
    _IN_ISDIR,
    _IN_MODIFY,
    _IN_MOVE_SELF,
    _IN_Q_OVERFLOW,
    _INOTIFY_EVENT,
    NativeLinuxBatchWatcher,
)

if TYPE_CHECKING:
    from pathlib import Path


def _event(mask: int, name: bytes = b"", *, wd: int = 1) -> bytes:
    raw = name + b"\0" if name else b""
    return _INOTIFY_EVENT.pack(wd, mask, 0, len(raw)) + raw


def _watcher(root: Path) -> NativeLinuxBatchWatcher:
    watcher = NativeLinuxBatchWatcher(root, lambda _paths: None)
    watcher._wd_to_rel[1] = ""
    watcher._rel_to_wd[""] = 1
    return watcher


def test_inotify_event_buffer_tracks_file_and_directory_changes(
    tmp_path: Path, monkeypatch
) -> None:
    watcher = _watcher(tmp_path)
    added: list[str] = []
    removed: list[str] = []
    monkeypatch.setattr(
        watcher, "_add_recursive", lambda _absolute, rel: added.append(rel)
    )
    monkeypatch.setattr(watcher, "_remove_prefix_watches", removed.append)

    watcher._process_data(
        _event(_IN_CREATE | _IN_ISDIR, b"pkg")
        + _event(_IN_MODIFY, b"owner.py")
        + _event(_IN_DELETE | _IN_ISDIR, b"old")
    )

    assert watcher._batch.drain() == ["old", "owner.py", "pkg"]
    assert added == ["pkg"]
    assert removed == ["old"]


def test_inotify_event_buffer_marks_overflow_and_root_watch_loss(
    tmp_path: Path, monkeypatch
) -> None:
    watcher = _watcher(tmp_path)
    reasons: list[str] = []
    monkeypatch.setattr(watcher, "mark_unknown", reasons.append)

    watcher._process_data(_event(_IN_Q_OVERFLOW) + _event(_IN_IGNORED))

    assert reasons == [
        "inotify queue overflow",
        "workspace root inotify watch was lost",
    ]
    assert watcher._wd_to_rel == {}
    assert watcher._rel_to_wd == {}


def test_inotify_root_move_marks_observation_unknown(
    tmp_path: Path, monkeypatch
) -> None:
    watcher = _watcher(tmp_path)
    reasons: list[str] = []
    monkeypatch.setattr(watcher, "mark_unknown", reasons.append)

    watcher._process_data(_event(_IN_MOVE_SELF))

    assert reasons == ["workspace root moved or deleted"]


def test_inotify_recursive_watch_failure_stops_current_event_buffer(
    tmp_path: Path, monkeypatch
) -> None:
    watcher = _watcher(tmp_path)
    reasons: list[str] = []
    monkeypatch.setattr(watcher, "mark_unknown", reasons.append)

    def fail_add(_absolute: Path, _rel: str) -> None:
        raise RuntimeError("watch capacity")

    monkeypatch.setattr(watcher, "_add_recursive", fail_add)
    watcher._process_data(
        _event(_IN_CREATE | _IN_ISDIR, b"new") + _event(_IN_MODIFY, b"later.py")
    )

    assert reasons == ["failed to extend recursive inotify coverage"]
    assert watcher._batch.drain() == ["new"]
