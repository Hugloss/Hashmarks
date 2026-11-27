"""Import edges use their authored module before exposing symbol locators."""

from pathlib import Path

from contract_assertions import assert_records

from hashmarks import CodeMap


def _imports(cm: CodeMap, query: str) -> list[dict[str, object]]:
    return [
        row
        for row in assert_records(cm.relationships.deps(query)["edges"])
        if row["kind"] == "import"
    ]


def _owners(edge: dict[str, object]) -> list[tuple[object, object]]:
    return [
        (row["path"], row["qualname"])
        for row in assert_records(edge["resolved_symbols"])
    ]


def test_dependency_imports_reach_the_authored_symbol_beyond_short_name_limit(
    tmp_path: Path,
) -> None:
    for i in range(10):
        (tmp_path / f"decoy{i}.py").write_text("def emit(): pass\nclass Public: pass\n")
    pkg = tmp_path / "zpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "owner.py").write_text("def emit(): pass\nclass Actual: pass\n")
    (pkg / "facade.py").write_text("from .owner import Actual as Public\n")
    (pkg / "consumer.py").write_text(
        "def use():\n    from .owner import emit as send\n    from .facade import Public\n    return send(), Public\n"
    )
    with CodeMap(tmp_path) as cm:
        by_file = _imports(cm, "zpkg/consumer.py")
        assert _imports(cm, "use") == by_file
        direct, facade = by_file
        assert direct["target"] == ".owner.emit" and direct["line"] == 2
        assert direct["resolved_paths"] == ["zpkg/owner.py"]
        assert facade["resolved_paths"] == ["zpkg/facade.py"]
        assert _owners(direct) == [("zpkg/owner.py", "emit")]
        assert _owners(facade) == [("zpkg/owner.py", "Actual")]
        assert all(row["symbol_resolution"] == "qualified-import" for row in by_file)
        assert all("resolved_symbols_truncated" not in row for row in by_file)
        (pkg / "facade.py").write_text("from .owner import emit as Public\n")
        cm.index.sync(["zpkg/facade.py"])
        assert _owners(_imports(cm, "use")[1]) == [("zpkg/owner.py", "emit")]


def test_module_import_and_unqualified_member_cannot_gain_a_homonym(
    tmp_path: Path,
) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("def missing(): pass\n")
    (pkg / "worker.py").write_text(
        "def worker(): pass\nVALUE = 42\nclass Nested:\n    def absent(self): pass\n"
    )
    (tmp_path / "old.py").write_text(
        "def worker(): pass\ndef VALUE(): pass\ndef absent(): pass\ndef missing(): pass\n"
    )
    (tmp_path / "consumer.py").write_text(
        "import pkg.worker\nfrom pkg.worker import worker as declared\n"
        "from pkg.worker import VALUE, absent\nfrom external import missing\n"
        "from pkg.unknown import missing\n"
        "import pkg.worker; from pkg import worker\n"
    )
    with CodeMap(tmp_path) as cm:
        plain, declared, value, absent, external, missing, first, second = _imports(
            cm, "consumer.py"
        )
        assert plain["symbol_resolution"] == "module-import" and _owners(plain) == []
        assert declared["symbol_resolution"] == "qualified-import"
        assert _owners(declared) == [("pkg/worker.py", "worker")]
        assert value["symbol_resolution"] == "unresolved" and _owners(value) == [
            ("pkg/worker.py", "VALUE")
        ]
        assert all(
            r["symbol_resolution"] == "unresolved" and not _owners(r)
            for r in (absent, external, missing, first, second)
        )


def test_dependency_member_requires_unique_visible_module(tmp_path: Path) -> None:
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern="restricted.py"\nvisibility="outline"\n'
    )
    (tmp_path / "restricted.py").write_text("def f(): pass\n")
    (tmp_path / "duplicate.py").write_text("def f(): pass\n")
    (tmp_path / "duplicate.pyi").write_text("def f(): ...\n")
    (tmp_path / "consumer.py").write_text(
        "from restricted import f\nfrom duplicate import f as second\n"
    )
    with CodeMap(tmp_path) as cm:
        assert all(
            r["symbol_resolution"] == "unresolved" and not _owners(r)
            for r in _imports(cm, "consumer.py")
        )


def test_missing_reexport_module_cannot_promote_a_parent_homonym(
    tmp_path: Path,
) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("def Public(): pass\n")
    (pkg / "facade.py").write_text("def Public(): pass\nfrom .missing import Public\n")
    (tmp_path / "consumer.py").write_text("from pkg.facade import Public\n")
    with CodeMap(tmp_path) as cm:
        (edge,) = _imports(cm, "consumer.py")
        assert edge["resolved_paths"] == ["pkg/facade.py"]
        assert edge["symbol_resolution"] == "unresolved" and _owners(edge) == []
