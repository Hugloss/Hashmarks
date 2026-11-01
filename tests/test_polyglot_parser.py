from __future__ import annotations

import base64
from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records, assert_text

from hashmarks import CodeMap
from hashmarks.codemap.parsers import parse_source
from hashmarks.codemap.providers import TreeSitterRangeProvider


def test_native_node_syntax_keeps_declarations_and_static_module_references() -> None:
    source = "\n".join(
        (
            "import './side'",
            "import { value } from './value'",
            "const dep = require('./dep')",
            "export default async function load() { return value }",
            "export class Loader {}",
            "export interface Contract {}",
            "export type Choice = string",
            "export enum State {}",
            "export const run = async () => value",
            "const cancel = useCallback(() => value)",
            "",
        )
    )
    pytest.importorskip("tree_sitter_language_pack")
    artifact = parse_source(
        source,
        file_digest="sha256:source",
        language="typescript",
        range_provider=TreeSitterRangeProvider.auto(),
    )
    assert [(edge.target, edge.line) for edge in artifact.edges] == [
        ("./side", 1),
        ("./value", 2),
    ]
    assert [(symbol.name, symbol.kind) for symbol in artifact.symbols] == [
        ("dep", "binding"),
        ("load", "function"),
        ("Loader", "class"),
        ("Contract", "interface"),
        ("Choice", "type"),
        ("State", "enum"),
        ("run", "function"),
        ("cancel", "binding"),
    ]
    assert all(edge.confidence == "native" for edge in artifact.edges)
    assert artifact.parse_error is None


def test_missing_native_syntax_keeps_only_lexical_retrieval() -> None:
    artifact = parse_source(
        "\n// commentary\nexport const marker = 42\n",
        file_digest="sha256:marker",
        language="javascript",
    )
    assert artifact.symbols == artifact.edges == ()
    assert artifact.parse_error == "native-syntax-unavailable"
    assert any(row.token == "marker" and row.line == 3 for row in artifact.lexical)


@pytest.mark.parametrize(
    "case", [("javascript", "server.js"), ("typescript", "server.ts")]
)
@pytest.mark.parametrize("separator", ["\u0085", "\u2028", "\u2029"])
@pytest.mark.parametrize(("newline", "final_newline"), [("\n", True), ("\r\n", False)])
@pytest.mark.parametrize("native", [False, True])
def test_node_coordinates_preserve_native_or_unavailable_structure(
    tmp_path: Path,
    case: tuple[str, str],
    separator: str,
    newline: str,
    final_newline: bool,
    native: bool,
) -> None:
    language, filename = case
    source = newline.join(
        (
            f"const label = 'before{separator}after';",
            "import { dependency } from './dependency.js';",
            "export function handleRequest() { return dependency(label); }",
        )
    ) + (newline if final_newline else "")
    if native:
        pytest.importorskip("tree_sitter_language_pack")
    provider = TreeSitterRangeProvider.auto() if native else TreeSitterRangeProvider()
    artifact = parse_source(
        source, file_digest="fixture-source", language=language, range_provider=provider
    )
    assert [(edge.target, edge.line) for edge in artifact.edges] == (
        [("./dependency.js", 2)] if native else []
    )
    (tmp_path / filename).write_bytes(source.encode("utf-8"))
    with CodeMap(
        tmp_path, state_dir=tmp_path / ".state", range_provider=provider
    ) as codemap:
        codemap.index.sync()
        query = codemap.search.packet("handleRequest")
        source_observation = codemap.source.observe(filename, literal="handleRequest")
        body = codemap.source.read(f"{filename}::handleRequest") if native else None
        outline = codemap.source.outline(filename)
    assert provider.status().available is native
    symbols = [
        row
        for row in assert_records(query["results"])
        if row["name"] == "handleRequest"
    ]
    assert len(symbols) == (1 if native else 0)
    if native:
        assert symbols[0]["lines"] == [3, 3]
    else:
        assert outline["parse_error"] == "native-syntax-unavailable"
    occurrences = assert_records(source_observation["occurrences"])
    assert len(occurrences) == 1
    assert occurrences[0]["line"] == 3
    assert occurrences[0]["enclosing_symbol"] == ("handleRequest" if native else None)
    if body is not None:
        assert (
            body["content"]
            == "export function handleRequest() { return dependency(label); }"
        )
    assert query["freshness"] == source_observation["freshness"] == "unknown"


