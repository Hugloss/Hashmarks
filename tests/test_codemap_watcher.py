from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Protocol

import pytest
from contract_assertions import assert_object

from hashmarks.codemap import CodeMap
from hashmarks.codemap.index_watch import (
    WatchLeaseHeldError,
    WatchLeaseLostError,
    _IndexWatchSession,
)
from hashmarks.codemap.watch_continuity import (
    WATCH_CONTINUITY_META,
    WatchContinuityRecord,
)


def _write_repo(root: Path) -> None:
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "src" / "auth.py").write_text(
        """from src.users import User

class AuthService:
    def login(self, name: str) -> User:
        return User(name)
""",
        encoding="utf-8",
    )
    (root / "src" / "users.py").write_text(
        """class User:
    def __init__(self, name: str):
        self.name = name
""",
        encoding="utf-8",
    )
    (root / "tests" / "test_auth.py").write_text(
        """from src.auth import AuthService

def test_login():
    assert AuthService().login('a').name == 'a'
""",
        encoding="utf-8",
    )


def _wait_for_clean_map(workspace: Path, *, symbol: str | None = None) -> bool:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with CodeMap(workspace) as reader:
            status = reader.views.status()
            symbol_ready = symbol is None or bool(reader.store.symbol(symbol))
            files_ready = symbol is not None or status["files"] == 3
            if (
                assert_object(status["watcher"])["state"] == "clean"
                and symbol_ready
                and files_ready
            ):
                return True
        time.sleep(0.03)
    return False


class _WatcherProcess(Protocol):
    def poll(self) -> int | None: ...
    def send_signal(self, signal: int, /) -> None: ...
    def wait(self, timeout: float) -> int: ...
    def kill(self) -> None: ...


def _stop_watcher(proc: _WatcherProcess) -> None:
    if proc.poll() is not None:
        return
    proc.send_signal(2)
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)


class _TimeoutProcess:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.wait_count = 0

    def poll(self) -> int | None:
        self.calls.append(("poll",))
        return None

    def send_signal(self, signal: int) -> None:
        self.calls.append(("send_signal", signal))

    def wait(self, timeout: float) -> int:
        self.calls.append(("wait", timeout))
        self.wait_count += 1
        if self.wait_count == 1:
            raise subprocess.TimeoutExpired("watcher", timeout)
        return 0

    def kill(self) -> None:
        self.calls.append(("kill",))


class _ExitedProcess(_TimeoutProcess):
    def poll(self) -> int | None:
        self.calls.append(("poll",))
        return 0


def test_watcher_shutdown_is_bounded_and_kills_after_timeout() -> None:
    proc = _TimeoutProcess()

    _stop_watcher(proc)

    assert proc.calls == [
        ("poll",),
        ("send_signal", 2),
        ("wait", 3),
        ("kill",),
        ("wait", 3),
    ]


def test_watcher_shutdown_does_nothing_after_process_exit() -> None:
    proc = _ExitedProcess()

    _stop_watcher(proc)

    assert proc.calls == [("poll",)]


def test_watcher_continuity_is_one_atomic_freshness_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_repo(tmp_path)
    state = tmp_path / ".state"
    with CodeMap(
        tmp_path,
        state_dir=state,
        artifact_db=tmp_path / "artifacts.sqlite3",
    ) as codemap:
        codemap.index.sync()
        monkeypatch.setattr(codemap._observation_source, "observe", lambda: None)
        session = _IndexWatchSession(codemap.index, None)
        session.acquire()
        assert session.tracker.mark_reconciled(expected_generation=0)
        session.publish()

        items = dict(codemap.store.meta_items(prefix="watcher"))
        assert set(items) == {WATCH_CONTINUITY_META}
        record = WatchContinuityRecord.from_json(items[WATCH_CONTINUITY_META])
        assert record is not None
        assert record.fence == session.fence
        assert record.observation.state.value == "clean"
        assert record.codemap_generation == codemap.store.generation()

        codemap.store.set_meta("watcher_pid", "999999")
        codemap.store.set_meta("watcher_state", "dirty")
        codemap.store.set_meta("watcher_heartbeat_unix", "0")
        status = codemap.views.status()
        assert status["daemon_generation_changed"] is False
        assert assert_object(status["watcher"])["state"] == "clean"
        assert assert_object(status["watcher"])["fence"] == session.fence

        session.tracker.mark_dirty(["src/auth.py"])
        session.publish()
        assert codemap.views.status()["daemon_generation_changed"] is True

        session.tracker.mark_unknown("synthetic overflow")
        session.publish()
        status = codemap.views.status()
        assert status["daemon_generation_changed"] is None
        assert assert_object(status["watcher"])["state"] == "unknown"
        assert assert_object(status["watcher"])["reason"] == "synthetic overflow"


def test_clean_watcher_observation_only_covers_its_published_codemap_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_repo(tmp_path)
    with CodeMap(
        tmp_path,
        state_dir=tmp_path / ".state",
        artifact_db=tmp_path / "artifacts.sqlite3",
    ) as codemap:
        codemap.index.sync()
        monkeypatch.setattr(codemap._observation_source, "observe", lambda: None)
        session = _IndexWatchSession(codemap.index, None)
        session.acquire()
        assert session.tracker.mark_reconciled(expected_generation=0)
        session.publish()
        assert codemap.views.status()["daemon_generation_changed"] is False

        with codemap.store.publication_transaction():
            codemap.store.bump_generation()

        status = codemap.views.status()
        assert status["daemon_generation_changed"] is None
        assert (
            assert_object(status["watcher"])["codemap_generation"]
            != status["generation"]
        )


