"""Native source facts retain exact ranges and never infer alias/call identity."""

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
from hashmarks.codemap import ecmascript_syntax
from hashmarks.codemap.providers import TreeSitterRangeProvider

if TYPE_CHECKING:
    from hashmarks import Digest
    from hashmarks.codemap.providers import StructuralTree


@pytest.fixture
def native_syntax() -> TreeSitterRangeProvider:
    pytest.importorskip("tree_sitter_language_pack")
    provider = TreeSitterRangeProvider.auto()
    assert provider.available
    return provider


@pytest.fixture
def source_bytes() -> bytes:
    return (
        Path(__file__).parent / "fixtures/ecmascript_source/consumer.ts"
    ).read_bytes()


def _facts(packet: dict[str, object], kind: str) -> list[dict[str, object]]:
    return [row for row in assert_records(packet["facts"]) if row["kind"] == kind]


def _text(value: object) -> str:
    return assert_text(assert_object(value)["text"])


def test_native_import_aliases_and_object_binding_facts(
    tmp_path: Path, native_syntax: TreeSitterRangeProvider, source_bytes: bytes
) -> None:
    (tmp_path / "consumer.ts").write_bytes(source_bytes)
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        packet = codemap.source.ecmascript("consumer.ts")
        source_observation = codemap.source.observe("consumer.ts")
    assert packet["schema"] == "hashmarks.ecmascript-source-observation.v1"
    assert packet["availability"] == "observed"
    assert packet["completeness"] == "complete"
    assert packet["freshness"] == source_observation["freshness"] == "unknown"
    assert packet["observed_fact_count"] == len(assert_records(packet["facts"]))
    assert {
        (row["name"], row["alias"], row["type_only"])
        for row in _facts(packet, "import-binding")
    } == {
        ("default", "primary", False),
        ("gateway", "client", False),
        ("Channel", "Channel", True),
        ("*", "registry", False),
        ("Channel", "SourceChannel", True),
    }
    assert [
        (row["name"], row["alias"]) for row in _facts(packet, "export-binding")
    ] == [("gateway", "publicClient")]
    transport = next(
        row for row in _facts(packet, "binding") if _text(row["binding"]) == "transport"
    )
    assert transport["declaration_kind"] == "const"
    assert _text(transport["initializer"]) == "client"
    send = next(
        row
        for row in _facts(packet, "destructured-binding")
        if _text(row["binding"]) == "transmit"
    )
    assert assert_object(send["property"])["name"] == "send"
    assert send["computed"] is False
    assert send["declaration_range"] is not None


def test_dynamic_properties_reassignment_and_shadowing_remain_unresolved(
    tmp_path: Path, native_syntax: TreeSitterRangeProvider, source_bytes: bytes
) -> None:
    (tmp_path / "consumer.ts").write_bytes(source_bytes)
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        packet = codemap.source.ecmascript("consumer.ts")
    assert packet["semantic_resolution"] == "not-performed"
    calls = _facts(packet, "call-site")
    assert all(row["resolved_target"] is None for row in calls)
    assert any(_text(row["callee"]) == "transmit" for row in calls)
    assert any(row["call_kind"] == "construct" for row in calls)
    computed = [row for row in _facts(packet, "property-access") if row["computed"]]
    assert [assert_object(row["property"])["name"] for row in computed] == [None] * 3
    assert [assert_object(row["property"])["literal_text"] for row in computed] == [
        "send",
        None,
        None,
    ]
    assignments = _facts(packet, "assignment")
    assert len(assignments) == 1
    assert (_text(assignments[0]["left"]), _text(assignments[0]["right"])) == (
        "mutable",
        "registry.gateway",
    )
    same_text = [row for row in calls if _text(row["callee"]) == "transport.send"]
    assert len(same_text) == 2
    assert same_text[0]["scope"] != same_text[1]["scope"]
    assert same_text[0]["evidence_identity"] != same_text[1]["evidence_identity"]


