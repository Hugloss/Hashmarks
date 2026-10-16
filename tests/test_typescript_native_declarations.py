"""Native grammar ranges preserve lexical declaration identity and uncertainty."""

from pathlib import Path

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.parsers import parse_source
from hashmarks.codemap.providers import TreeSitterRangeProvider
from hashmarks.codemap.task_evidence_contract import (
    read_initial_projection,
    read_task_evidence,
)
from hashmarks.codemap.task_evidence_initial import decode_initial_packet


@pytest.fixture
def native_ranges() -> TreeSitterRangeProvider:
    pytest.importorskip("tree_sitter_language_pack")
    provider = TreeSitterRangeProvider.auto()
    assert provider.available
    return provider


def test_native_typescript_namespace_alias_and_private_callable_ranges(
    native_ranges: TreeSitterRangeProvider,
) -> None:
    source = """namespace transport {
  export type Callback<T> =
    (value: T) => Promise<void>;
  export interface Options {
    secure?: false;
  }
  export class Request {
    #cachedBody = async <T>(key: T): Promise<T> => {
      return key;
    };
  }
}
export const some = (items: string[]): (() => string) => {
  return function some() { return items[0]; };
};
"""
    artifact = parse_source(
        source,
        file_digest="before",
        language="typescript",
        range_provider=native_ranges,
    )
    actual = {
        row.qualname: (row.kind, row.start_line, row.end_line, row.parent)
        for row in artifact.symbols
    }
    assert actual == {
        "transport": ("namespace", 1, 12, None),
        "transport.Callback": ("type", 2, 3, "transport"),
        "transport.Options": ("interface", 4, 6, "transport"),
        "transport.Request": ("class", 7, 11, "transport"),
        "transport.Request.#cachedBody": ("method", 8, 10, "transport.Request"),
        "some": ("function", 13, 15, None),
        "some.some": ("function", 14, 14, "some"),
    }


def test_same_line_namespaces_do_not_merge_same_named_declarations(
    native_ranges: TreeSitterRangeProvider,
) -> None:
    source = (
        "namespace left { export interface Options {} } "
        "namespace right { export interface Options {} }\n"
        "namespace outer.inner { export type Value = string; }\n"
    )
    artifact = parse_source(
        source,
        file_digest="same-line",
        language="typescript",
        range_provider=native_ranges,
    )
    assert {row.qualname for row in artifact.symbols} == {
        "left",
        "left.Options",
        "right",
        "right.Options",
        "outer.inner",
        "outer.inner.Value",
    }


def test_callable_bindings_do_not_name_destructuring_or_computed_members(
    native_ranges: TreeSitterRangeProvider,
) -> None:
    source = """const { misleading } = source;
const plain = 1;
class Request {
  [selectName()] = () => 'computed';
  field = 'not callable';
  method = (value: string) => value;
}
"""
    artifact = parse_source(
        source,
        file_digest="bindings",
        language="typescript",
        range_provider=native_ranges,
    )
    assert [(row.qualname, row.kind) for row in artifact.symbols] == [
        ("plain", "binding"),
        ("Request", "class"),
        ("Request.method", "method"),
    ]


def test_unavailable_native_ranges_keep_the_advisory_capability_explicit() -> None:
    provider = TreeSitterRangeProvider()
    assert provider.status().as_dict()["available"] is False
    artifact = parse_source(
        "export type Callback =\n  (value: string) => void;\n",
        file_digest="advisory",
        language="typescript",
        range_provider=provider,
    )
    assert [
        (row.qualname, row.start_line, row.end_line) for row in artifact.symbols
    ] == [
        ("Callback", 1, 1),
    ]
    assert "tree-sitter" not in artifact.parser


