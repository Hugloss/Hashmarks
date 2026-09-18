from pathlib import Path

import pytest

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
        return codemap._resolve_import_owner_evidence(
            "tests/test_public.py", "pkg.Public"
        )


def test_later_reexport_overrides_earlier_local_definition(tmp_path: Path) -> None:
    owners, ambiguous = _owners(
        tmp_path, "def Public(): pass\nfrom .impl import Public\n"
    )
    assert owners == ["pkg/__init__.py", "pkg/impl.py"]
    assert ambiguous is False


def test_later_local_definition_overrides_earlier_reexport(tmp_path: Path) -> None:
    owners, ambiguous = _owners(
        tmp_path, "from .impl import Public\ndef Public(): pass\n"
    )
    assert owners == ["pkg/__init__.py"]
    assert ambiguous is False


def test_alias_reexport_after_local_definition_keeps_underlying_owner(
    tmp_path: Path,
) -> None:
    owners, ambiguous = _owners(
        tmp_path, "def Public(): pass\nfrom .impl import Internal as Public\n"
    )
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
        owners, ambiguous = codemap._resolve_import_owner_evidence(
            "tests/test_public.py", "pkg.Public"
        )
    assert owners == ["pkg/__init__.py"]
    assert ambiguous is True


def test_type_checking_import_is_not_promoted_to_runtime_reexport_owner(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "pkg/__init__.py",
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from .impl import Public\n",
    )
    _write(tmp_path, "pkg/impl.py", "def Public(): pass\n")
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence(
            "tests/test_public.py", "pkg.Public"
        )
    assert owners == ["pkg/__init__.py"]
    assert ambiguous is True


