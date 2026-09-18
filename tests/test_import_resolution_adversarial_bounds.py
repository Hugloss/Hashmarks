from pathlib import Path

import pytest

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


def test_two_module_reexport_cycle_keeps_only_the_facade(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .first import Public\n")
    _write(tmp_path, "pkg/first.py", "from .second import Public\n")
    _write(tmp_path, "pkg/second.py", "from .first import Public\n")

    owners, unresolved = _owners(tmp_path)

    assert owners == ["pkg/__init__.py"]
    assert unresolved is True


def test_relative_import_above_repository_root_has_no_owner(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/use.py", "from ...impl import Public\n")
    _write(tmp_path, "pkg/impl.py", "class Public: pass\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners = codemap._resolve_import_paths("pkg/use.py", "...impl.Public")

    assert owners == []


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


@pytest.mark.parametrize("hops", [8, 9])
def test_reexport_hop_boundary(tmp_path: Path, hops: int) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .facade0 import Public\n")
    for index in range(hops - 1):
        target = f"facade{index + 1}" if index < hops - 2 else "impl"
        _write(tmp_path, f"pkg/facade{index}.py", f"from .{target} import Public\n")
    _write(tmp_path, "pkg/impl.py", "class Public: pass\n")

    owners, unresolved = _owners(tmp_path)

    assert owners == (
        ["pkg/__init__.py", "pkg/impl.py"] if hops == 8 else ["pkg/__init__.py"]
    )
    assert unresolved is (hops > 8)


@pytest.mark.parametrize(
    ("source", "binding"),
    [
        ("class Public: pass", ("local", [])),
        ("async def Public(): pass", ("local", [])),
        ("Public = 1", ("local", [])),
        ("other = Public = 1", ("local", [])),
        ("Public: int", ("local", [])),
        ("Public, other = pair", ("unknown", [])),
        ("obj.Public = 1", ("unknown", [])),
        ("from .impl import Internal as Public", ("reexport", [".impl.Internal"])),
        ("from .impl import Public as Other", ("unknown", [])),
        ("from .impl import *", ("star", [".impl.Public"])),
        (
            "from .impl import Public\nfrom .impl import Public",
            ("ambiguous", [".impl.Public"]),
        ),
        (
            "from .a import Public\nPublic = 1\nfrom .b import Public",
            ("ambiguous", [".a.Public", ".b.Public"]),
        ),
        ("if True:\n    from .impl import Public", ("unknown", [])),
    ],
)
def test_top_level_export_binding_authority(
    tmp_path: Path, source: str, binding: tuple[str, list[str]]
) -> None:
    _write(tmp_path, "pkg/__init__.py", source + "\n")
    with CodeMap(tmp_path) as codemap:
        assert codemap._python_export_binding("pkg/__init__.py", "Public") == binding


def test_reexport_target_bound_preserves_order_and_deduplicates(tmp_path: Path) -> None:
    statements = ["from .first import Internal as Public"] * 2
    statements.extend(f"from .module{index} import Public" for index in range(18))
    _write(tmp_path, "pkg/__init__.py", "\n".join(statements))
    with CodeMap(tmp_path) as codemap:
        targets = codemap._python_reexport_targets("pkg/__init__.py", "Public")
    assert targets == [".first.Internal"] + [
        f".module{index}.Public" for index in range(15)
    ]
