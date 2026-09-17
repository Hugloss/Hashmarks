from __future__ import annotations

import threading
import time
from pathlib import Path


from hashmarks.client import IdentityClient
from hashmarks.daemon import IdentityDaemon
from hashmarks.engine import IdentityEngine
from hashmarks.file_store import FileDigestStore
from hashmarks.inputs import InputManifest
from hashmarks.merkle import MerkleTree


class _FakeWatcher:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def synchronize(self) -> bool:
        return True


def test_manifest_hot_equality_cutoff_skips_all_file_metadata(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    paths = []
    for i in range(100):
        rel = f"f{i:03}.txt"
        (workspace / rel).write_text(str(i))
        paths.append(rel)

    engine = IdentityEngine(workspace, state_dir=tmp_path / "state")
    manifest = InputManifest(tuple(paths))
    first = engine.input_root(manifest)

    calls = {"count": 0}
    original = engine.file_store._metadata

    def counting(path):
        calls["count"] += 1
        return original(path)

    monkeypatch.setattr(engine.file_store, "_metadata", counting)
    assert engine.input_root(manifest) == first
    assert calls["count"] == 0
    engine.close()


def test_unrelated_dirty_path_does_not_invalidate_manifest(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "repo"
    (workspace / "src").mkdir(parents=True)
    (workspace / "docs").mkdir()
    (workspace / "src" / "a.py").write_text("A")
    (workspace / "docs" / "readme.md").write_text("one")

    engine = IdentityEngine(workspace, state_dir=tmp_path / "state")
    manifest = engine.manifest(["src/a.py"])
    first = engine.input_root(manifest)

    (workspace / "docs" / "readme.md").write_text("two")
    engine.record_changes(["docs/readme.md"])

    def should_not_stat(_path):
        raise AssertionError("unrelated dirty path invalidated manifest")

    monkeypatch.setattr(engine.file_store, "_metadata", should_not_stat)
    assert engine.input_root(manifest) == first
    engine.close()


def test_related_dirty_path_invalidates_manifest_and_changes_root(tmp_path: Path):
    workspace = tmp_path / "repo"
    (workspace / "src").mkdir(parents=True)
    target = workspace / "src" / "a.py"
    target.write_text("A")

    engine = IdentityEngine(workspace, state_dir=tmp_path / "state")
    manifest = engine.manifest(["src/a.py"])
    first = engine.input_root(manifest)

    target.write_text("B")
    engine.record_changes(["src/a.py"])
    second = engine.input_root(manifest)
    assert second != first
    engine.close()


def test_dirty_directory_ancestor_invalidates_explicit_file_manifest(tmp_path: Path):
    workspace = tmp_path / "repo"
    (workspace / "src" / "pkg").mkdir(parents=True)
    target = workspace / "src" / "pkg" / "a.py"
    target.write_text("A")

    engine = IdentityEngine(workspace, state_dir=tmp_path / "state")
    manifest = engine.manifest(["src/pkg/a.py"])
    first = engine.input_root(manifest)

    target.write_text("B")
    engine.record_changes(["src"])
    second = engine.input_root(manifest)
    assert second != first
    engine.close()


def test_default_engine_does_not_persist_unused_directory_nodes(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "a.txt").write_text("A")

    engine = IdentityEngine(workspace, state_dir=tmp_path / "state")
    assert engine.directory_store is None
    engine.workspace_root()
    assert not (tmp_path / "state" / "directories.sqlite3").exists()
    engine.close()


def test_directory_store_can_still_be_enabled_explicitly(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "a.txt").write_text("A")

    engine = IdentityEngine(
        workspace,
        state_dir=tmp_path / "state",
        persist_directory_digests=True,
    )
    engine.workspace_root()
    assert engine.directory_store is not None
    assert engine.directory_store.count(workspace) == 1
    engine.close()


def test_engine_watcher_excludes_internal_state_path(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    engine = IdentityEngine(workspace)
    watcher = engine.watcher()
    assert watcher.exclude_relative_paths == (".hashmarks",)
    engine.close()


def test_daemon_preserves_hot_manifest_state_across_clients(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    for i in range(50):
        (workspace / f"f{i:02}.txt").write_text(str(i))

    fake = _FakeWatcher()
    socket_path = tmp_path / "daemon.sock"
    daemon = IdentityDaemon(
        workspace,
        state_dir=tmp_path / "state",
        socket_path=socket_path,
        watcher_factory=lambda _engine: fake,
    )

    thread = threading.Thread(target=daemon.serve_forever, daemon=True)
    thread.start()
    deadline = time.monotonic() + 2
    while not socket_path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert socket_path.exists()
    assert fake.started

    client1 = IdentityClient(workspace, socket_path=socket_path)
    first = client1.input_root(["f00.txt", "f01.txt"])
    assert client1.status()["observation"] == "clean"

    calls = {"count": 0}
    original = daemon.engine.file_store._metadata

    def counting(path):
        calls["count"] += 1
        return original(path)

    monkeypatch.setattr(daemon.engine.file_store, "_metadata", counting)
    client2 = IdentityClient(workspace, socket_path=socket_path)
    second = client2.input_root(["f00.txt", "f01.txt"])
    assert second["hash"] == first["hash"]
    assert calls["count"] == 0

    # Simulate a watcher-observed source edit and prove the same daemon updates.
    (workspace / "f00.txt").write_text("changed")
    daemon.engine.record_changes(["f00.txt"])
    third = client2.input_root(["f00.txt", "f01.txt"])
    assert third["hash"] != first["hash"]

    client2.stop()
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert fake.stopped


def test_input_manifest_fingerprint_is_stable_and_path_sensitive():
    a = InputManifest(("a", "b/c"))
    b = InputManifest(("a", "b/c"))
    c = InputManifest(("a", "b/d"))
    assert a.fingerprint == b.fingerprint
    assert a.fingerprint != c.fingerprint


def test_parent_directory_modified_event_is_observer_noise():
    from hashmarks.watcher import should_ignore_observer_event

    assert should_ignore_observer_event(event_type="modified", is_directory=True)
    assert not should_ignore_observer_event(event_type="created", is_directory=True)
    assert not should_ignore_observer_event(event_type="deleted", is_directory=True)
    assert not should_ignore_observer_event(event_type="moved", is_directory=True)
    assert not should_ignore_observer_event(event_type="modified", is_directory=False)


def test_strong_manifest_verify_detects_leaf_type_change_without_tracker(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    target = workspace / "item"
    target.write_text("file")
    store = FileDigestStore(tmp_path / "files.sqlite3")
    tree = MerkleTree(workspace, store)
    manifest = InputManifest(("item",))
    first = tree.digest_manifest(manifest)

    target.unlink()
    target.mkdir()
    (target / "child").write_text("content")
    second = tree.digest_manifest(manifest, verify=True)
    assert second != first
