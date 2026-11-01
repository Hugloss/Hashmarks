"""Native source structure has one owner and cannot be restored by lexical text."""

from __future__ import annotations

from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records

from hashmarks import CodeMap
from hashmarks.codemap import ecmascript_syntax
from hashmarks.codemap.parsers import artifact_key_for, parse_source
from hashmarks.codemap.providers import TreeSitterRangeProvider


@pytest.fixture
def native() -> TreeSitterRangeProvider:
    pytest.importorskip("tree_sitter_language_pack")
    provider = TreeSitterRangeProvider.auto()
    assert provider.available
    return provider


def test_index_module_edges_are_the_source_native_projection(
    tmp_path: Path, native: TreeSitterRangeProvider
) -> None:
    raw = b"""// import { fake } from './comment';
const inert = "require('./string')";
const template = `import './template'`;
import {
  actual as local
} from './actual';
export { local as exposed } from './reexport';
import type { Shape } from './types';
import './escaped\\u002dname';
function f(require, fetch) { require('./shadowed'); return fetch('/api'); }
const dependency = require('./unresolved');
"""
    (tmp_path / "owner.ts").write_bytes(raw)
    with CodeMap(tmp_path, range_provider=native) as codemap:
        codemap.index.sync()
        edges = assert_records(codemap.relationships.deps("owner.ts")["edges"])
        packet = codemap.source.ecmascript("owner.ts", limit=500)
    modules = [
        row
        for row in assert_records(packet["facts"])
        if row["kind"] == "module-declaration"
    ]
    observed = {
        (row["module_specifier"], row["line"])
        for row in modules
        if row["module_specifier"] is not None
    }
    assert observed == {("./actual", 4), ("./reexport", 7), ("./types", 8)}
    assert {(row["target"], row["line"]) for row in edges} == observed
    assert all(row["confidence"] == "native" for row in edges)
    assert modules[2]["type_only"] is True
    assert modules[3]["module_specifier"] is None
    assert packet["semantic_resolution"] == "not-performed"
    calls = [
        row for row in assert_records(packet["facts"]) if row["kind"] == "call-site"
    ]
    assert calls
    assert all(row["resolved_target"] is None for row in calls)


@pytest.mark.parametrize("language", ["javascript", "typescript", "tsx"])
@pytest.mark.parametrize("mode", ["absent", "disabled", "raises"])
def test_unavailable_native_parser_never_recovers_regex_structure(
    native: TreeSitterRangeProvider,
    monkeypatch: pytest.MonkeyPatch,
    language: str,
    mode: str,
) -> None:
    def fail(*_: object) -> None:
        raise RuntimeError("native parser failed")

    if mode == "raises":
        monkeypatch.setattr(native, "syntax_tree", fail)
    provider = (
        None
        if mode == "absent"
        else TreeSitterRangeProvider()
        if mode == "disabled"
        else native
    )
    artifact = parse_source(
        "import { value } from './value';\nexport function owner() { return value; }",
        file_digest="source",
        language=language,
        range_provider=provider,
    )
    assert artifact.symbols == artifact.edges == ()
    assert artifact.outline == ""
    assert artifact.parse_error is not None
    assert any(row.token == "owner" for row in artifact.lexical)


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (
            b"import './before'; export function incomplete( {",
            "native-syntax-parse-failed",
        ),
        (b"import './before'; // invalid: \xff", "invalid-utf8"),
        (b"import './before'; // null: \x00", "null-byte-text"),
    ],
)
def test_index_preserves_original_bytes_and_rejects_partial_native_trees(
    tmp_path: Path,
    native: TreeSitterRangeProvider,
    raw: bytes,
    reason: str,
) -> None:
    (tmp_path / "owner.ts").write_bytes(raw)
    with CodeMap(tmp_path, range_provider=native) as codemap:
        result = codemap.index.sync()
        outline = codemap.source.outline("owner.ts")
        packet = codemap.source.ecmascript("owner.ts")
        assert codemap.relationships.deps("owner.ts")["edges"] == []
    assert result.parse_errors == 1
    assert outline["parse_error"] == packet["reason"] == reason
    assert outline["symbols"] == []
    assert packet["availability"] == "unavailable"
    assert packet["negative_evidence"] == "not-admissible"


def test_optional_provider_isolates_unencodable_source_only_input(
    native: TreeSitterRangeProvider,
) -> None:
    seed = parse_source("", file_digest="invalid", language="javascript")
    artifact = native.enrich(seed, "export function owner() {} // \ud800", "javascript")
    assert artifact.symbols == artifact.edges == ()
    assert artifact.parse_error == "native-syntax-parse-failed"


