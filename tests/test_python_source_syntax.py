"""The existing Python AST owner shares exact source only within an operation."""

from __future__ import annotations

import ast
from codecs import BOM_UTF8
from contextvars import copy_context
from pathlib import Path

import pytest
from contract_assertions import assert_integer, assert_object, assert_records

from hashmarks import CodeMap, python_ast_cache
from hashmarks.codemap.parsers import artifact_key_for, parse_source
from hashmarks.codemap.providers import TreeSitterRangeProvider
from hashmarks.digest import FILE_DOMAIN, hash_file


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


def test_bom_source_reuse_is_exact_and_returns_original_byte_positions(
    tmp_path: Path,
) -> None:
    raw = 'pré = "界"; token = (\n    "next"\n)\n'.encode()
    marked = BOM_UTF8 + raw
    path = tmp_path / "member.py"
    path.write_bytes(marked)
    with python_ast_cache.python_ast_session():
        plain = python_ast_cache.parse_python_ast(raw)
        tree = python_ast_cache.parse_python_ast(marked)
        assert plain is not tree
        assert python_ast_cache.parse_python_ast(marked.decode("utf-8")) is tree
        assert python_ast_cache.read_python_ast(path).tree is tree
        assert (
            python_ast_cache.read_python_ast(
                path, encoding="utf-8-sig", errors="replace"
            ).tree
            is tree
        )
        assert python_ast_cache.parse_python_ast(raw) is plain
        first, second = tree.body
        assert (first.col_offset, first.end_col_offset) == (
            len(BOM_UTF8),
            len(BOM_UTF8 + 'pré = "界"'.encode()),
        )
        assert (second.col_offset, second.end_col_offset) == (
            len(BOM_UTF8 + 'pré = "界"; '.encode()),
            1,
        )
        assert plain.body[0].col_offset == 0
        assert (
            ast.get_source_segment(marked.decode("utf-8"), second)
            == 'token = (\n    "next"\n)'
        )


def test_bom_occurrences_use_original_columns_and_exclude_the_mark_from_tokens(
    tmp_path: Path,
) -> None:
    (tmp_path / "member.py").write_bytes(BOM_UTF8 + "é='v'\r\nother=2\n".encode())
    with CodeMap(tmp_path) as codemap:
        for literal, line, column, kind in (
            ("\ufeff", 1, 1, "unknown"),
            ("\ufeffé", 1, 1, "unknown"),
            ("é", 1, 2, "identifier"),
            ("'v'", 1, 4, "string-literal"),
            ("other", 2, 1, "identifier"),
        ):
            packet = codemap.source.observe("member.py", literal=literal)
            (hit,) = assert_records(packet["occurrences"])
            assert (hit["line"], hit["column"], hit["occurrence_kind"]) == (
                line,
                column,
                kind,
            )
            assert hit["kind_basis"] == (
                "unknown" if kind == "unknown" else "python-tokenizer"
            )


def test_bom_index_bindings_and_source_reads_share_exact_member_bytes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    path = root / "mod.py"
    statement = 'é = "界"'
    raw = (statement + '; donnée = (\r\n    "next"\r\n); tail = donnée\r\n').encode()
    revisions: list[str] = []
    with CodeMap(root, state_dir=tmp_path / "state") as repository:
        for prefix in (BOM_UTF8, b"", BOM_UTF8):
            source = prefix + raw
            path.write_bytes(source)
            repository.index.sync()
            outline = repository.source.outline("mod.py")
            bindings = repository.source.bindings("mod.py")
            assert outline["parse_error"] is None
            assert bindings["availability"] == "observed"
            revision = hash_file(path, domain=FILE_DOMAIN).hash
            assert (
                assert_object(bindings["member"])["member_revision"]
                == outline["file_digest"]
                == revision
            )
            revisions.append(revision)
            for row in assert_records(bindings["facts"]):
                if row["kind"] == "literal-binding":
                    span = assert_object(row["range"])
                    assert (
                        source[
                            assert_integer(span["start_byte"]) : assert_integer(
                                span["end_byte"]
                            )
                        ].decode()
                        == row["name"]
                    )
                expr = assert_object(row["expression"])
                span = assert_object(expr["range"])
                assert (
                    source[
                        assert_integer(span["start_byte"]) : assert_integer(
                            span["end_byte"]
                        )
                    ].decode()
                    == expr["text"]
                )
            first = repository.source.read("mod.py::é")
            assert first["content"] == statement
            assert (first["start_byte_column"], first["end_byte_column"]) == (
                len(prefix),
                len(prefix + statement.encode()),
            )
            second = repository.source.read("mod.py::donnée")
            assert second["content"] == 'donnée = (\n    "next"\n)'
            assert (second["start_byte_column"], second["end_byte_column"]) == (
                len(prefix + (statement + "; ").encode()),
                1,
            )
            assert repository.source.read("mod.py::tail")["content"] == "tail = donnée"
    assert revisions[0] == revisions[2] != revisions[1]


@pytest.mark.parametrize(
    "comment", [b"# coding: utf-8\n", b"#!/usr/bin/python\r\n# coding=UTF_8\r\n"]
)
def test_bom_accepts_native_utf8_coding_cookie(comment: bytes) -> None:
    assert (
        len(python_ast_cache.parse_python_ast(BOM_UTF8 + comment + b"x = 1\n").body)
        == 1
    )


@pytest.mark.parametrize(
    ("raw", "expected_error", "reason"),
    [
        (
            BOM_UTF8 + b"# coding: latin-1\nx = 1\n",
            SyntaxError,
            "source-binding-syntax-unqualified",
        ),
        (
            BOM_UTF8 + b"#!/usr/bin/python\n# coding: ascii\nx = 1\n",
            SyntaxError,
            "source-binding-syntax-unqualified",
        ),
        (BOM_UTF8 * 2 + b"x = 1\n", SyntaxError, "source-binding-syntax-unqualified"),
        (BOM_UTF8 + b"x = '\xff'\n", UnicodeDecodeError, "invalid-utf8"),
    ],
)
def test_invalid_bom_source_cannot_qualify_native_syntax(
    tmp_path: Path, raw: bytes, expected_error: type[Exception], reason: str
) -> None:
    path = tmp_path / "mod.py"
    path.write_bytes(raw)
    with pytest.raises(expected_error):
        python_ast_cache.parse_python_ast(raw)
    with pytest.raises(expected_error):
        python_ast_cache.read_python_ast(path)
    with pytest.raises(expected_error):
        python_ast_cache.read_python_ast(path, encoding="utf-8-sig", errors="replace")
    with CodeMap(tmp_path) as repository:
        bindings = repository.source.bindings("mod.py")
        assert repository.source.outline("mod.py")["parse_error"]
    assert bindings["availability"] == "unavailable"
    assert bindings["reason"] == reason
    assert bindings["facts"] == []
    assert bindings["negative_evidence"] == "not-admissible"
