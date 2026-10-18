"""Function lookup belongs to the same stable source snapshot as the parsed tree."""

from __future__ import annotations

import os
from pathlib import Path

from hashmarks.python_ast_cache import read_python_ast


def test_function_index_retains_all_duplicate_and_nested_declarations(
    tmp_path: Path,
) -> None:
    source = tmp_path / "module.py"
    source.write_text(
        "class First:\n"
        "    def run(self): return 1\n"
        "class Second:\n"
        "    async def run(self): return 2\n"
        "def outer():\n"
        "    def run(): return 3\n"
        "    return run()\n"
    )
    snapshot = read_python_ast(source)
    functions = snapshot.function_definitions_by_name
    assert sorted(functions) == ["outer", "run"]
    assert sorted(node.lineno for node in functions["run"]) == [2, 4, 6]
    assert [node.lineno for node in functions["outer"]] == [5]
    assert snapshot.source.startswith("class First:")


def test_function_index_follows_same_size_source_changes_and_keeps_old_snapshot(
    tmp_path: Path,
) -> None:
    source = tmp_path / "module.py"
    source.write_text("def first(): return 1\n")
    original = source.stat()
    before = read_python_ast(source)
    assert set(before.function_definitions_by_name) == {"first"}
    source.write_text("def other(): return 2\n")
    assert source.stat().st_size == original.st_size
    os.utime(source, ns=(original.st_atime_ns, original.st_mtime_ns))
    after = read_python_ast(source)
    assert after.identity != before.identity
    assert set(after.function_definitions_by_name) == {"other"}
    assert set(before.function_definitions_by_name) == {"first"}