def test_comments_strings_and_type_queries_do_not_claim_value_calls(
    tmp_path: Path, native_syntax: TreeSitterRangeProvider, source_bytes: bytes
) -> None:
    (tmp_path / "consumer.ts").write_bytes(source_bytes)
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        packet = codemap.source.ecmascript("consumer.ts")
    assert all(
        "Only" not in _text(row["callee"]) for row in _facts(packet, "call-site")
    )
    type_facts = [
        row
        for row in assert_records(packet["facts"])
        if row["syntax_context"] == "type-syntax"
    ]
    assert [row["kind"] for row in type_facts] == ["property-access"]
    assert assert_object(type_facts[0]["property"])["name"] == "send"
    assert packet["negative_evidence"] == "not-admissible"
    assert packet["authority"] == "repository-evidence-only"
    assert packet["execution_effect"] == "none"


@pytest.mark.parametrize(
    ("filename", "raw", "grammar"),
    [
        ("plain.js", b"const alias = registry; alias.send();", "javascript"),
        (
            "component.jsx",
            b"const view = <Panel action={() => registry.send()} />;",
            "javascript",
        ),
        ("typed.ts", b"const alias: Channel = registry; alias.send();", "typescript"),
        ("typed.tsx", b"const view = <Panel action={() => registry.send()} />;", "tsx"),
    ],
)
def test_supported_grammars_use_native_expression_nodes(
    tmp_path: Path,
    native_syntax: TreeSitterRangeProvider,
    filename: str,
    raw: bytes,
    grammar: str,
) -> None:
    (tmp_path / filename).write_bytes(raw)
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        packet = codemap.source.ecmascript(filename)
    assert packet["availability"] == "observed"
    assert assert_object(packet["parser"])["grammar"] == grammar
    assert len(_facts(packet, "call-site")) == 1


def test_native_byte_ranges_preserve_unicode_crlf_and_optional_calls(
    tmp_path: Path, native_syntax: TreeSitterRangeProvider
) -> None:
    raw = "const café = registry;\r\ncafé?.send?.('é');\r\n".encode()
    (tmp_path / "consumer.ts").write_bytes(raw)
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        packet = codemap.source.ecmascript("consumer.ts")
    call = _facts(packet, "call-site")[0]
    offsets = assert_object(call["range"])
    assert (
        raw[assert_integer(offsets["start_byte"]) : assert_integer(offsets["end_byte"])]
        == "café?.send?.('é')".encode()
    )
    assert call["optional"] is True
    assert _facts(packet, "property-access")[0]["optional"] is True
    assert packet["coordinate_system"] == "zero-based-half-open-bytes"


def test_projection_limit_counts_whole_member_and_cannot_prove_absence(
    tmp_path: Path, native_syntax: TreeSitterRangeProvider, source_bytes: bytes
) -> None:
    (tmp_path / "consumer.ts").write_bytes(source_bytes)
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        full = codemap.source.ecmascript("consumer.ts")
        limited = codemap.source.ecmascript("consumer.ts", limit=2)
    assert limited["observed_fact_count"] == full["observed_fact_count"]
    assert limited["returned_fact_count"] == 2
    assert limited["completeness"] == "incomplete"
    assert limited["truncation"] == "truncated"
    assert limited["negative_evidence"] == "not-admissible"
    assert limited["facts"] == assert_records(full["facts"])[:2]
    assert limited["observation_identity"] != full["observation_identity"]


def test_observation_reuses_canonical_member_and_revision_identity(
    tmp_path: Path, native_syntax: TreeSitterRangeProvider
) -> None:
    path = tmp_path / "consumer.ts"
    path.write_text("registry.send();\n", encoding="utf-8")
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        before = codemap.source.ecmascript("consumer.ts")
        repeated = codemap.source.ecmascript("consumer.ts", max_bytes=100)
        member, _ = codemap.source.member("consumer.ts")
        path.write_text("registry.send();\n// new revision\n", encoding="utf-8")
        unreconciled = codemap.source.ecmascript("consumer.ts")
        codemap.index.sync()
        after = codemap.source.ecmascript("consumer.ts")
    assert before["member"] == member
    assert repeated["observation_identity"] == before["observation_identity"]
    assert unreconciled["availability"] == "unavailable"
    assert unreconciled["reason"] == "member-revision-mismatch"
    assert unreconciled["observation_identity"] is None
    assert after["observation_identity"] != before["observation_identity"]
    assert (
        _facts(after, "call-site")[0]["evidence_identity"]
        != _facts(before, "call-site")[0]["evidence_identity"]
    )


