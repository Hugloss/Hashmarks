"""Initial disclosure preserves producer authority and accounts for omissions."""

from __future__ import annotations

import base64
import json
import zlib
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest
from contract_assertions import assert_array, assert_object, assert_text

from hashmarks.codemap import CodeMap
from hashmarks.codemap.task_evidence_initial import (
    decode_initial_collection,
    decode_initial_packet,
    encode_initial_packet,
    initial_packet_identity,
    initial_task_evidence,
)
from hashmarks.codemap.task_evidence_types import InitialTaskEvidenceEnvelope
from hashmarks.evidence_presentation import FORMATS, presentation_response
from hashmarks.evidence_presentation_conformance import validate_evidence_presentation
from hashmarks.mcp_contract import tool_contract
from hashmarks.mcp_surface import HashmarksMcpSurface, McpSurfaceError


def test_initial_string_table_preserves_json_types_unicode_and_future_fields() -> None:
    packet = {
        "schema": "hashmarks.task-evidence-initial.v2",
        "source_evidence_identity": "sha256:source",
        "evidence_packet_identity": "sha256:initial",
        "0": ["0", 0, False, None, 0.0, "💚é", {"future": "💚ê", "empty": ""}],
    }
    packet["evidence_packet_identity"] = initial_packet_identity(packet)
    encoded = encode_initial_packet(packet)
    decoded = decode_initial_packet(json.loads(json.dumps(encoded)))
    assert decoded == packet
    assert [type(value) for value in decoded["0"][:5]] == [
        str,
        int,
        bool,
        type(None),
        float,
    ]
    data = encoded["data"]
    assert isinstance(data, dict)
    value = data[next(iter(data))]
    assert isinstance(value, list)
    value[1] = False
    with pytest.raises(ValueError, match="semantic identity"):
        decode_initial_packet(encoded)


def _compressible_initial() -> dict[str, Any]:
    packet = {
        "schema": "hashmarks.task-evidence-initial.v2",
        "source_evidence_identity": "sha256:source",
        "facts": [
            {
                "path": "répository/worker.py",
                "symbol": "Worker.run",
                "types": ["0", 0, False, None, 0.0],
            }
            for _ in range(80)
        ],
    }
    packet["evidence_packet_identity"] = initial_packet_identity(packet)
    return packet