def test_namespace_member_survives_reopen_and_revision_change(
    tmp_path: Path,
    native_ranges: TreeSitterRangeProvider,
) -> None:
    source = tmp_path / "request.ts"
    source.write_text("namespace api {\n export type Result =\n  string;\n}\n")
    state = tmp_path / "state"
    with CodeMap(tmp_path, state_dir=state) as codemap:
        codemap.range_provider = native_ranges
        codemap.sync()
        first = codemap.outline("request.ts")
        symbols = first["symbols"]
        assert isinstance(symbols, list)
        assert any(
            row["qualname"] == "api.Result"
            and (row["start_line"], row["end_line"]) == (2, 3)
            for row in symbols
        )
    source.write_text(
        "namespace api {\n export type Result =\n  string |\n  number;\n}\n"
    )
    with CodeMap(tmp_path, state_dir=state) as codemap:
        codemap.range_provider = native_ranges
        codemap.sync()
        second = codemap.outline("request.ts")
        assert second["file_digest"] != first["file_digest"]
        symbols = second["symbols"]
        assert isinstance(symbols, list)
        assert any(
            row["qualname"] == "api.Result"
            and (row["start_line"], row["end_line"]) == (2, 4)
            for row in symbols
        )


@pytest.mark.parametrize("result_mode", ["default", "initial"])
@pytest.mark.parametrize("limit", [1, 3, 20])
def test_literal_file_discloses_common_and_private_names_without_owner_promotion(
    tmp_path: Path,
    native_ranges: TreeSitterRangeProvider,
    result_mode: str,
    limit: int,
) -> None:
    (tmp_path / "handler.ts").write_text(
        "export const some = () => { return function some() {}; };\n"
        "namespace api { export type Options = { http2?: false }; }\n"
        "class Request { #cachedBody = () => 'body'; }\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.range_provider = native_ranges
        codemap.sync()
        for requested, expected, line in [
            ("some", "some", 1),
            ("Options", "api.Options", 2),
            ("Request.#cachedBody", "Request.#cachedBody", 3),
        ]:
            task = f"Inspect {requested} declarations. Source: handler.ts"
            action = codemap.task_action_map(task, limit=limit)
            response = codemap.task_evidence(task, limit=limit, result_mode=result_mode)
            packet = (
                read_initial_projection(decode_initial_packet(response))
                if result_mode == "initial"
                else read_task_evidence(response)
            )
            assert packet["retrieval"]["results"][0].get("symbol") == expected
            first = packet["retrieval"]["results"][0]
            assert (first.get("start_line"), first.get("end_line")) == (line, line)
            assert packet["retrieval"]["ownership_authority"] is False
            assert len(packet["retrieval"]["results"]) <= limit
            owner, admitted = packet["ownership"]["owner"], action["admitted_edit"]
            assert (owner is None) == (admitted is None)
            if owner is not None and admitted is not None:
                for key in ("path", "qualname", "start_line", "end_line"):
                    assert owner.get(key) == admitted.get(key)
            assert (
                packet["ownership"]["authority_proof_identity"]
                == action["ownership_authority"]["authority_proof_identity"]
            )
            assert (
                packet["ownership"]["ambiguity"]["ambiguous"]
                == action["ambiguity"]["ambiguous"]
            )


def test_literal_file_disclosure_preserves_duplicate_scopes_and_denied_visibility(
    tmp_path: Path,
    native_ranges: TreeSitterRangeProvider,
) -> None:
    (tmp_path / "handler.ts").write_text(
        "namespace left { export interface Options {} }\n"
        "namespace right { export interface Options {} }\n"
    )
    task = "Inspect Options declarations. Source: handler.ts"
    with CodeMap(tmp_path) as codemap:
        codemap.range_provider = native_ranges
        codemap.sync()
        action = codemap.task_action_map(task)
        packet = codemap.task_evidence(task)
        assert {row.get("symbol") for row in packet["retrieval"]["results"][:2]} == {
            "left.Options",
            "right.Options",
        }
        assert packet["ownership"]["owner"] == action["admitted_edit"]
        assert packet["ownership"]["ambiguity"] == action["ambiguity"]
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "handler.ts"\nvisibility = "deny"\n'
    )
    with CodeMap(tmp_path) as codemap:
        codemap.range_provider = native_ranges
        codemap.sync()
        packet = codemap.task_evidence(task)
        assert all(
            row["path"] != "handler.ts" for row in packet["retrieval"]["results"]
        )
