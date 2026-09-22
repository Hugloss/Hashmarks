from __future__ import annotations

from scripts.agent_evaluation.repository_quality_convergence import (
    require_surface_convergence,
)
from scripts.agent_evaluation.repository_quality_live import (
    canonical_authority_observation,
    convergence_observations,
    surface_authority_observation,
)


def _contract(proof: str = "sha256:proof", owner: str = "src/owner.py") -> dict:
    return {
        "owner_resolved": True,
        "resolved_owner": owner,
        "candidate_owner": owner,
        "proof_complete": True,
        "authority_proof_identity": proof,
    }


def test_live_surface_adapters_converge_direct_and_nested_contracts() -> None:
    payloads = [
        ("action-map", {"ownership_authority": _contract()}),
        ("task-evidence", {"retrieval": {"ownership_authority": _contract()}}),
        ("mcp-task-evidence", {"ownership": {"contract": _contract()}}),
    ]
    observations = convergence_observations(payloads)
    result = require_surface_convergence(
        observations, ("action-map", "task-evidence", "mcp-task-evidence")
    )

    assert result["complete"] is True
    assert {row["resolved_owner"] for row in observations} == {"src/owner.py"}


def test_live_surface_adapter_rejects_projection_without_proof_identity() -> None:
    payload = {"ownership_authority": {"owner_resolved": True}}
    try:
        surface_authority_observation("action-map", payload)
    except ValueError as exc:
        assert "no proof identity" in str(exc)
    else:
        raise AssertionError("missing proof identity must fail closed")


def test_scoped_proof_identity_changes_with_generation_not_presentation() -> None:
    trace = {
        "status": "resolved",
        "selected": {"path": "src/owner.py"},
        "structural_evidence": {"selected": "src/owner.py"},
        "ambiguity": {"ambiguous": False, "reason": "resolved"},
        "authority_basis": "literal-path",
        "evidence_state": {"proven": True},
    }
    first = canonical_authority_observation(
        trace,
        repository_identity="repo:a",
        task_identity="task:a",
        policy_identity="policy:v1",
        generation_identity="generation:1",
    )
    same = canonical_authority_observation(
        trace,
        repository_identity="repo:a",
        task_identity="task:a",
        policy_identity="policy:v1",
        generation_identity="generation:1",
    )
    changed = canonical_authority_observation(
        trace,
        repository_identity="repo:a",
        task_identity="task:a",
        policy_identity="policy:v1",
        generation_identity="generation:2",
    )

    assert first["authority_proof_identity"] == same["authority_proof_identity"]
    assert first["authority_proof_identity"] != changed["authority_proof_identity"]
    assert (
        first["semantic_authority_proof_identity"]
        == changed["semantic_authority_proof_identity"]
    )
