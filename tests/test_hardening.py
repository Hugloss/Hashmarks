from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from hashmarks import IdentityCycleError
from hashmarks.cas import CAS
from hashmarks.digest import hash_bytes
from hashmarks.file_store import FileDigestStore
from hashmarks.graph import IdentityGraph
from hashmarks.inputs import resolve_inputs
from hashmarks.merkle import MerkleTree
from hashmarks.watcher import DirtyBatch


def make_tree(workspace: Path) -> tuple[FileDigestStore, MerkleTree]:
    store = FileDigestStore(workspace / ".hashmarks" / "identity.sqlite3")
    return store, MerkleTree(workspace, store)


def test_state_directory_does_not_change_workspace_digest(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "src.py").write_text("x = 1\n")
    store, tree = make_tree(workspace)

    first = tree.directory_digest("")
    # Mutate SQLite after the first digest and force the root directory to be
    # recomputed. Internal state must still be invisible to content identity.
    store.digest(
        workspace / "src.py",
        workspace=workspace,
        relative_path="src.py",
        force=True,
    )
    tree.invalidate("src.py")
    second = tree.directory_digest("")

    assert first == second


def test_custom_in_workspace_store_files_are_auto_excluded(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "src.py").write_text("x")
    state_dir = workspace / "custom-state"
    store = FileDigestStore(state_dir / "digests.sqlite3")
    tree = MerkleTree(workspace, store, walk_ignore_names=(".git",))

    first = tree.directory_digest("")
    # Mutate the cache through its own API; the SQLite DB/WAL may change, but
    # those internal artifacts must never feed back into workspace identity.
    store.digest(
        workspace / "src.py",
        workspace=workspace,
        relative_path="src.py",
        force=True,
    )
    tree.invalidate("custom-state", kind="directory")
    second = tree.directory_digest("")

    assert first == second
    assert tree._is_mandatory_excluded("custom-state/digests.sqlite3")
    assert tree._is_mandatory_excluded("custom-state/digests.sqlite3-wal")
    assert tree._is_mandatory_excluded("custom-state/digests.sqlite3-shm")
    assert tree._is_mandatory_excluded("custom-state/digests.sqlite3-journal")


def test_default_noise_directories_are_ignored(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "src.py").write_text("x")
    store, tree = make_tree(workspace)
    first = tree.directory_digest("")

    for name in ("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"):
        d = workspace / name
        d.mkdir(exist_ok=True)
        (d / "noise").write_text(name)
        tree.invalidate(name, kind="directory")

    assert tree.directory_digest("") == first


def test_explicit_excluded_input_is_rejected(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    store, tree = make_tree(workspace)
    with pytest.raises(ValueError, match="excluded"):
        tree.digest_selected([".hashmarks"])


def test_resolve_inputs_rejects_absolute_literal(tmp_path: Path):
    absolute = tmp_path / "outside.txt"
    absolute.write_text("x")
    with pytest.raises(ValueError, match="relative to workspace"):
        resolve_inputs(tmp_path, [str(absolute)])


def test_resolve_inputs_rejects_absolute_glob(tmp_path: Path):
    with pytest.raises(ValueError, match="relative to workspace"):
        resolve_inputs(tmp_path, ["/tmp/*.py"])


def test_resolve_inputs_rejects_windows_absolute_pattern(tmp_path: Path):
    with pytest.raises(ValueError, match="relative to workspace"):
        resolve_inputs(tmp_path, [r"C:\\Windows\\*.dll"])


def test_resolve_inputs_rejects_parent_escape(tmp_path: Path):
    with pytest.raises(ValueError, match="must not contain '..'"):
        resolve_inputs(tmp_path, ["../outside"])


def test_resolve_inputs_glob_and_missing_pattern(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("a")
    (tmp_path / "src" / "b.txt").write_text("b")
    assert resolve_inputs(tmp_path, ["src/*.py"]) == ["src/a.py"]
    with pytest.raises(FileNotFoundError, match="matched nothing"):
        resolve_inputs(tmp_path, ["missing/*.py"])


def test_file_invalidation_never_adds_file_path_to_dirty_dirs(tmp_path: Path):
    workspace = tmp_path / "repo"
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "a.py").write_text("a")
    _, tree = make_tree(workspace)
    tree.directory_digest("")
    tree.invalidate("src/a.py", kind="file")

    assert "src/a.py" not in tree._dirty_dirs
    assert "src" in tree._dirty_dirs
    assert "" in tree._dirty_dirs


def test_directory_invalidation_includes_directory_itself(tmp_path: Path):
    workspace = tmp_path / "repo"
    (workspace / "src").mkdir(parents=True)
    _, tree = make_tree(workspace)
    tree.directory_digest("")
    tree.invalidate("src", kind="directory")
    assert tree._dirty_dirs == {"", "src"}


def test_identity_graph_cycle_detection():
    graph: IdentityGraph[str, str] = IdentityGraph()
    graph.add("a", lambda d: d["b"], dependencies=("b",))
    graph.add("b", lambda d: d["a"], dependencies=("a",))

    with pytest.raises(IdentityCycleError, match="dependency cycle"):
        graph.get("a")


def test_identity_graph_concurrent_get_and_invalidate():
    current = {"value": "A"}
    state_lock = threading.Lock()
    graph: IdentityGraph[str, str] = IdentityGraph()

    def leaf(_):
        with state_lock:
            return current["value"]

    graph.add("leaf", leaf)
    graph.add("parent", lambda deps: "P:" + deps["leaf"], dependencies=("leaf",))
    assert graph.get("parent") == "P:A"

    def reader():
        for _ in range(200):
            value = graph.get("parent")
            assert value in {"P:A", "P:B"}

    def writer():
        for i in range(100):
            with state_lock:
                current["value"] = "A" if i % 2 == 0 else "B"
            graph.invalidate("leaf")
            graph.get("parent")

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(reader) for _ in range(4)] + [pool.submit(writer)]
        for future in futures:
            future.result()


