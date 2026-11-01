"""Public source bindings retain admission, byte provenance and unknown authority."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from contract_assertions import (
    assert_integer,
    assert_object,
    assert_records,
    assert_text,
)

from hashmarks import CodeMap
from hashmarks.codemap import source_bindings
from hashmarks.codemap.providers import TreeSitterRangeProvider

if TYPE_CHECKING:
    from hashmarks.codemap.providers import SourceRangeProvider, StructuralTree


SOURCES = (
    (
        "member.py",
        'import example as client\r\nlabel = "é"\r\nsend = client.send\r\nsend(label)\r\n',
    ),
    (
        "member.ts",
        'import * as client from "example";\r\nconst label = "é";\r\nconst send = client.send;\r\nsend(label);\r\n',
    ),
)


def _provider(path: str) -> TreeSitterRangeProvider:
    if path.endswith(".py"):
        return TreeSitterRangeProvider()
    provider = TreeSitterRangeProvider.auto()
    if not provider.available:
        pytest.skip("optional native ECMAScript grammar unavailable")
    return provider


def _assert_range(value: object, raw: bytes) -> tuple[int, int]:
    span = assert_object(value)
    start = assert_integer(span["start_byte"])
    end = assert_integer(span["end_byte"])
    assert 0 <= start <= end <= len(raw)
    return start, end


def _assert_fact(fact: dict[str, object], raw: bytes) -> None:
    _assert_range(fact["range"], raw)
    _assert_range(assert_object(fact["scope"])["range"], raw)
    for support in assert_records(fact["supporting_ranges"]):
        _assert_range(support, raw)
    if fact["binding_range"] is not None:
        _assert_range(fact["binding_range"], raw)
    if fact["expression"] is not None:
        expression = assert_object(fact["expression"])
        start, end = _assert_range(expression["range"], raw)
        if not expression["text_truncated"]:
            assert expression["text"] == raw[start:end].decode("utf-8")
    assert fact["qualification"] in {"qualified", "conditional", "unknown"}
    assert fact["runtime_target"] == "not-established"
    assert assert_text(fact["evidence_identity"])


@pytest.mark.parametrize(("path", "source"), SOURCES)
def test_public_bindings_expose_exact_ranges_and_separate_authority(
    tmp_path: Path, path: str, source: str
) -> None:
    raw = source.encode("utf-8")
    (tmp_path / path).write_bytes(raw)
    with CodeMap(tmp_path, range_provider=_provider(path)) as codemap:
        codemap.index.sync()
        packet = codemap.source.bindings(path)
        member, _ = codemap.source.member(path)
        repeated = codemap.source.bindings(path, max_bytes=len(raw), limit=500)
    assert packet["schema"] == "hashmarks.source-bindings.v1"
    assert packet["member"] == member
    assert packet["availability"] == "observed"
    assert packet["completeness"] == "complete"
    assert packet["truncation"] == "not-truncated"
    assert packet["module_resolution"] == "not-performed"
    assert packet["runtime_target_resolution"] == "not-performed"
    assert assert_object(packet["semantic_coverage"])["state"] == "incomplete"
    assert packet["negative_evidence"] == "not-admissible"
    assert packet["authority"] == "repository-evidence-only"
    assert packet["execution_effect"] == "none"
    assert packet["freshness"] == "unknown"
    facts = assert_records(packet["facts"])
    assert packet["returned_fact_count"] == packet["observed_fact_count"] == len(facts)
    assert any(row["kind"] == "call-site" for row in facts)
    for fact in facts:
        _assert_fact(fact, raw)
    assert packet["observation_identity"] == repeated["observation_identity"]


@pytest.mark.parametrize(("path", "source"), SOURCES)
def test_binding_result_limit_clips_after_qualification(
    tmp_path: Path, path: str, source: str
) -> None:
    (tmp_path / path).write_text(source, encoding="utf-8")
    with CodeMap(tmp_path, range_provider=_provider(path)) as codemap:
        codemap.index.sync()
        full = codemap.source.bindings(path)
        small = codemap.source.bindings(path, limit=1)
    assert small["facts"] == assert_records(full["facts"])[:1]
    assert small["observed_fact_count"] == full["observed_fact_count"]
    assert small["returned_fact_count"] == 1
    assert small["completeness"] == "incomplete"
    assert small["truncation"] == "truncated"
    assert small["negative_evidence"] == "not-admissible"


@pytest.mark.parametrize(("path", "source"), SOURCES)
def test_binding_revisions_edits_deletes_and_reopen(
    tmp_path: Path, path: str, source: str
) -> None:
    member = tmp_path / path
    member.write_text(source, encoding="utf-8")
    state = tmp_path / "state"
    with CodeMap(tmp_path, state_dir=state, range_provider=_provider(path)) as codemap:
        codemap.index.sync()
        before = codemap.source.bindings(path)
        member.write_text(source.replace("send", "close"), encoding="utf-8")
        stale = codemap.source.bindings(path)
        codemap.index.sync()
        after = codemap.source.bindings(path)
    with CodeMap(tmp_path, state_dir=state, range_provider=_provider(path)) as reopened:
        reopened.index.sync()
        current = reopened.source.bindings(path)
        member.unlink()
        deleted = reopened.source.bindings(path)
    assert stale["availability"] == "unavailable"
    assert stale["reason"] == "member-revision-mismatch"
    assert stale["facts"] == []
    assert before["observation_identity"] != after["observation_identity"]
    assert current["observation_identity"] == after["observation_identity"]
    assert deleted["availability"] == "unavailable"
    assert deleted["reason"] == "member-not-present"
    assert deleted["facts"] == []


@pytest.mark.parametrize(("path", "source"), SOURCES)
def test_mutation_during_binding_projection_withdraws_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str, source: str
) -> None:
    member = tmp_path / path
    member.write_text(source, encoding="utf-8")
    original = source_bindings._binding_projection

    def mutating_projection(
        provider: SourceRangeProvider, raw: bytes, grammar: str, limit: int
    ) -> tuple[list[dict[str, object]], int]:
        result = original(provider, raw, grammar, limit)
        member.write_text(source.replace("send", "close"), encoding="utf-8")
        return result

    with CodeMap(tmp_path, range_provider=_provider(path)) as codemap:
        codemap.index.sync()
        monkeypatch.setattr(source_bindings, "_binding_projection", mutating_projection)
        packet = codemap.source.bindings(path)
    assert packet["availability"] == "unavailable"
    assert packet["freshness"] == "stale"
    assert packet["reason"] == "source-changed-during-observation"
    assert packet["facts"] == []
    assert packet["observation_identity"] is None


@pytest.mark.parametrize(
    ("path", "raw", "reason"),
    [
        ("invalid.py", b"def broken(:", "source-binding-syntax-unqualified"),
        ("invalid.py", b"value = '\xff'", "invalid-utf8"),
        ("invalid.py", b"value = '\x00'", "source-binding-syntax-unqualified"),
        ("invalid.ts", b"const broken = (", "native-syntax-parse-failed"),
        ("invalid.ts", b"const broken = '\xff'", "invalid-utf8"),
        ("other.rs", b"fn main() {}", "unsupported-source-language"),
    ],
)
def test_unqualified_source_never_supplies_known_empty_bindings(
    tmp_path: Path, path: str, raw: bytes, reason: str
) -> None:
    (tmp_path / path).write_bytes(raw)
    with CodeMap(tmp_path, range_provider=_provider(path)) as codemap:
        codemap.index.sync()
        packet = codemap.source.bindings(path)
    assert packet["reason"] == reason
    assert packet["availability"] == "unavailable"
    assert packet["completeness"] == "unknown"
    assert packet["observed_fact_count"] is None
    assert packet["facts"] == []
    assert packet["observation_identity"] is None
    assert packet["negative_evidence"] == "not-admissible"


@pytest.mark.parametrize(
    ("path", "raw"), [("empty.py", b"# comment\n"), ("empty.js", b"// comment\n")]
)
def test_empty_binding_projection_is_not_semantic_absence(
    tmp_path: Path, path: str, raw: bytes
) -> None:
    (tmp_path / path).write_bytes(raw)
    with CodeMap(tmp_path, range_provider=_provider(path)) as codemap:
        codemap.index.sync()
        packet = codemap.source.bindings(path)
    assert packet["availability"] == "observed"
    assert packet["completeness"] == "complete"
    assert packet["observed_fact_count"] == 0
    assert packet["negative_evidence"] == "not-admissible"
    assert assert_object(packet["semantic_coverage"])["state"] == "incomplete"


def test_missing_ecmascript_provider_keeps_python_binding_capability(
    tmp_path: Path,
) -> None:
    (tmp_path / "member.py").write_text("import example\nexample.send()\n")
    (tmp_path / "member.js").write_text("const send = client.send; send();")
    with CodeMap(tmp_path, range_provider=TreeSitterRangeProvider()) as codemap:
        codemap.index.sync()
        python = codemap.source.bindings("member.py")
        ecmascript = codemap.source.bindings("member.js")
    assert python["availability"] == "observed"
    assert ecmascript["availability"] == "unavailable"
    assert ecmascript["reason"] == "native-syntax-unavailable"
    assert ecmascript["facts"] == []


def test_provider_drift_withdraws_binding_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "member.ts").write_text("const send = client.send; send();")
    provider = _provider("member.ts")
    original = provider.syntax_tree

    def changing_tree(raw: bytes, grammar: str) -> StructuralTree | None:
        tree = original(raw, grammar)
        provider.version = "changed-provider"
        return tree

    with CodeMap(tmp_path, range_provider=provider) as codemap:
        codemap.index.sync()
        monkeypatch.setattr(provider, "syntax_tree", changing_tree)
        packet = codemap.source.bindings("member.ts")
    assert packet["availability"] == "unavailable"
    assert packet["reason"] == "source-binding-producer-changed"
    assert packet["freshness"] == "stale"
    assert packet["facts"] == []


@pytest.mark.parametrize(
    ("limit", "max_bytes"),
    [(False, 1), (0, 1), (501, 1), (1, True), (1, 0), (1, 8_388_609)],
)
def test_binding_limits_are_validated_before_reading(
    tmp_path: Path, limit: int, max_bytes: int
) -> None:
    with (
        CodeMap(tmp_path) as codemap,
        pytest.raises(ValueError, match="limit|max_bytes"),
    ):
        codemap.source.bindings("missing.py", limit=limit, max_bytes=max_bytes)


def test_byte_bound_does_not_publish_a_partial_python_scope(tmp_path: Path) -> None:
    (tmp_path / "member.py").write_text("import example\nexample.send()\n")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.source.bindings("member.py", max_bytes=4)
    assert packet["availability"] == "unavailable"
    assert packet["reason"] == "source-size-bound"
    assert packet["facts"] == []


def test_binding_and_syntax_projections_share_the_admitted_ecmascript_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = b'import { send } from "example"; const call = send; call();'
    (tmp_path / "member.tsx").write_bytes(raw)
    provider = _provider("member.tsx")
    original = provider._parse_syntax
    calls: list[tuple[bytes, str]] = []

    def counted(source: bytes, grammar: str) -> StructuralTree:
        calls.append((source, grammar))
        return original(source, grammar)

    monkeypatch.setattr(provider, "_parse_syntax", counted)
    with CodeMap(tmp_path, range_provider=provider) as codemap:
        with codemap.reads.session():
            binding = codemap.source.bindings("member.tsx")
            syntax = codemap.source.ecmascript("member.tsx")
            assert binding["availability"] == syntax["availability"] == "observed"
            assert binding["member"] == syntax["member"]
            assert binding["parser"] == syntax["parser"]
            assert calls == [(raw, "tsx")]
        codemap.source.bindings("member.tsx")
    assert calls == [(raw, "tsx"), (raw, "tsx")]


def test_interpreter_change_during_projection_withdraws_source_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "member.py").write_text("import example\nexample.send()\n")
    original = source_bindings._binding_projection

    def changed_interpreter(
        provider: SourceRangeProvider, raw: bytes, grammar: str, limit: int
    ) -> tuple[list[dict[str, object]], int]:
        facts = original(provider, raw, grammar, limit)
        monkeypatch.setattr(source_bindings, "BINDING_INTERPRETER_SIGNATURE", "changed")
        return facts

    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        monkeypatch.setattr(source_bindings, "_binding_projection", changed_interpreter)
        packet = codemap.source.bindings("member.py")
    assert packet["reason"] == "source-binding-producer-changed"
    assert packet["availability"] == "unavailable"
    assert packet["freshness"] == "stale"
    assert packet["facts"] == []