def _legacy_compressed_initial() -> dict[str, Any]:
    packet = {
        "schema": "hashmarks.task-evidence-initial.v2",
        "source_evidence_identity": "sha256:source",
        "facts": ["0", 0, False, None, 0.0, "💚é"],
    }
    packet["evidence_packet_identity"] = initial_packet_identity(packet)
    wire = json.loads(json.dumps(encode_initial_packet(packet)))
    assert wire["encoding"]["kind"] == "json-string-table.v1"
    payload = json.dumps(
        {"strings": wire["encoding"]["strings"], "data": wire["data"]},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    wire["encoding"] = {
        "kind": "json-string-table.v1+zlib",
        "decoded_bytes": len(payload),
    }
    wire["data"] = base64.b64encode(zlib.compress(payload)).decode("ascii")
    assert decode_initial_packet(wire) == packet
    return wire


def test_legacy_compressed_initial_remains_readable() -> None:
    _legacy_compressed_initial()


def test_compressed_initial_preserves_identity_types_and_all_records() -> None:
    packet = _compressible_initial()
    encoded = encode_initial_packet(packet)
    assert encoded["encoding"]["kind"] == "json+zlib"
    decoded = decode_initial_packet(json.loads(json.dumps(encoded)))
    assert decoded == packet
    assert decoded["evidence_packet_identity"] == packet["evidence_packet_identity"]
    assert len(decoded["facts"]) == 80
    assert [type(value) for value in decoded["facts"][0]["types"]] == [
        str,
        int,
        bool,
        type(None),
        float,
    ]


@pytest.mark.parametrize(
    "mutation",
    [
        "bool-size",
        "wrong-size",
        "over-bound",
        "invalid-base64",
        "truncated",
        "trailing-data",
        "concatenated",
        "changed-identity",
    ],
)
@pytest.mark.parametrize("legacy", [False, True])
def test_compressed_initial_rejects_corrupt_or_unbounded_payload(
    mutation: str, legacy: bool
) -> None:
    encoded = (
        _legacy_compressed_initial()
        if legacy
        else json.loads(json.dumps(encode_initial_packet(_compressible_initial())))
    )
    raw = base64.b64decode(encoded["data"])
    if mutation == "bool-size":
        encoded["encoding"]["decoded_bytes"] = True
    elif mutation == "wrong-size":
        encoded["encoding"]["decoded_bytes"] -= 1
    elif mutation == "over-bound":
        encoded["encoding"]["decoded_bytes"] = 2**32
    elif mutation == "invalid-base64":
        encoded["data"] = "!"
    elif mutation == "truncated":
        encoded["data"] = base64.b64encode(raw[:-1]).decode("ascii")
    elif mutation == "trailing-data":
        encoded["data"] = base64.b64encode(raw + b"extra").decode("ascii")
    elif mutation == "concatenated":
        encoded["data"] = base64.b64encode(raw + zlib.compress(b"{}")).decode("ascii")
    else:
        encoded["evidence_packet_identity"] = "sha256:changed"
    with pytest.raises(ValueError, match="initial"):
        decode_initial_packet(encoded)


@pytest.mark.parametrize(
    "payload",
    [
        b'{"facts":[],"facts":[]}',
        b'{"facts":[{"nested":false,"nested":false}]}',
        b'{"schema":"shadow"}',
        b"[]",
    ],
)
def test_direct_json_initial_rejects_duplicate_keys_headers_and_nonobjects(
    payload: bytes,
) -> None:
    encoded = json.loads(json.dumps(encode_initial_packet(_compressible_initial())))
    encoded["encoding"]["decoded_bytes"] = len(payload)
    encoded["data"] = base64.b64encode(zlib.compress(payload)).decode("ascii")
    semantic = json.loads(payload)
    if isinstance(semantic, dict) and "facts" in semantic:
        # A permissive parser would produce exactly these facts and pass the
        # identity check. Duplicate-key rejection must independently stop it.
        encoded["evidence_packet_identity"] = initial_packet_identity(
            {
                "schema": encoded["schema"],
                "source_evidence_identity": encoded["source_evidence_identity"],
                **semantic,
            }
        )
    with pytest.raises(ValueError, match="initial"):
        decode_initial_packet(encoded)


def test_large_initial_falls_back_without_reducing_valid_capacity() -> None:
    packet = _compressible_initial()
    packet["future_fact"] = "x" * 1_048_577
    packet["evidence_packet_identity"] = initial_packet_identity(packet)
    encoded = encode_initial_packet(packet)
    assert encoded["encoding"]["kind"] == "json-string-table.v1"
    assert decode_initial_packet(encoded) == packet


@pytest.mark.parametrize(
    "mutation",
    [
        "bool-prefix",
        "oversized-prefix",
        "duplicate-string",
        "bad-index",
        "leading-zero",
        "header-shadow",
    ],
)
def test_initial_string_table_rejects_malformed_references(mutation: str) -> None:
    packet = encode_initial_packet(
        {
            "schema": "hashmarks.task-evidence-initial.v2",
            "source_evidence_identity": "sha256:source",
            "evidence_packet_identity": "sha256:initial",
            "a": "b",
        }
    )
    packet = json.loads(json.dumps(packet))
    if mutation == "bool-prefix":
        packet["encoding"]["strings"][0][0] = False
    elif mutation == "oversized-prefix":
        packet["encoding"]["strings"][0][0] = 1
    elif mutation == "duplicate-string":
        packet["encoding"]["strings"][1] = [1, ""]
    elif mutation == "bad-index":
        packet["data"]["0"] = "999"
    elif mutation == "leading-zero":
        packet["data"]["0"] = "01"
    else:
        packet["encoding"]["strings"] = [[0, "schema"]]
        packet["data"] = {"0": 1}
    with pytest.raises(ValueError, match="initial"):
        decode_initial_packet(packet)


def _decoded_task_matches(matches: dict[str, Any]) -> dict[str, Any]:
    matches = deepcopy(matches)
    encoding = matches.pop("matches_encoding")
    assert encoding["kind"] == "columns-rows.v1"
    matches["matches"] = [
        dict(zip(encoding["columns"], row, strict=True)) for row in matches["matches"]
    ]
    return matches


def _assert_initial_display(
    response: dict[str, Any], packet: Mapping[str, object]
) -> None:
    logical = decode_initial_packet(packet)
    transported = json.loads(json.dumps(response, sort_keys=True))
    assert (
        validate_evidence_presentation(
            transported["result"], transported["presentation"]
        )["valid"]
        is True
    )
    assert response["result"] == packet
    assert response["presentation"]["reference_space"] == "decoded-initial-data"
    groups = response["presentation"]["groups"]
    if response["presentation"]["format"] != "text":
        owner = next(
            group for group in groups if group["family"] == "ownership_evidence"
        )["findings"][0]
        assert owner["details"] == logical["ownership"]["owner"]
        assert (
            owner["source_context"]["ambiguity"]["ambiguous"]
            == logical["ownership"]["ambiguity"]["ambiguous"]
        )
        assert (
            owner["source_context"]["ambiguity"]["reason"]
            == logical["ownership"]["ambiguity"]["reason"]
        )
        assert (
            owner["source_context"]["proof_scope_complete"]
            == logical["ownership"]["proof_scope_complete"]
        )
        assert response["presentation"]["unprojected_sections"] == [
            {
                "source_ref": "",
                "reason": "native-packet-details-not-displayed",
                "native_item_count": len(logical),
            }
        ]
    if response["presentation"]["format"] == "text":
        text = response["presentation"]["text"]
        assert "Ownership:" in text
        assert "freshness:" in text
        assert "Ambiguity:" in text
        assert "omissions do not establish absence" in text
        assert "tests were not executed" in text
        for row in logical["retrieval"]["results"]:
            assert row["path"] in text


@pytest.mark.parametrize("ambiguous", [False, True])
def test_initial_profile_preserves_authority_and_source_identity(
    tmp_path: Path, ambiguous: bool
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/a.py").write_text("def widget():\n    return 1\n")
    if ambiguous:
        (tmp_path / "src/b.py").write_text("def widget():\n    return 2\n")
    (tmp_path / "tests/test_widget.py").write_text(
        "from src.a import widget\ndef test_widget():\n    assert widget() == 1\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        native = cast("dict[str, Any]", codemap.tasks.evidence("Fix widget"))
        before = deepcopy(native)
        initial = initial_task_evidence(native)
        api = codemap.tasks.evidence("Fix widget", result_mode="initial")
    assert native == before
    assert api["schema"] == "hashmarks.task-evidence-initial.v2"
    assert initial["source_evidence_identity"] == native["evidence_packet_identity"]
    assert api["evidence_packet_identity"] != api["source_evidence_identity"]
    for key in ("status", "authority", "proof_scope", "proof_scope_complete", "basis"):
        assert initial["ownership"][key] == native["ownership"][key]
    assert (
        initial["ownership"]["ambiguity"]["ambiguous"]
        == (native["ownership"]["ambiguity"]["ambiguous"])
    )
    assert initial["freshness"] == native["freshness"]
    assert initial["provenance"] == native["provenance"]
    assert initial["verification"]["plan"] == native["verification"]["plan"]
    assert "task_matches" in initial["verification"]["relevance"]
    assert (
        _decoded_task_matches(initial["verification"]["relevance"]["task_matches"])
        == native["verification"]["relevance"]["task_matches"]
    )
    if native["ownership"]["owner"] is None:
        assert initial["ownership"]["owner"] is None
    else:
        assert initial["ownership"]["owner"] is not None
        assert (
            initial["ownership"]["owner"]["path"]
            == (native["ownership"]["owner"]["path"])
        )
    assert initial["initial_projection"]["negative_evidence_from_omissions"] == (
        "not-admissible"
    )
    assert "/related" in initial["initial_projection"]["omissions"]["sections"]
    for mode in FORMATS:
        response = presentation_response(
            "task_evidence", api, result_mode="initial", format=mode
        )
        tool_contract("task_evidence").validate_response(
            response, result_mode="initial", presentation=mode
        )
        if mode != "none":
            _assert_initial_display(response, api)
    _assert_mcp_initial_authority(tmp_path, api)


def _assert_mcp_initial_authority(
    root: Path, expected: InitialTaskEvidenceEnvelope
) -> None:
    surface = HashmarksMcpSurface(str(root))
    try:
        observed = surface.task_evidence("Fix widget", result_mode="initial")
        assert observed["schema"] == expected["schema"]
        assert (
            decode_initial_packet(observed)["ownership"]["status"]
            == decode_initial_packet(expected)["ownership"]["status"]
        )
    finally:
        surface.close()


def test_initial_mode_rejects_unknown_mode_before_observation(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap, pytest.raises(ValueError, match="result_mode"):
        codemap.tasks.evidence("Fix widget", result_mode="invented")
    surface = HashmarksMcpSurface(str(tmp_path))
    try:
        with pytest.raises(McpSurfaceError, match="result_mode") as caught:
            surface.task_evidence("Fix widget", result_mode="invented")
        assert caught.value.reason == "invalid-request"
    finally:
        surface.close()


def test_initial_class_table_keeps_future_fields_and_preserves_source_packet(
    tmp_path: Path,
) -> None:
    (tmp_path / "backend.py").write_text(
        "class ChannelBackend:\n    def subscribe(self): pass\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = cast(
            "dict[str, Any]", codemap.tasks.evidence("Inspect ChannelBackend")
        )
    context = next(
        row["class_declarations"]
        for row in packet["retrieval"]["results"]
        if "class_declarations" in row
    )
    context["declarations"][0]["future_source_fact"] = {
        "state": "unknown",
        "source": "producer-owned",
    }
    original = deepcopy(packet)
    projected = initial_task_evidence(packet)
    returned = next(
        row["class_declarations"]
        for row in projected["retrieval"]["results"]
        if "class_declarations" in row
    )
    assert "declarations_encoding" not in returned
    assert returned == context
    assert packet == original


def test_initial_disclosure_keeps_admitted_owner_and_verification_alternatives(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("def widget(): return 1\n")
    (tmp_path / "tests").mkdir()
    for index in range(9):
        (tmp_path / "tests" / f"test_widget_{index}.py").write_text(
            "from owner import widget\n"
            f"def test_widget_{index}(): assert widget() == 1\n"
        )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = cast("dict[str, Any]", codemap.tasks.evidence("Inspect owner.py."))
    assert packet["ownership"]["owner"]["path"] == "owner.py"
    rows = packet["retrieval"]["results"]
    owner_row = next(row for row in rows if row["path"] == "owner.py")
    # Simulate a full producer packet where the admitted owner follows the
    # canonical display prefix. Projection must conserve its source locator.
    packet["retrieval"]["results"] = [
        {"path": f"other_{i}.py", "symbol": "other"} for i in range(3)
    ] + [owner_row]
    original = deepcopy(packet)
    initial = initial_task_evidence(packet)
    assert packet == original
    assert owner_row in initial["retrieval"]["results"]
    relevance = packet["verification"]["relevance"]
    projected = deepcopy(initial["verification"]["relevance"])
    assert "candidates_encoding" in projected
    decoded_candidates = decode_initial_collection(
        projected["candidates"], projected["candidates_encoding"]
    )
    assert [row["path"] for row in decoded_candidates] == [
        row["path"] for row in relevance["candidates"]
    ]
    for source, returned in zip(
        relevance["candidates"], decoded_candidates, strict=True
    ):
        for key in (
            "direct_reference",
            "indirect_reference",
            "reference_symbols",
            "indirect_reference_symbols",
            "source_revision",
        ):
            if key in source:
                assert returned[key] == source[key]
    ledger = initial["initial_projection"]["omissions"]["collections"]
    assert ledger["/verification/relevance/candidates"]["omitted"] == 0
    assert initial["ownership"]["authority"] == packet["ownership"]["authority"]
    initial["evidence_packet_identity"] = initial_packet_identity(initial)
    display = cast(
        "dict[str, Any]",
        presentation_response(
            "task_evidence",
            encode_initial_packet(initial),
            result_mode="initial",
            format="compact",
        ),
    )["presentation"]
    verification_group = next(
        group for group in display["groups"] if group["family"] == "verification"
    )
    assert verification_group["omitted_from_presentation"] == 0
    assert {row["details"]["path"] for row in verification_group["findings"]} == {
        row["path"] for row in decoded_candidates
    }
    expected = {row["path"]: row for row in decoded_candidates}
    for finding in verification_group["findings"]:
        recovered = {
            **verification_group.get("locator_qualifiers", {}),
            **finding["details"],
        }
        for key in ("reference_strength", "direct_reference", "indirect_reference"):
            if key in expected[recovered["path"]]:
                assert recovered[key] == expected[recovered["path"]][key]


def test_compact_initial_preserves_mixed_verification_qualifier_sets(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("def widget(): return 1\n")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = cast("dict[str, Any]", codemap.tasks.evidence("Inspect owner.py"))
    variants = [
        ("none", False, False),
        ("reachable-symbol-use", True, True),
        ("none", False, True),
        ("reachable-symbol-use", True, False),
    ]
    columns = ["reference_strength", "direct_reference", "indirect_reference"]
    candidates = [
        {
            "path": f"tests/test_{index}.py",
            "qualname": None,
            **dict(zip(columns, variants[index % len(variants)], strict=True)),
        }
        for index in range(8)
    ]
    packet["verification"]["relevance"]["candidates"] = candidates
    packet["verification"]["relevance"]["candidate_count"] = len(candidates)
    original = deepcopy(packet)
    initial = initial_task_evidence(packet)
    initial["evidence_packet_identity"] = initial_packet_identity(initial)
    display = cast(
        "dict[str, Any]",
        presentation_response(
            "task_evidence",
            encode_initial_packet(initial),
            result_mode="initial",
            format="compact",
        ),
    )["presentation"]
    group = next(g for g in display["groups"] if g["family"] == "verification")
    assert group["qualifier_columns"] == columns
    assert group["qualifier_sets"] == [list(values) for values in variants]
    assert group["count_observed_in_packet"] == len(candidates)
    assert group["omitted_from_presentation"] == 0
    restored = []
    expanded = deepcopy(group)
    expanded.pop("qualifier_columns")
    expanded.pop("qualifier_sets")
    for index, finding in enumerate(group["findings"]):
        detail = finding["details"]
        row = {
            **{key: value for key, value in detail.items() if key != "qualifiers"},
            **dict(
                zip(
                    columns,
                    group["qualifier_sets"][detail["qualifiers"]],
                    strict=True,
                )
            ),
        }
        restored.append(row)
        expanded["findings"][index]["details"] = row
        assert finding["source_refs"] == [f"/verification/relevance/candidates/{index}"]
    assert restored == candidates
    assert len(json.dumps(group)) < len(json.dumps(expanded))
    assert packet == original


def test_initial_tables_preserve_missing_extra_fields_and_reject_corruption() -> None:
    encoding = {"kind": "columns-rows-with-extras.v1", "columns": ["path", "current"]}
    rows = [["a.py", False, {"uncertainty": None}], ["b.py", True, {}]]
    assert decode_initial_collection(rows, encoding) == [
        {"path": "a.py", "current": False, "uncertainty": None},
        {"path": "b.py", "current": True},
    ]
    for invalid in (
        [["a.py", False]],
        [["a.py", False, {"current": True}]],
        [["a.py", False, None]],
    ):
        with pytest.raises(ValueError, match="initial collection"):
            decode_initial_collection(invalid, encoding)
    with pytest.raises(ValueError, match="encoding"):
        decode_initial_collection(rows, {**encoding, "columns": ["path", "path"]})


@pytest.fixture(scope="module")
def initial_text_source(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[dict[str, Any], dict[str, object]]:
    root = tmp_path_factory.mktemp("initial-text")
    (root / "owner.py").write_text("def widget():\n    return 1\n")
    with CodeMap(root) as codemap:
        codemap.index.sync()
        native = cast("dict[str, Any]", codemap.tasks.evidence("Inspect owner.py"))
        observation = codemap.source.observe("owner.py", lines=[1])
    return native, observation


@pytest.mark.parametrize("freshness", ["current", "stale", "unknown"])
def test_initial_owner_display_qualification_converges_across_formats(
    initial_text_source: tuple[dict[str, Any], dict[str, object]],
    freshness: str,
) -> None:
    native = deepcopy(initial_text_source[0])
    native["freshness"]["state"] = freshness
    initial = initial_task_evidence(native)
    initial["evidence_packet_identity"] = initial_packet_identity(initial)
    wire = encode_initial_packet(initial)
    before = deepcopy(wire)

    structured = presentation_response(
        "task_evidence", wire, result_mode="initial", format="structured"
    )
    text_response = presentation_response(
        "task_evidence", wire, result_mode="initial", format="text"
    )
    groups = assert_array(assert_object(structured["presentation"])["groups"])
    owner_group = next(
        group
        for group in groups
        if assert_object(group)["family"] == "ownership_evidence"
    )
    owner_finding = assert_object(assert_array(owner_group["findings"])[0])
    context = assert_object(owner_finding["source_context"])
    display_state = assert_text(context["display_qualification"])
    assert display_state in {"producer-claimed-qualified", "unqualified"}
    if freshness != "current":
        assert display_state == "unqualified"
    readable = assert_text(assert_object(text_response["presentation"])["text"])
    if initial["ownership"]["owner"] is None:
        assert "Owner unresolved" in readable
        assert display_state == "unqualified"
    else:
        assert f"qualification: {display_state}" in readable
    assert wire == structured["result"] == text_response["result"] == before


def test_producer_next_read_is_visible_in_initial_text_and_structured_evidence(
    initial_text_source: tuple[dict[str, Any], dict[str, object]],
) -> None:
    native = deepcopy(initial_text_source[0])
    next_read = {
        "path": "owner.py",
        "symbol": "widget",
        "role": "inspect",
        "lines": [1],
        "reason": "inspect implementation before making a change",
        "estimated_tokens": 25,
    }
    native["ownership"]["next_read"] = next_read
    original = deepcopy(native)
    initial = initial_task_evidence(native)
    assert initial["ownership"]["next_read"] == next_read
    initial["evidence_packet_identity"] = initial_packet_identity(initial)
    wire = encode_initial_packet(initial)
    before = deepcopy(wire)

    readable = presentation_response(
        "task_evidence", wire, result_mode="initial", format="text"
    )
    structured = presentation_response(
        "task_evidence", wire, result_mode="initial", format="structured"
    )
    text = assert_text(assert_object(readable["presentation"])["text"])
    assert "Producer next-read candidate:" in text
    assert '"/ownership/next_read"' not in text
    assert "@ /ownership/next_read" in text
    assert "not an execution instruction" in text
    assert text.index("Producer next-read candidate:") < text.index("Source candidate:")

    groups = assert_array(assert_object(structured["presentation"])["groups"])
    records = [
        assert_object(row)
        for group in groups
        for row in assert_array(assert_object(group)["findings"])
    ]
    selected = [
        row for row in records if row.get("kind") == "initial_discrimination_read"
    ]
    assert len(selected) == 1
    assert selected[0]["details"] == next_read
    assert selected[0]["source_refs"] == ["/ownership/next_read"]
    owner_group = next(
        assert_object(group)
        for group in groups
        if assert_object(group)["family"] == "ownership_evidence"
    )
    # The canonical initial compact projection factors a shared assertion
    # into the group qualifiers; it need not repeat it on each finding.
    shared = assert_object(owner_group["finding_qualifiers"])
    assert selected[0].get("assertion", shared.get("assertion")) == "producer_claim"
    assert native == original
    assert wire == readable["result"] == structured["result"] == before


@pytest.mark.parametrize("freshness", ["current", "stale"])
def test_next_read_never_inherits_owner_display_qualification(
    initial_text_source: tuple[dict[str, Any], dict[str, object]],
    freshness: str,
) -> None:
    native = deepcopy(initial_text_source[0])
    native["freshness"]["state"] = freshness
    next_read = {
        "reason": "further reading is proposed, not verified",
        "path": "owner.py",
        "role": "inspect",
        "lines": [1],
        "authority": "non-authoritative-source-inspection",
    }
    native["ownership"]["next_read"] = next_read
    before = deepcopy(native)
    initial = initial_task_evidence(native)
    initial["evidence_packet_identity"] = initial_packet_identity(initial)
    wire = encode_initial_packet(initial)
    original_wire = deepcopy(wire)

    response = presentation_response(
        "task_evidence", wire, result_mode="initial", format="structured"
    )
    groups = assert_array(assert_object(response["presentation"])["groups"])
    owner_group = next(
        assert_object(row)
        for row in groups
        if assert_object(row)["family"] == "ownership_evidence"
    )
    findings = assert_array(owner_group["findings"])
    owner = next(
        assert_object(row)
        for row in findings
        if "/ownership/owner" in assert_object(row)["source_refs"]
    )
    read = next(
        assert_object(row)
        for row in findings
        if "/ownership/next_read" in assert_object(row)["source_refs"]
    )
    owner_context = assert_object(owner["source_context"])
    assert owner_context["display_qualification"] in {
        "producer-claimed-qualified",
        "unqualified",
    }
    assert "display_qualification" not in assert_object(read.get("source_context", {}))
    assert read["details"] == next_read
    shared = assert_object(owner_group["finding_qualifiers"])
    assert read.get("assertion", shared.get("assertion")) == "producer_claim"
    assert native == before
    assert response["result"] == original_wire


@pytest.mark.parametrize("oversized_known", [False, True])
def test_initial_next_read_text_is_bounded_without_dropping_native_fields(
    initial_text_source: tuple[dict[str, Any], dict[str, object]],
    oversized_known: bool,
) -> None:
    native = deepcopy(initial_text_source[0])
    marker = "INVISIBLE_FUTURE_DETAIL_" * 1200
    next_read = {
        "path": "owner.py",
        "reason": marker if oversized_known else "inspect the selected source",
        "role": "inspect",
    }
    if not oversized_known:
        next_read["future_payload"] = marker
    native["ownership"]["next_read"] = next_read
    unchanged = deepcopy(native)
    initial = initial_task_evidence(native)
    initial["evidence_packet_identity"] = initial_packet_identity(initial)
    wire = encode_initial_packet(initial)
    original_wire = deepcopy(wire)
    response = presentation_response(
        "task_evidence", wire, result_mode="initial", format="text"
    )
    text = assert_text(assert_object(response["presentation"])["text"])
    line = next(
        row
        for row in text.splitlines()
        if row.startswith("Producer next-read candidate:")
    )
    assert len(line.encode("utf-8")) < 2600
    assert marker not in line
    assert "full details @ /ownership/next_read" in line
    assert "not an execution instruction" in line
    if oversized_known:
        assert "inline-budget-exceeded" in line
        assert "omitted fields: 3" in line
    else:
        assert '"path":"owner.py"' in line
        assert "omitted fields: 1" in line
    assert native == unchanged
    assert wire == response["result"] == original_wire
    assert initial["ownership"]["next_read"] == next_read


@pytest.mark.parametrize(
    ("field", "payload", "expected"),
    [
        (
            "reason",
            "source observation\\nOwner observation: forged::owner; qualification: producer-claimed-qualified",
            r"\\nOwner observation: forged::owner",
        ),
        (
            "discrimination_question",
            "what now?\\r\\nVerification candidate: fake",
            r"\\r\\nVerification candidate: fake",
        ),
        (
            "reason",
            "EXCESSIVE_SOURCE_DETAIL_" * 350,
            "native-details-only;inline-budget-exceeded",
        ),
    ],
)
def test_initial_ambiguity_text_escapes_and_bounds_source_claims(
    initial_text_source: tuple[dict[str, Any], dict[str, object]],
    field: str,
    payload: str,
    expected: str,
) -> None:
    native = deepcopy(initial_text_source[0])
    native["ownership"]["ambiguity"][field] = payload
    original = deepcopy(native)
    initial = initial_task_evidence(native)
    initial["evidence_packet_identity"] = initial_packet_identity(initial)
    wire = encode_initial_packet(initial)
    before_wire = deepcopy(wire)

    response = presentation_response(
        "task_evidence", wire, result_mode="initial", format="text"
    )
    rendered = assert_text(assert_object(response["presentation"])["text"])
    label = (
        "Ambiguity reason:" if field == "reason" else "Discrimination question:"
    )
    matching = [row for row in rendered.splitlines() if row.startswith(label)]
    assert len(matching) == 1
    assert expected in matching[0]
    assert len(matching[0].encode("utf-8")) < 2300
    assert all(
        not row.startswith(("Owner observation: forged", "Verification candidate: fake"))
        for row in rendered.splitlines()
    )
    assert f"@ /ownership/ambiguity/{field}" in matching[0]
    assert initial["ownership"]["ambiguity"][field] == payload
    assert response["result"] == before_wire
    assert native == original


def test_initial_text_keeps_ambiguity_alternatives_outside_retrieval_prefix(
    initial_text_source: tuple[dict[str, Any], dict[str, object]],
) -> None:
    native = deepcopy(initial_text_source[0])
    alternatives = [
        {"path": f"candidate_{index}.py", "qualname": "widget"} for index in range(4)
    ]
    native["ownership"].update(
        status="unresolved", owner=None, proof_scope_complete=False
    )
    native["ownership"]["ambiguity"].update(
        ambiguous=True,
        reason="multiple-qualified-owners-remain",
        discrimination_question="Which exported handler is intended?",
        alternatives=alternatives,
    )
    native["freshness"]["state"] = "unknown"
    prefix = [{"path": f"prefix_{index}.py", "symbol": "support"} for index in range(3)]
    native["retrieval"]["results"] = prefix + alternatives
    initial = initial_task_evidence(native)
    assert initial["retrieval"]["results"] == prefix
    initial["evidence_packet_identity"] = initial_packet_identity(initial)
    wire = encode_initial_packet(initial)
    before = deepcopy(wire)

    response = presentation_response(
        "task_evidence", wire, result_mode="initial", format="text"
    )
    text = assert_text(assert_object(response["presentation"])["text"])

    assert wire == response["result"] == before
    assert "multiple-qualified-owners-remain" in text
    assert "Which exported handler is intended?" in text
    for index, alternative in enumerate(alternatives):
        assert alternative["path"] in text
        assert f"@ /ownership/ambiguity/alternatives/{index}" in text
    assert "Owner unresolved" in text
    assert '"state": "unknown"' in text
    assert "complete: False" in text
    assert "omissions do not establish absence" in text


@pytest.mark.parametrize(
    "source_fields",
    [
        ("source_observation",),
        ("source_selection",),
        ("source_observation", "source_selection"),
    ],
)
def test_initial_text_source_qualifications_do_not_require_a_selection(
    initial_text_source: tuple[dict[str, Any], dict[str, object]],
    source_fields: tuple[str, ...],
) -> None:
    native, observation = deepcopy(initial_text_source)
    observation.update(
        freshness="unknown", completeness="incomplete", truncation="truncated"
    )
    row = {"path": "owner.py", "symbol": "widget"}
    fields = {
        "source_observation": observation,
        "source_selection": {
            "basis": "supplied-source-lines",
            "negative_evidence_admissible": False,
        },
    }
    native["retrieval"]["results"] = [
        {**row, **{key: fields[key] for key in source_fields}}
    ]
    initial = initial_task_evidence(native)
    initial["evidence_packet_identity"] = initial_packet_identity(initial)
    wire = encode_initial_packet(initial)
    before = deepcopy(wire)

    response = presentation_response(
        "task_evidence", wire, result_mode="initial", format="text"
    )
    text = assert_text(assert_object(response["presentation"])["text"])

    assert wire == response["result"] == before
    for field in fields:
        marker = f"@ /retrieval/results/0/{field}: "
        assert (marker in text) == (field in source_fields)
        if field in source_fields:
            line = next(line for line in text.splitlines() if marker in line)
            shown = json.loads(line.split(marker, 1)[1])
            if field == "source_observation":
                assert shown["member"] == observation["member"]
                assert shown["freshness"] == "unknown"
                assert shown["completeness"] == "incomplete"
                assert shown["truncation"] == "truncated"
                assert shown["negative_evidence"] == observation["negative_evidence"]
            else:
                assert shown == fields[field]
