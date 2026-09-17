from pathlib import Path
from hashmarks.codemap import CodeMap


def _write(root: Path, path: str, text: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)


def _owners(tmp_path: Path, facade: str):
    _write(tmp_path, "pkg/__init__.py", facade)
    _write(tmp_path, "pkg/impl.py", "def Public(): pass\n")
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        return codemap._resolve_import_owner_evidence("tests/test_public.py", "pkg.Public")


def test_later_reexport_overrides_earlier_local_definition(tmp_path: Path) -> None:
    owners, ambiguous = _owners(tmp_path, "def Public(): pass\nfrom .impl import Public\n")
    assert owners == ["pkg/__init__.py", "pkg/impl.py"]
    assert ambiguous is False


def test_later_local_definition_overrides_earlier_reexport(tmp_path: Path) -> None:
    owners, ambiguous = _owners(tmp_path, "from .impl import Public\ndef Public(): pass\n")
    assert owners == ["pkg/__init__.py"]
    assert ambiguous is False


def test_alias_reexport_after_local_definition_keeps_underlying_owner(tmp_path: Path) -> None:
    owners, ambiguous = _owners(tmp_path, "def Public(): pass\nfrom .impl import Internal as Public\n")
    # The imported name need not match the exposed name; resolution remains fail-closed
    # if the underlying symbol does not exist.
    assert owners == ["pkg/__init__.py"]
    assert ambiguous is True


def test_nested_scope_import_is_not_promoted_to_reexport_owner(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "def setup():\n    from .impl import Public\n")
    _write(tmp_path, "pkg/impl.py", "def Public(): pass\n")
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence("tests/test_public.py", "pkg.Public")
    assert owners == ["pkg/__init__.py"]
    assert ambiguous is True


def test_type_checking_import_is_not_promoted_to_runtime_reexport_owner(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from .impl import Public\n")
    _write(tmp_path, "pkg/impl.py", "def Public(): pass\n")
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence("tests/test_public.py", "pkg.Public")
    assert owners == ["pkg/__init__.py"]
    assert ambiguous is True


def test_star_reexport_respects_static_all_exclusion(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import *\n")
    _write(tmp_path, "pkg/impl.py", "__all__ = []\ndef Public(): pass\n")
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence("tests/test_public.py", "pkg.Public")
    assert owners == ["pkg/__init__.py"]
    assert ambiguous is True


def test_star_reexport_respects_static_all_inclusion(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import *\n")
    _write(tmp_path, "pkg/impl.py", "__all__ = ['Public']\ndef Public(): pass\n")
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence("tests/test_public.py", "pkg.Public")
    assert owners == ["pkg/__init__.py", "pkg/impl.py"]
    assert ambiguous is False


def test_star_reexport_dynamic_all_fails_closed(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import *\n")
    _write(tmp_path, "pkg/impl.py", "__all__ = make_exports()\ndef Public(): pass\n")
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence("tests/test_public.py", "pkg.Public")
    assert owners == ["pkg/__init__.py"]
    assert ambiguous is True


def test_star_reexport_static_augmented_all_includes_name(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import *\n")
    _write(tmp_path, "pkg/impl.py", "__all__ = []\n__all__ += ['Public']\ndef Public(): pass\n")
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence("tests/test_public.py", "pkg.Public")
    assert owners == ["pkg/__init__.py", "pkg/impl.py"]
    assert ambiguous is False


def test_star_reexport_static_append_all_includes_name(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import *\n")
    _write(tmp_path, "pkg/impl.py", "__all__ = []\n__all__.append('Public')\ndef Public(): pass\n")
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence("tests/test_public.py", "pkg.Public")
    assert owners == ["pkg/__init__.py", "pkg/impl.py"]
    assert ambiguous is False


def test_star_reexport_dynamic_augmented_all_fails_closed(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import *\n")
    _write(tmp_path, "pkg/impl.py", "__all__ = ['Public']\n__all__ += dynamic_names\ndef Public(): pass\n")
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence("tests/test_public.py", "pkg.Public")
    assert owners == ["pkg/__init__.py"]
    assert ambiguous is True


def test_star_reexport_dynamic_append_all_fails_closed(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import *\n")
    _write(tmp_path, "pkg/impl.py", "__all__ = ['Public']\n__all__.append(dynamic_name)\ndef Public(): pass\n")
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence("tests/test_public.py", "pkg.Public")
    assert owners == ["pkg/__init__.py"]
    assert ambiguous is True


def test_star_reexport_static_extend_all_includes_name(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import *\n")
    _write(tmp_path, "pkg/impl.py", "__all__ = []\n__all__.extend(['Public'])\ndef Public(): pass\n")
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence("tests/test_public.py", "pkg.Public")
    assert owners == ["pkg/__init__.py", "pkg/impl.py"]
    assert ambiguous is False


def test_star_reexport_dynamic_extend_all_fails_closed(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import *\n")
    _write(tmp_path, "pkg/impl.py", "__all__ = ['Public']\n__all__.extend(dynamic_names)\ndef Public(): pass\n")
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence("tests/test_public.py", "pkg.Public")
    assert owners == ["pkg/__init__.py"]
    assert ambiguous is True


def test_private_name_never_acquires_star_export_authority(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import *\n")
    _write(tmp_path, "pkg/impl.py", "__all__ = ['_Private']\ndef _Private(): pass\n")
    _write(tmp_path, "tests/test_public.py", "from pkg import _Private\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence("tests/test_public.py", "pkg._Private")
    assert owners == ["pkg/__init__.py"]
    assert ambiguous is True


def test_chained_star_facade_keeps_leaf_owner_when_each_export_is_proven(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .facade import *\n")
    _write(tmp_path, "pkg/facade.py", "__all__ = ['Public']\nfrom .impl import *\n")
    _write(tmp_path, "pkg/impl.py", "__all__ = ['Public']\ndef Public(): pass\n")
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence("tests/test_public.py", "pkg.Public")
    assert owners == ["pkg/__init__.py", "pkg/impl.py"]
    assert ambiguous is False


def test_chained_star_facade_fails_closed_when_inner_all_is_dynamic(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .facade import *\n")
    _write(tmp_path, "pkg/facade.py", "__all__ = ['Public']\nfrom .impl import *\n")
    _write(tmp_path, "pkg/impl.py", "__all__ = ['Public']\n__all__ += dynamic_names\ndef Public(): pass\n")
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence("tests/test_public.py", "pkg.Public")
    assert owners == ["pkg/__init__.py"]
    assert ambiguous is True


def test_mixed_direct_and_star_reexports_do_not_invent_unique_owner(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .direct import Public\nfrom .star import *\n")
    _write(tmp_path, "pkg/direct.py", "def Public(): pass\n")
    _write(tmp_path, "pkg/star.py", "__all__ = ['Public']\ndef Public(): pass\n")
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence("tests/test_public.py", "pkg.Public")
    # Multiple independently plausible re-export statements remain unresolved;
    # most importantly, Hashmarks must not manufacture a unique leaf owner.
    assert owners == ["pkg/__init__.py"]
    assert ambiguous is True
