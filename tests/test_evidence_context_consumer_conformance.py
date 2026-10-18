from hashmarks.consumer_conformance import validate_native_evidence_context_bundle
from hashmarks.evidence_context import evidence_context_identity

PRODUCER = "sha256:" + "a" * 64


def _receipt() -> dict[str, object]:
    return {
        "evidence_identity": "authority",
        "repository_identity": "repo",
        "codemap_generation": 3,
    }


def _provenance() -> dict[str, object]:
    value: dict[str, object] = {"revision": "r1", "freshness": "current"}
    value["context_identity"] = evidence_context_identity(
        _receipt(), value, producer_implementation_identity=PRODUCER
    )
    return value


def test_consumer_uses_native_validator_for_exact_context() -> None:
    state = validate_native_evidence_context_bundle(
        _receipt(), _provenance(), expected_producer_implementation_identity=PRODUCER
    )
    assert state["valid"] is True
    assert state["identity_semantics"] == "opaque-hashmarks-issued"
    assert state["execution_authority"] == "external"


def test_consumer_context_tampering_fails_closed() -> None:
    for key, value in (("revision", "r2"), ("freshness", "stale")):
        provenance = _provenance()
        provenance[key] = value
        state = validate_native_evidence_context_bundle(
            _receipt(), provenance, expected_producer_implementation_identity=PRODUCER
        )
        assert state["valid"] is False
        assert "context-identity-mismatch" in state["reasons"]


def test_consumer_wrong_admitted_producer_identity_fails_closed() -> None:
    state = validate_native_evidence_context_bundle(
        _receipt(),
        _provenance(),
        expected_producer_implementation_identity="sha256:" + "b" * 64,
    )
    assert state["valid"] is False
    assert "context-identity-mismatch" in state["reasons"]