def test_native_traversal_bound_cannot_leave_partial_index_structure(
    native: TreeSitterRangeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ecmascript_syntax, "MAX_SYNTAX_NODES", 8)
    artifact = parse_source(
        "import './early'; export function owner() { return call(other(value)); }",
        file_digest="bounded",
        language="javascript",
        range_provider=native,
    )
    assert artifact.symbols == artifact.edges == ()
    assert artifact.parse_error == "native-syntax-node-bound"


def test_native_overloads_use_siblings_and_scope_instead_of_line_text(
    native: TreeSitterRangeProvider,
) -> None:
    artifact = parse_source(
        """export function convert(
  value: { item: string }
): { item: string };
// A comment containing } and ; is not a scope boundary.
export function convert(value: { item: string }) { return value; }
namespace other { export function convert(value: string): string; }
class Client { send(value: string): void; send(value: unknown) {} }
class Separate { static send(value: string): void; send(value: unknown) {} }
""",
        file_digest="overloads",
        language="typescript",
        range_provider=native,
    )
    assert artifact.parse_error is None
    symbols = {row.qualname: row for row in artifact.symbols}
    assert symbols["convert"].start_line == 5
    assert not any(name.startswith("convert@") for name in symbols)
    assert symbols["other.convert"].start_line == 6
    assert [row.qualname for row in artifact.symbols if row.parent == "Client"] == [
        "Client.send"
    ]
    assert len([row for row in artifact.symbols if row.parent == "Separate"]) == 2


def test_shared_artifact_cache_keeps_typescript_and_tsx_grammars_distinct(
    tmp_path: Path, native: TreeSitterRangeProvider
) -> None:
    raw = b"export const View = () => <Panel />;\n"
    (tmp_path / "view.ts").write_bytes(raw)
    (tmp_path / "view.tsx").write_bytes(raw)
    state = tmp_path / ".state"
    artifacts = tmp_path / "artifacts.sqlite3"
    keys = {
        artifact_key_for("same-bytes", "typescript", path=path, range_provider=native)
        for path in ("view.ts", "view.tsx")
    }
    assert len(keys) == 2
    with CodeMap(
        tmp_path, state_dir=state, artifact_db=artifacts, range_provider=native
    ) as codemap:
        result = codemap.index.sync()
        before = codemap.source.outline("view.tsx")
        assert result.parsed_artifacts == 2
        assert result.parse_errors == 1
        assert codemap.source.outline("view.ts")["parse_error"] is not None
        assert before["parse_error"] is None
        assert [row["name"] for row in assert_records(before["symbols"])] == ["View"]
        packet = codemap.source.ecmascript("view.tsx")
        assert assert_object(packet["parser"])["grammar"] == "tsx"
    with CodeMap(
        tmp_path, state_dir=state, artifact_db=artifacts, range_provider=native
    ) as reopened:
        result = reopened.index.sync()
        assert (result.parsed_artifacts, result.reused_artifacts) == (0, 2)
        assert reopened.source.outline("view.tsx")["symbols"] == before["symbols"]


def test_provider_drift_cannot_publish_or_cache_new_signature_over_old_syntax(
    tmp_path: Path, native: TreeSitterRangeProvider
) -> None:
    from hashmarks.codemap.providers import StructuralTree

    class DriftingProvider(TreeSitterRangeProvider):
        calls = 0

        def syntax_tree(self, source: bytes, language: str) -> StructuralTree | None:
            tree = super().syntax_tree(source, language)
            self.calls += 1
            if self.calls == 1:
                self.version = "after-parse"
            return tree

    provider = DriftingProvider(
        native._parser_factory,
        version="before-parse",
        binding_version=native._binding_version,
    )
    (tmp_path / "owner.ts").write_text(
        "import './dependency'; export function owner() {}\n", encoding="utf-8"
    )
    with CodeMap(
        tmp_path,
        state_dir=tmp_path / ".state",
        artifact_db=tmp_path / "artifacts.sqlite3",
        range_provider=provider,
    ) as codemap:
        first = codemap.index.sync()
        before = codemap.store.file_row("owner.ts")
        assert before is not None
        assert first.parse_errors == 1
        assert before["parse_error"] == "native-syntax-provider-changed"
        assert before["outline"] == ""
        assert codemap.store.all_edges("import") == []

        # The failed capture is still bound to the old parser identity. A stable
        # subsequent sync must parse under the new one, not reuse that failure.
        second = codemap.index.sync()
        after = codemap.store.file_row("owner.ts")
        assert after is not None
        assert second.parsed_artifacts == 1
        assert second.parse_errors == 0
        assert after["parse_error"] is None
        assert after["artifact_key"] != before["artifact_key"]
        assert provider.calls == 2
        assert [
            row["name"]
            for row in assert_records(codemap.source.outline("owner.ts")["symbols"])
        ] == ["owner"]
