"""Public regressions for binding invalidation and bidirectional alias evidence."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from hashmarks import CodeMap

if TYPE_CHECKING:
    from pathlib import Path


def _write(root: Path, name: str, text: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.mark.parametrize(
    "tail",
    [
        "load_config = None\n",
        "load_config, other = (None, None)\n",
        "[other, *load_config] = values\n",
        "load_config += 1\n",
        "import external_library as load_config\n",
        "del load_config\n",
        "if flag:\n    load_config = None\n",
        "for load_config in values:\n    pass\n",
        "with resource as load_config:\n    pass\n",
        "try:\n    pass\nexcept Exception as load_config:\n    pass\n",
        "match value:\n    case {'value': load_config}:\n        pass\n",
        "(load_config := None)\n",
        "match value:\n    case {**load_config}:\n        pass\n",
        "def unrelated(value=(load_config := None)):\n    pass\n",
        "factory = lambda value=(load_config := None): value\n",
    ],
)
def test_shadowed_export_never_becomes_an_exact_alias_call(
    tmp_path: Path, tail: str
) -> None:
    root = tmp_path / "repo"
    _write(root, "config.py", "def load_config():\n    return 1\n" + tail)
    _write(
        root,
        "service.py",
        "from config import load_config as read_config\ndef handle():\n    return read_config()\n",
    )
    with CodeMap(root, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        packet: Any = codemap.structural_locality("service.py::handle")
    assert all(row["resolved_symbol_id"] is None for row in packet["edges"])
    assert {row["symbol_id"] for row in packet["nodes"]} == {"service.py::handle"}


@pytest.mark.parametrize(
    "tail",
    [
        "load_config: object\n",
        "values = [load_config for load_config in items]\n",
        "def unrelated():\n    load_config = None\n",
        "load_config = None\ndef load_config():\n    return 2\n",
    ],
)
def test_current_unconditional_declaration_retains_alias_evidence(
    tmp_path: Path, tail: str
) -> None:
    root = tmp_path / "repo"
    _write(root, "config.py", "def load_config():\n    return 1\n" + tail)
    _write(
        root,
        "service.py",
        "from config import load_config as read_config\ndef handle():\n    return read_config()\n",
    )
    with CodeMap(root, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        packet: Any = codemap.structural_locality("service.py::handle")
    assert {row["resolved_symbol_id"] for row in packet["edges"]} == {
        "config.py::load_config"
    }


def test_reverse_aliases_and_relative_reexports_find_real_callers_and_tests(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    _write(root, "pkg/impl.py", "def original():\n    return 1\n")
    _write(root, "pkg/__init__.py", "from .impl import original as renamed\n")
    _write(root, "pkg/facade.py", "from . import renamed as public\n")
    _write(
        root,
        "consumer.py",
        "from pkg.facade import public as invoke\ndef use():\n    return invoke()\n",
    )
    _write(
        root,
        "tests/test_impl.py",
        "from pkg import renamed as exercise\ndef test_original():\n    assert exercise() == 1\n",
    )
    _write(
        root,
        "unrelated.py",
        "def original():\n    return 0\ndef use():\n    return original()\n",
    )
    with CodeMap(root, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        target: Any = codemap.structural_locality("pkg/impl.py::original")
        outgoing: Any = codemap.structural_locality("consumer.py::use")
    node = next(
        row for row in target["nodes"] if row["symbol_id"] == "pkg/impl.py::original"
    )
    assert {row["path"] for row in node["exact_callers"]} == {
        "consumer.py",
        "tests/test_impl.py",
    }
    assert node["caller_reference_bound_complete"] is True
    assert "tests/test_impl.py" in target["verification_paths"]
    assert {row["resolved_symbol_id"] for row in outgoing["edges"]} == {
        "pkg/impl.py::original"
    }


def test_reverse_alias_budget_never_reports_complete_prefix(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(root, "impl.py", "def original():\n    return 1\n")
    for n in range(5):
        _write(
            root,
            f"consumer{n}.py",
            "from impl import original as renamed\ndef use():\n    return renamed()\n",
        )
    with CodeMap(root, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        bounded: Any = codemap.structural_locality(
            "impl.py::original", ref_limit_per_symbol=2
        )
        complete: Any = codemap.structural_locality(
            "impl.py::original", ref_limit_per_symbol=64
        )
    assert bounded["nodes"][0]["caller_reference_bound_complete"] is False
    assert len(complete["nodes"][0]["exact_callers"]) == 5
    assert complete["nodes"][0]["caller_reference_bound_complete"] is True


def test_rebound_class_does_not_keep_exact_method_identity(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(
        root,
        "service.py",
        "class Handler:\n    @staticmethod\n    def handle():\n        return 1\nHandler, other = (None, None)\ndef use():\n    return Handler.handle()\n",
    )
    with CodeMap(root, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        packet: Any = codemap.structural_locality("service.py::use")
    assert all(row["resolved_symbol_id"] is None for row in packet["edges"])


def test_reverse_aliases_preserve_hidden_and_ambiguous_callers_as_unproven(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    _write(root, "impl.py", "def original():\n    return 1\n")
    _write(root, "other.py", "def original():\n    return 2\n")
    _write(
        root,
        "hidden.py",
        "from impl import original as renamed\ndef use():\n    return renamed()\n",
    )
    _write(
        root,
        "ambiguous.py",
        "from impl import original as renamed\nfrom other import original as renamed\ndef use():\n    return renamed()\n",
    )
    _write(
        root,
        ".hashmarks-context.toml",
        '[[rule]]\npattern = "hidden.py"\nvisibility = "outline"\n',
    )
    with CodeMap(root, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        packet: Any = codemap.structural_locality("impl.py::original")
    assert packet["nodes"][0]["exact_callers"] == []
    assert packet["nodes"][0]["caller_reference_bound_complete"] is False


@pytest.mark.parametrize("hops", [8, 9])
def test_reverse_reexport_hop_boundary_preserves_coverage(
    tmp_path: Path, hops: int
) -> None:
    root = tmp_path / "repo"
    _write(root, "impl.py", "def original():\n    return 1\n")
    module, name = "impl", "original"
    for n in range(hops):
        _write(root, f"facade{n}.py", f"from {module} import {name} as alias{n}\n")
        module, name = f"facade{n}", f"alias{n}"
    _write(
        root,
        "consumer.py",
        f"from {module} import {name}\ndef use():\n    return {name}()\n",
    )
    with CodeMap(root, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        packet: Any = codemap.structural_locality("impl.py::original")
    node = packet["nodes"][0]
    if hops == 8:
        assert {row["path"] for row in node["exact_callers"]} == {"consumer.py"}
    else:
        assert node["exact_callers"] == []
    assert node["caller_reference_bound_complete"] is (hops == 8)
