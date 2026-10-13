"""Initial disclosure preserves producer authority and accounts for omissions."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.task_evidence_initial import (
    decode_initial_collection,
    decode_initial_packet,
    encode_initial_packet,
    initial_packet_identity,
    initial_task_evidence,
)
from hashmarks.evidence_presentation import FORMATS, presentation_response
from hashmarks.evidence_presentation_conformance import validate_evidence_presentation
from hashmarks.mcp_contract import tool_contract
from hashmarks.mcp_surface import HashmarksMcpSurface, McpSurfaceError


def test_initial_string_table_preserves_json_types_unicode_and_future_fields():
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
    encoded["data"][next(iter(encoded["data"]))][1] = False
    with pytest.raises(ValueError, match="semantic identity"):
        decode_initial_packet(encoded)


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
def test_initial_string_table_rejects_malformed_references(mutation):
    packet = encode_initial_packet(
        {
            "schema": "hashmarks.task-evidence-initial.v2",
            "source_evidence_identity": "sha256:source",
            "evidence_packet_identity": "sha256:initial",
            "a": "b",
        }
    )
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


def _assert_initial_display(response: dict[str, Any], packet: dict[str, Any]) -> None:
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
        codemap.sync()
        native = cast("dict[str, Any]", codemap.task_evidence("Fix widget"))
        before = deepcopy(native)
        initial = initial_task_evidence(native)
        api = cast(
            "dict[str, Any]",
            codemap.task_evidence("Fix widget", result_mode="initial"),
        )
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
    assert (
        _decoded_task_matches(initial["verification"]["relevance"]["task_matches"])
        == native["verification"]["relevance"]["task_matches"]
    )
    if native["ownership"]["owner"] is None:
        assert initial["ownership"]["owner"] is None
    else:
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
    surface = HashmarksMcpSurface(str(tmp_path))
    try:
        observed = cast(
            "dict[str, Any]", surface.task_evidence("Fix widget", result_mode="initial")
        )
        assert observed["schema"] == api["schema"]
        assert (
            decode_initial_packet(observed)["ownership"]["status"]
            == decode_initial_packet(api)["ownership"]["status"]
        )
    finally:
        surface.close()


def test_initial_mode_rejects_unknown_mode_before_observation(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap, pytest.raises(ValueError, match="result_mode"):
        codemap.task_evidence("Fix widget", result_mode="invented")
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
        codemap.sync()
        packet = cast("dict[str, Any]", codemap.task_evidence("Inspect ChannelBackend"))
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
    for index in range(3):
        (tmp_path / "tests" / f"test_widget_{index}.py").write_text(
            "from owner import widget\n"
            f"def test_widget_{index}(): assert widget() == 1\n"
        )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = cast("dict[str, Any]", codemap.task_evidence("Inspect owner.py."))
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
    projected["candidates"] = decode_initial_collection(
        projected["candidates"], projected["candidates_encoding"]
    )
    assert [row["path"] for row in projected["candidates"]] == [
        row["path"] for row in relevance["candidates"]
    ]
    for source, returned in zip(
        relevance["candidates"], projected["candidates"], strict=True
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
