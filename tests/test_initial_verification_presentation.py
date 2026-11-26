"""Readable initial replies retain the nominated test and its source binding."""

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
)
from hashmarks.evidence_presentation import presentation_response


@pytest.fixture(scope="module")
def initial_verification_packets(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, dict[str, Any]]:
    packets = {}
    for mode, names in (
        ("unique", ["test_cached_generator", "test_plain_value"]),
        ("ambiguous", ["test_cached_generator_a", "test_cached_generator_b"]),
    ):
        root = tmp_path_factory.mktemp(mode)
        (root / "repository.py").write_text("def provide(): return 1\n")
        (root / "tests").mkdir()
        (root / "tests/test_repository.py").write_text(
            "from repository import provide\n"
            + "\n".join(f"def {name}(): assert provide() == 1" for name in names)
            + "\n"
        )
        with CodeMap(root) as repository:
            repository.index.sync()
            packets[mode] = cast(
                "dict[str, Any]",
                repository.tasks.evidence(
                    "Inspect cached generator in repository.py", result_mode="initial"
                ),
            )
    return packets


@pytest.mark.parametrize("mode", ["unique", "ambiguous"])
@pytest.mark.parametrize("format", ["structured", "compact", "text"])
def test_initial_verification_keeps_exact_test_identity_and_qualification(
    initial_verification_packets: dict[str, dict[str, Any]], mode: str, format: str
) -> None:
    wire = initial_verification_packets[mode]
    original = deepcopy(wire)
    packet = decode_initial_packet(wire)
    relevance = packet["verification"]["relevance"]
    rows = decode_initial_collection(
        relevance["candidates"], relevance["candidates_encoding"]
    )
    expected = next(row for row in rows if row["path"] == "tests/test_repository.py")
    assert expected["test_symbol"] == (
        "test_cached_generator" if mode == "unique" else None
    )
    assert expected["test_revision"]
    response = cast(
        "dict[str, Any]",
        presentation_response(
            "task_evidence", wire, result_mode="initial", format=format
        ),
    )
    projection = response["presentation"]
    if format == "text":
        line = next(
            line
            for line in projection["text"].splitlines()
            if line.startswith("Verification candidate:") and expected["path"] in line
        )
        displayed, _ = json.JSONDecoder().raw_decode(
            line.removeprefix("Verification candidate: ")
        )
    else:
        group = next(
            group for group in projection["groups"] if group["family"] == "verification"
        )
        finding = next(
            finding
            for finding in group["findings"]
            if finding["details"]["path"] == expected["path"]
        )
        displayed = {**group.get("locator_qualifiers", {}), **finding["details"]}
        if "qualifiers" in displayed:
            displayed.update(
                zip(
                    group["qualifier_columns"],
                    group["qualifier_sets"][displayed.pop("qualifiers")],
                    strict=True,
                )
            )
        assert finding["source_refs"] == [
            f"/verification/relevance/candidates/{rows.index(expected)}"
        ]
    for key in (
        "path",
        "test_symbol",
        "test_revision",
        "reference_strength",
        "direct_reference",
        "indirect_reference",
        "verification_selection_authority",
        "edit_relationship",
        "negative_evidence_admissible",
    ):
        assert key in expected
        assert key in displayed
        assert displayed[key] == expected[key]
        assert type(displayed[key]) is type(expected[key])
    if "test_declarations" in expected:
        assert displayed["test_declarations"] == expected["test_declarations"]
    assert response["result"] == wire == original


