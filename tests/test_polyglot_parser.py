from __future__ import annotations

from hashmarks.codemap.parsers import parse_source


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
