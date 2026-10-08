from pathlib import Path
from unittest.mock import patch

import pytest

import hashmarks.codemap.indexing_lifecycle as lifecycle
from hashmarks.codemap.engine import CodeMap


def test_preflight_reuses_discovery_size_without_restating_files(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src" / "module.py"
    source.parent.mkdir(parents=True)
    source.write_text("value = 1\n", encoding="utf-8")
    codemap = CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3")
    try:
        discovered, warnings = codemap._discover()
        assert warnings == []
        item = next(item for item in discovered if item.rel == "src/module.py")
        assert item.size == source.stat().st_size
        with patch.object(
            Path,
            "stat",
            side_effect=AssertionError("preflight must not restat discovered files"),
        ):
            preflight = codemap._preflight_from_discovered(discovered)
        assert preflight["source_bytes"] == item.size
        assert preflight["measured_files"] == 1
    finally:
        codemap.close()


def test_incremental_subtree_carries_measured_size_into_preflight(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src" / "module.py"
    source.parent.mkdir(parents=True)
    source.write_text("value = 123\n", encoding="utf-8")
    codemap = CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3")
    try:
        discovered = codemap._discover_subtree("src")
        item = next(item for item in discovered if item.rel == "src/module.py")
        assert item.size == source.stat().st_size
        preflight = codemap._preflight_from_discovered(discovered)
        assert preflight["source_bytes"] == item.size
    finally:
        codemap.close()


@pytest.mark.parametrize("mode", ["cold", "warm", "incremental"])
def test_sync_projects_module_identity_once_per_file(tmp_path: Path, mode: str) -> None:
    source = tmp_path / "src" / "pkg" / "module.py"
    source.parent.mkdir(parents=True)
    source.write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.setuptools.package-dir]\n"" = "src"\n', encoding="utf-8"
    )

    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as codemap:
        if mode != "cold":
            codemap.sync()
        with patch.object(
            lifecycle, "_module_name", wraps=lifecycle._module_name
        ) as project:
            codemap.sync(["src/pkg/module.py"] if mode == "incremental" else None)
        assert (
            sum(call.args[0] == "src/pkg/module.py" for call in project.call_args_list)
            == 1
        )
        row = codemap.store.file_row("src/pkg/module.py")
        assert row is not None
        assert row["module_name"] == "pkg.module"