def _assert_source_coordinate_surfaces(
    codemap: CodeMap,
    filename: str,
    lines: list[str],
    content: bytes,
    added_lines: int,
) -> str:
    line = len(lines) + added_lines
    query = codemap.search.packet("needle_owner")
    hits = [
        row for row in assert_records(query["results"]) if row["name"] == "needle_owner"
    ]
    assert len(hits) == 1
    assert hits[0]["lines"] == [line, line]
    body = codemap.source.read(f"{filename}::needle_owner")
    assert body["lines"] == [line, line]
    assert body["content"] == lines[-1]
    observed = codemap.source.observe(filename, literal="needle_owner")
    occurrences = assert_records(observed["occurrences"])
    assert len(occurrences) == 1
    assert occurrences[0]["line"] == line
    assert occurrences[0]["enclosing_symbol"] == "needle_owner"
    header = codemap.source.observe(filename, literal="after")
    header_occurrences = assert_records(header["occurrences"])
    assert len(header_occurrences) == 1
    assert header_occurrences[0]["line"] == 1 + added_lines
    assert header_occurrences[0]["column"] == lines[0].index("after") + 1
    assert header_occurrences[0]["column_unit"] == "unicode-codepoint"
    matches = assert_records(codemap.source.grep("needle_owner")["matches"])
    assert [(row["line"], row["content"]) for row in matches] == [(line, lines[-1])]
    byte = content.index("é".encode("utf-8")) + 1
    receipt = codemap.source.range_receipt(filename, start_byte=byte, end_byte=byte + 1)
    assert (
        base64.b64decode(
            assert_text(assert_object(receipt["content"])["data"]), validate=True
        )
        == content[byte : byte + 1]
    )
    assert receipt["source_byte_count"] == len(content)
    assert query["freshness"] == observed["freshness"] == "unknown"
    assert observed["negative_evidence"] == "not-admissible"
    assert receipt["negative_evidence"] == "not-admissible"
    return assert_text(assert_object(observed["member"])["member_revision"])


@pytest.mark.parametrize(
    "case",
    [
        (
            "go",
            "owner.go",
            (
                "// café before__SEP__after",
                "package sample",
                'import "fmt"',
                'func needle_owner() string { return fmt.Sprint("value") }',
            ),
            "fmt",
            3,
        ),
        (
            "rust",
            "owner.rs",
            (
                'const LABEL: &str = "café before__SEP__after";',
                "use std::string::String;",
                "fn needle_owner() -> String { LABEL.to_owned() }",
            ),
            "std::string::String",
            2,
        ),
    ],
    ids=["go", "rust"],
)
@pytest.mark.parametrize("separator", ["\u0085", "\u2028", "\u2029"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("native", [False, True])
def test_polyglot_source_coordinates_survive_cache_reopen_and_source_edit(
    tmp_path: Path,
    case: tuple[str, str, tuple[str, ...], str, int],
    separator: str,
    newline: str,
    native: bool,
) -> None:
    language, filename, templates, import_target, import_line = case
    lines = [line.replace("__SEP__", separator) for line in templates]
    raw = newline.join(lines).encode("utf-8")
    path = tmp_path / filename
    path.write_bytes(raw)
    state = tmp_path / ".state"
    provider = TreeSitterRangeProvider.auto() if native else TreeSitterRangeProvider()
    if native:
        if not provider.available:
            pytest.skip("optional native range provider unavailable")
        assert provider.syntax_tree(raw, language) is not None

    with CodeMap(
        tmp_path,
        state_dir=state,
        artifact_db=state / "artifacts.sqlite3",
        range_provider=provider,
    ) as codemap:
        assert codemap.index.sync().parsed_artifacts == 1
        before_revision = _assert_source_coordinate_surfaces(
            codemap, filename, lines, raw, 0
        )
        warm = codemap.index.sync()
        assert (warm.parsed_artifacts, warm.reused_artifacts) == (0, 1)
        assert (
            _assert_source_coordinate_surfaces(codemap, filename, lines, raw, 0)
            == before_revision
        )
    with CodeMap(
        tmp_path,
        state_dir=state,
        artifact_db=state / "artifacts.sqlite3",
        range_provider=provider,
    ) as reopened:
        warm = reopened.index.sync()
        assert (warm.parsed_artifacts, warm.reused_artifacts) == (0, 1)
        assert (
            _assert_source_coordinate_surfaces(reopened, filename, lines, raw, 0)
            == before_revision
        )
        edited = ("// moved café" + newline).encode() + raw
        path.write_bytes(edited)
        unknown = reopened.source.observe(filename, literal="needle_owner")
        assert unknown["availability"] == "unavailable"
        assert unknown["negative_evidence"] == "not-admissible"
        assert reopened.index.sync().parsed_artifacts == 1
        assert (
            _assert_source_coordinate_surfaces(reopened, filename, lines, edited, 1)
            != before_revision
        )
    with CodeMap(
        tmp_path,
        state_dir=state,
        artifact_db=state / "artifacts.sqlite3",
        range_provider=provider,
    ) as edited_reopen:
        warm = edited_reopen.index.sync()
        assert (warm.parsed_artifacts, warm.reused_artifacts) == (0, 1)
        assert (
            _assert_source_coordinate_surfaces(
                edited_reopen, filename, lines, edited, 1
            )
            != before_revision
        )
    assert provider.status().available is native
    artifact = parse_source(
        edited.decode("utf-8"), file_digest="edited-fixture", language=language
    )
    assert [(edge.target, edge.line) for edge in artifact.edges] == [
        (import_target, import_line + 1)
    ]
    assert path.read_bytes() == edited
