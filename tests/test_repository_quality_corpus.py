from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.agent_evaluation.repository_quality_convergence import (
    require_surface_convergence,
)
from scripts.agent_evaluation.repository_quality_corpus import (
    corpus_layer_health,
    corpus_manifest_identity,
    promotion_transition,
    qualification_membership_identity,
    validate_manifest,
)
from scripts.agent_evaluation.repository_quality_mutation import (
    MutationChallenge,
    run_mutation_challenges,
)

ROOT = Path(__file__).resolve().parents[1]


def _manifest() -> dict:
    return json.loads(
        (ROOT / "benchmarks/repository_quality/retained-real-world.v1.json").read_text()
    )


def test_retained_real_world_manifest_is_valid_and_identity_bound() -> None:
    manifest = _manifest()
    validate_manifest(manifest)
    assert corpus_manifest_identity(manifest).startswith("sha256:")
    assert qualification_membership_identity(manifest).startswith("sha256:")
    cases = {case["case_id"]: case for case in manifest["cases"]}
    assert (
        cases["oh-goon-993-publish-strict-attempt-outputs"]["state"] == "qualification"
    )
    assert cases["oh-goon-physical-attempt-reincarnation"]["state"] == "shadow"


def test_diagnostic_membership_does_not_change_qualification_identity() -> None:
    manifest = _manifest()
    baseline = qualification_membership_identity(manifest)
    manifest["cases"].append(
        {
            "case_id": "fresh-canary",
            "layer": "L3-fresh-dogfood",
            "state": "canary",
            "task": "fresh task",
            "source_identity": "sha256:fresh",
            "ground_truth_basis": "fresh reviewed evidence",
            "provenance_reference": "fresh dogfood run",
        }
    )
    assert qualification_membership_identity(manifest) == baseline
    assert corpus_manifest_identity(manifest) != corpus_manifest_identity(_manifest())


def test_real_world_case_without_provenance_fails_closed() -> None:
    manifest = _manifest()
    manifest["cases"][0].pop("provenance_reference")
    with pytest.raises(ValueError, match="requires provenance_reference"):
        validate_manifest(manifest)


def test_promotion_to_qualification_is_explicit_and_identity_bound() -> None:
    case = next(
        case
        for case in _manifest()["cases"]
        if case["case_id"] == "oh-goon-physical-attempt-reincarnation"
    )
    transition = promotion_transition(
        case,
        target_state="qualification",
        reviewer_identity="reviewer:dogfood",
        evidence_identity="sha256:fresh-proof",
    )
    assert transition["from"] == "shadow"
    assert transition["to"] == "qualification"
    assert transition["transition_identity"].startswith("sha256:")


def test_historical_case_cannot_be_silently_repromoted() -> None:
    case = dict(_manifest()["cases"][0], state="historical")
    with pytest.raises(ValueError, match="shadow or canary"):
        promotion_transition(
            case,
            target_state="qualification",
            reviewer_identity="reviewer:dogfood",
            evidence_identity="sha256:fresh-proof",
        )


def test_mutation_harness_enforces_presentation_invariance_and_generation_change() -> (
    None
):
    def evaluate(payload):
        if payload.get("owner_generation_mutation"):
            return "sha256:new-owner"
        return "sha256:baseline"

    results = run_mutation_challenges({"limit": 20}, evaluate=evaluate)
    assert not [row for row in results if row["violation"]]
    generation = next(row for row in results if row["family"] == "generation-mutation")
    assert generation["proof_changed"] is True


def test_mutation_harness_detects_limit_sensitive_authority_bug() -> None:
    def evaluate(payload):
        return "sha256:wrong" if payload.get("limit") == 1 else "sha256:baseline"

    results = run_mutation_challenges(
        {"limit": 20},
        evaluate=evaluate,
        challenges=(
            MutationChallenge(
                "retrieval-limit",
                "invariant",
                lambda payload: {**payload, "limit": 1},
            ),
        ),
    )
    assert results[0]["violation"] is True
    assert results[0]["presentation_only"] is True


def test_corpus_health_distinguishes_retained_from_fresh_dogfood() -> None:
    health = corpus_layer_health(_manifest())
    assert health["has_retained_real_world"] is True
    assert health["has_fresh_dogfood"] is False
    assert health["fresh_dogfood_qualified"] is False
    assert health["qualification_layers"]["L2-retained-real-world"] == 2


def test_cross_surface_authority_convergence_requires_one_proof_identity() -> None:
    rows = [
        {"surface": surface, "authority_proof_identity": "sha256:proof"}
        for surface in ("task-evidence", "mcp", "compact", "tests")
    ]
    result = require_surface_convergence(
        rows, ("task-evidence", "mcp", "compact", "tests")
    )
    assert result["complete"] is True
    assert result["authority_proof_identities"] == ["sha256:proof"]


def test_cross_surface_authority_drift_remains_visible() -> None:
    rows = [
        {"surface": "task-evidence", "authority_proof_identity": "sha256:a"},
        {"surface": "mcp", "authority_proof_identity": "sha256:b"},
    ]
    result = require_surface_convergence(rows, ("task-evidence", "mcp"))
    assert result["converged"] is False
    assert result["complete"] is False
