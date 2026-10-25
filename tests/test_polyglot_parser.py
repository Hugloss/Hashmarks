from __future__ import annotations

from pathlib import Path

import pytest
from contract_assertions import assert_records

from hashmarks import CodeMap
from hashmarks.codemap.parsers import parse_source
from hashmarks.codemap.providers import TreeSitterRangeProvider


def test_node_outline_keeps_distinct_declarations_and_lexical_imports() -> None:
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
    artifact = parse_source(source, file_digest="sha256:source", language="typescript")
    assert [(edge.target, edge.line) for edge in artifact.edges] == [
        ("./side", 1),
        ("./value", 2),
        ("./dep", 3),
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
    assert artifact.symbols[-1].signature == "const cancel = …"
    assert artifact.symbols[-2].signature.endswith("=>")


def test_node_outline_ignores_unmatched_and_blank_lines() -> None:
    artifact = parse_source(
        "\n// commentary\nexport const marker = 42\n",
        file_digest="sha256:marker",
        language="javascript",
    )
    assert [
        (symbol.name, symbol.kind, symbol.start_line) for symbol in artifact.symbols
    ] == [("marker", "binding", 3)]
    assert artifact.edges == ()


@pytest.mark.parametrize(
    ("language", "filename"), [("javascript", "server.js"), ("typescript", "server.ts")]
)
@pytest.mark.parametrize("separator", ["\u0085", "\u2028", "\u2029"])
@pytest.mark.parametrize(("newline", "final_newline"), [("\n", True), ("\r\n", False)])
def test_node_outline_coordinates_match_canonical_source_lines_without_native_ranges(
    tmp_path: Path,
    language: str,
    filename: str,
    separator: str,
    newline: str,
    final_newline: bool,
) -> None:
    source = newline.join(
        (
            f"const label = 'before{separator}after';",
            "import { dependency } from './dependency.js';",
            "export function handleRequest() { return dependency(label); }",
        )
    ) + (newline if final_newline else "")
    artifact = parse_source(source, file_digest="fixture-source", language=language)
    assert [(edge.target, edge.line) for edge in artifact.edges] == [
        ("./dependency.js", 2)
    ]
    (tmp_path / filename).write_bytes(source.encode("utf-8"))
    provider = TreeSitterRangeProvider()
    with CodeMap(
        tmp_path, state_dir=tmp_path / ".state", range_provider=provider
    ) as codemap:
        codemap.index.sync()
        query = codemap.search.packet("handleRequest")
        source_observation = codemap.source.observe(filename, literal="handleRequest")
        body = codemap.source.read(f"{filename}::handleRequest")
    assert provider.status().available is False
    symbols = [
        row
        for row in assert_records(query["results"])
        if row["name"] == "handleRequest"
    ]
    assert len(symbols) == 1
    assert symbols[0]["lines"] == [3, 3]
    occurrences = assert_records(source_observation["occurrences"])
    assert len(occurrences) == 1
    assert occurrences[0]["line"] == 3
    assert occurrences[0]["enclosing_symbol"] == "handleRequest"
    assert (
        body["content"]
        == "export function handleRequest() { return dependency(label); }"
    )
    assert query["freshness"] == source_observation["freshness"] == "unknown"