@pytest.mark.parametrize(
    ("filename", "raw", "reason"),
    [
        ("invalid.ts", b"const broken = (", "native-syntax-parse-failed"),
        ("invalid.ts", b"const text = '\xff';", "invalid-utf8"),
        ("invalid.ts", b"const text = '\x00';", "null-byte-text"),
        ("other.py", b"value = 1\n", "unsupported-source-language"),
    ],
)
def test_unsupported_or_failed_observation_is_unknown(
    tmp_path: Path,
    native_syntax: TreeSitterRangeProvider,
    filename: str,
    raw: bytes,
    reason: str,
) -> None:
    (tmp_path / filename).write_bytes(raw)
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        packet = codemap.source.ecmascript(filename)
    assert packet["availability"] == "unavailable"
    assert packet["completeness"] == "unknown"
    assert packet["reason"] == reason
    assert packet["observed_fact_count"] is None
    assert packet["facts"] == []
    assert packet["observation_identity"] is None
    assert packet["negative_evidence"] == "not-admissible"


def test_absent_optional_provider_has_no_lexical_fallback(tmp_path: Path) -> None:
    (tmp_path / "consumer.ts").write_text("registry.send();", encoding="utf-8")
    with CodeMap(tmp_path, range_provider=TreeSitterRangeProvider()) as codemap:
        codemap.index.sync()
        packet = codemap.source.ecmascript("consumer.ts")
    assert packet["reason"] == "native-syntax-unavailable"
    assert packet["availability"] == "unavailable"
    assert packet["observed_fact_count"] is None
    assert packet["facts"] == []
    assert assert_object(packet["parser"])["signature"] is None


def test_source_and_native_traversal_bounds_leave_unknown_evidence(
    tmp_path: Path,
    native_syntax: TreeSitterRangeProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "consumer.ts").write_text("registry.send();", encoding="utf-8")
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        oversized = codemap.source.ecmascript("consumer.ts", max_bytes=2)
        monkeypatch.setattr(ecmascript_syntax, "MAX_SYNTAX_NODES", 2)
        bounded = codemap.source.ecmascript("consumer.ts")
    assert oversized["reason"] == "source-size-bound"
    assert bounded["reason"] == "native-syntax-node-bound"
    assert bounded["observed_fact_count"] is None
    assert bounded["facts"] == []
    assert bounded["completeness"] == "unknown"


@pytest.mark.parametrize("raw", [b"", b"// no covered expressions\n"])
def test_empty_native_syntax_has_scoped_coverage_without_negative_evidence(
    tmp_path: Path, native_syntax: TreeSitterRangeProvider, raw: bytes
) -> None:
    (tmp_path / "empty.ts").write_bytes(raw)
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        packet = codemap.source.ecmascript("empty.ts")
    assert packet["availability"] == "observed"
    assert packet["completeness"] == "complete"
    assert packet["observed_fact_count"] == packet["returned_fact_count"] == 0
    assert packet["negative_evidence"] == "not-admissible"


@pytest.mark.parametrize(
    ("limit", "max_bytes"),
    [(False, 1), (501, 1), (0, 1), (1, True), (1, 0), (1, 8_388_609)],
)
def test_invalid_bounds_are_rejected_before_source_access(
    tmp_path: Path, limit: int, max_bytes: int
) -> None:
    with CodeMap(tmp_path) as codemap:
        with pytest.raises(ValueError, match="limit|max_bytes"):
            codemap.source.ecmascript("missing.ts", limit=limit, max_bytes=max_bytes)


