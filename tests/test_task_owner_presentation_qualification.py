"""Fail-closed agent-facing owner labels, using only existing producer claims."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from contract_assertions import assert_object, assert_records, assert_text

from hashmarks.evidence_presentation import present_repository_evidence


def _packet() -> dict[str, Any]:
    return {
        "schema": "hashmarks.task-evidence.v5",
        "retrieval": {"results": [], "bounds": {"canonical_completeness": "complete"}},
        "ownership": {
            "status": "resolved",
            "authority": "repository-ownership-only",
            "authority_proof_identity": "sha256:producer-claimed",
            "proof_scope_complete": True,
            "owner": {"path": "src/archive.py", "name": "archive"},
            "candidate": None,
            "source_evidence": {
                "representation": "source-range",
                "content": "ZipInfo(name)",
                "start_line": 12,
                "end_line": 12,
            },
            "next_read": None,
        },
        "verification": {
            "selected": {"path": "tests/test_archive.py"},
            "plan": {"argv": ["uv", "run", "pytest"]},
            "authority": "repository-verification-evidence-only",
        },
        "freshness": {"state": "current", "reason": None},
        "evidence_receipt": {"repository_identity": "fixture"},
    }


def _rows(
    packet: dict[str, Any], *, format: str = "compact"
) -> list[dict[str, object]]:
    projection = present_repository_evidence(packet, format=format)
    return [
        row
        for group in assert_records(projection["groups"])
        for row in assert_records(group["findings"])
    ]


def test_qualified_structural_resolution_preserves_owner_and_source_labels() -> None:
    """The canonical resolver may settle competing candidates structurally."""
    from hashmarks.ownership_decision import (
        OwnershipDecisionState,
        ownership_decision_trace,
    )

    resolved = ownership_decision_trace(
        OwnershipDecisionState(
            edit={"path": "src/archive.py"},
            competing=({"path": "src/other.py"},),
            structural_owner={"selected": "src/archive.py"},
            ambiguous=True,
            ambiguity_reason="competing-ranked-candidate",
            proof_scope="task",
            proof_scope_complete=True,
        )
    )
    assert resolved["status"] == "resolved"
    assert resolved["ambiguity"]["ambiguous"] is True
    assert resolved["evidence_state"]["proven"] is True
    native = _packet()
    native["ownership"]["status"] = resolved["status"]
    native["ownership"]["ambiguity"] = resolved["ambiguity"]
    original = deepcopy(native)

    for format in ("structured", "compact", "text"):
        rows = _rows(native, format=format)
        qualified = next(row for row in rows if row["kind"] == "qualified_owner")
        source = next(row for row in rows if row["kind"] == "owner_source_evidence")
        assert qualified["assertion"] == "observed_fact"
        assert source["assertion"] == "observed_fact"
        assert qualified["source_refs"] == ["/ownership/owner"]
        assert source["source_refs"] == ["/ownership/source_evidence"]
        ctx = assert_object(assert_object(qualified["source_context"])["task_ownership"])
        assert ctx["display_qualification"] == "producer-claimed-qualified"
    assert native == original


def test_current_resolved_complete_owner_keeps_native_paths_and_source() -> None:
    native = _packet()
    original = deepcopy(native)
    rows = _rows(native)
    owner = next(row for row in rows if row["kind"] == "qualified_owner")
    source = next(row for row in rows if row["kind"] == "owner_source_evidence")

    assert owner["assertion"] == "observed_fact"
    assert source["assertion"] == "observed_fact"
    assert owner["source_refs"] == ["/ownership/owner"]
    assert source["source_refs"] == ["/ownership/source_evidence"]
    assert owner["details"] == native["ownership"]["owner"]
    assert source["details"] == native["ownership"]["source_evidence"]
    ctx = assert_object(assert_object(owner["source_context"])["task_ownership"])
    assert ctx["display_qualification"] == "producer-claimed-qualified"
    assert ctx["freshness_state"] == "current"
    assert ctx["proof_scope_complete"] is True
    assert ctx["authority_proof_identity"] == "sha256:producer-claimed"
    assert native == original


@pytest.mark.parametrize(
    ("target", "value"),
    [
        ("status", "ambiguous"),
        ("status", "unresolved"),
        ("status", "stale"),
        ("proof_scope_complete", False),
        ("proof_scope_complete", None),
        ("proof_scope_complete", 1),
        ("authority", "untrusted-producer"),
        ("owner", {"path": ""}),
        ("owner", {"path": None}),
    ],
)
def test_incomplete_ownership_never_acquires_qualified_owner_label(
    target: str, value: object
) -> None:
    packet = _packet()
    packet["ownership"][target] = value
    assert_unqualified(packet)


@pytest.mark.parametrize("state", ["stale", "unknown", "pending", None])
def test_stale_or_unknown_freshness_never_qualifies_owner(state: object) -> None:
    packet = _packet()
    packet["freshness"] = {"state": state, "reason": "generation-changed"}
    assert_unqualified(packet)


@pytest.mark.parametrize("bad_freshness", [None, {}, "current"])
def test_missing_or_malformed_freshness_does_not_invent_currentness(
    bad_freshness: object,
) -> None:
    packet = _packet()
    packet["freshness"] = bad_freshness
    assert_unqualified(packet)


def test_no_freshness_field_keeps_owner_claim_visible_but_not_qualified() -> None:
    packet = _packet()
    del packet["freshness"]
    assert_unqualified(packet)


def assert_unqualified(packet: dict[str, Any]) -> None:
    original = deepcopy(packet)
    for format in ("structured", "compact", "text"):
        result = present_repository_evidence(packet, format=format)
        rows = [
            row
            for group in assert_records(result["groups"])
            for row in assert_records(group["findings"])
        ]
        owner = next(row for row in rows if row["kind"] == "unqualified_owner")
        source = next(row for row in rows if row["kind"] == "unqualified_owner_source")
        assert "qualified_owner" not in {row["kind"] for row in rows}
        assert "owner_source_evidence" not in {row["kind"] for row in rows}
        assert owner["assertion"] == "producer_claim"
        assert source["assertion"] == "producer_claim"
        assert owner["details"] == packet["ownership"]["owner"]
        assert source["details"] == packet["ownership"]["source_evidence"]
        assert owner["source_refs"] == ["/ownership/owner"]
        assert source["source_refs"] == ["/ownership/source_evidence"]
        owner_context = assert_object(
            assert_object(owner["source_context"])["task_ownership"]
        )
        assert owner_context["display_qualification"] == "unqualified"
        if format == "text":
            assert "unqualified_owner" in assert_text(result["text"])
    assert packet == original


def test_unqualified_owner_does_not_relabel_independent_candidates_and_verifiers() -> (
    None
):
    packet = _packet()
    packet["ownership"]["status"] = "ambiguous"
    packet["ownership"]["proof_scope_complete"] = False
    packet["ownership"]["candidate"] = {"path": "src/other.py"}
    packet["ownership"]["next_read"] = {
        "path": "src/other.py",
        "authority": "non-authoritative-discrimination",
    }
    rows = _rows(packet)
    candidate = next(row for row in rows if row["kind"] == "owner_candidate")
    next_read = next(row for row in rows if row["kind"] == "discrimination_read")
    verifier = next(row for row in rows if row["kind"] == "selected_verifier")
    assert candidate["assertion"] == "producer_claim"
    assert next_read["assertion"] == "producer_claim"
    assert verifier["assertion"] == "producer_claim"
    assert verifier["source_refs"] == ["/verification/selected"]
    assert next_read["source_refs"] == ["/ownership/next_read"]
    assert candidate["source_refs"] == ["/ownership/candidate"]


def test_incomplete_owner_does_not_hide_native_qualification_or_source() -> None:
    packet = _packet()
    packet["freshness"] = {"state": "stale", "reason": "generation-changed"}
    result = present_repository_evidence(packet, format="compact")
    assert result["coverage"] == "projection-only"
    assert any(
        row["source_refs"] == ["/ownership"]
        for group in assert_records(result["groups"])
        for row in assert_records(group["findings"])
    )
    assert any(
        row["source_refs"] == ["/evidence_receipt"]
        for group in assert_records(result["groups"])
        for row in assert_records(group["findings"])
    )
