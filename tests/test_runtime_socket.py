from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import pytest

from hashmarks.client import IdentityClient, default_runtime_dir, default_socket_path
from hashmarks.daemon import IdentityDaemon


@pytest.mark.skipif(os.name != "posix", reason="Unix runtime socket policy")
def test_default_socket_is_separate_from_persistent_state(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    state = workspace / ".hashmarks"

    # Make the fallback deterministic and independent of the caller's shell.
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    socket_path = default_socket_path(workspace)

    assert socket_path.name == "identity.sock"
    assert state not in socket_path.parents
    assert len(os.fsencode(str(socket_path))) < 100


@pytest.mark.skipif(os.name != "posix", reason="Unix runtime socket policy")
def test_socket_path_stays_short_for_very_long_workspace(tmp_path: Path, monkeypatch):
    workspace = tmp_path
    for i in range(12):
        workspace = workspace / ("very-long-workspace-component-" + str(i).zfill(2))
    workspace.mkdir(parents=True)

    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    socket_path = default_socket_path(workspace)

    # Linux sockaddr_un.sun_path is commonly 108 bytes including terminator.
    assert len(os.fsencode(str(socket_path))) < 100


@pytest.mark.skipif(os.name != "posix", reason="Unix runtime socket policy")
def test_state_dir_does_not_move_default_socket(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)

    a = default_socket_path(workspace)
    b = default_socket_path(workspace)
    assert a == b


@pytest.mark.skipif(os.name != "posix", reason="Unix runtime socket policy")
def test_default_daemon_socket_round_trip_with_separate_state(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "a.txt").write_text("A")
    state = workspace / ".hashmarks"

    # Put runtime IPC under a known short local directory for this test.
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))

    daemon = IdentityDaemon(workspace, state_dir=state)
    assert daemon.socket_path == default_socket_path(workspace)
    assert state not in daemon.socket_path.parents

    thread = threading.Thread(target=daemon.serve_forever, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not daemon.socket_path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert daemon.socket_path.exists()

    client = IdentityClient(workspace, state_dir=state)
    status = client.status()
    assert status["workspace"] == str(workspace.resolve())
    assert Path(status["state_dir"]) == state.resolve()
    assert Path(status["socket"]) == daemon.socket_path

    client.stop()
    thread.join(timeout=5)
    assert not thread.is_alive()
