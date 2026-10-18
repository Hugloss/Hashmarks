"""Lossless initial disclosure rejects corrupt and oversized compression streams."""

from __future__ import annotations

import base64
import hashlib
import json
import lzma
from copy import deepcopy

import pytest

from hashmarks.codemap.task_evidence_initial import (
    decode_initial_packet,
    encode_initial_packet,
    initial_packet_identity,
)
from hashmarks.codemap.task_evidence_types import CompressedInitialEnvelope


def test_varied_source_facts_fit_compact_wire_without_losing_qualifiers() -> None:
    packet: dict[str, object] = {
        "schema": "hashmarks.task-evidence-initial.v2",
        "source_evidence_identity": "sha256:source",
        "facts": [
            {
                "path": f"pkg/module_{index % 4}/worker_{index}.py",
                "symbol": f"Worker{index}.apply",
                "revision": hashlib.sha256(str(index).encode()).hexdigest(),
                "basis": {
                    "path": f"pkg/module_{index % 4}/worker_{index}.py",
                    "symbol": f"Worker{index}.apply",
                    "ownership_authority": False,
                    "unknown": None,
                    "generation": index % 3,
                },
                "future": ["0", 0, False, None, 0.0, "💚é"],
            }
            for index in range(128)
        ],
    }
    packet["evidence_packet_identity"] = initial_packet_identity(packet)
    wire = encode_initial_packet(packet)
    assert len(json.dumps(wire, ensure_ascii=False).encode()) < 8192
    assert decode_initial_packet(wire) == packet


def _envelope(payload: bytes) -> CompressedInitialEnvelope:
    semantic = {
        "schema": "hashmarks.task-evidence-initial.v2",
        "source_evidence_identity": "sha256:source",
        **json.loads(payload),
    }
    return {
        "schema": "hashmarks.task-evidence-initial.v2",
        "source_evidence_identity": "sha256:source",
        "evidence_packet_identity": initial_packet_identity(semantic),
        "encoding": {"kind": "json+lzma-base85", "decoded_bytes": len(payload)},
        "data": base64.b85encode(lzma.compress(payload)).decode("ascii"),
    }


def test_lzma_disclosure_keeps_types_future_fields_and_semantic_identity() -> None:
    facts = {
        "facts": ["0", 0, False, None, 0.0, "💚é"],
        "future": {"unknown": None, "absent": False, "count": 0},
    }
    envelope = _envelope(json.dumps(facts, ensure_ascii=False).encode())
    original = deepcopy(envelope)
    decoded = decode_initial_packet(envelope)
    assert envelope == original
    assert decoded == {
        "schema": envelope["schema"],
        "source_evidence_identity": envelope["source_evidence_identity"],
        "evidence_packet_identity": envelope["evidence_packet_identity"],
        **facts,
    }
    assert [type(value) for value in decoded["facts"][:5]] == [
        str,
        int,
        bool,
        type(None),
        float,
    ]
    assert decode_initial_packet(encode_initial_packet(decoded)) == decoded


@pytest.mark.parametrize(
    "mutation",
    [
        "bool-size",
        "wrong-size",
        "over-bound",
        "invalid-base85",
        "truncated",
        "trailing-data",
        "concatenated",
        "changed-identity",
    ],
)
def test_lzma_disclosure_rejects_corrupt_streams(mutation: str) -> None:
    envelope = _envelope(b'{"facts":[false,null,0]}')
    raw = base64.b85decode(envelope["data"])
    if mutation == "bool-size":
        envelope["encoding"]["decoded_bytes"] = True
    elif mutation == "wrong-size":
        envelope["encoding"]["decoded_bytes"] -= 1
    elif mutation == "over-bound":
        envelope["encoding"]["decoded_bytes"] = 2**32
    elif mutation == "invalid-base85":
        envelope["data"] = " "
    elif mutation == "truncated":
        envelope["data"] = base64.b85encode(raw[:-1]).decode("ascii")
    elif mutation == "trailing-data":
        envelope["data"] = base64.b85encode(raw + b"extra").decode("ascii")
    elif mutation == "concatenated":
        envelope["data"] = base64.b85encode(raw + lzma.compress(b"{}")).decode("ascii")
    else:
        envelope["evidence_packet_identity"] = "sha256:changed"
    with pytest.raises(ValueError, match="initial"):
        decode_initial_packet(envelope)


@pytest.mark.parametrize(
    "payload",
    [
        b'{"facts":[],"facts":[]}',
        b'{"facts":[{"nested":false,"nested":false}]}',
        b'{"schema":"shadow"}',
    ],
)
def test_lzma_disclosure_rejects_duplicate_keys_and_header_shadowing(
    payload: bytes,
) -> None:
    with pytest.raises(ValueError, match="initial"):
        decode_initial_packet(_envelope(payload))


def test_small_lzma_result_cannot_request_an_unbounded_dictionary() -> None:
    payload = b'{"facts":[]}'
    envelope = _envelope(payload)
    envelope["data"] = base64.b85encode(lzma.compress(payload, preset=9)).decode(
        "ascii"
    )
    with pytest.raises(ValueError, match="initial"):
        decode_initial_packet(envelope)


def test_lzma_output_is_bounded_before_semantic_decoding() -> None:
    envelope = _envelope(b'{"facts":[]}')
    envelope["data"] = base64.b85encode(
        lzma.compress(b'{"facts":"' + b"x" * 1_048_577 + b'"}')
    ).decode("ascii")
    with pytest.raises(ValueError, match="initial"):
        decode_initial_packet(envelope)
