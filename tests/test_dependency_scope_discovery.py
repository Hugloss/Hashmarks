from pathlib import Path

from hashmarks.codemap import CodeMap


def _write_scope_fixture(root: Path) -> dict[str, Path]:
    owned = root / "src" / "app.py"
    venv_dep = root / ".venv" / "lib" / "python3.13" / "site-packages" / "demo_dep" / "core.py"
    plain_venv_dep = root / "venv" / "lib" / "python3.13" / "site-packages" / "other_dep.py"
    node_dep = root / "frontend" / "node_modules" / "demo_pkg" / "index.js"
    lexical_neighbor = root / "src" / "node_modules_adapter.py"

    for path in (owned, venv_dep, plain_venv_dep, node_dep, lexical_neighbor):
        path.parent.mkdir(parents=True, exist_ok=True)
    owned.write_text("def owned():\n    return 1\n", encoding="utf-8")
    venv_dep.write_text("def dependency_impl():\n    return 2\n", encoding="utf-8")
    plain_venv_dep.write_text("def other_dependency():\n    return 3\n", encoding="utf-8")
    node_dep.write_text("export const dependencyImpl = () => 4;\n", encoding="utf-8")
    lexical_neighbor.write_text("def adapter():\n    return 5\n", encoding="utf-8")
    return {
        "owned": owned,
        "venv_dep": venv_dep,
        "plain_venv_dep": plain_venv_dep,
        "node_dep": node_dep,
        "lexical_neighbor": lexical_neighbor,
    }


def test_full_and_incremental_sync_share_dependency_scope_boundary(tmp_path: Path) -> None:
    paths = _write_scope_fixture(tmp_path)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        cold = codemap.sync()
        assert cold.discovered == 2
        assert codemap.store.paths() == {"src/app.py", "src/node_modules_adapter.py"}

        for rel in (
            paths["venv_dep"].relative_to(tmp_path).as_posix(),
            paths["plain_venv_dep"].relative_to(tmp_path).as_posix(),
            paths["node_dep"].relative_to(tmp_path).as_posix(),
            ".venv",
            "venv",
            "frontend/node_modules",
        ):
            result = codemap.sync(paths=[rel])
            assert result.discovered == 0
            assert codemap.store.paths() == {"src/app.py", "src/node_modules_adapter.py"}


def test_incremental_scope_pruning_is_segment_aware(tmp_path: Path) -> None:
    paths = _write_scope_fixture(tmp_path)
    rel = paths["lexical_neighbor"].relative_to(tmp_path).as_posix()
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        result = codemap.sync(paths=[rel])
        assert result.discovered == 1
        assert codemap.store.paths() == {rel}


def test_incremental_scope_removes_previously_admitted_dependency_rows(tmp_path: Path, monkeypatch) -> None:
    import hashmarks.codemap.indexing_lifecycle as lifecycle

    paths = _write_scope_fixture(tmp_path)
    dep_rel = paths["venv_dep"].relative_to(tmp_path).as_posix()
    original_prune_dirs = lifecycle._PRUNE_DIRS
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        # Simulate a pre-HM299 incremental admission through the same public
        # CodeMap surface, then restore the current scope contract.
        monkeypatch.setattr(lifecycle, "_PRUNE_DIRS", original_prune_dirs - {".venv"})
        historical = codemap.sync(paths=[dep_rel])
        assert historical.discovered == 1
        assert dep_rel in codemap.store.paths()

        monkeypatch.setattr(lifecycle, "_PRUNE_DIRS", original_prune_dirs)
        result = codemap.sync(paths=[dep_rel])
        assert result.discovered == 0
        assert dep_rel not in codemap.store.paths()
