from __future__ import annotations

from pathlib import Path

import pytest

from hashmarks.cas import CAS
from hashmarks.directory_store import DirectoryDigestStore
from hashmarks.engine import IdentityEngine
from hashmarks.file_store import FileDigestStore
from hashmarks.inputs import InputManifest
from hashmarks.merkle import MerkleTree
from hashmarks.observation import ChangeTracker, ObservationState


def test_input_manifest_resolves_once_and_matches_selected_digest(tmp_path: Path):
    workspace = tmp_path / "repo"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "a.py").write_text("a")
    (workspace / "src" / "b.py").write_text("b")
    store = FileDigestStore(tmp_path / "files.sqlite3")
    tree = MerkleTree(workspace, store)

    manifest = InputManifest.resolve(workspace, ["src/*.py"])
    assert manifest.paths == ("src/a.py", "src/b.py")
    assert tree.digest_manifest(manifest) == tree.digest_selected(manifest.paths)


def test_dirty_tracker_invalidates_without_direct_tree_call(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    target = workspace / "a.txt"
    target.write_text("A")
    tracker = ChangeTracker()
    store = FileDigestStore(tmp_path / "files.sqlite3")
    tree = MerkleTree(workspace, store, change_tracker=tracker)

    first = tree.directory_digest("")
    assert tracker.snapshot().state is ObservationState.CLEAN

    target.write_text("B")
    tracker.mark_dirty(["a.txt"])
    second = tree.directory_digest("")
    assert second != first
    assert tracker.snapshot().state is ObservationState.CLEAN


def test_unknown_tracker_forces_safe_reconciliation_without_path_list(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    target = workspace / "a.txt"
    target.write_text("A")
    tracker = ChangeTracker()
    store = FileDigestStore(tmp_path / "files.sqlite3")
    tree = MerkleTree(workspace, store, change_tracker=tracker)

    first = tree.directory_digest("")
    target.write_text("B")
    tracker.mark_unknown("simulated watcher overflow")
    second = tree.directory_digest("")

    assert second != first
    assert tracker.snapshot().state is ObservationState.CLEAN


def test_reconciliation_generation_cannot_erase_newer_event():
    tracker = ChangeTracker()
    assert tracker.mark_reconciled()
    before = tracker.snapshot()
    tracker.mark_dirty(["src/a.py"])

    assert not tracker.mark_reconciled(expected_generation=before.generation)
    after = tracker.snapshot()
    assert after.state is ObservationState.DIRTY
    assert after.paths == ("src/a.py",)


def test_verify_rehashes_bytes_but_preserves_canonical_identity(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "a.txt").write_text("A")
    store = FileDigestStore(tmp_path / "files.sqlite3")
    tree = MerkleTree(workspace, store)

    first = tree.directory_digest("")

    import hashmarks.file_store as file_store_module

    real_hash_file = file_store_module.hash_file
    calls = {"count": 0}

    def counting_hash_file(path):
        calls["count"] += 1
        return real_hash_file(path)

    monkeypatch.setattr(file_store_module, "hash_file", counting_hash_file)

    # Hot normal read should not even descend to file hashing.
    assert tree.directory_digest("") == first
    assert calls["count"] == 0

    # Strong verification bypasses the hot directory cache and file metadata
    # reuse, but canonical identity remains identical.
    assert tree.directory_digest("", verify=True) == first
    assert calls["count"] == 1


def test_directory_nodes_are_persisted_but_not_used_as_freshness_authority(tmp_path: Path):
    workspace = tmp_path / "repo"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "a.py").write_text("a")
    file_store = FileDigestStore(tmp_path / "files.sqlite3")
    dir_store = DirectoryDigestStore(tmp_path / "dirs.sqlite3")
    tree = MerkleTree(workspace, file_store, directory_store=dir_store)

    root = tree.directory_digest("")
    assert dir_store.count(workspace) == 2  # src + root
    assert dir_store.get(workspace=workspace, relative_path="") == root

    # A new MerkleTree must still reconcile from filesystem/file metadata.
    (workspace / "src" / "a.py").write_text("b")
    fresh = MerkleTree(workspace, file_store, directory_store=dir_store)
    assert fresh.directory_digest("") != root


def test_warm_scan_reuses_file_bytes_after_hot_cache_drop(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    for i in range(25):
        (workspace / f"f{i:02}.txt").write_text(str(i))
    store = FileDigestStore(tmp_path / "files.sqlite3")
    tree = MerkleTree(workspace, store)
    first = tree.directory_digest("")
    tree.drop_hot_cache()

    import hashmarks.file_store as file_store_module

    def should_not_hash(_path):
        raise AssertionError("unchanged file bytes were reread")

    monkeypatch.setattr(file_store_module, "hash_file", should_not_hash)
    assert tree.directory_digest("") == first






def test_identity_engine_owns_state_and_keeps_it_out_of_identity(tmp_path: Path):
    workspace = tmp_path / "repo"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "a.py").write_text("A")

    engine = IdentityEngine(workspace)
    manifest = engine.manifest(["src"])
    first = engine.input_root(manifest)

    # Internal derived state must not enter repository content identity.
    state_marker = engine.state_dir / "diagnostic.txt"
    state_marker.write_text("derived")
    second = engine.input_root(manifest)
    assert second == first

    (workspace / "src" / "a.py").write_text("B")
    engine.record_changes(["src/a.py"])
    third = engine.input_root(manifest)
    assert third != first
    engine.close()



def test_file_hash_retries_if_file_changes_during_read(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    target = workspace / "a.txt"
    target.write_text("A")
    store = FileDigestStore(tmp_path / "files.sqlite3")

    import hashmarks.file_store as file_store_module

    real_hash_file = file_store_module.hash_file
    calls = {"count": 0}

    def mutating_hash_file(path):
        digest = real_hash_file(path)
        if calls["count"] == 0:
            Path(path).write_text("B")
        calls["count"] += 1
        return digest

    monkeypatch.setattr(file_store_module, "hash_file", mutating_hash_file)
    digest = store.digest(
        target,
        workspace=workspace,
        relative_path="a.txt",
        force=True,
    )

    assert calls["count"] == 2
    assert digest == real_hash_file(target)


def test_observation_change_during_reconciliation_is_retried(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "a.txt").write_text("A")
    tracker = ChangeTracker()
    tracker.mark_reconciled()
    store = FileDigestStore(tmp_path / "files.sqlite3")
    tree = MerkleTree(workspace, store, change_tracker=tracker)

    original = tree._directory_digest
    calls = {"count": 0}

    def changing_once(rel, *, verify):
        result = original(rel, verify=verify)
        if calls["count"] == 0:
            tracker.mark_dirty(["a.txt"])
        calls["count"] += 1
        return result

    monkeypatch.setattr(tree, "_directory_digest", changing_once)
    tree.directory_digest("")

    assert calls["count"] >= 2
    assert tracker.snapshot().state is ObservationState.CLEAN


def test_cas_streaming_file_put_and_materialize(tmp_path: Path):
    source = tmp_path / "large.bin"
    source.write_bytes((b"abcdef" * 10000) + b"tail")
    cas = CAS(tmp_path / "cas")

    digest = cas.put_file(source)
    target = tmp_path / "out" / "large.bin"
    cas.materialize(digest, target, verify=True)

    assert target.read_bytes() == source.read_bytes()
    assert cas.get_bytes(digest) == source.read_bytes()


def test_manifest_collapses_descendants_of_selected_directory(tmp_path: Path):
    workspace = tmp_path / "repo"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "a.py").write_text("a")
    manifest = InputManifest.resolve(workspace, ["src", "src/*.py"])
    assert manifest.paths == ("src",)


def test_engine_relative_state_dir_is_workspace_relative(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    engine = IdentityEngine(workspace, state_dir="state/cache")
    assert engine.state_dir == (workspace / "state" / "cache").resolve()
    engine.close()


def test_watcher_stop_marks_observation_unknown(tmp_path: Path):
    from hashmarks.watcher import WatchdogBatchWatcher

    tracker = ChangeTracker()
    tracker.mark_reconciled()
    watcher = WatchdogBatchWatcher(tmp_path, lambda _paths: None, change_tracker=tracker)
    watcher.stop()
    assert tracker.snapshot().state is ObservationState.UNKNOWN


def test_selected_file_manifest_uses_one_batched_store_lookup(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    paths = []
    for i in range(30):
        rel = f"f{i:02}.txt"
        (workspace / rel).write_text(rel)
        paths.append(rel)

    store = FileDigestStore(tmp_path / "files.sqlite3")
    tree = MerkleTree(workspace, store)
    calls = {"count": 0}
    original = store._rows_many

    def counting_rows_many(workspace_key, relpaths):
        calls["count"] += 1
        return original(workspace_key, relpaths)

    monkeypatch.setattr(store, "_rows_many", counting_rows_many)
    tree.digest_manifest(InputManifest(tuple(paths)))
    assert calls["count"] == 1
