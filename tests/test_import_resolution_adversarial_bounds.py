from pathlib import Path

from hashmarks.codemap import CodeMap


def _write(root: Path, path: str, text: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)


def _owners(root: Path, target: str = "pkg.Public") -> tuple[list[str], bool]:
    _write(
        root, "tests/test_public.py", f"from pkg import {target.rsplit('.', 1)[-1]}\n"
    )
    with CodeMap(root) as codemap:
        codemap.sync()
        return codemap._resolve_import_owner_evidence("tests/test_public.py", target)


def test_reexport_cycle_remains_unresolved(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .facade import Public\n")
    _write(tmp_path, "pkg/facade.py", "from . import Public\n")

    owners, ambiguous = _owners(tmp_path)

    assert owners == ["pkg/__init__.py"]
    assert ambiguous is True


def test_reexport_walk_fails_closed_beyond_eight_hops(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .facade0 import Public\n")
    for index in range(9):
        next_module = f"facade{index + 1}" if index < 8 else "impl"
        _write(
            tmp_path,
            f"pkg/facade{index}.py",
            f"from .{next_module} import Public\n",
        )
    _write(tmp_path, "pkg/impl.py", "def Public(): pass\n")

    owners, ambiguous = _owners(tmp_path)

    assert owners == ["pkg/__init__.py"]
    assert ambiguous is True


def test_deleted_static_all_remains_unknown(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import *\n")
    _write(
        tmp_path,
        "pkg/impl.py",
        "__all__ = ['Public']\ndel __all__\ndef Public(): pass\n",
    )

    owners, ambiguous = _owners(tmp_path)

    assert owners == ["pkg/__init__.py"]
    assert ambiguous is True


def test_invalid_static_all_append_form_remains_unknown(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import *\n")
    _write(
        tmp_path,
        "pkg/impl.py",
        "__all__ = []\n__all__.append('Public', 'Other')\ndef Public(): pass\n",
    )

    owners, ambiguous = _owners(tmp_path)

    assert owners == ["pkg/__init__.py"]
    assert ambiguous is True
