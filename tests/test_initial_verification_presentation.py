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
