"""Readable initial evidence must not silently promote an owner observation."""

from __future__ import annotations

from copy import deepcopy

import pytest

from hashmarks.evidence_presentation_task import initial_evidence_text


def _packet() -> dict[str, object]:
    """Minimal producer-shaped initial facts, not a second ownership classifier."""
    return {
        "freshness": {"state": "current"},
        "ownership": {
            "status": "resolved",
            "authority": "repository-ownership-only",
            "proof_scope": "repository",
            "proof_scope_complete": True,
            "ambiguity": {"ambiguous": False},
            "owner": {"path": "src/owner.py", "qualname": "serve"},
        },
        "retrieval": {"results": []},
        "verification": {"relevance": {"candidates": []}},
    }


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({}, "producer-claimed-qualified"),
        ({"freshness": {"state": "stale"}}, "unqualified"),
        ({"freshness": {"state": "unknown"}}, "unqualified"),
        ({"ownership": {"proof_scope_complete": False}}, "unqualified"),
        ({"ownership": {"status": "unresolved"}}, "unqualified"),
        ({"ownership": {"authority": "retrieval-candidate-only"}}, "unqualified"),
    ],
)
def test_initial_owner_text_uses_existing_producer_qualification(
    change: dict[str, dict[str, object]], expected: str
) -> None:
    packet = _packet()
    for section, fields in change.items():
        part = packet[section]
        assert isinstance(part, dict)
        part.update(fields)
    original = deepcopy(packet)

    result = initial_evidence_text(packet)

    assert "Owner observation: src/owner.py::serve" in result
    assert f"qualification: {expected}" in result
    assert "@ /ownership/owner" in result
    assert packet == original


def test_unresolved_initial_owner_does_not_fabricate_a_qualified_owner() -> None:
    packet = _packet()
    owner = packet["ownership"]
    assert isinstance(owner, dict)
    owner["status"] = "unresolved"
    owner["owner"] = None

    result = initial_evidence_text(packet)

    assert "Owner unresolved" in result
    assert "producer-claimed-qualified" not in result
