from __future__ import annotations

from typing import TYPE_CHECKING

from contract_assertions import assert_array, assert_object, assert_records

from hashmarks.codemap import CodeMap

if TYPE_CHECKING:
    from pathlib import Path


def test_relative_import_impact_uses_the_importers_indexed_package(
    tmp_path: Path,
) -> None:
    files = {
        "pyproject.toml": '[tool.setuptools.package-dir]\n"" = "src"\n',
        "src/pkg/__init__.py": "from .rules import check\n",
        "src/pkg/rules.py": "def check(): pass\n",
        "src/pkg/sub/__init__.py": "",
        "src/pkg/sub/reader.py": "from ..rules import check\n",
        "src/pkg/client.py": "from .sub import reader\n",
        "src/other/rules.py": "def check(): pass\n",
        "src/other/reader.py": "from .rules import check\n",
        "src/other/bridge.py": "import pkg.sub.reader\n",
        "src/other/tests/test_bridge.py": "from ..bridge import reader\n",
    }
    for rel, source in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    with CodeMap(tmp_path) as cm:
        cm.index.sync()
        root = "src/pkg/rules.py"
        levels = [
            ["src/pkg/__init__.py", "src/pkg/sub/reader.py"],
            ["src/other/bridge.py", "src/pkg/client.py"],
            ["src/other/tests/test_bridge.py"],
        ]
        cm.store.reset_read_counters()
        assert cm.relationships.affected(root, max_depth=3)["levels"] == levels
        # A second frontier inside pkg reuses its observed relative imports.
        assert cm.store.read_counters()["relative_python_imports"] == 2
        assert cm.relationships.tests(root, max_depth=3)["tests"] == levels[-1]
        assert cm.relationships.affected("src/other/rules.py")["affected_files"] == [
            "src/other/reader.py"
        ]
        reverse = cm.relationships._reverse_file_graph()
        assert reverse[root] == set(levels[0])
        assert reverse["src/other/bridge.py"] == set(levels[-1])
        (tmp_path / "src/pkg/sub/reader.py").write_text(
            "from other.rules import check\n"
        )
        cm.index.sync(["src/pkg/sub/reader.py"])
        assert cm.relationships.affected(root)["affected_files"] == [
            "src/pkg/__init__.py"
        ]


def test_python_imports_cannot_escape_the_indexed_package(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg/__init__.py").write_text("")
    (tmp_path / "rules.py").write_text("def check(): pass\n")
    for path, target in (("loose.py", ".rules"), ("pkg/over.py", "..rules")):
        (tmp_path / path).write_text(
            f"from {target} import check\ndef run(): return check()\n"
        )
    with CodeMap(tmp_path) as cm:
        cm.index.sync()
        for path in ("loose.py", "pkg/over.py"):
            imports = [
                r
                for r in assert_records(cm.relationships.deps(path)["edges"])
                if r["kind"] == "import"
            ]
            assert [r["resolved_paths"] for r in imports] == [[]]
            (edge,) = assert_records(
                cm.structure.locality(f"{path}::run", max_depth=1)["edges"]
            )
            assert edge["resolved_symbol_id"] is None
        assert cm.relationships.affected("rules.py")["affected_files"] == []


def test_fast_and_full_impact_withhold_ambiguous_python_module_owners(
    tmp_path: Path,
) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg/__init__.py").write_text("")
    for name in ("api.py", "api.pyi"):
        (tmp_path / "pkg" / name).write_text("def check(): ...\n")
    (tmp_path / "pkg/consumer.py").write_text("from .api import check\n")
    (tmp_path / "reader.py").write_text("import pkg.api\n")
    with CodeMap(tmp_path) as cm:
        cm.index.sync()
        reverse = cm.relationships._reverse_file_graph()
        for name in ("pkg/api.py", "pkg/api.pyi", "pkg/__init__.py"):
            assert cm.relationships.affected(name)["affected_files"] == []
            assert not reverse.get(name)
        wide = ["pkg.api", *(f"missing{i}" for i in range(1100))]
        assert [
            r["path"]
            for r in cm.store.python_import_candidates_for_modules(wide)["pkg.api"]
        ] == ["reader.py"]


def test_python_reverse_fast_path_preserves_longest_module_resolution(
    tmp_path: Path,
) -> None:
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "pkg" / "sub.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "src" / "consumer.py").write_text(
        "import src.pkg.sub\n", encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\nversion="0"\n', encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        package = codemap.relationships.affected("src/pkg/__init__.py", max_depth=2)
        module = codemap.relationships.affected("src/pkg/sub.py", max_depth=2)
    assert "src/consumer.py" not in assert_array(package["affected_files"])
    assert "src/consumer.py" in assert_array(module["affected_files"])


def test_exact_path_change_impact_does_not_reinterpret_path_as_free_text(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "m000000.py").write_text(
        "def f(): return 0\n", encoding="utf-8"
    )
    (tmp_path / "src" / "m050000.py").write_text(
        "from src.m000000 import f\n", encoding="utf-8"
    )
    (tmp_path / "src" / "m050001.py").write_text(
        "from src.m050000 import f\n", encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\nversion="0"\n', encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        impact = codemap.changes.impact(
            "src/m050000.py", max_depth=2, limit_per_surface=6
        )
    rows = assert_records(assert_object(impact["surfaces"])["implementation"])
    reverse = {row["path"] for row in rows if row["provenance"] == "reverse-file-graph"}
    adjacency = {
        row["path"] for row in rows if row["provenance"] == "task-graph-adjacency"
    }
    assert reverse == {"src/m050001.py"}
    assert adjacency == {"src/m000000.py"}


def test_python_reverse_fast_path_matches_full_graph_on_chain(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "m0.py").write_text("def f(): return 0\n", encoding="utf-8")
    for i in range(1, 20):
        (tmp_path / "src" / f"m{i}.py").write_text(
            f"import src.m{i - 1}\n", encoding="utf-8"
        )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\nversion="0"\n', encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        roots = {"src/m7.py"}
        fast = codemap.relationships._python_reverse_levels(roots, max_depth=8)
        reverse = codemap.relationships._reverse_file_graph()
        seen = set(roots)
        frontier = set(roots)
        expected = []
        for _ in range(8):
            nxt = {p for path in frontier for p in reverse.get(path, ())} - seen
            if not nxt:
                break
            expected.append(sorted(nxt))
            seen.update(nxt)
            frontier = nxt
    assert fast == expected
