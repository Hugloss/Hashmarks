from __future__ import annotations

from typing import TYPE_CHECKING

from hashmarks import CodeMap

if TYPE_CHECKING:
    from pathlib import Path


def test_python_module_identity_requires_package_chain(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "owner.py").write_text("cache = {}\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        assert codemap._python_module_for_path("pkg/owner.py") is None
        (package / "__init__.py").write_text("", encoding="utf-8")
        assert codemap._python_module_for_path("pkg/owner.py") == "pkg.owner"
        assert codemap._python_module_for_path("pkg/__init__.py") == "pkg"
        assert codemap._python_module_for_path("pkg/readme.txt") is None


def test_cache_reader_requires_qualified_import_identity(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "owner.py").write_text("cache = {}\n", encoding="utf-8")
    (tmp_path / "from_reader.py").write_text(
        "from pkg.owner import cache\n", encoding="utf-8"
    )
    (tmp_path / "module_reader.py").write_text("import pkg.owner\n", encoding="utf-8")
    (tmp_path / "unrelated.py").write_text(
        "from other.owner import cache\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        assert codemap._reader_imports_cache_owner(
            "from_reader.py", "pkg/owner.py", "cache"
        )
        assert codemap._reader_imports_cache_owner(
            "module_reader.py", "pkg/owner.py", "cache"
        )
        assert not codemap._reader_imports_cache_owner(
            "unrelated.py", "pkg/owner.py", "cache"
        )