def test_inactive_watcher_observation_cannot_authorize_current_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_repo(tmp_path)
    with CodeMap(
        tmp_path,
        state_dir=tmp_path / ".state",
        artifact_db=tmp_path / "artifacts.sqlite3",
    ) as codemap:
        codemap.index.sync()
        monkeypatch.setattr(codemap._observation_source, "observe", lambda: None)
        session = _IndexWatchSession(codemap.index, None)
        session.acquire()
        assert session.tracker.mark_reconciled(expected_generation=0)
        session.publish(active=False)

        status = codemap.views.status()
        assert status["daemon_generation_changed"] is None
        assert assert_object(status["watcher"])["active"] is False
        assert assert_object(status["watcher"])["pid"] is None


def test_second_live_watcher_cannot_claim_continuity_authority(
    tmp_path: Path,
) -> None:
    _write_repo(tmp_path)
    with CodeMap(
        tmp_path,
        state_dir=tmp_path / ".state",
        artifact_db=tmp_path / "artifacts.sqlite3",
    ) as codemap:
        codemap.index.sync()
        first = _IndexWatchSession(codemap.index, None)
        first.acquire()
        second = _IndexWatchSession(codemap.index, None)

        with pytest.raises(WatchLeaseHeldError, match="already owned"):
            second.acquire()

        record = WatchContinuityRecord.from_json(
            codemap.store.meta(WATCH_CONTINUITY_META)
        )
        assert record is not None
        assert record.owner == first.owner
        assert record.fence == first.fence
        first.release()


def test_replacement_fence_blocks_stale_clean_overwrite(
    tmp_path: Path,
) -> None:
    _write_repo(tmp_path)
    with CodeMap(
        tmp_path,
        state_dir=tmp_path / ".state",
        artifact_db=tmp_path / "artifacts.sqlite3",
    ) as codemap:
        codemap.index.sync()
        first = _IndexWatchSession(codemap.index, None)
        assert first.tracker.mark_reconciled(expected_generation=0)
        first.acquire()

        first_record = WatchContinuityRecord.from_json(
            codemap.store.meta(WATCH_CONTINUITY_META)
        )
        assert first_record is not None
        expired = WatchContinuityRecord(
            owner=first_record.owner,
            fence=first_record.fence,
            pid=first_record.pid,
            heartbeat_unix=0.0,
            active=True,
            codemap_generation=first_record.codemap_generation,
            observation=first_record.observation,
        )
        codemap.store.set_meta(WATCH_CONTINUITY_META, expired.to_json())

        replacement = _IndexWatchSession(codemap.index, None)
        assert replacement.tracker.mark_reconciled(expected_generation=0)
        replacement.tracker.mark_dirty(["src/auth.py"])
        replacement.acquire()

        replacement_record = WatchContinuityRecord.from_json(
            codemap.store.meta(WATCH_CONTINUITY_META)
        )
        assert replacement_record is not None
        assert replacement_record.owner == replacement.owner
        assert replacement_record.fence == first_record.fence + 1
        assert replacement_record.observation.state.value == "dirty"

        with pytest.raises(WatchLeaseLostError, match="replaced"):
            first.publish()

        first.release()
        final_record = WatchContinuityRecord.from_json(
            codemap.store.meta(WATCH_CONTINUITY_META)
        )
        assert final_record == replacement_record
        replacement.release()


def test_released_watcher_advances_fence_on_next_claim(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    with CodeMap(
        tmp_path,
        state_dir=tmp_path / ".state",
        artifact_db=tmp_path / "artifacts.sqlite3",
    ) as codemap:
        codemap.index.sync()
        first = _IndexWatchSession(codemap.index, None)
        first.acquire()
        first_fence = first.fence
        first.release()

        second = _IndexWatchSession(codemap.index, None)
        second.acquire()
        assert first_fence is not None
        assert second.fence == first_fence + 1
        second.release()


def test_codemap_watcher_keeps_map_hot_without_identity_daemon(tmp_path: Path) -> None:
    if not sys.platform.startswith("linux"):
        pytest.skip("native watcher regression is Linux-specific")
    _write_repo(tmp_path)
    source_root = Path(__file__).parents[1]
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "hashmarks.cli",
            "--workspace",
            str(tmp_path),
            "map",
            "watch",
            "--debounce",
            "0.01",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "PYTHONPATH": str(source_root)},
    )
    try:
        if not _wait_for_clean_map(tmp_path):
            pytest.fail(
                f"CodeMap watcher did not become ready (returncode={proc.returncode})"
            )

        auth = tmp_path / "src" / "auth.py"
        auth.write_text(
            auth.read_text(encoding="utf-8")
            + "\ndef watcher_added():\n    return True\n",
            encoding="utf-8",
        )
        if not _wait_for_clean_map(tmp_path, symbol="watcher_added"):
            pytest.fail("CodeMap watcher did not incrementally index the changed file")
    finally:
        _stop_watcher(proc)
