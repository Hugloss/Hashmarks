import pytest
from hashmarks.evidence_context import evidence_context_identity, validate_evidence_context

PRODUCER = "sha256:" + "1" * 64


def _receipt() -> dict[str, object]:
    return {"evidence_identity": "a", "repository_identity": "repo", "codemap_generation": 7}


def _provenance() -> dict[str, object]:
    return {"revision": "r1", "freshness": "unknown"}


def test_native_context_validation_accepts_exact_producer_identity() -> None:
    receipt, provenance = _receipt(), _provenance()
    provenance["context_identity"] = evidence_context_identity(receipt, provenance, producer_implementation_identity=PRODUCER)
    assert validate_evidence_context(receipt, provenance, producer_implementation_identity=PRODUCER)["valid"] is True


def test_native_context_validation_rejects_tampered_revision_or_freshness() -> None:
    receipt, provenance = _receipt(), _provenance()
    provenance["context_identity"] = evidence_context_identity(receipt, provenance, producer_implementation_identity=PRODUCER)
    for key, value in (("revision", "r2"), ("freshness", "proven")):
        tampered = dict(provenance); tampered[key] = value
        result = validate_evidence_context(receipt, tampered, producer_implementation_identity=PRODUCER)
        assert result["valid"] is False
        assert "context-identity-mismatch" in result["reasons"]


def test_native_context_validation_rejects_tampered_authority() -> None:
    receipt, provenance = _receipt(), _provenance()
    provenance["context_identity"] = evidence_context_identity(receipt, provenance, producer_implementation_identity=PRODUCER)
    changed = dict(receipt); changed["evidence_identity"] = "other"
    assert validate_evidence_context(changed, provenance, producer_implementation_identity=PRODUCER)["valid"] is False


def test_context_identity_rejects_nonportable_generation_and_scalar_coercion() -> None:
    import math
    for generation in (True, 1.0, -1, math.nan, 2**53):
        receipt = _receipt(); receipt["codemap_generation"] = generation
        with pytest.raises(ValueError):
            evidence_context_identity(receipt, _provenance(), producer_implementation_identity=PRODUCER)
    provenance = _provenance(); provenance["freshness"] = False
    with pytest.raises(ValueError):
        evidence_context_identity(_receipt(), provenance, producer_implementation_identity=PRODUCER)


def test_context_validator_fails_closed_for_invalid_semantic_payloads() -> None:
    import math

    valid_receipt, valid_provenance = _receipt(), _provenance()
    valid_provenance["context_identity"] = evidence_context_identity(
        valid_receipt, valid_provenance, producer_implementation_identity=PRODUCER
    )
    cases = []
    for generation in (True, 1.0, -1, math.nan, 2**53):
        receipt = dict(valid_receipt); receipt["codemap_generation"] = generation
        cases.append((receipt, dict(valid_provenance), PRODUCER))
    for freshness in (False, 1, " "):
        provenance = dict(valid_provenance); provenance["freshness"] = freshness
        cases.append((dict(valid_receipt), provenance, PRODUCER))
    provenance = dict(valid_provenance); provenance["revision"] = math.nan
    cases.append((dict(valid_receipt), provenance, PRODUCER))
    cases.append((dict(valid_receipt), dict(valid_provenance), "bad"))

    for receipt, provenance, producer in cases:
        result = validate_evidence_context(
            receipt, provenance, producer_implementation_identity=producer
        )
        assert result["valid"] is False
        assert "invalid-context-payload" in result["reasons"]
