from copy import deepcopy

from hashmarks.consumer_conformance import validate_native_repository_evidence_bundle
from hashmarks.evidence_context import evidence_context_identity
from hashmarks.verification_selection import (
    VerificationSelectionEnvelopeState,
    downstream_consumption_contract,
    verification_member,
    verification_membership,
    verification_selection_envelope,
)

PRODUCER_A = "sha256:" + "a" * 64
PRODUCER_B = "sha256:" + "b" * 64
REPO_A = "sha256:" + "1" * 64 + ":1"
REPO_B = "sha256:" + "2" * 64 + ":1"


def _bundle(producer=PRODUCER_A, repo=REPO_A, generation=7):
    membership = verification_membership([verification_member("tests/test_a.py", test_symbol="test_a")])
    envelope = verification_selection_envelope(VerificationSelectionEnvelopeState(
        repository_identity=repo,
        source_identity="sha256:" + "3" * 64,
        codemap_generation=generation,
        identity_generation=3,
        stale=False,
        membership=membership,
        owner_evidence={"status": "resolved"},
        evidence_hashes={"ownership": "sha256:" + "4" * 64},
        producer_implementation_identity=producer,
    ))
    contract = downstream_consumption_contract(envelope)
    receipt = {"evidence_identity": "sha256:" + "5" * 64, "repository_identity": repo, "codemap_generation": generation}
    provenance = {"revision": {"path": "pyproject.toml", "sha256": "sha256:" + "6" * 64}, "freshness": "proven"}
    provenance["context_identity"] = evidence_context_identity(receipt, provenance, producer_implementation_identity=producer)
    return envelope, contract, receipt, provenance


def test_accepts_same_producer_repository_and_generation():
    assert validate_native_repository_evidence_bundle(*_bundle(), expected_producer_implementation_identity=PRODUCER_A)["valid"] is True


def test_rejects_cross_producer_context_pairing():
    envelope, contract, _, _ = _bundle(PRODUCER_A)
    _, _, receipt, provenance = _bundle(PRODUCER_B)
    state = validate_native_repository_evidence_bundle(envelope, contract, receipt, provenance, expected_producer_implementation_identity=PRODUCER_A)
    assert state["valid"] is False
    assert "context:context-identity-mismatch" in state["reasons"]


def test_rejects_cross_repository_pairing_even_when_each_side_is_self_consistent():
    envelope, contract, _, _ = _bundle(PRODUCER_A, REPO_A)
    _, _, receipt, provenance = _bundle(PRODUCER_A, REPO_B)
    state = validate_native_repository_evidence_bundle(envelope, contract, receipt, provenance, expected_producer_implementation_identity=PRODUCER_A)
    assert "cross-contract-repository-identity-mismatch" in state["reasons"]


def test_rejects_cross_generation_pairing_even_when_each_side_is_self_consistent():
    envelope, contract, _, _ = _bundle(PRODUCER_A, REPO_A, 7)
    _, _, receipt, provenance = _bundle(PRODUCER_A, REPO_A, 8)
    state = validate_native_repository_evidence_bundle(envelope, contract, receipt, provenance, expected_producer_implementation_identity=PRODUCER_A)
    assert "cross-contract-codemap-generation-mismatch" in state["reasons"]


def test_rejects_tampered_verification_membership_with_valid_context():
    envelope, contract, receipt, provenance = _bundle()
    tampered = deepcopy(envelope)
    tampered["selection"]["members"][0]["member_id"] = "sha256:" + "f" * 64
    state = validate_native_repository_evidence_bundle(tampered, contract, receipt, provenance, expected_producer_implementation_identity=PRODUCER_A)
    assert state["valid"] is False
    assert any(reason.startswith("selection:") for reason in state["reasons"])
