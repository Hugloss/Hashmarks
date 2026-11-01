"""Bounded syntax reuse spans readiness, ends with the operation, and requalifies."""

from __future__ import annotations

from contextvars import Context, copy_context
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from test_source_syntax_consumers import (
    _native_parse_calls,
)
from test_source_syntax_consumers import (
    native_syntax as native_syntax,
)

from hashmarks import CodeMap
from hashmarks.codemap import providers
from hashmarks.codemap.providers import SourceSyntaxError, TreeSitterRangeProvider

if TYPE_CHECKING:
    from hashmarks.codemap.providers import StructuralTree


def _write(root: Path, name: str, raw: bytes) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


def test_cold_public_nomination_reuses_the_readiness_parse(
    tmp_path: Path,
    native_syntax: TreeSitterRangeProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = b"import test from 'node:test'; test('case', () => {});"
    other = b"export const finalMember = 1;"
    path = "tests/a.test.js"
    _write(tmp_path, path, raw)
    _write(tmp_path, "tests/z.test.js", other)
    calls = _native_parse_calls(native_syntax, monkeypatch)
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        first = codemap.verification.nomination(path)
        assert first["available"] is True
        assert calls.count(("javascript", raw)) == 1
        assert calls.count(("javascript", other)) == 1
        calls.clear()
        second = codemap.verification.nomination(path)
        assert second == first
        assert calls == [("javascript", raw)]


def test_existing_read_scope_shares_syntax_across_public_projections(
    tmp_path: Path,
    native_syntax: TreeSitterRangeProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = b"import test from 'node:test'; test('case', () => {});"
    path = "tests/member.test.js"
    _write(tmp_path, path, raw)
    calls = _native_parse_calls(native_syntax, monkeypatch)
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        with codemap.reads.session():
            source = codemap.source.ecmascript(path)
            nomination = codemap.verification.nomination(path)
            assert source["availability"] == "observed"
            assert nomination["available"] is True
            assert calls == [("javascript", raw)]
        codemap.source.ecmascript(path)
        assert calls == [("javascript", raw), ("javascript", raw)]


def test_reconciliation_and_verification_reuse_the_new_source_parse(
    tmp_path: Path,
    native_syntax: TreeSitterRangeProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = "tests/member.test.js"
    before = b"const previous = 1;"
    after = b"import test from 'node:test'; test('case', () => {});"
    member = _write(tmp_path, path, before)
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        member.write_bytes(after)
        calls = _native_parse_calls(native_syntax, monkeypatch)
        packet = codemap.verification.nomination(path)
    assert packet["available"] is True
    assert calls == [("javascript", after)]


def test_reuse_requires_exact_bytes_grammar_and_provider_signature(
    native_syntax: TreeSitterRangeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _native_parse_calls(native_syntax, monkeypatch)
    raw = b"client.send();"
    changed = b"client.close();"
    with native_syntax.syntax_session():
        first = native_syntax.syntax_tree(raw, "javascript")
        assert native_syntax.syntax_tree(raw, "javascript") is first
        native_syntax.version = "changed-provider"
        assert native_syntax.syntax_tree(raw, "javascript") is not first
        native_syntax.syntax_tree(changed, "javascript")
        native_syntax.syntax_tree(raw, "typescript")
    assert calls == [
        ("javascript", raw),
        ("javascript", raw),
        ("javascript", changed),
        ("typescript", raw),
    ]
    assert native_syntax._syntax_reuse.get() is None


@pytest.mark.parametrize("bound", ["count", "bytes"])
def test_session_reuse_is_bounded_and_retains_recent_inputs(
    native_syntax: TreeSitterRangeProvider,
    monkeypatch: pytest.MonkeyPatch,
    bound: str,
) -> None:
    if bound == "count":
        monkeypatch.setattr(providers, "SYNTAX_SESSION_MAX_TREES", 2)
    else:
        monkeypatch.setattr(providers, "SYNTAX_SESSION_MAX_SOURCE_BYTES", 8)
    calls = _native_parse_calls(native_syntax, monkeypatch)
    with native_syntax.syntax_session():
        first = native_syntax.syntax_tree(b"a();", "javascript")
        native_syntax.syntax_tree(b"b();", "javascript")
        assert native_syntax.syntax_tree(b"a();", "javascript") is first
        native_syntax.syntax_tree(b"c();", "javascript")
        assert native_syntax.syntax_tree(b"a();", "javascript") is first
        native_syntax.syntax_tree(b"b();", "javascript")
    assert calls == [
        ("javascript", source) for source in (b"a();", b"b();", b"c();", b"b();")
    ]


def test_oversized_source_is_parsed_without_retention(
    native_syntax: TreeSitterRangeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(providers, "SYNTAX_SESSION_MAX_SOURCE_BYTES", 2)
    calls = _native_parse_calls(native_syntax, monkeypatch)
    with native_syntax.syntax_session():
        native_syntax.syntax_tree(b"a();", "javascript")
        native_syntax.syntax_tree(b"a();", "javascript")
    assert calls == [("javascript", b"a();"), ("javascript", b"a();")]


def test_recovered_syntax_failure_is_reused_without_retaining_exception_state(
    native_syntax: TreeSitterRangeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _native_parse_calls(native_syntax, monkeypatch)
    raw = b"function broken( {"
    with native_syntax.syntax_session():
        for _ in range(2):
            with pytest.raises(SourceSyntaxError, match="native-syntax-parse-failed"):
                native_syntax.syntax_tree(raw, "javascript")
    assert calls == [("javascript", raw)]
    assert native_syntax._syntax_reuse.get() is None


def test_failed_operation_discards_its_syntax_state(
    native_syntax: TreeSitterRangeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _native_parse_calls(native_syntax, monkeypatch)
    raw = b"client.send();"
    with pytest.raises(RuntimeError, match="consumer failure"):
        with native_syntax.syntax_session():
            native_syntax.syntax_tree(raw, "javascript")
            raise RuntimeError("consumer failure")
    assert native_syntax._syntax_reuse.get() is None
    with native_syntax.syntax_session():
        native_syntax.syntax_tree(raw, "javascript")
    assert calls == [("javascript", raw), ("javascript", raw)]


def test_syntax_reuse_is_context_local_and_expired_contexts_do_not_retain_it(
    native_syntax: TreeSitterRangeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _native_parse_calls(native_syntax, monkeypatch)
    raw = b"client.send();"

    def observe() -> None:
        with native_syntax.syntax_session():
            native_syntax.syntax_tree(raw, "javascript")
            native_syntax.syntax_tree(raw, "javascript")

    with native_syntax.syntax_session():
        first = native_syntax.syntax_tree(raw, "javascript")
        Context().run(observe)
        assert native_syntax.syntax_tree(raw, "javascript") is first
        inherited = copy_context()
    assert calls == [("javascript", raw), ("javascript", raw)]
    inherited.run(observe)
    inherited.run(observe)
    assert calls == [("javascript", raw)] * 4


@pytest.mark.parametrize("indexed", [False, True])
@pytest.mark.parametrize("mutation", ["replace", "delete"])
def test_source_mutation_during_parse_withdraws_observation(
    tmp_path: Path,
    native_syntax: TreeSitterRangeProvider,
    monkeypatch: pytest.MonkeyPatch,
    indexed: bool,
    mutation: str,
) -> None:
    path = _write(tmp_path, "member.js", b"client.before();")
    original = native_syntax.syntax_tree

    def changed(raw: bytes, language: str) -> StructuralTree | None:
        tree = original(raw, language)
        if mutation == "replace":
            path.write_bytes(b"client.after();")
        else:
            path.unlink()
        return tree

    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        if indexed:
            codemap.index.sync()
        monkeypatch.setattr(native_syntax, "syntax_tree", changed)
        before_generation = codemap.store.generation()
        packet = codemap.source.ecmascript("member.js")
        assert codemap.store.generation() == before_generation
    assert packet["availability"] == "unavailable"
    assert packet["reason"] == "source-changed-during-observation"
    assert packet["freshness"] == "stale"
    assert packet["facts"] == []
    assert packet["observation_identity"] is None
    assert packet["negative_evidence"] == "not-admissible"


@pytest.mark.parametrize("surface", ["source", "nomination", "role"])
def test_provider_mutation_during_parse_withdraws_consumer_facts(
    tmp_path: Path,
    native_syntax: TreeSitterRangeProvider,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
) -> None:
    path = "tests/member.test.js"
    _write(tmp_path, path, b"import test from 'node:test';")
    original = native_syntax.syntax_tree

    def changed(raw: bytes, language: str) -> StructuralTree | None:
        tree = original(raw, language)
        native_syntax.version = "changed-during-parse"
        return tree

    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        monkeypatch.setattr(native_syntax, "syntax_tree", changed)
        if surface == "source":
            packet = codemap.source.ecmascript(path)
            assert packet["availability"] == "unavailable"
            assert packet["reason"] == "native-syntax-provider-changed"
            assert packet["facts"] == []
            assert packet["observation_identity"] is None
        elif surface == "nomination":
            packet = codemap.verification.nomination(path)
            assert packet["available"] is False
            assert packet["reason"] == "source-evidence-unqualified"
        else:
            with codemap.reads.session():
                role = codemap.verification._verification_path_kind(path)
            assert role["kind"] == "unknown"


@pytest.mark.parametrize("surface", ["nomination", "role"])
def test_source_mutation_during_parse_withdraws_native_verifier_facts(
    tmp_path: Path,
    native_syntax: TreeSitterRangeProvider,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
) -> None:
    path = "tests/member.test.js"
    member = _write(tmp_path, path, b"import test from 'node:test';")
    original = native_syntax.syntax_tree

    def changed(raw: bytes, language: str) -> StructuralTree | None:
        tree = original(raw, language)
        member.write_bytes(b"const example = 'node:test';")
        return tree

    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        monkeypatch.setattr(native_syntax, "syntax_tree", changed)
        if surface == "nomination":
            packet = codemap.verification.nomination(path)
            assert packet["available"] is False
            assert packet["reason"] == "source-evidence-unqualified"
        else:
            with codemap.reads.session():
                role = codemap.verification._verification_path_kind(path)
            assert role["kind"] == "unknown"
            assert role["reason"] == "source-changed-during-observation"