def test_star_reexport_respects_static_all_exclusion(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import *\n")
    _write(tmp_path, "pkg/impl.py", "__all__ = []\ndef Public(): pass\n")
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence(
            "tests/test_public.py", "pkg.Public"
        )
    assert owners == ["pkg/__init__.py"]
    assert ambiguous is True


def test_star_reexport_respects_static_all_inclusion(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import *\n")
    _write(tmp_path, "pkg/impl.py", "__all__ = ['Public']\ndef Public(): pass\n")
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence(
            "tests/test_public.py", "pkg.Public"
        )
    assert owners == ["pkg/__init__.py", "pkg/impl.py"]
    assert ambiguous is False


def test_star_reexport_dynamic_all_fails_closed(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import *\n")
    _write(tmp_path, "pkg/impl.py", "__all__ = make_exports()\ndef Public(): pass\n")
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence(
            "tests/test_public.py", "pkg.Public"
        )
    assert owners == ["pkg/__init__.py"]
    assert ambiguous is True


def test_star_reexport_static_augmented_all_includes_name(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import *\n")
    _write(
        tmp_path,
        "pkg/impl.py",
        "__all__ = []\n__all__ += ['Public']\ndef Public(): pass\n",
    )
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence(
            "tests/test_public.py", "pkg.Public"
        )
    assert owners == ["pkg/__init__.py", "pkg/impl.py"]
    assert ambiguous is False


def test_star_reexport_static_append_all_includes_name(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import *\n")
    _write(
        tmp_path,
        "pkg/impl.py",
        "__all__ = []\n__all__.append('Public')\ndef Public(): pass\n",
    )
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence(
            "tests/test_public.py", "pkg.Public"
        )
    assert owners == ["pkg/__init__.py", "pkg/impl.py"]
    assert ambiguous is False


def test_star_reexport_dynamic_augmented_all_fails_closed(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import *\n")
    _write(
        tmp_path,
        "pkg/impl.py",
        "__all__ = ['Public']\n__all__ += dynamic_names\ndef Public(): pass\n",
    )
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence(
            "tests/test_public.py", "pkg.Public"
        )
    assert owners == ["pkg/__init__.py"]
    assert ambiguous is True


def test_star_reexport_dynamic_append_all_fails_closed(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import *\n")
    _write(
        tmp_path,
        "pkg/impl.py",
        "__all__ = ['Public']\n__all__.append(dynamic_name)\ndef Public(): pass\n",
    )
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence(
            "tests/test_public.py", "pkg.Public"
        )
    assert owners == ["pkg/__init__.py"]
    assert ambiguous is True


def test_star_reexport_static_extend_all_includes_name(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import *\n")
    _write(
        tmp_path,
        "pkg/impl.py",
        "__all__ = []\n__all__.extend(['Public'])\ndef Public(): pass\n",
    )
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence(
            "tests/test_public.py", "pkg.Public"
        )
    assert owners == ["pkg/__init__.py", "pkg/impl.py"]
    assert ambiguous is False


def test_star_reexport_dynamic_extend_all_fails_closed(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import *\n")
    _write(
        tmp_path,
        "pkg/impl.py",
        "__all__ = ['Public']\n__all__.extend(dynamic_names)\ndef Public(): pass\n",
    )
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence(
            "tests/test_public.py", "pkg.Public"
        )
    assert owners == ["pkg/__init__.py"]
    assert ambiguous is True


def test_private_name_never_acquires_star_export_authority(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import *\n")
    _write(tmp_path, "pkg/impl.py", "__all__ = ['_Private']\ndef _Private(): pass\n")
    _write(tmp_path, "tests/test_public.py", "from pkg import _Private\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence(
            "tests/test_public.py", "pkg._Private"
        )
    assert owners == ["pkg/__init__.py"]
    assert ambiguous is True


def test_chained_star_facade_keeps_leaf_owner_when_each_export_is_proven(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .facade import *\n")
    _write(tmp_path, "pkg/facade.py", "__all__ = ['Public']\nfrom .impl import *\n")
    _write(tmp_path, "pkg/impl.py", "__all__ = ['Public']\ndef Public(): pass\n")
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence(
            "tests/test_public.py", "pkg.Public"
        )
    assert owners == ["pkg/__init__.py", "pkg/impl.py"]
    assert ambiguous is False


def test_chained_star_facade_fails_closed_when_inner_all_is_dynamic(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .facade import *\n")
    _write(tmp_path, "pkg/facade.py", "__all__ = ['Public']\nfrom .impl import *\n")
    _write(
        tmp_path,
        "pkg/impl.py",
        "__all__ = ['Public']\n__all__ += dynamic_names\ndef Public(): pass\n",
    )
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence(
            "tests/test_public.py", "pkg.Public"
        )
    assert owners == ["pkg/__init__.py"]
    assert ambiguous is True


def test_mixed_direct_and_star_reexports_do_not_invent_unique_owner(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path, "pkg/__init__.py", "from .direct import Public\nfrom .star import *\n"
    )
    _write(tmp_path, "pkg/direct.py", "def Public(): pass\n")
    _write(tmp_path, "pkg/star.py", "__all__ = ['Public']\ndef Public(): pass\n")
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        owners, ambiguous = codemap._resolve_import_owner_evidence(
            "tests/test_public.py", "pkg.Public"
        )
    # Multiple independently plausible re-export statements remain unresolved;
    # most importantly, Hashmarks must not manufacture a unique leaf owner.
    assert owners == ["pkg/__init__.py"]
    assert ambiguous is True


@pytest.mark.parametrize(
    ("declaration", "authority"),
    [
        pytest.param("", True, id="implicit-symbol"),
        pytest.param("__all__: list[str]", True, id="annotation-without-value"),
        pytest.param("__all__: list[str] = ['Public']", True, id="annotated-value"),
        pytest.param("other = __all__ = ['Public']", True, id="chained-assignment"),
        pytest.param("__all__ = ('Public',)", True, id="tuple"),
        pytest.param("__all__ = {'Public'}", True, id="set"),
        pytest.param("__all__ = []", False, id="empty-excludes-symbol"),
        pytest.param("__all__ = ['Other']", False, id="other-name-excludes-symbol"),
        pytest.param("__all__ = ['Public', 1]", None, id="mixed-literal"),
        pytest.param("__all__ = ['Public', *names]", None, id="unpacked-value"),
        pytest.param("__all__ = ['Public']\n__all__ = []", False, id="replacement"),
        pytest.param("__all__ = []\n__all__ = ['Public']", True, id="later-inclusion"),
        pytest.param(
            "__all__ = dynamic\n__all__ = ['Public']", None, id="unknown-is-terminal"
        ),
        pytest.param(
            "__all__ = ['Public']\ndel __all__\n__all__ = ['Public']",
            None,
            id="deletion-is-terminal",
        ),
        pytest.param("__all__ += ['Public']", None, id="augment-without-base"),
        pytest.param("__all__ = ['Public']\n__all__ *= 1", None, id="non-add-augment"),
        pytest.param("__all__.append('Public')", None, id="append-without-base"),
        pytest.param("__all__.extend(['Public'])", None, id="extend-without-base"),
        pytest.param("__all__ = []\n__all__.append()", None, id="append-no-argument"),
        pytest.param(
            "__all__ = []\n__all__.append(name='Public')", None, id="append-keyword"
        ),
        pytest.param("__all__ = []\n__all__.append(1)", None, id="append-non-string"),
        pytest.param("__all__ = []\n__all__.extend()", None, id="extend-no-argument"),
        pytest.param(
            "__all__ = []\n__all__.extend(['Public'], ['Other'])",
            None,
            id="extend-extra-argument",
        ),
        pytest.param(
            "__all__ = []\n__all__.extend(names=['Public'])", None, id="extend-keyword"
        ),
        pytest.param(
            "__all__ = []\n__all__.extend('Public')", None, id="extend-scalar-string"
        ),
        pytest.param(
            "__all__ = []\n__all__.append('Other')\n__all__.extend(('Public',))",
            True,
            id="ordered-static-mutations",
        ),
    ],
)
def test_star_export_declaration_authority(
    tmp_path: Path, declaration: str, authority: bool | None
) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import *\n")
    _write(tmp_path, "pkg/impl.py", f"{declaration}\ndef Public(): pass\n")
    _write(tmp_path, "tests/test_public.py", "from pkg import Public\n")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        assert (
            codemap._python_star_export_authority(
                "pkg/__init__.py", ".impl.Public", "Public"
            )
            is authority
        )
        owners, unresolved = codemap._resolve_import_owner_evidence(
            "tests/test_public.py", "pkg.Public"
        )

    expected_owners = ["pkg/__init__.py"]
    if authority is True:
        expected_owners.append("pkg/impl.py")
    assert owners == expected_owners
    assert unresolved is (authority is not True)
