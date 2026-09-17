from __future__ import annotations

from pathlib import Path

from hashmarks.codemap import CodeMap


def test_python_reverse_fast_path_preserves_longest_module_resolution(tmp_path: Path) -> None:
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "pkg" / "sub.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "src" / "consumer.py").write_text("import src.pkg.sub\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\nversion="0"\n', encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        package = codemap.affected("src/pkg/__init__.py", max_depth=2)
        module = codemap.affected("src/pkg/sub.py", max_depth=2)
    assert "src/consumer.py" not in package["affected_files"]
    assert "src/consumer.py" in module["affected_files"]


def test_exact_path_change_impact_does_not_reinterpret_path_as_free_text(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "m000000.py").write_text("def f(): return 0\n", encoding="utf-8")
    (tmp_path / "src" / "m050000.py").write_text("from src.m000000 import f\n", encoding="utf-8")
    (tmp_path / "src" / "m050001.py").write_text("from src.m050000 import f\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\nversion="0"\n', encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        impact = codemap.change_impact("src/m050000.py", max_depth=2, limit_per_surface=6)
    rows = impact["surfaces"]["implementation"]
    reverse = {row["path"] for row in rows if row["provenance"] == "reverse-file-graph"}
    adjacency = {row["path"] for row in rows if row["provenance"] == "task-graph-adjacency"}
    assert reverse == {"src/m050001.py"}
    assert adjacency == {"src/m000000.py"}


def test_python_reverse_fast_path_matches_full_graph_on_chain(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "m0.py").write_text("def f(): return 0\n", encoding="utf-8")
    for i in range(1, 20):
        (tmp_path / "src" / f"m{i}.py").write_text(f"import src.m{i-1}\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\nversion="0"\n', encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        roots = {"src/m7.py"}
        fast = codemap._python_reverse_levels(roots, max_depth=8)
        reverse = codemap._reverse_file_graph()
        seen = set(roots); frontier = set(roots); expected = []
        for _ in range(8):
            nxt = {p for path in frontier for p in reverse.get(path, ())} - seen
            if not nxt: break
            expected.append(sorted(nxt)); seen.update(nxt); frontier = nxt
    assert fast == expected
