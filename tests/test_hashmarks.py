from pathlib import Path

from hashmarks.cas import CAS
from hashmarks.file_store import FileDigestStore
from hashmarks.graph import IdentityGraph
from hashmarks.merkle import MerkleTree


def test_merkle_changes_when_file_changes(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "src").mkdir()
    target = workspace / "src" / "a.py"
    target.write_text("x = 1\n")

    store = FileDigestStore(tmp_path / "state.sqlite3")
    tree = MerkleTree(workspace, store)

    before = tree.directory_digest("")
    target.write_text("x = 2\n")
    tree.invalidate("src/a.py")
    after = tree.directory_digest("")

    assert before != after


def test_merkle_same_when_content_restored(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    target = workspace / "a.txt"
    target.write_text("same")

    store = FileDigestStore(tmp_path / "state.sqlite3")
    tree = MerkleTree(workspace, store)

    before = tree.directory_digest("")
    target.write_text("different")
    tree.invalidate("a.txt")
    middle = tree.directory_digest("")
    assert middle != before

    target.write_text("same")
    tree.invalidate("a.txt")
    after = tree.directory_digest("")
    assert after == before


def test_selected_inputs_ignore_unrelated_file(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "src").mkdir()
    (workspace / "src" / "a.py").write_text("a")
    unrelated = workspace / "notes.txt"
    unrelated.write_text("one")

    store = FileDigestStore(tmp_path / "state.sqlite3")
    tree = MerkleTree(workspace, store)

    before = tree.digest_selected(["src"])
    unrelated.write_text("two")
    tree.invalidate("notes.txt")
    after = tree.digest_selected(["src"])

    assert before == after




def test_cas_round_trip(tmp_path: Path):
    cas = CAS(tmp_path / "cas")
    digest = cas.put_bytes(b"hello")
    assert cas.get_bytes(digest) == b"hello"
    assert cas.has(digest)




def test_graph_equality_cutoff():
    values = {"file": "A"}
    calls = {"leaf": 0, "parent": 0}

    graph: IdentityGraph[str, str] = IdentityGraph()

    def leaf(_):
        calls["leaf"] += 1
        return values["file"]

    def parent(deps):
        calls["parent"] += 1
        return "P:" + deps["leaf"]

    graph.add("leaf", leaf)
    graph.add("parent", parent, dependencies=("leaf",))

    assert graph.get("parent") == "P:A"
    leaf_version = graph.version("leaf")
    parent_version = graph.version("parent")

    # An event occurs, but canonical leaf value does not change.
    graph.invalidate("leaf")
    assert graph.get("parent") == "P:A"
    assert graph.version("leaf") == leaf_version
    assert graph.version("parent") == parent_version

    # Now content changes, so versions propagate.
    values["file"] = "B"
    graph.invalidate("leaf")
    assert graph.get("parent") == "P:B"
    assert graph.version("leaf") > leaf_version
    assert graph.version("parent") > parent_version
