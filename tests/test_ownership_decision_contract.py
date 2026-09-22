from __future__ import annotations

import pytest

from hashmarks.ownership_decision import (
    OwnershipDecisionState,
    bounded_presentation_contract,
    ownership_authority_contract,
    ownership_decision_trace,
    presentation_identity,
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
            authority_basis="structural-owner",
            proof_scope="repository-relationship-proof",
            proof_scope_complete=True,
        )
    )
    authority = ownership_authority_contract(trace)

    assert trace["status"] == "resolved"
    assert trace["confidence"] == "high"
    assert (
        trace["candidates"][1]["rejection_reason"]
        == "verification-evidence-not-edit-authority"
    )
    assert authority["owner_resolved"] is True
    assert authority["resolved_owner"] == "src/a.py"


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
    assert authority["owner_resolved"] is False
    assert authority["resolved_owner"] is None
    assert authority["candidate_owner"] == "src/a.py"
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
    assert authority["owner_resolved"] is False
    assert authority["resolved_owner"] is None


def test_ownership_contract_never_grants_edit_permission() -> None:
    trace = ownership_decision_trace(
        OwnershipDecisionState(
            edit={"path": "src/owner.py", "canonical_rank": 1, "roles": ["edit"]},
            competing=[],
            structural_owner={"selected": "src/owner.py"},
            ambiguous=False,
            ambiguity_reason="",
            authority_basis="structural-owner",
            proof_scope="repository-relationship-proof",
            proof_scope_complete=True,
        )
    )

    contract = ownership_authority_contract(trace)

    assert contract["owner_resolved"] is True
    assert contract["resolved_owner"] == "src/owner.py"
    assert contract["authority"] == "repository-ownership-only"
    assert contract["consumer_action"] == "external"
    assert "safe_to_edit" not in contract
    assert "authoritative_edit" not in contract


def test_structural_owner_resolves_residual_candidate_ambiguity() -> None:
    trace = ownership_decision_trace(
        OwnershipDecisionState(
            edit={"path": "src/a.py", "canonical_rank": 1, "roles": ["edit"]},
            competing=[{"path": "src/b.py", "canonical_rank": 2, "roles": ["edit"]}],
            structural_owner={
                "selected": "src/a.py",
                "via": "import",
                "owner_path": [
                    {"from": "src/route.py", "to": "src/a.py", "relation": "import"}
                ],
            },
            ambiguous=True,
            ambiguity_reason="competing-ranked-candidate",
            authority_basis="structural-owner",
            proof_scope="repository-relationship-proof",
            proof_scope_complete=True,
        )
    )
    authority = ownership_authority_contract(trace)

    assert trace["status"] == "resolved"
    assert trace["confidence"] == "high"
    assert authority["owner_resolved"] is True
    assert authority["resolved_owner"] == "src/a.py"


def test_unique_canonical_owner_without_structural_edge_remains_resolved() -> None:
    trace = ownership_decision_trace(
        OwnershipDecisionState(
            edit={"path": "src/owner.py", "canonical_rank": 1, "roles": ["edit"]},
            competing=[
                {
                    "path": "tests/test_owner.py",
                    "canonical_rank": 2,
                    "roles": ["verify"],
                }
            ],
            structural_owner=None,
            ambiguous=False,
            ambiguity_reason="resolved-by-role",
            authority_basis="canonical-role-discrimination",
            proof_scope="bounded-retrieval",
            proof_scope_complete=False,
        )
    )
    authority = ownership_authority_contract(trace)

    assert trace["status"] == "resolved"
    assert authority["owner_resolved"] is True
    assert authority["resolved_owner"] == "src/owner.py"
    assert authority["proof_complete"] is True


def test_exact_symbol_basis_is_positive_authority_evidence() -> None:
    trace = ownership_decision_trace(
        OwnershipDecisionState(
            edit={"path": "src/owner.py", "canonical_rank": 7, "roles": ["edit"]},
            competing=[],
            structural_owner=None,
            ambiguous=False,
            ambiguity_reason="resolved-by-role",
            authority_basis="unique-exact-symbol",
            proof_scope="repository-global-symbol-identity",
            proof_scope_complete=True,
        )
    )
    authority = ownership_authority_contract(trace)

    assert trace["status"] == "resolved"
    assert trace["evidence_state"]["retrieved"] is True
    assert trace["evidence_state"]["admissible"] is True
    assert authority["owner_resolved"] is True
    assert authority["proof_complete"] is True


