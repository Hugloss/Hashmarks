from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

import pytest

from hashmarks import (
    Directory,
    File,
    Glob,
    InputManifest,
    RepositoryIdentity,
    RepositoryIdentityMode,
)
from hashmarks.client import DaemonUnavailableError, IdentityClient
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


def _start_daemon(workspace: Path, tmp_path: Path):
    watcher = _BarrierWatcher()
    socket_path = tmp_path / "identity.sock"
    daemon = IdentityDaemon(
        workspace,
        state_dir=tmp_path / "state",
        socket_path=socket_path,
        watcher_factory=lambda _engine: watcher,
    )
    thread = threading.Thread(target=daemon.serve_forever, daemon=True)
    thread.start()
    client = IdentityClient(workspace, socket_path=socket_path)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            client.status()
            break
        except OSError:
            time.sleep(0.01)
    else:
        raise AssertionError("identity daemon did not become ready")
    return daemon, watcher, socket_path, thread


def test_identity_auto_falls_back_to_safe_local(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    target = workspace / "a.txt"
    target.write_text("A")

    with RepositoryIdentity(
        workspace, mode="auto", state_dir=tmp_path / "state"
    ) as identity:
        first = identity.snapshot(File("a.txt"))
        assert first.mode == "local"
        target.write_text("B")
        # Default local observer is per-read reconciliation, so no stale hot hit.
        second = identity.snapshot(File("a.txt"))
        assert second.hash != first.hash


def test_identity_daemon_mode_uses_daemon_snapshot(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "a.txt").write_text("A")
    daemon, watcher, socket_path, thread = _start_daemon(workspace, tmp_path)
    try:
        identity = RepositoryIdentity(
            workspace,
            mode=RepositoryIdentityMode.DAEMON,
            state_dir=tmp_path / "state",
            socket_path=socket_path,
        )
        snap = identity.snapshot(File("a.txt"))
        assert snap.mode == "daemon"
        assert snap.manifest_fingerprint
        identity.close()
    finally:
        IdentityClient(workspace, socket_path=socket_path).stop()
        thread.join(timeout=2)
        assert watcher.stopped


def test_input_specs_are_small_and_explicit(tmp_path: Path):
    workspace = tmp_path / "repo"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "a.py").write_text("A")
    (workspace / "uv.lock").write_text("lock")
    with RepositoryIdentity(
        workspace, mode="local", state_dir=tmp_path / "state"
    ) as identity:
        manifest = identity.manifest([Directory("src"), File("uv.lock")])
        assert manifest.paths == ("src", "uv.lock")
        globbed = identity.manifest([Glob("src/*.py")])
        assert globbed.paths == ("src/a.py",)


def test_snapshot_diff_explains_repository_identity_change(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    target = workspace / "a.txt"
    target.write_text("A")
    with RepositoryIdentity(
        workspace, mode="local", state_dir=tmp_path / "state"
    ) as identity:
        first = identity.snapshot(File("a.txt"))
        target.write_text("B")
        second = identity.snapshot(File("a.txt"))

    diff = second.diff(first)
    assert diff.changed
    assert diff.old_digest != diff.new_digest


def test_registered_manifest_is_uploaded_once_and_reused_hot(
    tmp_path: Path, monkeypatch
):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    paths = []
    for i in range(500):
        rel = f"f{i:04}.txt"
        (workspace / rel).write_text(str(i))
        paths.append(rel)

    daemon, _watcher, socket_path, thread = _start_daemon(workspace, tmp_path)
    client = IdentityClient(workspace, socket_path=socket_path)
    manifest = InputManifest(tuple(paths))
    handle = client.register_manifest(manifest, chunk_size=37)
    first = client.input_root_manifest(handle)

    calls = {"count": 0}
    original = daemon.engine.file_store._metadata

    def counting(path):
        calls["count"] += 1
        return original(path)

    monkeypatch.setattr(daemon.engine.file_store, "_metadata", counting)
    second = client.input_root_manifest(handle)
    assert second["hash"] == first["hash"]
    assert calls["count"] == 0
    assert client.status()["registered_manifests"] == 1

    client.stop()
    thread.join(timeout=2)


def test_stats_expose_cache_and_incremental_counters(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "a.txt").write_text("A")
    with RepositoryIdentity(
        workspace, mode="local", state_dir=tmp_path / "state"
    ) as identity:
        identity.snapshot(File("a.txt"))
        stats = identity.stats()
    assert stats["schema"] == "fastidentity.identity.v1"
    assert stats["file_store"]["content_hashes"] >= 1
    assert "manifest_digest_calls" in stats["merkle"]


def test_daemon_mode_is_explicitly_required_when_requested(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    with pytest.raises(DaemonUnavailableError):
        RepositoryIdentity(workspace, mode="daemon", state_dir=tmp_path / "state")


def test_typed_input_specs_reject_wrong_kind(tmp_path: Path):
    workspace = tmp_path / "repo"
    (workspace / "src").mkdir(parents=True)
    (workspace / "a.txt").write_text("A")
    with RepositoryIdentity(
        workspace, mode="local", state_dir=tmp_path / "state"
    ) as identity:
        with pytest.raises(ValueError, match="not a file"):
            identity.manifest([File("src")])
        with pytest.raises(ValueError, match="not a real directory"):
            identity.manifest([Directory("a.txt")])


def test_local_watcher_mode_detects_immediate_edit_without_manual_record(
    tmp_path: Path,
):
    if not __import__("sys").platform.startswith("linux"):
        pytest.skip("native request barrier test is Linux-specific")
    workspace = tmp_path / "repo"
    workspace.mkdir()
    target = workspace / "a.txt"
    target.write_text("A")
    with RepositoryIdentity(
        workspace,
        mode="local",
        state_dir=tmp_path / "state",
        local_observer="watcher",
    ) as identity:
        first = identity.snapshot(File("a.txt"))
        target.write_text("B")
        second = identity.snapshot(File("a.txt"))
        assert second.hash != first.hash


def test_cli_snapshot_auto_mode_safely_falls_back_local(tmp_path: Path, capsys):
    from hashmarks.cli import main

    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "a.txt").write_text("A")
    rc = main(
        [
            "--workspace",
            str(workspace),
            "snapshot",
            "--mode",
            "auto",
            "--input",
            "a.txt",
        ]
    )
    assert rc == 0
    output = capsys.readouterr().out
    assert '"mode": "local"' in output


def test_cli_stats_and_doctor_are_available(tmp_path: Path, capsys):
    from hashmarks.cli import main

    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "a.txt").write_text("A")
    assert main(["--workspace", str(workspace), "stats", "--mode", "local"]) == 0
    stats = capsys.readouterr().out
    assert "fastidentity.identity.v1" in stats
    assert main(["--workspace", str(workspace), "doctor", "--mode", "local"]) == 0
    doctor = capsys.readouterr().out
    assert '"requested_mode": "local"' in doctor


