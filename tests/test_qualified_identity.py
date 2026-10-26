from pathlib import Path

import pytest
from contract_assertions import assert_records, assert_text

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


def test_equivalent_relative_and_absolute_imports_share_qualified_identity(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/impl.py", "class Public: pass\n")
    _write(tmp_path, "pkg/use.py", "from .impl import Public\n")
    with _map(tmp_path) as codemap:
        codemap.index.sync()
        relative = qualified_import_identity(
            codemap._imports, source_path="pkg/use.py", target=".impl.Public"
        )
        absolute = qualified_import_identity(
            codemap._imports, source_path="pkg/use.py", target="pkg.impl.Public"
        )
    assert relative["status"] == absolute["status"] == "resolved"
    assert relative["owner_paths"] == absolute["owner_paths"] == ["pkg/impl.py"]
    assert relative["qualified_identity"] == absolute["qualified_identity"]


def test_reexport_alias_identity_is_stable_across_reopen(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import Internal as Public\n")
    _write(tmp_path, "pkg/impl.py", "class Internal: pass\n")
    _write(tmp_path, "tests/test_a.py", "from pkg import Public\n")
    with _map(tmp_path) as codemap:
        codemap.index.sync()
        first = qualified_import_identity(
            codemap._imports, source_path="tests/test_a.py", target="pkg.Public"
        )
    with _map(tmp_path) as codemap:
        second = qualified_import_identity(
            codemap._imports, source_path="tests/test_a.py", target="pkg.Public"
        )
    assert first == second
    assert assert_text(first["qualified_identity"]).startswith("sha256:")
    assert first["owner_paths"] == ["pkg/__init__.py", "pkg/impl.py"]


def test_ambiguous_reexport_has_no_qualified_identity(tmp_path: Path) -> None:
    _write(
        tmp_path, "pkg/__init__.py", "from .a import Public\nfrom .b import Public\n"
    )
    _write(tmp_path, "pkg/a.py", "class Public: pass\n")
    _write(tmp_path, "pkg/b.py", "class Public: pass\n")
    _write(tmp_path, "tests/test_a.py", "from pkg import Public\n")
    with _map(tmp_path) as codemap:
        codemap.index.sync()
        result = qualified_import_identity(
            codemap._imports, source_path="tests/test_a.py", target="pkg.Public"
        )
    assert result["status"] == "ambiguous"
    assert result["qualified_identity"] is None


def test_executed_class_global_write_invalidates_reexport_identity(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pkg/impl.py", "def parse_pointer(value): return value\n")
    _write(tmp_path, "pkg/replacement.py", "def parse_pointer(value): return value\n")
    _write(
        tmp_path,
        "pkg/__init__.py",
        "from .impl import parse_pointer\n"
        "from .replacement import parse_pointer as replacement\nclass Rebind:\n"
        "    global parse_pointer\n    parse_pointer = replacement\n",
    )
    _write(tmp_path, "consumer.py", "from pkg import parse_pointer\n")
    with _map(tmp_path) as codemap:
        codemap.index.sync()
        result = qualified_import_identity(
            codemap._imports, source_path="consumer.py", target="pkg.parse_pointer"
        )
    assert result["status"] == "ambiguous"
    assert result["qualified_identity"] is None
    assert result["owner_paths"] == ["pkg/__init__.py"]


@pytest.mark.parametrize(
    ("facade_tail", "caller", "owner", "exact_call"),
    [
        pytest.param(
            "", "def invoke(): return selected()\n", "impl.py", True, id="alias"
        ),
        pytest.param(
            "exposed: object\n",
            "def invoke(): return selected()\n",
            "impl.py",
            True,
            id="module-annotation-target",
        ),
        pytest.param(
            "if True:\n    exposed: object\n",
            "def invoke(): return selected()\n",
            "impl.py",
            True,
            id="nested-annotation-target",
        ),
        pytest.param(
            "annotation: (exposed := replacement)\n",
            "def invoke(): return selected()\n",
            None,
            False,
            id="possible-annotation-effect",
        ),
        pytest.param(
            "ignored = False and (exposed := replacement)\n",
            "def invoke(): return selected()\n",
            None,
            False,
            id="conditional-expression-effect",
        ),
        pytest.param(
            "ignored = [(exposed := replacement) for item in ()]\n",
            "def invoke(): return selected()\n",
            None,
            False,
            id="comprehension-expression-effect",
        ),
        pytest.param(
            "deferred = lambda: (exposed := replacement)\n",
            "def invoke(): return selected()\n",
            "impl.py",
            True,
            id="deferred-lambda-effect",
        ),
        pytest.param(
            "deferred = lambda value=(exposed := replacement): value\n",
            "def invoke(): return selected()\n",
            None,
            False,
            id="lambda-default-expression-effect",
        ),
        pytest.param(
            "exposed = replacement\n",
            "def invoke(): return selected()\n",
            "facade.py",
            False,
            id="direct-assignment",
        ),
        pytest.param(
            "try:\n    raise ValueError()\nexcept ValueError as exposed:\n    pass\n",
            "def invoke(): return selected()\n",
            None,
            False,
            id="module-exception-target",
        ),
        pytest.param(
            "",
            "def invoke(selected): return selected()\n",
            "impl.py",
            False,
            id="parameter-shadows-call-only",
        ),
        pytest.param(
            "",
            "def invoke():\n    selected: object\n    return selected()\n",
            "impl.py",
            False,
            id="function-annotation-target-is-local",
        ),
        pytest.param(
            "",
            "def invoke():\n    try:\n        raise ValueError()\n"
            "    except ValueError as selected:\n        pass\n    return selected()\n",
            "impl.py",
            False,
            id="function-exception-target-is-local",
        ),
        pytest.param(
            "",
            "def invoke():\n    try:\n        raise ValueError()\n"
            "    except ValueError as other:\n        pass\n    return selected()\n",
            "impl.py",
            True,
            id="unrelated-exception-target",
        ),
    ],
)
def test_binding_authority_conforms_across_imports_calls_and_callers(
    tmp_path: Path, facade_tail: str, caller: str, owner: str | None, exact_call: bool
) -> None:
    _write(tmp_path, "impl.py", "def build(): return 'impl'\n")
    _write(tmp_path, "decoy.py", "def build(): return 'decoy'\n")
    _write(
        tmp_path,
        "facade.py",
        "from impl import build as exposed\nreplacement = lambda: 'replacement'\n"
        + facade_tail,
    )
    _write(tmp_path, "consumer.py", "from facade import exposed as selected\n" + caller)
    with _map(tmp_path) as codemap:
        codemap.index.sync()
        identity = qualified_import_identity(
            codemap._imports, source_path="consumer.py", target="facade.exposed"
        )
        forward = codemap.structure.locality("consumer.py::invoke")
        reverse = codemap.structure.locality("impl.py::build", max_depth=0)
    assert identity["status"] == ("ambiguous" if owner is None else "resolved")
    assert (identity["qualified_identity"] is not None) is (owner is not None)
    assert identity["owner_paths"] == (
        ["facade.py", "impl.py"] if owner == "impl.py" else ["facade.py"]
    )
    call = next(
        row
        for row in assert_records(forward["edges"])
        if row["target_text"] == "selected"
    )
    assert call["resolved_symbol_id"] == ("impl.py::build" if exact_call else None)
    node = assert_records(reverse["nodes"])[0]
    assert {
        (row["path"], row["source"]) for row in assert_records(node["exact_callers"])
    } == ({("consumer.py", "invoke")} if exact_call else set())
    assert (
        identity["producer_implementation_identity"]
        == forward["provider_implementation_identity"]
        == reverse["provider_implementation_identity"]
    )


@pytest.mark.parametrize(
    ("class_tail", "exact_call"),
    [
        ("    if True:\n        build: object\n", True),
        ("    annotation: (build := replacement)\n", False),
    ],
)
def test_class_annotation_targets_and_possible_effects_keep_distinct_authority(
    tmp_path: Path, class_tail: str, exact_call: bool
) -> None:
    _write(
        tmp_path,
        "factory.py",
        "replacement = lambda: 'replacement'\nclass Factory:\n"
        "    def build(): return 'original'\n" + class_tail,
    )
    _write(
        tmp_path,
        "consumer.py",
        "from factory import Factory\ndef invoke(): return Factory.build()\n",
    )
    with _map(tmp_path) as codemap:
        codemap.index.sync()
        identity = qualified_import_identity(
            codemap._imports, source_path="consumer.py", target="factory.Factory"
        )
        forward = codemap.structure.locality("consumer.py::invoke")
        reverse = codemap.structure.locality("factory.py::Factory.build", max_depth=0)
    assert identity["status"] == "resolved"
    assert identity["owner_paths"] == ["factory.py"]
    call = next(
        row
        for row in assert_records(forward["edges"])
        if row["target_text"] == "Factory.build"
    )
    assert call["resolved_symbol_id"] == (
        "factory.py::Factory.build" if exact_call else None
    )
    node = assert_records(reverse["nodes"])[0]
    assert {
        (row["path"], row["source"]) for row in assert_records(node["exact_callers"])
    } == ({("consumer.py", "invoke")} if exact_call else set())


def test_annotation_only_module_target_has_no_qualified_binding(tmp_path: Path) -> None:
    _write(tmp_path, "facade.py", "exposed: object\n")
    _write(tmp_path, "consumer.py", "from facade import exposed\n")
    with _map(tmp_path) as codemap:
        codemap.index.sync()
        identity = qualified_import_identity(
            codemap._imports, source_path="consumer.py", target="facade.exposed"
        )
    assert identity["status"] in {"ambiguous", "unresolved"}
    assert identity["qualified_identity"] is None


@pytest.mark.parametrize(
    ("name", "declaration", "exported"),
    [
        ("_build", "__all__ = ['_build']\n", True),
        ("_build", "__all__ = []\n__all__.append('_build')\n", True),
        ("_build", "", False),
        ("build", "", True),
        ("_build", "__all__ = ['other']\n", False),
        ("build", "__all__ = ['other']\n", False),
        ("_build", "__all__ = names\n", False),
        ("build", "__all__ = names\n", False),
        ("_build", "__all__ = ['_build']\ndel __all__\n", False),
    ],
)
def test_star_export_membership_qualifies_identity_calls_and_test_callers(
    tmp_path: Path, name: str, declaration: str, exported: bool
) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import *\n")
    _write(tmp_path, "pkg/impl.py", declaration + f"def {name}(): return 1\n")
    _write(
        tmp_path,
        "tests/test_build.py",
        f"from pkg import {name} as selected\ndef test_build(): return selected()\n",
    )
    owner = f"pkg/impl.py::{name}"
    with _map(tmp_path) as codemap:
        codemap.index.sync()
        identity = qualified_import_identity(
            codemap._imports, source_path="tests/test_build.py", target=f"pkg.{name}"
        )
        forward = codemap.structure.locality("tests/test_build.py::test_build")
        reverse = codemap.structure.locality(owner, max_depth=0)
    calls = [
        row
        for row in assert_records(forward["edges"])
        if row["target_text"] == "selected"
    ]
    target = next(
        row for row in assert_records(reverse["nodes"]) if row["symbol_id"] == owner
    )
    assert len(calls) == 1
    if exported:
        assert identity["status"] == "resolved"
        assert identity["qualified_identity"] is not None
        assert identity["owner_paths"] == ["pkg/__init__.py", "pkg/impl.py"]
        assert calls[0]["resolved_symbol_id"] == owner
        assert {
            (row["path"], row["source"])
            for row in assert_records(target["exact_callers"])
        } == {("tests/test_build.py", "test_build")}
    else:
        assert identity["qualified_identity"] is None
        assert calls[0]["resolved_symbol_id"] is None
        assert target["exact_callers"] == []
    assert (
        identity["producer_implementation_identity"]
        == forward["provider_implementation_identity"]
    )
    assert (
        forward["provider_implementation_identity"]
        == reverse["provider_implementation_identity"]
    )
    assert identity["source_path"] == "tests/test_build.py"
    assert identity["requested_target"] == f"pkg.{name}"
    assert forward["repository_identity"] == reverse["repository_identity"]


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


def test_cross_repository_shared_input_identity_binds_projects_and_content(
    tmp_path: Path,
) -> None:
    _shared_repo(tmp_path)
    with _map(tmp_path) as codemap:
        codemap.index.sync()
        codemap.native.enrich_projects(("npm-package-graph", "declared-project-links"))
        first = qualified_shared_input_identity(codemap.native, relpath="contract.json")
        second = qualified_shared_input_identity(
            codemap.native, relpath="contract.json"
        )
    assert first == second
    assert first["status"] == "resolved"
    assert assert_text(first["qualified_identity"]).startswith("sha256:")
    assert [row["project_id"] for row in assert_records(first["projects"])] == [
        "npm:backend",
        "npm:frontend",
    ]


def test_shared_input_change_is_stale_until_authoritative_refresh_then_rebinds(
    tmp_path: Path,
) -> None:
    _shared_repo(tmp_path)
    with _map(tmp_path) as codemap:
        codemap.index.sync()
        codemap.native.enrich_projects(("npm-package-graph", "declared-project-links"))
        before = qualified_shared_input_identity(
            codemap.native, relpath="contract.json"
        )
        _write(tmp_path, "contract.json", '{"v":2}\n')
        stale = qualified_shared_input_identity(codemap.native, relpath="contract.json")
        codemap.changes.task_impact("contract changed", ["contract.json"])
        after = qualified_shared_input_identity(codemap.native, relpath="contract.json")
    assert stale["status"] == "stale"
    assert stale["qualified_identity"] is None
    assert after["status"] == "resolved"
    assert after["qualified_identity"] != before["qualified_identity"]
    assert after["content_sha256"] != before["content_sha256"]


def test_shared_input_change_during_identity_read_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _shared_repo(tmp_path)
    with _map(tmp_path) as codemap:
        codemap.index.sync()
        codemap.native.enrich_projects(("npm-package-graph", "declared-project-links"))
        before = qualified_shared_input_identity(
            codemap.native, relpath="contract.json"
        )
        original_digest = codemap.native._manifest_digest
        changed = False

        def change_after_digest(relpath: str) -> str | None:
            nonlocal changed
            digest = original_digest(relpath)
            if relpath == "contract.json" and not changed:
                changed = True
                _write(tmp_path, "contract.json", '{"v":2}\n')
            return digest

        monkeypatch.setattr(codemap.native, "_manifest_digest", change_after_digest)
        during = qualified_shared_input_identity(
            codemap.native, relpath="contract.json"
        )

    assert changed
    assert before["status"] == "resolved"
    assert during["content_sha256"] == before["content_sha256"]
    assert during["status"] == "stale"
    assert during["fresh"] is False
    assert during["qualified_identity"] is None


def test_undeclared_shared_input_fails_closed(tmp_path: Path) -> None:
    _write(tmp_path, "contract.json", "{}\n")
    with _map(tmp_path) as codemap:
        codemap.index.sync()
        result = qualified_shared_input_identity(
            codemap.native, relpath="contract.json"
        )
    assert result["status"] == "unresolved"
    assert result["qualified_identity"] is None


def test_deleted_import_owner_cannot_retain_false_unique_qualified_identity(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import Public\n")
    _write(tmp_path, "pkg/impl.py", "class Public: pass\n")
    _write(tmp_path, "tests/test_a.py", "from pkg import Public\n")
    with _map(tmp_path) as codemap:
        codemap.index.sync()
        before = qualified_import_identity(
            codemap._imports, source_path="tests/test_a.py", target="pkg.Public"
        )
        (tmp_path / "pkg/impl.py").unlink()
        after = qualified_import_identity(
            codemap._imports, source_path="tests/test_a.py", target="pkg.Public"
        )
    assert before["status"] == "resolved"
    assert before["qualified_identity"] is not None
    assert after["owner_paths"] != ["pkg/__init__.py", "pkg/impl.py"]
    assert after["qualified_identity"] is None


def test_qualified_import_identity_is_independent_of_consumer_path(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/impl.py", "class Public: pass\n")
    _write(tmp_path, "a/use.py", "from pkg.impl import Public\n")
    _write(tmp_path, "b/use.py", "from pkg.impl import Public\n")
    with _map(tmp_path) as codemap:
        codemap.index.sync()
        first = qualified_import_identity(
            codemap._imports, source_path="a/use.py", target="pkg.impl.Public"
        )
        second = qualified_import_identity(
            codemap._imports, source_path="b/use.py", target="pkg.impl.Public"
        )
    assert first["status"] == second["status"] == "resolved"
    assert first["owner_paths"] == second["owner_paths"] == ["pkg/impl.py"]
    assert first["qualified_identity"] == second["qualified_identity"]


def test_public_reexport_alias_identity_stays_distinct_from_internal_symbol(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .impl import Internal as Public\n")
    _write(tmp_path, "pkg/impl.py", "class Internal: pass\n")
    _write(
        tmp_path,
        "tests/use.py",
        "from pkg import Public\nfrom pkg.impl import Internal\n",
    )
    with _map(tmp_path) as codemap:
        codemap.index.sync()
        public = qualified_import_identity(
            codemap._imports, source_path="tests/use.py", target="pkg.Public"
        )
        internal = qualified_import_identity(
            codemap._imports, source_path="tests/use.py", target="pkg.impl.Internal"
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
        codemap.index.sync()
        result = qualified_import_identity(
            codemap._imports, source_path="tests/use.py", target="pkg.Public"
        )
    assert result["status"] == "ambiguous"
    assert result["qualified_identity"] is None


def test_qualified_import_identity_rebinds_unsynced_facade_retarget(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "pkg/__init__.py", "from .a import Public\n")
    _write(tmp_path, "pkg/a.py", "class Public: pass\n")
    _write(tmp_path, "pkg/b.py", "class Public: pass\n")
    _write(tmp_path, "tests/use.py", "from pkg import Public\n")
    with _map(tmp_path) as codemap:
        codemap.index.sync()
        before = qualified_import_identity(
            codemap._imports, source_path="tests/use.py", target="pkg.Public"
        )
        _write(tmp_path, "pkg/__init__.py", "from .b import Public\n")
        after = qualified_import_identity(
            codemap._imports, source_path="tests/use.py", target="pkg.Public"
        )
    assert before["status"] == after["status"] == "resolved"
    assert before["owner_paths"] == ["pkg/__init__.py", "pkg/a.py"]
    assert after["owner_paths"] == ["pkg/__init__.py", "pkg/b.py"]
    assert before["qualified_identity"] != after["qualified_identity"]
