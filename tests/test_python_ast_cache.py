from __future__ import annotations

import ast
from pathlib import Path

from hashmarks.python_ast_cache import ast_cache_info, clear_ast_cache, read_python_ast


def _function_names(tree: ast.Module) -> list[str]:
    return [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def test_python_ast_cache_reuses_unchanged_snapshot(tmp_path: Path) -> None:
    clear_ast_cache()
    source = tmp_path / "sample.py"
    source.write_text("def first():\n    return 1\n", encoding="utf-8")
    before = ast_cache_info()

    first = read_python_ast(source)
    second = read_python_ast(source)
    after = ast_cache_info()

    assert first is second
    assert _function_names(first.tree) == ["first"]
    assert after.misses == before.misses + 1
    assert after.hits == before.hits + 1


def test_python_ast_cache_invalidates_when_file_changes(tmp_path: Path) -> None:
    clear_ast_cache()
    source = tmp_path / "sample.py"
    source.write_text("def first():\n    return 1\n", encoding="utf-8")
    first = read_python_ast(source)

    source.write_text("def second(value):\n    return value + 2\n", encoding="utf-8")
    second = read_python_ast(source)

    assert first is not second
    assert first.identity != second.identity
    assert _function_names(second.tree) == ["second"]


def test_python_ast_cache_preserves_source_and_filename(tmp_path: Path) -> None:
    clear_ast_cache()
    source = tmp_path / "broken.py"
    source.write_text("def broken(:\n    pass\n", encoding="utf-8")

    try:
        read_python_ast(source)
    except SyntaxError as exc:
        assert exc.filename == str(source.resolve())
    else:
        raise AssertionError("invalid Python must still fail closed with SyntaxError")


def test_python_ast_cache_observes_same_size_rewrite_with_restored_mtime(
    tmp_path: Path,
) -> None:
    clear_ast_cache()
    source = tmp_path / "sample.py"
    source.write_text("def alpha():\n    return 1\n", encoding="utf-8")
    original_stat = source.stat()
    first = read_python_ast(source)

    source.write_text("def bravo():\n    return 2\n", encoding="utf-8")
    assert source.stat().st_size == original_stat.st_size
    import os

    os.utime(source, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    second = read_python_ast(source)

    assert first is not second
    assert _function_names(second.tree) == ["bravo"]


def test_python_ast_cache_observes_atomic_replace_with_same_size_and_mtime(
    tmp_path: Path,
) -> None:
    clear_ast_cache()
    source = tmp_path / "sample.py"
    replacement = tmp_path / "replacement.py"
    source.write_text("def alpha():\n    return 1\n", encoding="utf-8")
    original_stat = source.stat()
    first = read_python_ast(source)

    replacement.write_text("def bravo():\n    return 2\n", encoding="utf-8")
    assert replacement.stat().st_size == original_stat.st_size
    import os

    os.utime(replacement, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    os.replace(replacement, source)
    second = read_python_ast(source)

    assert first is not second
    assert first.identity[1] != second.identity[1]
    assert _function_names(second.tree) == ["bravo"]


def test_python_ast_cache_retries_when_source_changes_during_read(
    tmp_path: Path, monkeypatch
) -> None:
    clear_ast_cache()
    source = tmp_path / "sample.py"
    source.write_text("def alpha():\n    return 1\n", encoding="utf-8")
    original_read_text = Path.read_text
    calls = 0

    def mutating_read_text(path: Path, *args, **kwargs) -> str:
        nonlocal calls
        text = original_read_text(path, *args, **kwargs)
        if path == source and calls == 0:
            calls += 1
            source.write_text("def bravo():\n    return 2\n", encoding="utf-8")
        return text

    monkeypatch.setattr(Path, "read_text", mutating_read_text)
    snapshot = read_python_ast(source)

    assert calls == 1
    assert _function_names(snapshot.tree) == ["bravo"]


def test_python_ast_cache_does_not_serve_stale_tree_when_current_source_is_invalid(
    tmp_path: Path,
) -> None:
    clear_ast_cache()
    source = tmp_path / "sample.py"
    source.write_text("def alpha():\n    return 1\n", encoding="utf-8")
    cached = read_python_ast(source)
    assert _function_names(cached.tree) == ["alpha"]

    source.write_text("def alpha(:\n    return 1\n", encoding="utf-8")
    try:
        read_python_ast(source)
    except SyntaxError:
        pass
    else:
        raise AssertionError(
            "current invalid source must raise SyntaxError instead of serving cached AST"
        )


def test_python_ast_cache_observes_rapid_rewrite(tmp_path: Path) -> None:
    source = tmp_path / "rapid.py"
    source.write_text("VALUE = 1\n")
    first = read_python_ast(source)

    source.write_text("VALUE = 2\n")
    second = read_python_ast(source)
    source.write_text("VALUE = 3\n")
    third = read_python_ast(source)

    assert first.source == "VALUE = 1\n"
    assert second.source == "VALUE = 2\n"
    assert third.source == "VALUE = 3\n"
    assert first.identity != second.identity
    assert second.identity != third.identity


def test_python_ast_cache_observes_delete_and_recreate(tmp_path: Path) -> None:
    source = tmp_path / "recreated.py"
    source.write_text("VALUE = 1\n")
    first = read_python_ast(source)

    first_inode = source.stat().st_ino
    source.unlink()
    source.write_text("VALUE = 2\n")
    second = read_python_ast(source)

    assert first.source == "VALUE = 1\n"
    assert second.source == "VALUE = 2\n"
    assert second.identity != first.identity
    assert source.stat().st_ino != first_inode or second.identity != first.identity
