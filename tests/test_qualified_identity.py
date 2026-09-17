from pathlib import Path

from hashmarks.codemap import CodeMap
from hashmarks.qualified_identity import (
    qualified_import_identity,
    qualified_shared_input_identity,
)


def _write(root: Path, path: str, text: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _map(root: Path) -> CodeMap:
    state = root / ".hm-state"
    return CodeMap(root, state_dir=state, artifact_db=state / "artifacts.sqlite3")


def test_equivalent_relative_and_absolute_imports_share_qualified_identity(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/impl.py", "class Public: pass\n")
    _write(tmp_path, "pkg/use.py", "from .impl import Public\n")
    with _map(tmp_path) as codemap:
        codemap.sync()
        relative = qualified_import_identity(codemap, source_path="pkg/use.py", target=".impl.Public")
        absolute = qualified_import_identity(codemap, source_path="pkg/use.py", target="pkg.impl.Public")
    assert relative["status"] == absolute["status"] == "resolved"
    assert relative["owner_paths"] == absolute["owner_paths"] == ["pkg/impl.py"]
    assert relative["qualified_identity"] == absolute["qualified_identity"]


def test_reexport_alias_identity_is_stable_across_reopen(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import Internal as Public\n")
    _write(tmp_path, "pkg/impl.py", "class Internal: pass\n")
    _write(tmp_path, "tests/test_a.py", "from pkg import Public\n")
    with _map(tmp_path) as codemap:
        codemap.sync()
        first = qualified_import_identity(codemap, source_path="tests/test_a.py", target="pkg.Public")
    with _map(tmp_path) as codemap:
        second = qualified_import_identity(codemap, source_path="tests/test_a.py", target="pkg.Public")
    assert first == second
    assert first["qualified_identity"].startswith("sha256:")
    assert first["owner_paths"] == ["pkg/__init__.py", "pkg/impl.py"]


def test_ambiguous_reexport_has_no_qualified_identity(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .a import Public\nfrom .b import Public\n")
    _write(tmp_path, "pkg/a.py", "class Public: pass\n")
    _write(tmp_path, "pkg/b.py", "class Public: pass\n")
    _write(tmp_path, "tests/test_a.py", "from pkg import Public\n")
    with _map(tmp_path) as codemap:
        codemap.sync()
        result = qualified_import_identity(codemap, source_path="tests/test_a.py", target="pkg.Public")
    assert result["status"] == "ambiguous"
    assert result["qualified_identity"] is None


def _shared_repo(root: Path) -> None:
    (root / "backend").mkdir()
    (root / "frontend").mkdir()
    _write(root, "backend/package.json", '{"name":"backend"}')
    _write(root, "frontend/package.json", '{"name":"frontend"}')
    _write(root, "contract.json", '{"v":1}\n')
    _write(
        root,
        ".hashmarks-project-links.toml",
        "[[shared_input]]\npath='contract.json'\nprojects=['npm:backend','npm:frontend']\nkind='contract'\n",
    )


def test_cross_repository_shared_input_identity_binds_projects_and_content(tmp_path: Path) -> None:
    _shared_repo(tmp_path)
    with _map(tmp_path) as codemap:
        codemap.sync()
        codemap.enrich_projects(("npm-package-graph", "declared-project-links"))
        first = qualified_shared_input_identity(codemap, relpath="contract.json")
        second = qualified_shared_input_identity(codemap, relpath="contract.json")
    assert first == second
    assert first["status"] == "resolved"
    assert first["qualified_identity"].startswith("sha256:")
    assert [row["project_id"] for row in first["projects"]] == ["npm:backend", "npm:frontend"]


def test_shared_input_change_is_stale_until_authoritative_refresh_then_rebinds(tmp_path: Path) -> None:
    _shared_repo(tmp_path)
    with _map(tmp_path) as codemap:
        codemap.sync()
        codemap.enrich_projects(("npm-package-graph", "declared-project-links"))
        before = qualified_shared_input_identity(codemap, relpath="contract.json")
        _write(tmp_path, "contract.json", '{"v":2}\n')
        stale = qualified_shared_input_identity(codemap, relpath="contract.json")
        codemap.task_change_impact("contract changed", ["contract.json"])
        after = qualified_shared_input_identity(codemap, relpath="contract.json")
    assert stale["status"] == "stale"
    assert stale["qualified_identity"] is None
    assert after["status"] == "resolved"
    assert after["qualified_identity"] != before["qualified_identity"]
    assert after["content_sha256"] != before["content_sha256"]


def test_undeclared_shared_input_fails_closed(tmp_path: Path) -> None:
    _write(tmp_path, "contract.json", '{}\n')
    with _map(tmp_path) as codemap:
        codemap.sync()
        result = qualified_shared_input_identity(codemap, relpath="contract.json")
    assert result["status"] == "unresolved"
    assert result["qualified_identity"] is None


def test_deleted_import_owner_cannot_retain_false_unique_qualified_identity(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import Public\n")
    _write(tmp_path, "pkg/impl.py", "class Public: pass\n")
    _write(tmp_path, "tests/test_a.py", "from pkg import Public\n")
    with _map(tmp_path) as codemap:
        codemap.sync()
        before = qualified_import_identity(codemap, source_path="tests/test_a.py", target="pkg.Public")
        (tmp_path / "pkg/impl.py").unlink()
        after = qualified_import_identity(codemap, source_path="tests/test_a.py", target="pkg.Public")
    assert before["status"] == "resolved"
    assert before["qualified_identity"] is not None
    assert after["owner_paths"] != ["pkg/__init__.py", "pkg/impl.py"]
    assert after["qualified_identity"] is None


def test_qualified_import_identity_is_independent_of_consumer_path(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/impl.py", "class Public: pass\n")
    _write(tmp_path, "a/use.py", "from pkg.impl import Public\n")
    _write(tmp_path, "b/use.py", "from pkg.impl import Public\n")
    with _map(tmp_path) as codemap:
        codemap.sync()
        first = qualified_import_identity(
            codemap, source_path="a/use.py", target="pkg.impl.Public"
        )
        second = qualified_import_identity(
            codemap, source_path="b/use.py", target="pkg.impl.Public"
        )
    assert first["status"] == second["status"] == "resolved"
    assert first["owner_paths"] == second["owner_paths"] == ["pkg/impl.py"]
    assert first["qualified_identity"] == second["qualified_identity"]


def test_public_reexport_alias_identity_stays_distinct_from_internal_symbol(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import Internal as Public\n")
    _write(tmp_path, "pkg/impl.py", "class Internal: pass\n")
    _write(
        tmp_path,
        "tests/use.py",
        "from pkg import Public\nfrom pkg.impl import Internal\n",
    )
    with _map(tmp_path) as codemap:
        codemap.sync()
        public = qualified_import_identity(
            codemap, source_path="tests/use.py", target="pkg.Public"
        )
        internal = qualified_import_identity(
            codemap, source_path="tests/use.py", target="pkg.impl.Internal"
        )
    assert public["status"] == internal["status"] == "resolved"
    assert public["owner_paths"] == ["pkg/__init__.py", "pkg/impl.py"]
    assert internal["owner_paths"] == ["pkg/impl.py"]
    assert public["qualified_identity"] != internal["qualified_identity"]


def test_qualified_import_identity_cycle_fails_closed(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .a import Public\n")
    _write(tmp_path, "pkg/a.py", "from .b import Public\n")
    _write(tmp_path, "pkg/b.py", "from .a import Public\n")
    _write(tmp_path, "tests/use.py", "from pkg import Public\n")
    with _map(tmp_path) as codemap:
        codemap.sync()
        result = qualified_import_identity(
            codemap, source_path="tests/use.py", target="pkg.Public"
        )
    assert result["status"] == "ambiguous"
    assert result["qualified_identity"] is None


def test_qualified_import_identity_rebinds_unsynced_facade_retarget(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .a import Public\n")
    _write(tmp_path, "pkg/a.py", "class Public: pass\n")
    _write(tmp_path, "pkg/b.py", "class Public: pass\n")
    _write(tmp_path, "tests/use.py", "from pkg import Public\n")
    with _map(tmp_path) as codemap:
        codemap.sync()
        before = qualified_import_identity(
            codemap, source_path="tests/use.py", target="pkg.Public"
        )
        _write(tmp_path, "pkg/__init__.py", "from .b import Public\n")
        after = qualified_import_identity(
            codemap, source_path="tests/use.py", target="pkg.Public"
        )
    assert before["status"] == after["status"] == "resolved"
    assert before["owner_paths"] == ["pkg/__init__.py", "pkg/a.py"]
    assert after["owner_paths"] == ["pkg/__init__.py", "pkg/b.py"]
    assert before["qualified_identity"] != after["qualified_identity"]
