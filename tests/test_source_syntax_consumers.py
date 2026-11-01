"""Source and verification consume the same admitted native syntax owner."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from contract_assertions import assert_object, assert_records

from hashmarks import CodeMap
from hashmarks.codemap import ecmascript_syntax
from hashmarks.codemap.providers import TreeSitterRangeProvider

if TYPE_CHECKING:
    from hashmarks.codemap.providers import StructuralParser, StructuralTree


class _CountingParser:
    def __init__(
        self,
        parser: StructuralParser,
        grammar: str,
        calls: list[tuple[str, bytes]],
    ) -> None:
        self.parser = parser
        self.grammar = grammar
        self.calls = calls

    def parse(self, source: bytes) -> StructuralTree:
        self.calls.append((self.grammar, source))
        return self.parser.parse(source)


@pytest.fixture
def native_syntax() -> TreeSitterRangeProvider:
    pytest.importorskip("tree_sitter_language_pack")
    provider = TreeSitterRangeProvider.auto()
    assert provider.available
    return provider


def _native_parse_calls(
    provider: TreeSitterRangeProvider, monkeypatch: pytest.MonkeyPatch
) -> list[tuple[str, bytes]]:
    """Count actual native parse invocations, not facade method calls."""
    calls: list[tuple[str, bytes]] = []
    original = provider._parser

    def counted(language: str) -> StructuralParser:
        return _CountingParser(original(language), language, calls)

    monkeypatch.setattr(provider, "_parser", counted)
    return calls


@pytest.mark.parametrize(
    ("suffix", "raw", "grammar"),
    [
        ("js", b"export const run = () => client.send();", "javascript"),
        ("mjs", b"export const run = () => client.send();", "javascript"),
        ("cjs", b"const run = () => client.send();", "javascript"),
        (
            "jsx",
            b"export const view = <Panel action={() => client.send()} />;",
            "javascript",
        ),
        ("ts", b"export const run = (client: Client) => client.send();", "typescript"),
        ("mts", b"export const run = (client: Client) => client.send();", "typescript"),
        ("cts", b"const run = (client: Client) => client.send();", "typescript"),
        ("tsx", b"export const view = <Panel action={() => client.send()} />;", "tsx"),
    ],
)
def test_index_source_and_verifier_share_native_grammar(
    tmp_path: Path,
    native_syntax: TreeSitterRangeProvider,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    raw: bytes,
    grammar: str,
) -> None:
    path = f"tests/example.test.{suffix}"
    (tmp_path / "tests").mkdir()
    (tmp_path / path).write_bytes(raw)
    calls = _native_parse_calls(native_syntax, monkeypatch)
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        assert calls == [(grammar, raw)]
        calls.clear()
        packet = codemap.source.ecmascript(path)
        assert packet["availability"] == "observed"
        assert assert_object(packet["parser"])["grammar"] == grammar
        assert calls == [(grammar, raw)]
        calls.clear()
        with codemap.verification.reads.session():
            role = codemap.verification._verification_path_kind(path)
        assert role["kind"] == "verifier"
        assert calls == [(grammar, raw)]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"import {\n test as check\n} from 'node:test';", "verifier"),
        (b"// import test from 'node:test';", "verification-support"),
        (b"""const text = "import test from 'node:test';";""", "verification-support"),
        (b"const text = `import test from 'node:test';`;", "verification-support"),
        (b"import 'node:\\u0074est';", "unknown"),
        (b"const candidate = import('node:test');", "verification-support"),
    ],
)
def test_node_test_role_reuses_one_admitted_parse(
    tmp_path: Path,
    native_syntax: TreeSitterRangeProvider,
    monkeypatch: pytest.MonkeyPatch,
    raw: bytes,
    expected: str,
) -> None:
    path = "tests/support.js"
    (tmp_path / "tests").mkdir()
    (tmp_path / path).write_bytes(raw)
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        calls = _native_parse_calls(native_syntax, monkeypatch)
        with codemap.verification.reads.session():
            role = codemap.verification._verification_path_kind(path)
    assert role["kind"] == expected
    assert calls == [("javascript", raw)]


@pytest.mark.parametrize(
    "raw",
    [
        b"import test from 'node:test'; function broken( {",
        b"import test from 'node:test'; const value = '\xff';",
        b"import test from 'node:test'; const value = '\x00';",
    ],
)
def test_canonical_parse_failure_stays_unknown_across_consumers(
    tmp_path: Path, native_syntax: TreeSitterRangeProvider, raw: bytes
) -> None:
    path = "tests/example.test.js"
    (tmp_path / "tests").mkdir()
    (tmp_path / path).write_bytes(raw)
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        packet = codemap.source.ecmascript(path)
        nomination = codemap.verification.nomination(path)
        with codemap.verification.reads.session():
            role = codemap.verification._verification_path_kind(path)
    assert packet["availability"] == "unavailable"
    assert packet["facts"] == []
    assert packet["negative_evidence"] == "not-admissible"
    assert role["kind"] == "unknown"
    assert nomination["available"] is False
    assert nomination["reason"] == "source-evidence-unqualified"


def test_module_projection_preserves_source_rows_and_type_only_qualification(
    native_syntax: TreeSitterRangeProvider,
) -> None:
    raw = (
        b"import type { Test } from 'node:test';\n"
        b"import {\n test as check\n} from 'node:test';\n"
        b"export { check } from 'node:test';\n"
        b"import 'node:\\u0074est';\n"
    )
    tree = native_syntax.syntax_tree(raw, "typescript")
    assert tree is not None
    facts, _ = ecmascript_syntax.ecmascript_facts(tree, raw, 200)
    modules = ecmascript_syntax.module_declarations(tree, raw)
    assert modules == [row for row in facts if row["kind"] == "module-declaration"]
    assert [row["type_only"] for row in modules] == [True, False, False, False]
    assert [row["module_specifier"] for row in modules] == [
        "node:test",
        "node:test",
        "node:test",
        None,
    ]


def test_module_bounds_never_restore_node_test_from_a_partial_projection(
    tmp_path: Path,
    native_syntax: TreeSitterRangeProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = "tests/support.js"
    (tmp_path / "tests").mkdir()
    (tmp_path / path).write_text("import test from 'node:test';\nconst extra = {};")
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        monkeypatch.setattr(ecmascript_syntax, "MAX_SYNTAX_NODES", 4)
        packet = codemap.source.ecmascript(path)
        with codemap.verification.reads.session():
            role = codemap.verification._verification_path_kind(path)
    assert packet["availability"] == "unavailable"
    assert packet["reason"] == "native-syntax-node-bound"
    assert assert_records(packet["facts"]) == []
    assert role["kind"] == "unknown"
