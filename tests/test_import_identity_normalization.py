from __future__ import annotations

from pathlib import Path

from hashmarks.codemap import CodeMap


def _write(root: Path, path: str, text: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)


def _codemap(root: Path) -> CodeMap:
    state = root / ".hm-state"
    return CodeMap(root, state_dir=state, artifact_db=state / "artifacts.sqlite3")


def test_aliased_package_init_reexport_resolves_underlying_owner(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import Internal as Public\n")
    _write(tmp_path, "pkg/impl.py", "class Internal: pass\n")
    _write(tmp_path, "tests/test_a.py", "from pkg import Public\n")

    with _codemap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence(
            "tests/test_a.py", "pkg.Public"
        )

    assert owners == ["pkg/__init__.py", "pkg/impl.py"]
    assert ambiguous is False


def test_chained_reexport_resolves_leaf_owner(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .api import Public\n")
    _write(tmp_path, "pkg/api.py", "from .impl import Internal as Public\n")
    _write(tmp_path, "pkg/impl.py", "class Internal: pass\n")
    _write(tmp_path, "tests/test_a.py", "from pkg import Public\n")

    with _codemap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence(
            "tests/test_a.py", "pkg.Public"
        )

    assert owners == ["pkg/__init__.py", "pkg/impl.py"]
    assert ambiguous is False


def test_namespace_package_import_keeps_exact_module_identity(tmp_path: Path) -> None:
    _write(tmp_path, "ns/pkg/impl.py", "class Public: pass\n")
    _write(tmp_path, "tests/test_a.py", "from ns.pkg.impl import Public\n")

    with _codemap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence(
            "tests/test_a.py", "ns.pkg.impl.Public"
        )

    assert owners == ["ns/pkg/impl.py"]
    assert ambiguous is False


def test_relative_and_absolute_import_forms_resolve_identically(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/impl.py", "class Public: pass\n")
    _write(tmp_path, "pkg/use.py", "from .impl import Public\n")

    with _codemap(tmp_path) as codemap:
        codemap.sync()
        relative = codemap._resolve_import_paths("pkg/use.py", ".impl.Public")
        absolute = codemap._resolve_import_paths("pkg/use.py", "pkg.impl.Public")

    assert relative == ["pkg/impl.py"]
    assert absolute == relative


def test_multiple_reexport_leaves_fail_closed(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "pkg/__init__.py",
        "from .a import Public\nfrom .b import Public\n",
    )
    _write(tmp_path, "pkg/a.py", "class Public: pass\n")
    _write(tmp_path, "pkg/b.py", "class Public: pass\n")
    _write(tmp_path, "tests/test_a.py", "from pkg import Public\n")

    with _codemap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence(
            "tests/test_a.py", "pkg.Public"
        )

    assert "pkg/__init__.py" in owners
    assert ambiguous is True
