from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.agent_evaluation.repository_quality_corpus import (
    corpus_manifest_identity,
    promotion_transition,
)
from scripts.agent_evaluation.repository_quality_mutation import (
    mutation_coverage,
    repository_counterfactual_challenges,
    run_mutation_challenges,
)
from scripts.agent_evaluation.repository_quality_receipt import (
    execution_receipt,
    external_evidence_receipt,
    promotion_evidence_identity,
    receipt_is_fresh,
)

ROOT = Path(__file__).resolve().parents[1]


def _corpus() -> dict:
    return json.loads(
        (ROOT / "benchmarks/repository_quality/retained-real-world.v1.json").read_text()
    )


def _identities() -> dict[str, str]:
    return {
        "repository_identity": "sha256:repo",
        "source_identity": "sha256:source",
        "task_identity": "sha256:task",
        "policy_identity": "hashmarks.authority.v1",
        "generation_identity": "sha256:generation",
        "authority_proof_identity": "sha256:proof",
    }


def test_fresh_execution_receipt_binds_all_authority_identities() -> None:
    receipt = execution_receipt(
        case_id="fresh-dogfood",
        corpus_identity=corpus_manifest_identity(_corpus()),
        identities=_identities(),
        surfaces=[
            {"surface": "task-evidence", "authority_proof_identity": "sha256:proof"}
        ],
        mutations=[{"family": "retrieval-limit", "violation": False}],
        external_evidence={"authority_unchanged": True},
    )

    assert receipt["receipt_identity"].startswith("sha256:")
    assert receipt_is_fresh(
        receipt,
        repository_identity="sha256:repo",
        generation_identity="sha256:generation",
    )
    assert promotion_evidence_identity(receipt) == receipt["receipt_identity"]


def test_stale_execution_receipt_cannot_claim_fresh_generation() -> None:
    receipt = execution_receipt(
        case_id="fresh-dogfood",
        corpus_identity=corpus_manifest_identity(_corpus()),
        identities=_identities(),
        surfaces=[
            {"surface": "task-evidence", "authority_proof_identity": "sha256:proof"}
        ],
        mutations=[],
    )
    assert not receipt_is_fresh(
        receipt,
        repository_identity="sha256:repo",
        generation_identity="sha256:new-generation",
    )


def test_execution_receipt_refuses_to_seal_mutation_violation() -> None:
    with pytest.raises(ValueError, match="cannot seal metamorphic violations"):
        execution_receipt(
            case_id="broken",
            corpus_identity=corpus_manifest_identity(_corpus()),
            identities=_identities(),
            surfaces=[
                {"surface": "task-evidence", "authority_proof_identity": "sha256:proof"}
            ],
            mutations=[{"family": "pagination", "violation": True}],
        )


def test_counterfactual_mutations_cover_invariant_and_authority_changes() -> None:
    def evaluate(payload):
        mutation = payload.get("repository_mutation")
        if mutation in {
            "replace-owner-definition",
            "duplicate-exact-owner",
            "remove-decisive-evidence",
        }:
            return "sha256:changed"
        return "sha256:baseline"

    results = run_mutation_challenges(
        {},
        evaluate=evaluate,
        challenges=repository_counterfactual_challenges(),
    )
    coverage = mutation_coverage(results)
    assert coverage["clean"] is True
    assert coverage["cases"] == 4
    assert "irrelevant-file-addition" in coverage["families"]
    assert "generation-mutation" in coverage["families"]


def test_fresh_receipt_can_authorize_shadow_to_qualification_promotion() -> None:
    corpus = _corpus()
    case = next(
        row
        for row in corpus["cases"]
        if row["case_id"] == "oh-goon-physical-attempt-reincarnation"
    )
    receipt = execution_receipt(
        case_id=case["case_id"],
        corpus_identity=corpus_manifest_identity(corpus),
        identities=_identities(),
        surfaces=[
            {"surface": "task-evidence", "authority_proof_identity": "sha256:proof"}
        ],
        mutations=[],
    )
    transition = promotion_transition(
        case,
        target_state="qualification",
        reviewer_identity="reviewer:fresh-dogfood",
        evidence_identity=promotion_evidence_identity(receipt),
    )
    assert transition["to"] == "qualification"
    assert transition["evidence_identity"] == receipt["receipt_identity"]


def test_external_evidence_receipt_keeps_conflict_without_promoting_authority() -> None:
    receipt = external_evidence_receipt(
        before_authority_proof_identity="sha256:proof",
        after_authority_proof_identity="sha256:proof",
        correlation_identity="sha256:correlation",
        conflicts=2,
    )
    assert receipt["authority_unchanged"] is True
    assert receipt["repository_authority_promoted"] is False
    assert receipt["conflicts"] == 2


def test_external_evidence_receipt_exposes_authority_interference() -> None:
    receipt = external_evidence_receipt(
        before_authority_proof_identity="sha256:before",
        after_authority_proof_identity="sha256:after",
        correlation_identity="sha256:correlation",
        conflicts=0,
    )
    assert receipt["authority_unchanged"] is False
    assert receipt["repository_authority_promoted"] is True
