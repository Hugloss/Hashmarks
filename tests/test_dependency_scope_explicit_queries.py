from pathlib import Path
from unittest.mock import patch

import pytest

from hashmarks.codemap import CodeMap


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _dependency_path(root: Path) -> Path:
    return (
        root
        / ".venv"
        / "lib"
        / "python3.13"
        / "site-packages"
        / "demo_dep"
        / "core.py"
    )


def test_outline_rejects_pruned_dependency_before_digest_or_index(tmp_path: Path) -> None:
    owned = tmp_path / "src" / "app.py"
    dependency = _dependency_path(tmp_path)
    _write(owned, "def owned():\n    return 1\n")
    _write(dependency, "def dependency_impl():\n    return 2\n")
    rel = dependency.relative_to(tmp_path).as_posix()

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        assert rel not in codemap.store.paths()
        with patch.object(
            codemap.file_store,
            "digest",
            side_effect=AssertionError("pruned dependency source must not be read"),
        ):
            with pytest.raises(FileNotFoundError, match="not indexed"):
                codemap.outline(rel)
        assert rel not in codemap.store.paths()


def test_explicit_source_cannot_resurrect_pruned_dependency(tmp_path: Path) -> None:
    dependency = _dependency_path(tmp_path)
    _write(dependency, "def dependency_impl():\n    return 2\n")
    rel = dependency.relative_to(tmp_path).as_posix()

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        with patch.object(
            codemap.file_store,
            "digest",
            side_effect=AssertionError("pruned dependency source must not be read"),
        ):
            with pytest.raises(KeyError, match="symbol not found"):
                codemap.source(f"{rel}::dependency_impl")
        assert rel not in codemap.store.paths()


def test_explicit_query_currentness_respects_context_index_denial(tmp_path: Path) -> None:
    hidden = tmp_path / "private" / "hidden.py"
    _write(hidden, "def hidden():\n    return 3\n")
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "private/**"\nindex = false\n',
        encoding="utf-8",
    )
    rel = hidden.relative_to(tmp_path).as_posix()

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        assert rel not in codemap.store.paths()
        with patch.object(
            codemap.file_store,
            "digest",
            side_effect=AssertionError("context-denied source must not be read"),
        ):
            with pytest.raises(FileNotFoundError, match="not indexed"):
                codemap.outline(rel)
        assert rel not in codemap.store.paths()


def test_explicit_query_scope_pruning_is_segment_aware(tmp_path: Path) -> None:
    owner = tmp_path / "src" / "node_modules_adapter.py"
    _write(owner, "def adapter():\n    return 4\n")
    rel = owner.relative_to(tmp_path).as_posix()

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        codemap.sync()
        outline = codemap.outline(rel)
        assert outline["path"] == rel
        source = codemap.source(f"{rel}::adapter")
        assert source["path"] == rel
        assert "return 4" in source["content"]


def test_explicit_query_retires_historical_pruned_dependency_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dependency = _dependency_path(tmp_path)
    _write(dependency, "def dependency_impl():\n    return 5\n")
    rel = dependency.relative_to(tmp_path).as_posix()

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        original = codemap._path_admitted_for_analysis
        monkeypatch.setattr(codemap, "_path_admitted_for_analysis", lambda _rel: True)
        historical = codemap.outline(rel)
        assert historical["path"] == rel
        assert rel in codemap.store.paths()
        generation_before = codemap.store.generation()

        monkeypatch.setattr(codemap, "_path_admitted_for_analysis", original)
        with pytest.raises(FileNotFoundError, match="not indexed"):
            codemap.outline(rel)
        assert rel not in codemap.store.paths()
        assert codemap.store.generation() > generation_before