def test_presentation_bounds_do_not_change_authority_proof_identity() -> None:
    trace = ownership_decision_trace(
        OwnershipDecisionState(
            edit={"path": "src/owner.py", "canonical_rank": 1, "roles": ["edit"]},
            competing=[],
            structural_owner=None,
            ambiguous=False,
            ambiguity_reason="resolved-by-role",
            authority_basis="literal-path",
            proof_scope="repository-global-path-identity",
            proof_scope_complete=True,
        )
    )
    authority = ownership_authority_contract(trace)
    proof = authority["authority_proof_identity"]

    compact = presentation_identity(proof, limit=1, per_role=1, compact=True)
    full = presentation_identity(proof, limit=20, per_role=3, compact=False)

    assert compact != full
    assert ownership_authority_contract(trace)["authority_proof_identity"] == proof


def test_bounded_presentation_reports_truncation_without_mutating_proof() -> None:
    proof = "sha256:proof"
    bounded = bounded_presentation_contract(
        proof,
        total_candidates=12,
        returned_candidates=3,
        limit=3,
        per_role=1,
        compact=True,
    )
    complete = bounded_presentation_contract(
        proof,
        total_candidates=12,
        returned_candidates=12,
        limit=20,
        per_role=3,
        compact=False,
    )

    assert bounded["authority_proof_identity"] == proof
    assert complete["authority_proof_identity"] == proof
    assert bounded["presentation_identity"] != complete["presentation_identity"]
    assert bounded["complete"] is False
    assert bounded["truncated"] is True
    assert complete["complete"] is True
    assert complete["truncated"] is False


def test_invalid_bounded_presentation_counts_fail_closed() -> None:
    with pytest.raises(ValueError, match="cannot exceed"):
        bounded_presentation_contract(
            "sha256:proof",
            total_candidates=1,
            returned_candidates=2,
            limit=2,
            per_role=1,
            compact=False,
        )


def test_resolved_canonical_selection_remains_admissible_without_new_metadata() -> None:
    trace = ownership_decision_trace(
        OwnershipDecisionState(
            edit={"path": "src/owner.py", "canonical_rank": 1, "roles": ["edit"]},
            competing=[],
            structural_owner=None,
            ambiguous=False,
            ambiguity_reason="resolved-by-role",
        )
    )
    authority = ownership_authority_contract(trace)

    assert trace["status"] == "resolved"
    assert trace["evidence_state"]["canonical_selection"] is True
    assert trace["evidence_state"]["admissible"] is True
    assert trace["evidence_state"]["proven"] is True
    assert trace["proof_scope_complete"] is False
    assert authority["owner_resolved"] is True
    assert authority["proof_complete"] is True


def test_structural_evidence_is_admissible_without_new_metadata_basis() -> None:
    trace = ownership_decision_trace(
        OwnershipDecisionState(
            edit={"path": "src/owner.py", "canonical_rank": 1, "roles": ["edit"]},
            competing=[],
            structural_owner={
                "selected": "src/owner.py",
                "via": "import",
                "owner_path": [],
            },
            ambiguous=False,
            ambiguity_reason="resolved-structurally",
            authority_basis="structural-owner",
            proof_scope="repository-relationship-proof",
            proof_scope_complete=True,
        )
    )
    authority = ownership_authority_contract(trace)

    assert trace["evidence_state"]["structural"] is True
    assert trace["evidence_state"]["admissible"] is True
    assert trace["evidence_state"]["proven"] is True
    assert authority["owner_resolved"] is True


def test_authority_proof_ignores_selected_row_presentation_metadata() -> None:
    def proof(rank: int, roles: list[str]) -> str:
        trace = ownership_decision_trace(
            OwnershipDecisionState(
                edit={
                    "path": "src/owner.py",
                    "name": "owner",
                    "qualname": "owner",
                    "canonical_rank": rank,
                    "roles": roles,
                },
                competing=[],
                structural_owner=None,
                ambiguous=False,
                ambiguity_reason="resolved-by-role",
                authority_basis="literal-path",
                proof_scope="repository-global-path-identity",
                proof_scope_complete=True,
            )
        )
        return ownership_authority_contract(trace)["authority_proof_identity"]

    assert proof(1, ["edit"]) == proof(99, ["edit", "related"])