def test_shared_text_qualifiers_round_trip_partial_and_distinct_candidate_evidence(
    tmp_path: Path,
) -> None:
    (tmp_path / "codec.py").write_text("def encode_record(value): return value\n")
    for index in range(5):
        (tmp_path / f"test_codec_{index}.py").write_text(
            f"from codec import encode_record\ndef test_encode_{index}(): assert encode_record(1) == 1\n"
        )
    with CodeMap(tmp_path) as repository:
        packet = decode_initial_packet(
            repository.tasks.evidence(
                "Fix encode_record in codec.py", result_mode="initial"
            )
        )
    relevance = packet["verification"]["relevance"]
    rows = decode_initial_collection(
        relevance["candidates"], relevance.pop("candidates_encoding")
    )
    assert len(rows) > 2
    rows[0].pop("indirect_reference")
    rows[1]["test_symbol"] = None
    rows[2]["reference_strength"] = "unknown"
    relevance["candidates"] = rows
    packet["evidence_packet_identity"] = initial_packet_identity(packet)
    wire = encode_initial_packet(packet)
    displays = {
        mode: cast(
            "dict[str, Any]",
            presentation_response(
                "task_evidence", wire, result_mode="initial", format=mode
            ),
        )
        for mode in ("text", "structured")
    }
    text = displays["text"]["presentation"]["text"]
    prefix = "Verification qualifiers for every displayed candidate: "
    shared = json.loads(
        next(
            line.removeprefix(prefix)
            for line in text.splitlines()
            if line.startswith(prefix)
        )
    )
    assert shared["verification_selection_authority"] is False
    assert shared["negative_evidence_admissible"] is False
    assert "indirect_reference" not in shared and "reference_strength" not in shared
    group = next(
        group
        for group in displays["structured"]["presentation"]["groups"]
        if group["family"] == "verification"
    )
    candidate_lines = [
        line
        for line in text.splitlines()
        if line.startswith("Verification candidate: ")
    ]
    for line, finding in zip(candidate_lines, group["findings"], strict=True):
        record, end = json.JSONDecoder().raw_decode(
            line.removeprefix("Verification candidate: ")
        )
        assert {**shared, **record} == finding["details"]
        assert (
            line.removeprefix("Verification candidate: ")[end:]
            == f" (@ {finding['source_refs'][0]})."
        )
    assert displays["text"]["result"] == wire


@pytest.mark.parametrize("different_revision", [False, True])
def test_verification_declaration_source_refs_are_per_candidate(
    tmp_path: Path, different_revision: bool
) -> None:
    (tmp_path / "backend.py").write_text("def execute(): return 1\n")
    for index in range(5):
        (tmp_path / f"test_lifecycle_{index}.py").write_text(
            "from backend import execute\n"
            + "".join(
                f"def test_stateful_cleanup_{name}(): assert execute() == {index}\n"
                for name in ("starts", "stops", "fails")
            )
        )
    with CodeMap(tmp_path) as repository:
        packet = decode_initial_packet(
            repository.tasks.evidence(
                "Inspect stateful cleanup in backend.py", result_mode="initial"
            )
        )
    relevance = packet["verification"]["relevance"]
    rows = decode_initial_collection(
        relevance["candidates"], relevance.pop("candidates_encoding")
    )
    assert len(rows) == 5
    rows[0].pop("test_declarations")
    if different_revision:
        cast("dict[str, Any]", rows[1]["test_declarations"]).pop("source_revision")
        cast("dict[str, Any]", rows[2]["test_declarations"])["source_revision"] = (
            "independent"
        )
    relevance["candidates"] = rows
    packet["evidence_packet_identity"] = initial_packet_identity(packet)
    wire = encode_initial_packet(packet)
    response = cast(
        "dict[str, Any]",
        presentation_response(
            "task_evidence", wire, result_mode="initial", format="text"
        ),
    )
    lines = response["presentation"]["text"].splitlines()
    prefix = "Within each displayed test_declarations, copy these fields from its own candidate: "
    refs = json.loads(
        next(line.removeprefix(prefix) for line in lines if line.startswith(prefix))
    )
    assert refs == (
        {"path": "path"}
        if different_revision
        else {"path": "path", "source_revision": "test_revision"}
    )
    candidate_prefix = "Verification candidate: "
    candidate_lines = [
        line.removeprefix(candidate_prefix)
        for line in lines
        if line.startswith(candidate_prefix)
    ]
    for index, (line, row) in enumerate(zip(candidate_lines, rows, strict=True)):
        locator, end = json.JSONDecoder().raw_decode(line)
        assert line[end:] == f" (@ /verification/relevance/candidates/{index})."
        if "test_declarations" in row:
            scope = locator["test_declarations"]
            assert not scope.keys() & refs.keys()
            assert {
                **scope,
                **{key: locator[field] for key, field in refs.items()},
            } == row["test_declarations"]
        else:
            assert "test_declarations" not in locator
    assert response["result"] == wire
