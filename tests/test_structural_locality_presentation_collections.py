"""Every admitted bounded call fact survives the public presentation formats."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from contract_assertions import assert_array, assert_object, assert_records

from hashmarks.codemap import CodeMap
from hashmarks.evidence_presentation import present_repository_evidence

_COLLECTIONS = ("nodes", "edges", "unresolved_calls", "external_or_unindexed_calls")


def _recover(findings: list[dict[str, object]], key: str) -> list[object]:
    """Follow literal native references, supporting records or whole arrays."""
    rows = {}
    for finding in findings:
        for reference in assert_array(finding["source_refs"]):
            assert isinstance(reference, str)
            if reference == "/" + key:
                return assert_array(finding["details"])
            if reference.startswith("/" + key + "/"):
                rows[int(reference.rsplit("/", 1)[1])] = finding["details"]
    return [rows[index] for index in sorted(rows)]


@pytest.mark.parametrize("mode", ["structured", "compact", "text"])
def test_locality_display_conserves_complete_bounded_collections(
    tmp_path: Path, mode: str
) -> None:
    (tmp_path / "worker.py").write_text(
        "\n".join(f"def leaf_{index}(): return {index}" for index in range(8))
        + "\ndef owner(receiver):\n"
        + "\n".join(f"    leaf_{index}()" for index in range(8))
        + "\n    return receiver.deliver()\n"
    )
    with CodeMap(tmp_path) as codemap:
        packet = codemap.structural_locality("worker.py::owner")
    # The pure projection also conserves future producer-owned qualifiers.
    assert_records(packet["edges"])[-1]["future_qualification"] = {
        "unknown": None,
        "literal": False,
        "zero": 0,
        "empty": [],
    }
    before = json.dumps(packet, sort_keys=True)
    projection = present_repository_evidence(packet, format=mode)
    findings = [
        row
        for group in assert_records(projection["groups"])
        for row in assert_records(group["findings"])
    ]
    if mode == "text":
        text = projection["text"]
        assert isinstance(text, str)
        findings = [
            assert_object(json.loads(line.strip()))
            for line in text.splitlines()
            if line.startswith("  {")
        ]
    for key in _COLLECTIONS:
        actual = _recover(findings, key)
        assert json.dumps(actual, sort_keys=True) == json.dumps(
            packet[key], sort_keys=True
        )
    assert json.dumps(packet, sort_keys=True) == before


def test_locality_collection_counts_describe_native_members(tmp_path: Path) -> None:
    (tmp_path / "worker.py").write_text("def owner():\n    return 1\n")
    with CodeMap(tmp_path) as codemap:
        packet = codemap.structural_locality("worker.py::owner")
    projection = present_repository_evidence(packet, format="compact")
    findings = [
        row
        for group in assert_records(projection["groups"])
        for row in assert_records(group["findings"])
    ]
    for key in _COLLECTIONS:
        collection = next(row for row in findings if row["source_refs"] == ["/" + key])
        assert collection["native_item_count"] == len(assert_array(packet[key]))
        assert collection["details"] == packet[key]
