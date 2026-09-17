from pathlib import Path

from hashmarks.codemap import CodeMap


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_setuptools_src_layout_uses_import_identity_not_repository_prefix(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "pyproject.toml",
        '[project]\nname="demo"\nversion="0"\n[tool.setuptools.package-dir]\n""="src"\n',
    )
    _write(tmp_path, "src/pkg/__init__.py", "")
    _write(tmp_path, "src/pkg/api.py", "def run(): return 1\n")
    _write(
        tmp_path, "src/pkg/use.py", "from pkg.api import run\ndef use(): return run()\n"
    )
    _write(
        tmp_path,
        "tests/test_api.py",
        "from pkg.api import run\ndef test_run(): assert run() == 1\n",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        row = codemap.store.file_row("src/pkg/api.py")
        affected = codemap.affected("src/pkg/api.py", max_depth=2)
        owners, ambiguous = codemap._resolve_import_owner_evidence(
            "tests/test_api.py", "pkg.api.run"
        )
    assert row is not None and row["module_name"] == "pkg.api"
    assert "src/pkg/use.py" in affected["affected_files"]
    assert owners == ["src/pkg/api.py"]
    assert ambiguous is False


def test_relative_import_in_setuptools_src_layout_uses_configured_module_root(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "pyproject.toml",
        '[project]\nname="demo"\nversion="0"\n[tool.setuptools.package-dir]\n""="src"\n',
    )
    _write(tmp_path, "src/pkg/__init__.py", "")
    _write(tmp_path, "src/pkg/api.py", "def run(): return 1\n")
    _write(
        tmp_path, "src/pkg/use.py", "from .api import run\ndef use(): return run()\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence(
            "src/pkg/use.py", ".api.run"
        )
    assert owners == ["src/pkg/api.py"]
    assert ambiguous is False


def test_unconfigured_src_namespace_keeps_src_as_module_identity(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pyproject.toml", '[project]\nname="demo"\nversion="0"\n')
    _write(tmp_path, "src/m0.py", "def run(): return 1\n")
    _write(tmp_path, "src/m1.py", "from src.m0 import run\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        row = codemap.store.file_row("src/m0.py")
        affected = codemap.affected("src/m0.py", max_depth=2)
    assert row is not None and row["module_name"] == "src.m0"
    assert "src/m1.py" in affected["affected_files"]


def test_source_root_configuration_change_reprojects_reused_module_identity(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pyproject.toml", '[project]\nname="demo"\nversion="0"\n')
    _write(tmp_path, "src/pkg/api.py", "def run(): return 1\n")
    _write(tmp_path, "src/pkg/use.py", "from pkg.api import run\n")
    state = tmp_path / ".state"
    with CodeMap(tmp_path, state_dir=state) as codemap:
        codemap.sync()
        before = codemap.store.file_row("src/pkg/api.py")
        assert before is not None and before["module_name"] == "src.pkg.api"
    _write(
        tmp_path,
        "pyproject.toml",
        '[project]\nname="demo"\nversion="0"\n[tool.setuptools.package-dir]\n""="src"\n',
    )
    with CodeMap(tmp_path, state_dir=state) as codemap:
        result = codemap.sync()
        after = codemap.store.file_row("src/pkg/api.py")
        affected = codemap.affected("src/pkg/api.py", max_depth=2)
    assert result.parsed_artifacts == 1
    assert result.reused_artifacts >= 2
    assert after is not None and after["module_name"] == "pkg.api"
    assert "src/pkg/use.py" in affected["affected_files"]


def test_duplicate_configured_import_identity_is_ambiguous_and_not_reverse_owned(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "pyproject.toml",
        """[tool.poetry]\nname="demo"\nversion="0"\npackages=[\n  {include="shared", from="services/a/src"},\n  {include="shared", from="services/b/src"},\n]\n""",
    )
    for service in ("a", "b"):
        _write(tmp_path, f"services/{service}/src/shared/__init__.py", "")
        _write(
            tmp_path, f"services/{service}/src/shared/api.py", "def run(): return 1\n"
        )
    _write(
        tmp_path, "consumer.py", "from shared.api import run\ndef use(): return run()\n"
    )
    _write(
        tmp_path,
        "tests/test_consumer.py",
        "from shared.api import run\ndef test_run(): assert run() == 1\n",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        paths = codemap.store.module_paths("shared.api")
        owners, ambiguous = codemap._resolve_import_owner_evidence(
            "tests/test_consumer.py", "shared.api.run"
        )
        affected_a = codemap.affected("services/a/src/shared/api.py", max_depth=2)
        affected_b = codemap.affected("services/b/src/shared/api.py", max_depth=2)
    assert paths == ["services/a/src/shared/api.py", "services/b/src/shared/api.py"]
    assert owners == []
    assert ambiguous is True
    assert "consumer.py" not in affected_a["affected_files"]
    assert "consumer.py" not in affected_b["affected_files"]


def test_duplicate_import_identity_becomes_unique_after_one_owner_removed(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "pyproject.toml",
        """[tool.poetry]\nname="demo"\nversion="0"\npackages=[\n  {include="shared", from="services/a/src"},\n  {include="shared", from="services/b/src"},\n]\n""",
    )
    for service in ("a", "b"):
        _write(
            tmp_path, f"services/{service}/src/shared/api.py", "def run(): return 1\n"
        )
    _write(tmp_path, "consumer.py", "from shared.api import run\n")
    state = tmp_path / ".state"
    with CodeMap(tmp_path, state_dir=state) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence(
            "consumer.py", "shared.api.run"
        )
        assert owners == [] and ambiguous is True
    (tmp_path / "services/b/src/shared/api.py").unlink()
    with CodeMap(tmp_path, state_dir=state) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence(
            "consumer.py", "shared.api.run"
        )
        affected = codemap.affected("services/a/src/shared/api.py", max_depth=1)
    assert owners == ["services/a/src/shared/api.py"]
    assert ambiguous is False
    assert "consumer.py" in affected["affected_files"]


def test_nested_project_pyproject_scopes_src_root_to_project_directory(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "services/a/pyproject.toml",
        '[project]\nname="service-a"\nversion="0"\n[tool.setuptools.package-dir]\n""="src"\n',
    )
    _write(tmp_path, "services/a/src/pkg/api.py", "def run(): return 1\n")
    _write(tmp_path, "services/a/src/pkg/use.py", "from pkg.api import run\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        row = codemap.store.file_row("services/a/src/pkg/api.py")
        affected = codemap.affected("services/a/src/pkg/api.py", max_depth=1)
    assert row is not None and row["module_name"] == "pkg.api"
    assert "services/a/src/pkg/use.py" in affected["affected_files"]


def test_nested_projects_exposing_same_import_identity_remain_ambiguous(
    tmp_path: Path,
) -> None:
    for service in ("a", "b"):
        _write(
            tmp_path,
            f"services/{service}/pyproject.toml",
            f'[project]\nname="service-{service}"\nversion="0"\n[tool.setuptools.package-dir]\n""="src"\n',
        )
        _write(
            tmp_path, f"services/{service}/src/shared/api.py", "def run(): return 1\n"
        )
    _write(tmp_path, "consumer.py", "from shared.api import run\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        paths = codemap.store.module_paths("shared.api")
        owners, ambiguous = codemap._resolve_import_owner_evidence(
            "consumer.py", "shared.api.run"
        )
    assert paths == ["services/a/src/shared/api.py", "services/b/src/shared/api.py"]
    assert owners == []
    assert ambiguous is True


def test_same_service_targeted_pyproject_change_refreshes_import_roots(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "services/a/pyproject.toml",
        '[project]\nname="service-a"\nversion="0"\n',
    )
    _write(tmp_path, "services/a/src/pkg/api.py", "def run(): return 1\n")
    _write(tmp_path, "services/a/src/pkg/use.py", "from pkg.api import run\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.store.file_row("services/a/src/pkg/api.py")
        assert before is not None and before["module_name"] == "services.a.src.pkg.api"
        _write(
            tmp_path,
            "services/a/pyproject.toml",
            '[project]\nname="service-a"\nversion="0"\n[tool.setuptools.package-dir]\n""="src"\n',
        )
        codemap.sync(paths=["services/a/pyproject.toml", "services/a/src/pkg"])
        after = codemap.store.file_row("services/a/src/pkg/api.py")
        affected = codemap.affected("services/a/src/pkg/api.py", max_depth=1)
    assert after is not None and after["module_name"] == "pkg.api"
    assert "services/a/src/pkg/use.py" in affected["affected_files"]


def test_uv_workspace_exclude_does_not_create_false_import_ambiguity(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "pyproject.toml",
        """[project]\nname="root"\nversion="0"\n[tool.uv.workspace]\nmembers=["packages/*"]\nexclude=["packages/legacy"]\n""",
    )
    for member in ("app", "legacy"):
        _write(
            tmp_path,
            f"packages/{member}/pyproject.toml",
            f'''[project]\nname="{member}"\nversion="0"\n[tool.setuptools.package-dir]\n""="src"\n''',
        )
        _write(
            tmp_path, f"packages/{member}/src/shared/api.py", "def run(): return 1\n"
        )
    _write(tmp_path, "consumer.py", "from shared.api import run\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        app = codemap.store.file_row("packages/app/src/shared/api.py")
        legacy = codemap.store.file_row("packages/legacy/src/shared/api.py")
        owners, ambiguous = codemap._resolve_import_owner_evidence(
            "consumer.py", "shared.api.run"
        )
    assert app is not None and app["module_name"] == "shared.api"
    assert (
        legacy is not None and legacy["module_name"] == "packages.legacy.src.shared.api"
    )
    assert owners == ["packages/app/src/shared/api.py"]
    assert ambiguous is False


def test_targeted_pyproject_change_reprojects_python_without_explicit_source_paths(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "services/a/pyproject.toml",
        '[project]\nname="service-a"\nversion="0"\n',
    )
    _write(tmp_path, "services/a/src/pkg/api.py", "def run(): return 1\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.store.file_row("services/a/src/pkg/api.py")
        assert before is not None and before["module_name"] == "services.a.src.pkg.api"
        _write(
            tmp_path,
            "services/a/pyproject.toml",
            '[project]\nname="service-a"\nversion="0"\n[tool.setuptools.package-dir]\n""="src"\n',
        )
        result = codemap.sync(paths=["services/a/pyproject.toml"])
        after = codemap.store.file_row("services/a/src/pkg/api.py")
    assert result.discovered == 2
    assert after is not None and after["module_name"] == "pkg.api"


def test_uv_workspace_membership_change_reprojects_existing_member_files(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "pyproject.toml",
        """[project]\nname="root"\nversion="0"\n[tool.uv.workspace]\nmembers=["packages/a"]\n""",
    )
    for member in ("a", "b"):
        _write(
            tmp_path,
            f"packages/{member}/pyproject.toml",
            f'''[project]\nname="{member}"\nversion="0"\n[tool.setuptools.package-dir]\n""="src"\n''',
        )
        _write(tmp_path, f"packages/{member}/src/pkg/api.py", "def run(): return 1\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.store.file_row("packages/b/src/pkg/api.py")
        assert before is not None and before["module_name"] == "packages.b.src.pkg.api"
        _write(
            tmp_path,
            "pyproject.toml",
            """[project]\nname="root"\nversion="0"\n[tool.uv.workspace]\nmembers=["packages/a", "packages/b"]\n""",
        )
        codemap.sync(paths=["pyproject.toml"])
        after = codemap.store.file_row("packages/b/src/pkg/api.py")
        paths = codemap.store.module_paths("pkg.api")
    assert after is not None and after["module_name"] == "pkg.api"
    assert paths == ["packages/a/src/pkg/api.py", "packages/b/src/pkg/api.py"]


def test_uv_workspace_member_move_root_only_sync_discovers_new_and_drops_ghost_owner(
    tmp_path: Path,
) -> None:
    import shutil

    _write(
        tmp_path,
        "pyproject.toml",
        """[project]\nname="root"\nversion="0"\n[tool.uv.workspace]\nmembers=["packages/a"]\n""",
    )
    _write(
        tmp_path,
        "packages/a/pyproject.toml",
        """[project]\nname="a"\nversion="0"\n[tool.setuptools.package-dir]\n""="src"\n""",
    )
    _write(tmp_path, "packages/a/src/pkg/api.py", "def run(): return 1\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        shutil.move(str(tmp_path / "packages/a"), str(tmp_path / "packages/b"))
        _write(
            tmp_path,
            "pyproject.toml",
            """[project]\nname="root"\nversion="0"\n[tool.uv.workspace]\nmembers=["packages/b"]\n""",
        )
        result = codemap.sync(paths=["pyproject.toml"])
        old = codemap.store.file_row("packages/a/src/pkg/api.py")
        new = codemap.store.file_row("packages/b/src/pkg/api.py")
        paths = codemap.store.module_paths("pkg.api")
    assert result.discovered == 2
    assert old is None
    assert new is not None and new["module_name"] == "pkg.api"
    assert paths == ["packages/b/src/pkg/api.py"]


def test_uv_workspace_member_removal_reprojects_files_without_deleting_repository_evidence(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "pyproject.toml",
        """[project]\nname="root"\nversion="0"\n[tool.uv.workspace]\nmembers=["packages/a", "packages/b"]\n""",
    )
    for member in ("a", "b"):
        _write(
            tmp_path,
            f"packages/{member}/pyproject.toml",
            f'''[project]\nname="{member}"\nversion="0"\n[tool.setuptools.package-dir]\n""="src"\n''',
        )
        _write(tmp_path, f"packages/{member}/src/pkg/api.py", "def run(): return 1\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        assert codemap.store.module_paths("pkg.api") == [
            "packages/a/src/pkg/api.py",
            "packages/b/src/pkg/api.py",
        ]
        _write(
            tmp_path,
            "pyproject.toml",
            """[project]\nname="root"\nversion="0"\n[tool.uv.workspace]\nmembers=["packages/a"]\n""",
        )
        result = codemap.sync(paths=["pyproject.toml"])
        removed_member = codemap.store.file_row("packages/b/src/pkg/api.py")
        paths = codemap.store.module_paths("pkg.api")
    assert result.discovered == 2
    assert (
        removed_member is not None
        and removed_member["module_name"] == "packages.b.src.pkg.api"
    )
    assert paths == ["packages/a/src/pkg/api.py"]


def test_uv_member_source_root_move_pyproject_only_sync_drops_ghost_and_discovers_new_root(
    tmp_path: Path,
) -> None:
    import shutil

    _write(
        tmp_path,
        "pyproject.toml",
        """[project]\nname="root"\nversion="0"\n[tool.uv.workspace]\nmembers=["packages/a"]\n""",
    )
    _write(
        tmp_path,
        "packages/a/pyproject.toml",
        """[project]\nname="a"\nversion="0"\n[tool.setuptools.package-dir]\n""="src"\n""",
    )
    _write(tmp_path, "packages/a/src/pkg/api.py", "def run(): return 1\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        shutil.move(
            str(tmp_path / "packages/a/src"), str(tmp_path / "packages/a/python")
        )
        _write(
            tmp_path,
            "packages/a/pyproject.toml",
            """[project]\nname="a"\nversion="0"\n[tool.setuptools.package-dir]\n""="python"\n""",
        )
        result = codemap.sync(paths=["packages/a/pyproject.toml"])
        old = codemap.store.file_row("packages/a/src/pkg/api.py")
        new = codemap.store.file_row("packages/a/python/pkg/api.py")
        paths = codemap.store.module_paths("pkg.api")
    assert result.discovered == 2
    assert old is None
    assert new is not None and new["module_name"] == "pkg.api"
    assert paths == ["packages/a/python/pkg/api.py"]


def test_uv_member_manifest_deletion_revokes_packaging_import_authority(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "pyproject.toml",
        """[project]\nname="root"\nversion="0"\n[tool.uv.workspace]\nmembers=["packages/a"]\n""",
    )
    _write(
        tmp_path,
        "packages/a/pyproject.toml",
        """[project]\nname="a"\nversion="0"\n[tool.setuptools.package-dir]\n""="src"\n""",
    )
    _write(tmp_path, "packages/a/src/pkg/api.py", "def run(): return 1\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        (tmp_path / "packages/a/pyproject.toml").unlink()
        result = codemap.sync(paths=["packages/a/pyproject.toml"])
        row = codemap.store.file_row("packages/a/src/pkg/api.py")
        paths = codemap.store.module_paths("pkg.api")
    assert result.discovered == 1
    assert row is not None and row["module_name"] == "packages.a.src.pkg.api"
    assert paths == []


def test_uv_workspace_namespace_portions_are_distinct_modules_not_duplicate_owners(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "pyproject.toml",
        """[project]\nname="root"\nversion="0"\n[tool.uv.workspace]\nmembers=["packages/a", "packages/b"]\n""",
    )
    _write(
        tmp_path,
        "packages/a/pyproject.toml",
        """[project]\nname="a"\nversion="0"\n[tool.setuptools.package-dir]\n""="src"\n""",
    )
    _write(
        tmp_path,
        "packages/b/pyproject.toml",
        """[project]\nname="b"\nversion="0"\n[tool.setuptools.package-dir]\n""="src"\n""",
    )
    _write(tmp_path, "packages/a/src/company/alpha/api.py", "def alpha(): return 1\n")
    _write(tmp_path, "packages/b/src/company/beta/api.py", "def beta(): return 2\n")
    _write(
        tmp_path,
        "consumer.py",
        "from company.alpha.api import alpha\nfrom company.beta.api import beta\n",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        a = codemap._resolve_import_paths("consumer.py", "company.alpha.api.alpha")
        b = codemap._resolve_import_paths("consumer.py", "company.beta.api.beta")
        assert codemap.store.module_paths("company.alpha.api") == [
            "packages/a/src/company/alpha/api.py"
        ]
        assert codemap.store.module_paths("company.beta.api") == [
            "packages/b/src/company/beta/api.py"
        ]
    assert a == ["packages/a/src/company/alpha/api.py"]
    assert b == ["packages/b/src/company/beta/api.py"]


def test_uv_workspace_same_namespace_concrete_module_duplicate_fails_closed(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "pyproject.toml",
        """[project]\nname="root"\nversion="0"\n[tool.uv.workspace]\nmembers=["packages/a", "packages/b"]\n""",
    )
    for member in ("a", "b"):
        _write(
            tmp_path,
            f"packages/{member}/pyproject.toml",
            f'''[project]\nname="{member}"\nversion="0"\n[tool.setuptools.package-dir]\n""="src"\n''',
        )
        _write(
            tmp_path,
            f"packages/{member}/src/company/shared/api.py",
            "def run(): return 1\n",
        )
    _write(tmp_path, "consumer.py", "from company.shared.api import run\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        paths = codemap.store.module_paths("company.shared.api")
        resolved = codemap._resolve_import_paths(
            "consumer.py", "company.shared.api.run"
        )
        ambiguous = codemap._python_import_identity_ambiguous(
            "consumer.py", "company.shared.api.run"
        )
    assert paths == [
        "packages/a/src/company/shared/api.py",
        "packages/b/src/company/shared/api.py",
    ]
    assert resolved == []
    assert ambiguous is True


def test_uv_workspace_transition_reprojection_does_not_scan_all_persisted_rows(
    tmp_path: Path, monkeypatch
) -> None:
    _write(
        tmp_path,
        "pyproject.toml",
        """[project]\nname="root"\nversion="0"\n[tool.uv.workspace]\nmembers=["packages/a"]\n""",
    )
    for member in ("a", "b"):
        _write(
            tmp_path,
            f"packages/{member}/pyproject.toml",
            f'''[project]\nname="{member}"\nversion="0"\n[tool.setuptools.package-dir]\n""="src"\n''',
        )
        for index in range(20):
            _write(
                tmp_path, f"packages/{member}/src/pkg/m{index}.py", f"VALUE = {index}\n"
            )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()

        def forbidden():
            raise AssertionError(
                "uv member reprojection must not materialize all repository rows"
            )

        monkeypatch.setattr(codemap.store, "all_file_rows", forbidden)
        _write(
            tmp_path,
            "pyproject.toml",
            """[project]\nname="root"\nversion="0"\n[tool.uv.workspace]\nmembers=["packages/a", "packages/b"]\n""",
        )
        result = codemap.sync(paths=["pyproject.toml"])
        row = codemap.store.file_row("packages/b/src/pkg/m10.py")
    assert result.discovered == 21
    assert row is not None and row["module_name"] == "pkg.m10"
