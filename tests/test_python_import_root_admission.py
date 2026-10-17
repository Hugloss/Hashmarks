"""Construction and sync must use the same admitted packaging authority."""

from pathlib import Path

import pytest

from hashmarks.codemap import CodeMap


@pytest.mark.parametrize("denial", ["index", "visibility", "symlink"])
def test_unadmitted_root_manifest_cannot_supply_initial_import_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, denial: str
) -> None:
    workspace = tmp_path / "repo"
    package = workspace / "src/pkg"
    package.mkdir(parents=True)
    (package / "owner.py").write_text("class Owner: pass\n")
    manifest = workspace / "pyproject.toml"
    metadata = '[tool.setuptools.package-dir]\n"" = "src"\n'
    if denial == "symlink":
        outside = tmp_path / "outside.toml"
        outside.write_text(metadata)
        manifest.symlink_to(outside)
    else:
        manifest.write_text(metadata)
        setting = "index = false" if denial == "index" else "visibility = 'deny'"
        (workspace / ".hashmarks-context.toml").write_text(
            f"[[rule]]\npattern = 'pyproject.toml'\n{setting}\n"
        )
    read = Path.read_text

    def qualified_read(
        path: Path, encoding: str | None = None, errors: str | None = None
    ) -> str:
        assert path != manifest, "unadmitted root manifest must not be read"
        return read(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", qualified_read)
    with CodeMap(
        workspace,
        state_dir=tmp_path / "partial",
        artifact_db=tmp_path / "artifacts.sqlite3",
    ) as partial:
        partial.index.sync(["src/pkg/owner.py"])
        row = partial.store.file_row("src/pkg/owner.py")
        assert row is not None
        assert row["module_name"] == "src.pkg.owner"
    with CodeMap(
        workspace,
        state_dir=tmp_path / "full",
        artifact_db=tmp_path / "artifacts.sqlite3",
    ) as full:
        full.index.sync()
        row = full.store.file_row("src/pkg/owner.py")
        assert row is not None
        assert row["module_name"] == "src.pkg.owner"


def test_hidden_workspace_declaration_cannot_filter_admitted_nested_projects(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.uv.workspace]\nmembers = ["allowed"]\n'
    )
    (tmp_path / ".hashmarks-context.toml").write_text(
        "[[rule]]\npattern = 'pyproject.toml'\nvisibility = 'deny'\n"
        "[[rule]]\npattern = '*/pyproject.toml'\nvisibility = 'source'\n"
    )
    for project in ("allowed", "other"):
        package = tmp_path / project / "src" / project
        package.mkdir(parents=True)
        (package / "owner.py").write_text("class Owner: pass\n")
        (tmp_path / project / "pyproject.toml").write_text(
            '[tool.setuptools.package-dir]\n"" = "src"\n'
        )
    with CodeMap(
        tmp_path,
        state_dir=tmp_path / ".state",
        artifact_db=tmp_path / ".state/artifacts.sqlite3",
    ) as codemap:
        codemap.index.sync()
        for project in ("allowed", "other"):
            row = codemap.store.file_row(f"{project}/src/{project}/owner.py")
            assert row is not None
            assert row["module_name"] == f"{project}.owner"


def test_admitted_workspace_members_and_excludes_keep_native_scope(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.uv.workspace]\nmembers = ["allowed", "excluded"]\nexclude = ["excluded"]\n'
    )
    for project in ("allowed", "excluded", "other"):
        package = tmp_path / project / "src" / project
        package.mkdir(parents=True)
        (package / "owner.py").write_text("class Owner: pass\n")
        (tmp_path / project / "pyproject.toml").write_text(
            '[tool.setuptools.package-dir]\n"" = "src"\n'
        )
    with CodeMap(
        tmp_path,
        state_dir=tmp_path / ".state",
        artifact_db=tmp_path / ".state/artifacts.sqlite3",
    ) as codemap:
        codemap.index.sync()
        for project in ("allowed", "excluded", "other"):
            row = codemap.store.file_row(f"{project}/src/{project}/owner.py")
            assert row is not None
            expected = (
                "allowed.owner"
                if project == "allowed"
                else f"{project}.src.{project}.owner"
            )
            assert row["module_name"] == expected
