from __future__ import annotations

from typing import TYPE_CHECKING

from hashmarks.codemap import CodeMap
from hashmarks.codemap.repository_index_store import WorkspaceMapStore

if TYPE_CHECKING:
    from pathlib import Path


def test_repository_ownership_uses_single_current_name(tmp_path: Path) -> None:
    (tmp_path / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        value = codemap.repository_ownership_graph()
        assert not hasattr(codemap, "authority_ownership_graph")
    assert value["schema"] == "hashmarks.authority-ownership-graph.v3"


def test_repository_instruction_scope_uses_single_current_name(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# repository instructions\n", encoding="utf-8")
    (tmp_path / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        value = codemap.repository_instruction_scope("sample.py")
        assert not hasattr(codemap, "scoped_authority")
    assert value["schema"] == "hashmarks.codemap-scoped-authority.v1"


def test_repository_instruction_store_uses_single_current_name(tmp_path: Path) -> None:
    store = WorkspaceMapStore(tmp_path / "codemap.sqlite3")
    try:
        assert not hasattr(store, "authority_file_rows")
        assert store.repository_instruction_file_rows() == []
    finally:
        store.close()
