from __future__ import annotations

from copy import deepcopy

from hashmarks import (
    native_producer_implementation_identity,
    validate_repository_intelligence_evidence,
)


def _sha(char: str) -> str:
    return "sha256:" + char * 64


def _decision_packet() -> dict[str, object]:
    return {
        "schema": "hashmarks.task-decision-packet.v2",
        "task": "repair admission",
        "edit": {"path": "src/owner.py"},
        "verify": {"path": "tests/test_owner.py"},
        "discrimination": {"needed": False, "reason": ""},
        "identity": {
            "schema": "hashmarks.worker-packet-identity.v1",
            "repository_identity": "repo:one",
            "codemap_generation": 7,
            "identity_generation": 7,
            "stale": False,
            "codemap_complete": True,
            "task_identity": _sha("1"),
            "decision_generation": _sha("2"),
        },
        "canonical_generation": 7,
        "authority": "repository-observation-only",
    }


def test_public_validator_binds_current_decision_to_loaded_producer() -> None:
    checked = validate_repository_intelligence_evidence(
        _decision_packet(), require_fresh=True
    )
    assert checked["valid"] is True
    normalized = checked["normalized"]
    assert normalized["evidence_kind"] == "decision"
    assert normalized["repository_identity"] == "repo:one"
    assert normalized["codemap_generation"] == 7
    assert normalized["stale"] is False
    assert (
        normalized["producer_implementation_identity"]
        == native_producer_implementation_identity()
    )
    assert checked["execution_authority"] == "external"
    assert checked["result_authority"] == "external"
    assert checked["certification_authority"] == "external"


def test_public_validator_rejects_stale_or_inconsistent_decision() -> None:
    stale = _decision_packet()
    stale["identity"]["stale"] = True
    checked = validate_repository_intelligence_evidence(stale, require_fresh=True)
    assert checked["valid"] is False
    assert "fresh-evidence-required" in checked["reasons"]

    inconsistent = _decision_packet()
    inconsistent["canonical_generation"] = 8
    checked = validate_repository_intelligence_evidence(inconsistent)
    assert checked["valid"] is False
    assert "canonical-generation-mismatch" in checked["reasons"]


def test_public_validator_owns_current_schema_registry_without_legacy_aliases() -> None:
    for schema in (
        "hashmarks.agent-change-impact.v1",
        "hashmarks.task-recovery-brief.v1",
        "hashmarks.recovery-delta.v1",
    ):
        checked = validate_repository_intelligence_evidence({"schema": schema})
        assert checked["valid"] is False
        assert "unsupported-evidence-schema" in checked["reasons"]

    checked = validate_repository_intelligence_evidence(
        {
            "schema": "hashmarks.task-change-impact.v1",
            "generation": 3,
            "changed": [],
            "changed_evidence": {
                "reported": 0,
                "accounted_for": 0,
                "complete": True,
                "states": {},
            },
            "surfaces": {},
            "bounds": {"depth": 1, "per_surface": 1, "project_impact": 1},
            "authority": "advisory",
            "owner": "external",
            "completeness": "not-claimed",
        }
    )
    assert checked["valid"] is True
    assert checked["normalized"]["evidence_kind"] == "impact"


def test_public_validator_treats_action_map_as_evidence_not_execution() -> None:
    checked = validate_repository_intelligence_evidence(
        {
            "schema": "hashmarks.task-action-map.v1",
            "ownership_authority": {
                "schema": "hashmarks.ownership-authority.v1",
                "status": "resolved",
                "owner_resolved": True,
                "resolved_owner": "src/owner.py",
                "candidate_owner": "src/owner.py",
                "reason": "unique-owner-established",
                "authority": "repository-ownership-only",
                "consumer_action": "external",
                "proof_complete": True,
                "proof_scope": {},
                "proof_scope_complete": True,
                "authority_proof_identity": _sha("3"),
                "evidence_state": {},
            },
        }
    )
    assert checked["valid"] is True
    assert checked["normalized"]["evidence_kind"] == "action-map"
    assert checked["execution_authority"] == "external"

    tampered = deepcopy(checked)
    assert tampered["normalized"]["evidence_kind"] == "action-map"


def test_public_validator_requires_executable_shape_only_for_available_verification() -> None:
    checked = validate_repository_intelligence_evidence(
        {
            "schema": "hashmarks.verification-plan.v1",
            "path": "tests/test_x.py",
            "available": True,
            "runner": "pytest",
            "argv": ["python", "-m", "pytest", "-q", "tests/test_x.py"],
            "working_directory": ".",
            "confidence": "high",
            "evidence": "python-test-domain",
        }
    )
    assert checked["valid"] is True
    assert checked["normalized"]["evidence_kind"] == "verification"
    assert checked["normalized"]["available"] is True

    invalid = validate_repository_intelligence_evidence(
        {
            "schema": "hashmarks.verification-plan.v1",
            "path": "tests/test_x.py",
            "available": True,
            "argv": [],
            "working_directory": ".",
        }
    )
    assert invalid["valid"] is False
    assert "invalid-verification-argv" in invalid["reasons"]


def test_public_validator_checks_snapshot_and_delta_observer_authority() -> None:
    snapshot = {
        "schema": "hashmarks.repository-intelligence-snapshot.v1",
        "observer": {
            "schema": "hashmarks.repository-observer.v1",
            "identity": _sha("4"),
        },
        "repository": {
            "repository_identity": "repo:one",
            "codemap_generation": 11,
            "stale": False,
        },
        "authority": "repository-intelligence-only",
        "execution_effect": "none",
        "snapshot_identity": _sha("5"),
    }
    checked = validate_repository_intelligence_evidence(snapshot, require_fresh=True)
    assert checked["valid"] is True
    assert checked["normalized"]["repository_identity"] == "repo:one"
    assert checked["normalized"]["codemap_generation"] == 11

    delta = {
        "schema": "hashmarks.repository-intelligence-delta.v1",
        "repository_identity": "repo:one",
        "from": {"snapshot_identity": _sha("5"), "codemap_generation": 10},
        "to": {"snapshot_identity": _sha("6"), "codemap_generation": 11},
        "authority": "repository-intelligence-only",
        "execution_effect": "none",
        "delta_identity": _sha("7"),
    }
    checked = validate_repository_intelligence_evidence(delta)
    assert checked["valid"] is True
    assert checked["normalized"]["codemap_generation"] == 11


def test_public_validator_rejects_nonportable_payload() -> None:
    checked = validate_repository_intelligence_evidence(
        {
            "schema": "hashmarks.task-context-plan.v1",
            "task": "x",
            "query": "x",
            "token_budget": 128,
            "disclosure": "outline",
            "limit": 20,
            "reasons": [float("nan")],
            "ranking_effect": "none",
        }
    )
    assert checked["valid"] is False
    assert "nonportable-evidence-payload" in checked["reasons"]
    assert checked["normalized"] is None
