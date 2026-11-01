"""The existing Python AST owner shares exact source only within an operation."""

from __future__ import annotations

import ast
from contextvars import copy_context
from pathlib import Path

import pytest

from hashmarks import CodeMap, python_ast_cache
from hashmarks.codemap.parsers import artifact_key_for, parse_source
from hashmarks.codemap.providers import TreeSitterRangeProvider


def _count_parses(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    original = ast.parse

    def counted(source: str, filename: str = "<unknown>") -> ast.Module:
        calls.append(source)
        return original(source, filename=filename)

    monkeypatch.setattr(python_ast_cache.ast, "parse", counted)
    return calls


def test_source_ast_reuse_is_exact_nested_and_signature_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _count_parses(monkeypatch)
    raw = b"import example\r\nexample.send()\r\n"
    with python_ast_cache.python_ast_session():
        first = python_ast_cache.parse_python_ast(raw)
        with python_ast_cache.python_ast_session():
            assert python_ast_cache.parse_python_ast(raw.decode()) is first
        assert (
            python_ast_cache.parse_python_ast(raw.replace(b"\r\n", b"\n")) is not first
        )
        monkeypatch.setattr(python_ast_cache, "python_ast_signature", lambda: "changed")
        assert python_ast_cache.parse_python_ast(raw) is not first
    assert len(calls) == 3
    assert python_ast_cache.parse_python_ast(raw) is not first
    assert len(calls) == 4


@pytest.mark.parametrize("bound", ["count", "bytes"])
def test_python_source_tree_eviction_does_not_change_meaning(
    monkeypatch: pytest.MonkeyPatch, bound: str
) -> None:
    if bound == "count":
        monkeypatch.setattr(python_ast_cache, "_MAX_SOURCE_TREES", 1)
    else:
        monkeypatch.setattr(python_ast_cache, "_MAX_SOURCE_BYTES", 12)
    calls = _count_parses(monkeypatch)
    with python_ast_cache.python_ast_session():
        first = python_ast_cache.parse_python_ast("first = 1\n")
        second = python_ast_cache.parse_python_ast("other = 2\n")
        assert python_ast_cache.parse_python_ast("other = 2\n") is second
        reparsed = python_ast_cache.parse_python_ast("first = 1\n")
    assert len(calls) == 3
    assert reparsed is not first
    assert ast.dump(reparsed) == ast.dump(first)


def test_python_source_reuse_ends_for_inherited_contexts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _count_parses(monkeypatch)
    with python_ast_cache.python_ast_session():
        initial = python_ast_cache.parse_python_ast("value = 1\n")
        inherited = copy_context()
    assert (
        inherited.run(python_ast_cache.parse_python_ast, "value = 1\n") is not initial
    )
    assert (
        inherited.run(python_ast_cache.parse_python_ast, "value = 1\n") is not initial
    )
    assert len(calls) == 3


def test_python_source_syntax_errors_keep_each_callers_filename() -> None:
    with python_ast_cache.python_ast_session():
        for name in ("first.py", "second.py"):
            with pytest.raises(SyntaxError) as error:
                python_ast_cache.parse_python_ast("def broken(:", filename=name)
            assert error.value.filename == name


def test_canonical_python_parser_rejects_invalid_utf8_without_replacement() -> None:
    with pytest.raises(UnicodeDecodeError):
        python_ast_cache.parse_python_ast(b"value = '\xff'\n")


def test_existing_read_scope_shares_python_ingestion_and_binding_syntax(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = "import example\nexample.send()\n"
    (tmp_path / "member.py").write_text(source)
    calls = _count_parses(monkeypatch)
    with CodeMap(tmp_path, range_provider=TreeSitterRangeProvider()) as codemap:
        with codemap.reads.session():
            first = codemap.source.bindings("member.py")
            second = codemap.source.bindings("member.py")
            assert first["availability"] == "observed"
            assert second == first
            assert calls.count(source) == 1
        codemap.source.bindings("member.py")
        assert calls.count(source) == 2


def test_native_python_grammar_identity_invalidates_structural_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = "import example\ndef send(): return example.send()\n"
    before = parse_source(source, file_digest="same-bytes", language="python")
    monkeypatch.setattr(python_ast_cache, "python_ast_signature", lambda: "changed")
    after = parse_source(source, file_digest="same-bytes", language="python")
    assert before.symbols == after.symbols
    assert before.parser != after.parser
    assert before.artifact_key != after.artifact_key
    assert after.artifact_key == artifact_key_for("same-bytes", "python")


def test_python_grammar_change_during_ingestion_withdraws_structure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = "import example\ndef send(): return example.send()\n"
    key = artifact_key_for("same-bytes", "python")
    original = ast.parse

    def changing_parser(text: str, filename: str = "<unknown>") -> ast.Module:
        tree = original(text, filename=filename)
        monkeypatch.setattr(python_ast_cache, "python_ast_signature", lambda: "changed")
        return tree

    monkeypatch.setattr(python_ast_cache.ast, "parse", changing_parser)
    changed = parse_source(source, file_digest="same-bytes", language="python")
    current = parse_source(source, file_digest="same-bytes", language="python")
    assert changed.artifact_key == key
    assert changed.symbols == changed.edges == ()
    assert changed.parse_error == "native-syntax-provider-changed"
    assert current.artifact_key != key
    assert current.symbols and current.edges
    assert current.parse_error is None
