from __future__ import annotations

from hashmarks.ownership_decision import (
    OwnershipDecisionState,
    ownership_authority_contract,
    ownership_decision_trace,
)


def test_resolved_structural_owner_is_authoritative() -> None:
    trace = ownership_decision_trace(
        OwnershipDecisionState(
            edit={"path": "src/a.py", "canonical_rank": 1, "roles": ["edit"]},
            competing=[
                {"path": "tests/test_a.py", "canonical_rank": 2, "roles": ["verify"]}
            ],
            structural_owner={
                "selected": "src/a.py",
                "via": "import",
                "owner_path": [
                    {"from": "tests/test_a.py", "to": "src/a.py", "relation": "import"}
                ],
            },
            ambiguous=False,
            ambiguity_reason="resolved-by-role",
        )
    )
    authority = ownership_authority_contract(trace)

    assert trace["status"] == "resolved"
    assert trace["confidence"] == "high"
    assert (
        trace["candidates"][1]["rejection_reason"]
        == "verification-evidence-not-edit-authority"
    )
    assert authority["safe_to_edit"] is True
    assert authority["authoritative_edit"] == "src/a.py"


def test_ambiguous_owner_fails_closed_while_retaining_candidate_evidence() -> None:
    trace = ownership_decision_trace(
        OwnershipDecisionState(
            edit={"path": "src/a.py", "canonical_rank": 1, "roles": ["edit"]},
            competing=[{"path": "src/b.py", "canonical_rank": 2, "roles": ["edit"]}],
            structural_owner=None,
            ambiguous=True,
            ambiguity_reason="multiple-identifier-edit-owners",
        )
    )
    authority = ownership_authority_contract(trace)

    assert trace["status"] == "ambiguous"
    assert trace["candidates"][0]["disposition"] == "provisional"
    assert trace["candidates"][1]["disposition"] == "competing"
    assert authority["safe_to_edit"] is False
    assert authority["authoritative_edit"] is None
    assert authority["candidate_edit"] == "src/a.py"
    assert authority["reason"] == "multiple-identifier-edit-owners"


def test_missing_edit_is_explicitly_unresolved() -> None:
    trace = ownership_decision_trace(
        OwnershipDecisionState(
            edit=None,
            competing=[],
            structural_owner=None,
            ambiguous=True,
            ambiguity_reason="no-edit-candidate",
        )
    )
    authority = ownership_authority_contract(trace)

    assert trace["status"] == "unresolved"
    assert trace["confidence"] == "none"
    assert authority["safe_to_edit"] is False
    assert authority["authoritative_edit"] is None
