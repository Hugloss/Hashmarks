from __future__ import annotations

import os
import threading
import time
from typing import TYPE_CHECKING

import pytest

from hashmarks.client import IdentityClient
from hashmarks.codemap.repository_index_store import WorkspaceMapStore
from hashmarks.daemon import IdentityDaemon

if TYPE_CHECKING:
    from pathlib import Path


class _BarrierWatcher:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def synchronize(self) -> bool:
        return True


def test_workspace_generation_bump_is_one_atomic_read_modify_write(
    tmp_path: Path, monkeypatch
) -> None:
    store = WorkspaceMapStore(tmp_path / "map.sqlite3")
    try:
        workers = 12
        old_style_read_barrier = threading.Barrier(workers)
        original_generation = store.generation

        # The pre-fix implementation called generation() and set_meta() under
        # separate lock acquisitions.  Force those reads to line up so this
        # regression test deterministically exposes that lost-update shape.
        def synchronized_generation() -> int:
            value = original_generation()
            old_style_read_barrier.wait(timeout=2)
            return value

        monkeypatch.setattr(store, "generation", synchronized_generation)
        start = threading.Barrier(workers)
        values: list[int] = []
        values_lock = threading.Lock()

        def bump() -> None:
            start.wait(timeout=2)
            value = store.bump_generation()
            with values_lock:
                values.append(value)

        threads = [threading.Thread(target=bump) for _ in range(workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
            assert not thread.is_alive()

        assert sorted(values) == list(range(1, workers + 1))
        # Call the original method because the monkeypatched compatibility trap
        # above intentionally blocks callers that still use the split read path.
        assert original_generation() == workers
    finally:
        store.close()


@pytest.mark.skipif(os.name != "posix", reason="Unix identity daemon transport")
def test_identity_daemon_status_is_not_serialized_behind_large_snapshot(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "a.txt").write_text("a", encoding="utf-8")
    watcher = _BarrierWatcher()
    socket_path = tmp_path / "identity.sock"
    daemon = IdentityDaemon(
        workspace,
        state_dir=tmp_path / "state",
        socket_path=socket_path,
        watcher_factory=lambda _engine: watcher,
    )

    entered = threading.Event()
    release = threading.Event()
    original_snapshot = daemon.engine.snapshot

    def blocking_snapshot(*args, **kwargs):
        entered.set()
        if not release.wait(timeout=5):
            raise TimeoutError("test did not release blocked snapshot")
        return original_snapshot(*args, **kwargs)

    monkeypatch.setattr(daemon.engine, "snapshot", blocking_snapshot)
    server_thread = threading.Thread(target=daemon.serve_forever, daemon=True)
    server_thread.start()
    deadline = time.monotonic() + 3
    while not socket_path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert socket_path.exists()

    slow_client = IdentityClient(workspace, socket_path=socket_path, timeout=5)
    fast_client = IdentityClient(workspace, socket_path=socket_path, timeout=5)
    slow_error: list[BaseException] = []

    def slow_request() -> None:
        try:
            slow_client.input_root(["a.txt"], verify=True)
        except BaseException as exc:  # pragma: no cover - surfaced below
            slow_error.append(exc)

    slow_thread = threading.Thread(target=slow_request)
    slow_thread.start()
    assert entered.wait(timeout=2)

    status_done = threading.Event()
    status_rows: list[dict] = []

    def status_request() -> None:
        status_rows.append(fast_client.status())
        status_done.set()

    status_thread = threading.Thread(target=status_request)
    status_thread.start()
    try:
        # Do not use elapsed-time thresholds for the product operation itself:
        # simply prove status completes while the heavy request is still held.
        assert status_done.wait(timeout=1), (
            "status was serialized behind heavy identity work"
        )
        assert status_rows[0]["workspace"] == str(workspace.resolve())
        assert slow_thread.is_alive()
    finally:
        release.set()

    slow_thread.join(timeout=5)
    status_thread.join(timeout=5)
    assert not slow_thread.is_alive()
    assert not status_thread.is_alive()
    assert slow_error == []

    fast_client.stop()
    server_thread.join(timeout=5)
    assert not server_thread.is_alive()
    assert watcher.started and watcher.stopped


@pytest.mark.skipif(os.name != "posix", reason="Unix identity daemon transport")
def test_registered_manifest_can_be_dropped_while_snapshot_uses_immutable_handle(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "a.txt").write_text("a", encoding="utf-8")
    watcher = _BarrierWatcher()
    socket_path = tmp_path / "identity.sock"
    daemon = IdentityDaemon(
        workspace,
        state_dir=tmp_path / "state",
        socket_path=socket_path,
        watcher_factory=lambda _engine: watcher,
    )
    entered = threading.Event()
    release = threading.Event()
    original_snapshot = daemon.engine.snapshot

    def blocking_snapshot(*args, **kwargs):
        entered.set()
        if not release.wait(timeout=5):
            raise TimeoutError("test did not release blocked snapshot")
        return original_snapshot(*args, **kwargs)

    monkeypatch.setattr(daemon.engine, "snapshot", blocking_snapshot)
    server_thread = threading.Thread(target=daemon.serve_forever, daemon=True)
    server_thread.start()
    deadline = time.monotonic() + 3
    while not socket_path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert socket_path.exists()

    owner = IdentityClient(workspace, socket_path=socket_path, timeout=5)
    control = IdentityClient(workspace, socket_path=socket_path, timeout=5)
    manifest = daemon.engine.manifest(["a.txt"])
    handle = owner.register_manifest(manifest)
    result: list[dict] = []

    thread = threading.Thread(
        target=lambda: result.append(owner.input_root_manifest(handle, verify=True))
    )
    thread.start()
    assert entered.wait(timeout=2)
    try:
        # Dropping the registry reference does not invalidate the immutable
        # InputManifest already owned by the in-flight operation.
        assert control.drop_manifest(handle) is True
        assert thread.is_alive()
    finally:
        release.set()

    thread.join(timeout=5)
    assert not thread.is_alive()
    assert result and result[0]["manifest"] == manifest.fingerprint

    control.stop()
    server_thread.join(timeout=5)
    assert not server_thread.is_alive()


def test_workspace_generation_bump_is_atomic_across_store_instances(tmp_path):
    from hashmarks.codemap.repository_index_store import WorkspaceMapStore

    db = tmp_path / "codemap.sqlite3"
    stores = [WorkspaceMapStore(db) for _ in range(4)]
    barrier = threading.Barrier(len(stores))
    values: list[int] = []
    values_lock = threading.Lock()

    def bump(store):
        barrier.wait(timeout=5)
        value = store.bump_generation()
        with values_lock:
            values.append(value)

    threads = [threading.Thread(target=bump, args=(store,)) for store in stores]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        assert all(not thread.is_alive() for thread in threads)
        assert sorted(values) == [1, 2, 3, 4]
        assert stores[0].generation() == 4
    finally:
        for store in stores:
            store.close()