def test_generation_change_during_native_parse_is_stale(
    tmp_path: Path,
    native_syntax: TreeSitterRangeProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "consumer.ts").write_text("registry.send();", encoding="utf-8")
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        parse = native_syntax.syntax_tree
        before = codemap.store.generation()

        def observed_tree(raw: bytes, language: str) -> StructuralTree | None:
            tree = parse(raw, language)
            monkeypatch.setattr(codemap.store, "generation", lambda: before + 1)
            return tree

        monkeypatch.setattr(native_syntax, "syntax_tree", observed_tree)
        packet = codemap.source.ecmascript("consumer.ts")
    assert packet["availability"] == "observed"
    assert packet["freshness"] == "stale"


def test_syntax_uses_one_canonical_byte_read_without_following_imports(
    tmp_path: Path,
    native_syntax: TreeSitterRangeProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "consumer.ts").write_text(
        "import {client} from './missing'; client.send();", encoding="utf-8"
    )
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        read_bytes = codemap.source.file_store.read_bytes_stable
        reads: list[Path] = []

        def captured(path: Path) -> tuple[bytes, Digest]:
            reads.append(path)
            return read_bytes(path)

        monkeypatch.setattr(codemap.source.file_store, "read_bytes_stable", captured)
        packet = codemap.source.ecmascript("consumer.ts")
    assert packet["availability"] == "observed"
    assert reads == [tmp_path / "consumer.ts"]


def test_native_destructuring_defaults_and_parameter_scope_stay_distinct(
    tmp_path: Path, native_syntax: TreeSitterRangeProvider
) -> None:
    (tmp_path / "consumer.ts").write_text(
        "const callback = ({send: transmit = fallback, receive = other}) => transmit();\n"
        "const {send: direct = fallback, nested: {close}, ...rest} = registry;\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        packet = codemap.source.ecmascript("consumer.ts")
    destructured = {
        _text(row["binding"]): row for row in _facts(packet, "destructured-binding")
    }
    assert _text(destructured["transmit"]["default"]) == "fallback"
    assert _text(destructured["receive"]["default"]) == "other"
    assert destructured["transmit"]["declaration_range"] is None
    assert _text(destructured["direct"]["default"]) == "fallback"
    assert destructured["direct"]["declaration_range"] is not None
    assert (
        destructured["close"]["pattern_range"]
        != destructured["direct"]["pattern_range"]
    )
    assert destructured["rest"]["rest"] is True
    assert assert_object(destructured["rest"]["property"])["name"] is None


def test_expression_previews_and_escaped_keys_do_not_invent_static_names(
    tmp_path: Path, native_syntax: TreeSitterRangeProvider
) -> None:
    long_name = "a" * 300
    (tmp_path / "consumer.ts").write_text(
        f"registry[{long_name}]();\nregistry['s\\u0065nd']();\nregistry['se' + 'nd']();\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        packet = codemap.source.ecmascript("consumer.ts")
    properties = [
        assert_object(row["property"]) for row in _facts(packet, "property-access")
    ]
    assert all(row["name"] is row["literal_text"] is None for row in properties)
    preview = assert_object(properties[0]["expression"])
    assert preview["text_truncated"] is True
    assert len(assert_text(preview["text"]).encode()) == 256
    assert packet["completeness"] == "complete"


def test_missing_denied_and_link_members_publish_no_syntax(
    tmp_path: Path, native_syntax: TreeSitterRangeProvider
) -> None:
    (tmp_path / "consumer.ts").write_text("registry.send();", encoding="utf-8")
    (tmp_path / ".env").write_text("PRIVATE=repository.value", encoding="utf-8")
    (tmp_path / "alias.ts").symlink_to("consumer.ts")
    with CodeMap(tmp_path, range_provider=native_syntax) as codemap:
        codemap.index.sync()
        packets = [
            codemap.source.ecmascript(path)
            for path in (".env", "alias.ts", "missing.ts")
        ]
    assert all(packet["availability"] == "unavailable" for packet in packets)
    assert all(packet["facts"] == [] for packet in packets)
    assert all(packet["observation_identity"] is None for packet in packets)
    assert all(packet["observed_fact_count"] is None for packet in packets)
