from __future__ import annotations

import os
from pathlib import Path

import pytest

from hashmarks.cas import CAS
from hashmarks.directory_store import DirectoryDigestStore
from hashmarks.file_store import FileDigestStore
from hashmarks.merkle import MerkleTree
from hashmarks.paths import canonical_event_relative_path, canonical_host_path


def _make_dir_symlink(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlinks unavailable")


def test_symlinked_workspace_store_auto_exclusion_is_stable(tmp_path: Path):
    real = tmp_path / "real"
    repo = real / "repo"
    repo.mkdir(parents=True)
    (repo / "src.py").write_text("x = 1\n")

    alias_root = tmp_path / "alias"
    _make_dir_symlink(alias_root, real)
    workspace_alias = alias_root / "repo"

    store = FileDigestStore(workspace_alias / "custom-state" / "digests.sqlite3")
    tree = MerkleTree(workspace_alias, store, walk_ignore_names=(".git",))

    first = tree.directory_digest("")
    store.digest(
        repo / "src.py",
        workspace=repo,
        relative_path="src.py",
        force=True,
    )
    tree.invalidate("custom-state", kind="directory")
    second = tree.directory_digest("")

    assert store.db_path == (repo / "custom-state" / "digests.sqlite3").resolve()
    assert tree._is_mandatory_excluded("custom-state/digests.sqlite3")
    assert first == second


def test_relative_store_roots_are_cwd_independent(tmp_path: Path, monkeypatch):
    first_cwd = tmp_path / "first"
    second_cwd = tmp_path / "second"
    first_cwd.mkdir()
    second_cwd.mkdir()
    source = tmp_path / "source.txt"
    source.write_text("payload")

    monkeypatch.chdir(first_cwd)
    files = FileDigestStore("state/files.sqlite3")
    directories = DirectoryDigestStore("state/directories.sqlite3")
    cas = CAS("state/cas")

    expected = canonical_host_path(first_cwd / "state")
    assert files.db_path.parent == expected
    assert directories.db_path.parent == expected
    assert cas.root == expected / "cas"

    monkeypatch.chdir(second_cwd)

    digest = files.digest(source, workspace=tmp_path, relative_path="source.txt")
    directories.put(workspace=tmp_path, relative_path="", digest=digest)
    assert directories.flush() == 1

    blob = cas.put_bytes(b"blob")

    assert files.db_path.is_file()
    assert directories.db_path.is_file()
    assert cas.has(blob)
    assert not (second_cwd / "state").exists()


def test_watcher_event_alias_collapses_but_symlink_leaf_is_preserved(tmp_path: Path):
    real = tmp_path / "real"
    repo = real / "repo"
    repo.mkdir(parents=True)
    alias = tmp_path / "alias"
    _make_dir_symlink(alias, real)

    outside = tmp_path / "outside.txt"
    outside.write_text("payload")
    link = repo / "link"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")

    assert canonical_event_relative_path(repo, alias / "repo" / "link") == "link"
    assert canonical_event_relative_path(repo, outside) is None
    assert canonical_event_relative_path(repo, "src/new.py") == "src/new.py"


def test_walk_ignored_directory_is_ignored_broadly_but_selectable_explicitly(tmp_path: Path):
    workspace = tmp_path / "repo"
    ignored = workspace / "__pycache__"
    ignored.mkdir(parents=True)
    target = ignored / "cache.bin"
    target.write_text("A")
    (workspace / "src.py").write_text("source")

    store = FileDigestStore(tmp_path / "files.sqlite3")
    tree = MerkleTree(workspace, store)

    broad_before = tree.directory_digest("")
    selected_before = tree.digest_selected(["__pycache__"])

    target.write_text("B")
    tree.invalidate("__pycache__/cache.bin", kind="file")

    assert tree.directory_digest("") == broad_before
    assert tree.digest_selected(["__pycache__"]) != selected_before


def test_mandatory_hashmarks_exclusion_cannot_be_disabled_by_legacy_ignore_names(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    state = workspace / ".hashmarks"
    state.mkdir()
    (state / "manual.txt").write_text("state")

    store = FileDigestStore(tmp_path / "files.sqlite3")
    tree = MerkleTree(workspace, store, walk_ignore_names=())

    with pytest.raises(ValueError, match="excluded"):
        tree.digest_selected([".hashmarks"])


def test_relative_explicit_exclusion_preserves_symlink_leaf(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = workspace / "state-link"
    _make_dir_symlink(link, outside)

    store = FileDigestStore(tmp_path / "files.sqlite3")
    tree = MerkleTree(workspace, store, exclude_paths=("state-link",))

    with pytest.raises(ValueError, match="excluded"):
        tree.digest_selected(["state-link"])


def test_package_has_no_absolute_path_authority_calls():
    package = Path(__file__).resolve().parents[1] / "hashmarks"
    offenders = []
    for source in package.glob("*.py"):
        if ".absolute(" in source.read_text():
            offenders.append(source.name)
    assert offenders == []


def test_real_symlink_and_dotdot_workspace_aliases_produce_same_identity(tmp_path: Path):
    real = tmp_path / "real"
    repo = real / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "a.py").write_text("print('x')\n")

    alias = tmp_path / "alias"
    _make_dir_symlink(alias, real)
    dotdot = real / "unused" / ".." / "repo"

    roots = []
    for index, workspace in enumerate((repo, alias / "repo", dotdot)):
        store = FileDigestStore(tmp_path / f"store-{index}.sqlite3")
        tree = MerkleTree(workspace, store)
        roots.append(tree.digest_selected(["src"]))
        store.close()

    assert roots[0] == roots[1] == roots[2]


def test_direct_primitives_and_identity_engine_share_path_semantics(tmp_path: Path):
    from hashmarks.engine import IdentityEngine

    real = tmp_path / "real"
    repo = real / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "a.py").write_text("A")
    alias = tmp_path / "alias"
    _make_dir_symlink(alias, real)

    direct_store = FileDigestStore(tmp_path / "direct.sqlite3")
    direct_tree = MerkleTree(alias / "repo", direct_store)
    direct_root = direct_tree.digest_selected(["src"])

    engine = IdentityEngine(alias / "repo", state_dir=tmp_path / "engine-state")
    manifest = engine.manifest(["src"])
    engine_root = engine.input_root(manifest)

    assert direct_tree.workspace == engine.workspace == repo.resolve()
    assert direct_root == engine_root

    direct_store.close()
    engine.close()