def test_symlink_target_string_changes_identity_without_following(tmp_path: Path):
    if not hasattr(os, "symlink"):
        pytest.skip("symlinks unsupported")

    workspace = tmp_path / "repo"
    workspace.mkdir()
    outside_a = tmp_path / "outside-a.txt"
    outside_b = tmp_path / "outside-b.txt"
    outside_a.write_text("same")
    outside_b.write_text("same")
    link = workspace / "link"
    try:
        link.symlink_to(outside_a)
    except OSError:
        pytest.skip("symlink creation unavailable")

    _, tree = make_tree(workspace)
    first = tree.digest_selected(["link"])

    link.unlink()
    link.symlink_to(outside_b)
    tree.invalidate("link", kind="file")
    second = tree.digest_selected(["link"])

    assert first != second

    # Changing target content does not change link identity: the link target
    # string is canonical; external content is not followed/read.
    outside_b.write_text("different contents")
    tree.invalidate("link", kind="file")
    third = tree.digest_selected(["link"])
    assert third == second


def test_selected_symlink_uses_link_node_semantics(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    target = workspace / "target"
    target.write_text("payload")
    link = workspace / "link"
    try:
        link.symlink_to("target")
    except OSError:
        pytest.skip("symlink creation unavailable")

    _, tree = make_tree(workspace)
    selected = tree.digest_selected(["link"])

    target.write_text("changed")
    tree.invalidate("target")
    assert tree.digest_selected(["link"]) == selected


def test_cas_detects_corruption_and_maintenance(tmp_path: Path):
    cas = CAS(tmp_path / "cas")
    digest = cas.put_bytes(b"hello")
    assert cas.size_bytes() == 5
    assert list(cas.iter_digests()) == [digest.hash]

    cas._path(digest).write_bytes(b"xxxxx")
    with pytest.raises(IOError, match="CAS corruption"):
        cas.get_bytes(digest)

    assert cas.delete(digest)
    assert not cas.delete(digest)




def test_file_store_count_and_prune_missing(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    file = workspace / "a.txt"
    file.write_text("a")
    store = FileDigestStore(tmp_path / "state.sqlite3")
    store.digest(file, workspace=workspace, relative_path="a.txt")
    assert store.count(workspace) == 1
    file.unlink()
    assert store.prune_missing_files(workspace) == 1
    assert store.count(workspace) == 0


def test_dirty_batch_deduplicates_and_sorts():
    batch = DirtyBatch()
    batch.add("foo")
    batch.add("foo")
    batch.extend(["bar", "foo"])
    assert batch.drain() == ["bar", "foo"]
    assert batch.drain() == []


def test_fresh_process_style_reopen_is_stable_with_state_inside_workspace(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "src.py").write_text("x = 1\n")
    db = workspace / ".hashmarks" / "identity.sqlite3"

    store1 = FileDigestStore(db)
    tree1 = MerkleTree(workspace, store1)
    first = tree1.directory_digest("")
    store1.close()

    store2 = FileDigestStore(db)
    tree2 = MerkleTree(workspace, store2)
    second = tree2.directory_digest("")
    store2.close()

    assert first == second
