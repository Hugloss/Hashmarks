import ast
from pathlib import Path

import pytest
from contract_assertions import assert_records

from hashmarks import CodeMap, python_ast_cache


@pytest.mark.parametrize("newline", [b"\n", b"\r\n", b"\r"])
def test_different_declared_decoding_cannot_supply_python_evidence(
    tmp_path: Path, newline: bytes
) -> None:
    raw = newline.join(
        (
            b"#!/usr/bin/python",
            b"# coding: latin-1",
            'VALUE = "café"'.encode(),
            b"def visible(): return VALUE",
            b"",
        )
    )
    path = tmp_path / "sample.py"
    path.write_bytes(raw)
    native = ast.parse(raw).body[0]
    assert isinstance(native, ast.Assign) and isinstance(native.value, ast.Constant)
    assert native.value.value == "cafÃ©"
    with python_ast_cache.python_ast_session():
        for source in (raw.decode(), raw):
            with pytest.raises(python_ast_cache.PythonSourceEncodingError) as err:
                python_ast_cache.parse_python_ast(source, filename="sample.py")
            assert err.value.filename == "sample.py"
    with pytest.raises(python_ast_cache.PythonSourceEncodingError):
        python_ast_cache.read_python_ast(path, encoding="latin-1")
    with CodeMap(tmp_path) as repository:
        outline = repository.source.outline("sample.py")
        assert outline["parse_error"] == python_ast_cache.UNQUALIFIED_SOURCE_ENCODING
        assert outline["symbols"] == []
        bindings = repository.source.bindings("sample.py")
        assert bindings["availability"] == "unavailable" and bindings["facts"] == []
        observed = repository.source.observe("sample.py", literal="café")
        (hit,) = assert_records(observed["occurrences"])
        assert hit["enclosing_symbol"] is None and hit["occurrence_kind"] == "unknown"
        assert hit["literal"] == "café" and observed["observed_match_count"] == 1


@pytest.mark.parametrize("cookie", [b"ascii", b"latin-1", b"utf8", b"cp65001"])
def test_equivalent_declared_encoding_preserves_bindings_and_requalifies(
    tmp_path: Path, cookie: bytes
) -> None:
    path = tmp_path / "settings.py"
    path.write_bytes(b"# coding: unavailable-charset\nLABEL = 'field'\n")
    with CodeMap(tmp_path) as repository:
        assert repository.source.outline("settings.py")["parse_error"]
        assert (
            repository.source.bindings("settings.py")["availability"] == "unavailable"
        )
        raw = b"# coding: " + cookie + b"\nLABEL = 'field'\n"
        path.write_bytes(raw)
        repository.index.sync(["settings.py"])
        assert repository.source.outline("settings.py")["parse_error"] is None
        bindings = repository.source.bindings("settings.py")
        assert bindings["availability"] == "observed"
        assert any(
            r.get("literal") == "field" for r in assert_records(bindings["facts"])
        )
        assert (
            repository.source.read("settings.py::LABEL")["content"] == "LABEL = 'field'"
        )


@pytest.mark.parametrize(
    "raw",
    [
        b"# coding: no_such_codec\nx = 1\n",
        b"# coding: ascii\nx = '\xc3\xa9'\n",
        b"# coding: utf-7\nx = '+AOk-'\n",
        b"# first\fcomment\n# coding: latin-1\nx = '\xc3\xa9'\n",
    ],
)
def test_invalid_or_nonequivalent_cookie_never_acquires_a_cached_tree(
    raw: bytes,
) -> None:
    with python_ast_cache.python_ast_session():
        for source in (raw, raw.decode(), raw):
            with pytest.raises(python_ast_cache.PythonSourceEncodingError):
                python_ast_cache.parse_python_ast(source)


def test_third_physical_line_cookie_does_not_declare_an_encoding() -> None:
    raw = b"# first\rpass\r# coding: latin-1\rx = '\xc3\xa9'\r"
    assert ast.dump(python_ast_cache.parse_python_ast(raw)) == ast.dump(ast.parse(raw))


def test_declared_codec_can_change_an_identifier_into_an_apparent_string(
    tmp_path: Path,
) -> None:
    raw = b"# coding: unicode_escape\n" + rb'VALUE = "a\x22; other = 7; tail = \x22z"'
    (tmp_path / "settings.py").write_bytes(raw)
    assert any(
        isinstance(node, ast.Name) and node.id == "other"
        for node in ast.walk(ast.parse(raw))
    )
    with CodeMap(tmp_path) as repository:
        observed = repository.source.observe("settings.py", literal="other")
        (hit,) = assert_records(observed["occurrences"])
        assert hit["literal"] == "other" and hit["occurrence_kind"] == "unknown"
        assert hit["enclosing_symbol"] is None


def test_lossy_file_read_cannot_invent_cache_ownership(tmp_path: Path) -> None:
    path = tmp_path / "cache.py"
    path.write_bytes(
        b"import functools\n@functools.lru_cache()\ndef lookup(key): return '\xff'\n"
    )
    with pytest.raises(UnicodeDecodeError):
        python_ast_cache.read_python_ast(path, errors="replace")
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        assert repository.ownership.cache_findings(["cache.py"])["owners"] == []
        assert repository.source.outline("cache.py")["symbols"] == []