def test_identity_snapshot_manifest_registers_once_with_daemon(
    tmp_path: Path, monkeypatch
):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    paths = []
    for i in range(200):
        rel = f"f{i:04}.txt"
        (workspace / rel).write_text(str(i))
        paths.append(rel)
    _daemon, _watcher, socket_path, thread = _start_daemon(workspace, tmp_path)
    identity = RepositoryIdentity(
        workspace,
        mode="auto",
        state_dir=tmp_path / "state",
        socket_path=socket_path,
    )
    manifest = InputManifest(tuple(paths))
    calls = {"count": 0}
    original = identity.client.register_manifest

    def counting(manifest, *, chunk_size=10_000):
        calls["count"] += 1
        return original(manifest, chunk_size=chunk_size)

    monkeypatch.setattr(identity.client, "register_manifest", counting)
    first = identity.snapshot_manifest(manifest)
    second = identity.snapshot_manifest(manifest)
    assert first.hash == second.hash
    assert first.mode == "daemon"
    assert calls["count"] == 1
    identity.client.stop()
    thread.join(timeout=2)
    identity.close()


def test_manual_local_observer_reuses_hot_state_when_changes_are_reported(
    tmp_path: Path,
):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    target = workspace / "a.txt"
    target.write_text("A")
    with RepositoryIdentity(
        workspace,
        mode="local",
        state_dir=tmp_path / "state",
        local_observer="manual",
    ) as identity:
        first = identity.snapshot(File("a.txt"))
        target.write_text("B")
        identity.record_changes(["a.txt"])
        second = identity.snapshot(File("a.txt"))
        assert second.hash != first.hash


def test_workspace_isolation_with_shared_persistent_state(tmp_path: Path):
    a = tmp_path / "worktree-a"
    b = tmp_path / "worktree-b"
    a.mkdir()
    b.mkdir()
    (a / "same.txt").write_text("A")
    (b / "same.txt").write_text("B")
    shared = tmp_path / "shared-state"

    with (
        RepositoryIdentity(a, mode="local", state_dir=shared / "a") as ia,
        RepositoryIdentity(b, mode="local", state_dir=shared / "b") as ib,
    ):
        sa = ia.snapshot(File("same.txt"))
        sb = ib.snapshot(File("same.txt"))
        assert sa.hash != sb.hash
        (a / "same.txt").write_text("A2")
        sa2 = ia.snapshot(File("same.txt"))
        sb2 = ib.snapshot(File("same.txt"))
        assert sa2.hash != sa.hash
        assert sb2.hash == sb.hash


def test_workspace_runtime_socket_namespaces_are_distinct(tmp_path: Path):
    from hashmarks.client import default_socket_path

    a = tmp_path / "worktree-a"
    b = tmp_path / "worktree-b"
    a.mkdir()
    b.mkdir()
    assert default_socket_path(a) != default_socket_path(b)
