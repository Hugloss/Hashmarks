from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from hashmarks.engine import IdentityEngine
from hashmarks.observation import ObservationState
from hashmarks.watcher import NativeLinuxBatchWatcher, create_default_watcher


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux inotify test")
def test_default_linux_watcher_has_no_third_party_dependency(tmp_path: Path):
    watcher = create_default_watcher(tmp_path, lambda _paths: None)
    assert isinstance(watcher, NativeLinuxBatchWatcher)


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux inotify test")
def test_native_linux_watcher_observes_file_edit(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    target = workspace / "a.txt"
    target.write_text("one")

    engine = IdentityEngine(workspace, state_dir=tmp_path / "state")
    engine.changes.mark_reconciled()
    watcher = engine.watcher(debounce_seconds=0.01)
    assert isinstance(watcher, NativeLinuxBatchWatcher)
    watcher.start()
    try:
        target.write_text("two")
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            snap = engine.changes.snapshot()
            if snap.state is ObservationState.DIRTY and "a.txt" in snap.paths:
                break
            time.sleep(0.01)
        else:
            raise AssertionError(
                f"inotify edit was not observed: {engine.changes.snapshot()}"
            )
    finally:
        watcher.stop()
        engine.close()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux inotify test")
def test_native_linux_watcher_excludes_engine_state(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    engine = IdentityEngine(workspace)
    engine.changes.mark_reconciled()
    watcher = engine.watcher(debounce_seconds=0.01)
    watcher.start()
    try:
        (engine.state_dir / "noise.txt").write_text("ignored")
        time.sleep(0.08)
        assert engine.changes.snapshot().state is ObservationState.CLEAN
    finally:
        watcher.stop()
        engine.close()


def test_cli_does_not_import_watchdog_as_daemon_gate():
    import hashmarks.cli as cli

    source = Path(cli.__file__).read_text()
    assert "import watchdog" not in source
    assert "_require_watcher" not in source


def test_project_core_and_daemon_metadata_are_registry_free():
    import tomllib

    project_root = Path(__file__).resolve().parents[1]
    data = tomllib.loads((project_root / "pyproject.toml").read_text())
    assert data["build-system"]["requires"] == []
    assert data["build-system"]["build-backend"] == "hashmarks_build"
    assert data["project"]["dependencies"] == []
    assert data["project"]["optional-dependencies"] == {"mcp": ["mcp>=2.2.0"]}


def test_daemon_request_barrier_observes_immediate_write(tmp_path: Path):
    if not sys.platform.startswith("linux"):
        pytest.skip("native inotify barrier is Linux-specific")
    import threading

    from hashmarks.client import IdentityClient
    from hashmarks.daemon import IdentityDaemon

    workspace = tmp_path / "repo"
    workspace.mkdir()
    target = workspace / "a.txt"
    target.write_text("A")
    socket_path = tmp_path / "identity.sock"
    daemon = IdentityDaemon(
        workspace,
        state_dir=tmp_path / "state",
        socket_path=socket_path,
    )
    thread = threading.Thread(target=daemon.serve_forever, daemon=True)
    thread.start()
    deadline = time.monotonic() + 3
    while not socket_path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert socket_path.exists()

    client = IdentityClient(workspace, socket_path=socket_path)
    first = client.input_root(["a.txt"])
    target.write_text("B")
    # No wait for the watcher thread: request-time synchronize() must drain
    # already-queued inotify events before hot identity is trusted.
    second = client.input_root(["a.txt"])
    assert second["hash"] != first["hash"]
    client.stop()
    thread.join(timeout=3)
