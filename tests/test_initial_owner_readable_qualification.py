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
        ({"ownership": {"ambiguity": {"ambiguous": True}}}, "unqualified"),
        ({"ownership": {"ambiguity": {"ambiguous": None}}}, "unqualified"),
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


def test_owner_display_requires_explicit_disambiguation_even_if_status_resolved() -> None:
    from hashmarks.evidence_presentation_task import _task_owner_display_qualified

    packet = _packet()
    ownership = packet["ownership"]
    assert isinstance(ownership, dict)
    owner = ownership["owner"]
    assert isinstance(owner, dict)
    assert _task_owner_display_qualified(
        ownership, owner["path"], packet["freshness"]
    )

    ownership["ambiguity"] = {"ambiguous": True}
    assert not _task_owner_display_qualified(
        ownership, owner["path"], packet["freshness"]
    )
    ownership["ambiguity"] = {"ambiguous": None}
    assert not _task_owner_display_qualified(
        ownership, owner["path"], packet["freshness"]
    )
    assert "qualification: unqualified" in initial_evidence_text(packet)


def test_unresolved_initial_owner_does_not_fabricate_a_qualified_owner() -> None:
    packet = _packet()
    owner = packet["ownership"]
    assert isinstance(owner, dict)
    owner["status"] = "unresolved"
    owner["owner"] = None

    result = initial_evidence_text(packet)

    assert "Owner unresolved" in result
    assert "producer-claimed-qualified" not in result


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("current", "producer-claimed-qualified"),
        ("stale", "unqualified"),
        ("unknown", "unqualified"),
    ],
)
def test_readable_initial_evidence_leads_with_qualified_owner(
    state: str, expected: str
) -> None:
    packet = _packet()
    freshness = packet["freshness"]
    assert isinstance(freshness, dict)
    freshness["state"] = state
    before = deepcopy(packet)

    result = initial_evidence_text(packet)
    rows = result.splitlines()

    assert rows[0] == (
        f"Owner observation: src/owner.py::serve; qualification: {expected} "
        "(@ /ownership/owner)."
    )
    assert rows[1].startswith("Ownership: resolved; freshness:")
    assert rows[2].startswith("Ambiguity: False")
    assert "Owner proof scope:" in rows[3]
    assert result.count("Owner observation:") == 1
    assert "omissions do not establish absence" in result
    assert "tests were not executed" in result
    assert packet == before


def test_readable_initial_evidence_leads_with_unresolved_not_candidate() -> None:
    packet = _packet()
    owner = packet["ownership"]
    assert isinstance(owner, dict)
    owner["status"] = "unresolved"
    owner["owner"] = None
    ambiguity = owner["ambiguity"]
    assert isinstance(ambiguity, dict)
    ambiguity.update(
        ambiguous=True,
        reason="multiple-qualified-owners-remain",
        alternatives=[{"path": "src/other.py", "qualname": "serve"}],
    )
    rows = initial_evidence_text(packet).splitlines()
    assert rows[0] == "Owner unresolved (@ /ownership/owner)."
    assert rows[1].startswith("Ownership: unresolved;")
    assert "Ambiguity: True" in rows[2]
    assert any("Owner alternative:" in row for row in rows[4:])
    assert not any("producer-claimed-qualified" in row for row in rows)
