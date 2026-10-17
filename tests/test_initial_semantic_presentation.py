"""Recover every supplied-claim value using the public view's native references."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

from hashmarks import CodeMap
from hashmarks.codemap.task_evidence_initial import (
    decode_initial_packet,
    encode_initial_packet,
    initial_packet_identity,
)
from hashmarks.evidence_presentation import presentation_response


def _pointer(value: object, pointer: str) -> object:
    for part in pointer.lstrip("/").split("/") if pointer else []:
        key = part.replace("~1", "/").replace("~0", "~")
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def _read_record(view: dict[str, Any], native: dict[str, Any]) -> dict[str, Any]:
    record = deepcopy(view["record"])
    for destination, source in view["value_refs"].items():
        parent, _, key = destination.rpartition("/")
        target = _pointer(record, parent)
        restored = deepcopy(_pointer(native, view["value_ref_base"] + source))
        decoded = key.replace("~1", "/").replace("~0", "~")
        target[int(decoded) if isinstance(target, list) else decoded] = restored
    return record


@pytest.mark.parametrize("format", ["compact", "text"])
def test_initial_relationship_view_preserves_all_values_and_future_types(
    tmp_path: Path, format: str
) -> None:
    (tmp_path / "owner.py").write_text("class Worker:\n    pass\n")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        wire = cast(
            "dict[str, Any]",
            codemap.task_evidence("Inspect owner.py", result_mode="initial"),
        )
    logical = decode_initial_packet(wire)
    binding: dict[str, Any] = {
        "state": "matching",
        "future": {"false": False, "zero": 0.0, "missing": None},
    }
    endpoint: dict[str, Any] = {
        "source_binding": deepcopy(binding),
        "resolution": {
            "state": "unique-candidate",
            "source_binding": deepcopy(binding),
            "candidates": [{"source_binding": deepcopy(binding), "future": "α"}],
        },
    }
    relationship: dict[str, Any] = {
        "subject": "owner.py::Worker",
        "authority": "external-producer-claims-only",
        "claims": [
            {"source": endpoint, "target": deepcopy(endpoint), "kind": "implementation"}
        ],
        "qualifications": [{"source_bindings": [deepcopy(binding)]}],
        "negative_evidence_admissible": False,
        "future/key~": {"unicode": "α", "unknown": None},
    }
    relationship["evidence"] = deepcopy(relationship)
    relationship["evidence"]["authority"] = 0
    relationship["claims"][0]["source"]["resolution"]["candidates"][0][
        "source_binding"
    ]["future"]["false"] = 0
    logical["semantic_relationships"] = relationship
    logical["evidence_packet_identity"] = initial_packet_identity(logical)
    original = deepcopy(logical)
    response = presentation_response(
        "task_evidence",
        encode_initial_packet(logical),
        format=format,
        result_mode="initial",
    )
    projection = response["presentation"]
    assert isinstance(projection, dict)
    if format == "compact":
        group = next(
            group for group in projection["groups"] if group["family"] == "relationship"
        )
        view = group["findings"][0]["details"]
    else:
        line = next(
            line
            for line in projection["text"].splitlines()
            if line.startswith("Producer relationships: ")
        )
        view, _ = json.JSONDecoder().raw_decode(
            line.removeprefix("Producer relationships: ")
        )
    restored = _read_record(view, logical)
    assert json.dumps(restored, sort_keys=True) == json.dumps(
        relationship, sort_keys=True
    )
    assert logical == original
    native = response["result"]
    assert isinstance(native, dict)
    assert decode_initial_packet(native) == logical
