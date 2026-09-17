from copy import deepcopy
from pathlib import Path

from hashmarks.consumer_conformance import (
    _consumer_conformance_vectors_from_handoff,
    validate_native_consumer_bundle,
)
from hashmarks.qualification_units import (
    validate_native_qualification_handoff,
)
from hashmarks.verification_selection import (
    VerificationSelectionEnvelopeState,
    downstream_consumption_contract,
    verification_member,
    verification_membership,
    verification_selection_envelope,
)


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _bundle(identity: str) -> tuple[dict[str, object], dict[str, object]]:
    membership = verification_membership([verification_member("tests/test_x.py")])
    envelope = verification_selection_envelope(
        VerificationSelectionEnvelopeState(
            repository_identity="sha256:" + "1" * 64 + ":1",
            source_identity="sha256:" + "2" * 64,
            codemap_generation=1,
            identity_generation=1,
            stale=False,
            membership=membership,
            owner_evidence={},
            evidence_hashes={},
            producer_implementation_identity=identity,
        )
    )
    return envelope, downstream_consumption_contract(envelope)


def test_consumer_bundle_treats_producer_identity_as_opaque_pinned_value() -> None:
    identity = "sha256:" + "a" * 64
    envelope, contract = _bundle(identity)
    checked = validate_native_consumer_bundle(
        envelope,
        contract,
        expected_producer_implementation_identity=identity,
    )
    assert checked["valid"] is True
    assert checked["identity_semantics"] == "opaque-hashmarks-issued"


def test_consumer_bundle_rejects_same_version_cross_pair() -> None:
    a, a_contract = _bundle("sha256:" + "a" * 64)
    _b, b_contract = _bundle("sha256:" + "b" * 64)
    assert validate_native_consumer_bundle(a, a_contract)["valid"] is True
    result = validate_native_consumer_bundle(a, b_contract)
    assert result["valid"] is False
    assert any(
        "producer-implementation-identity-mismatch" in reason
        for reason in result["reasons"]
    )


def test_native_handoff_validator_rejects_tampering_and_keeps_authority_external(
    repository_qualification_handoff,
) -> None:
    handoff = repository_qualification_handoff
    assert validate_native_qualification_handoff(handoff)["valid"] is True
    tampered = deepcopy(handoff)
    tampered["provenance"]["producer_implementation_identity"] = "sha256:" + "f" * 64
    result = validate_native_qualification_handoff(tampered)
    assert result["valid"] is False
    assert "provenance-producer_implementation_identity-mismatch" in result["reasons"]


def test_consumer_conformance_vectors_are_deterministic_and_self_describing(
    repository_qualification_handoff,
) -> None:
    first = _consumer_conformance_vectors_from_handoff(repository_qualification_handoff)
    second = _consumer_conformance_vectors_from_handoff(
        repository_qualification_handoff
    )
    assert first == second
    assert [row["name"] for row in first] == [
        "same-version-a-with-a",
        "same-version-a-envelope-b-contract",
        "native-envelope-contract-handoff",
        "native-producer-pin-rejects-other-same-version-build",
        "boolean-codemap-generation",
        "boolean-identity-generation",
        "negative-codemap-generation",
        "negative-identity-generation",
        "overflow-codemap-generation",
        "overflow-identity-generation",
    ]
    assert all(row["result"]["valid"] == row["expected_valid"] for row in first)
    for row in first[4:]:
        assert row["expected_reason"] in row["result"]["reasons"]
        assert row["normalized_projection_allowed"] is False
        assert row["result"]["normalized"] is None


def test_consumer_bundle_cross_binds_native_handoff_producer(
    repository_qualification_handoff,
) -> None:
    handoff = repository_qualification_handoff
    identity = str(handoff["producer"]["implementation_identity"])
    envelope, contract = _bundle(identity)
    checked = validate_native_consumer_bundle(envelope, contract, handoff=handoff)
    assert checked["valid"] is True
    assert checked["execution_authority"] == "external"
    assert checked["result_authority"] == "external"
    assert checked["certification_authority"] == "external"


def test_consumer_bundle_returns_small_normalized_repository_projection() -> None:
    identity = "sha256:" + "a" * 64
    envelope, contract = _bundle(identity)
    checked = validate_native_consumer_bundle(envelope, contract)
    assert checked["valid"] is True
    assert checked["authority"] == "repository-intelligence-only"
    normalized = checked["normalized"]
    assert normalized["producer"]["implementation_identity"] == identity
    assert (
        normalized["repository_identity"]
        == envelope["repository"]["repository_identity"]
    )
    assert normalized["source_identity"] == envelope["repository"]["source_identity"]
    assert (
        normalized["membership_identity"]
        == envelope["selection"]["membership_identity"]
    )
    assert normalized["selection_identity"] == envelope["envelope_identity"]
    assert normalized["stale"] is False
    assert "timeout" not in normalized
    assert "workers" not in normalized


def test_consumer_bundle_can_require_fresh_repository_evidence() -> None:
    identity = "sha256:" + "a" * 64
    membership = verification_membership([verification_member("tests/test_x.py")])
    envelope = verification_selection_envelope(
        VerificationSelectionEnvelopeState(
            repository_identity="sha256:" + "1" * 64 + ":1",
            source_identity="sha256:" + "2" * 64,
            codemap_generation=1,
            identity_generation=1,
            stale=True,
            membership=membership,
            owner_evidence={},
            evidence_hashes={},
            producer_implementation_identity=identity,
        )
    )
    contract = downstream_consumption_contract(envelope)
    assert validate_native_consumer_bundle(envelope, contract)["valid"] is True
    checked = validate_native_consumer_bundle(envelope, contract, require_fresh=True)
    assert checked["valid"] is False
    assert "fresh-evidence-required" in checked["reasons"]


def test_consumer_bundle_rejects_unknown_native_authority_fields_even_with_recomputed_identity() -> (
    None
):
    from hashmarks.verification_selection import SELECTION_ENVELOPE_SCHEMA, _identity

    identity = "sha256:" + "a" * 64
    envelope, _contract = _bundle(identity)
    tampered = deepcopy(envelope)
    tampered["timeout"] = 30
    payload = {
        key: value for key, value in tampered.items() if key != "envelope_identity"
    }
    tampered["envelope_identity"] = _identity(SELECTION_ENVELOPE_SCHEMA, payload)
    # Contract construction itself must fail closed on the unsupported producer field.
    checked = validate_native_consumer_bundle(tampered, {})
    assert checked["valid"] is False
    assert "envelope:unexpected-envelope-field:timeout" in checked["reasons"]


def test_consumer_bundle_rejects_unknown_nested_native_fields() -> None:
    from hashmarks.verification_selection import SELECTION_ENVELOPE_SCHEMA, _identity

    identity = "sha256:" + "a" * 64
    envelope, _contract = _bundle(identity)
    tampered = deepcopy(envelope)
    tampered["repository"]["workers"] = 8
    payload = {
        key: value for key, value in tampered.items() if key != "envelope_identity"
    }
    tampered["envelope_identity"] = _identity(SELECTION_ENVELOPE_SCHEMA, payload)
    checked = validate_native_consumer_bundle(tampered, {})
    assert checked["valid"] is False
    assert "envelope:unexpected-repository-field:workers" in checked["reasons"]


def test_consumer_bundle_rejects_unknown_producer_and_member_fields() -> None:
    from hashmarks.verification_selection import SELECTION_ENVELOPE_SCHEMA, _identity

    identity = "sha256:" + "a" * 64
    envelope, _contract = _bundle(identity)
    for section, key, value, expected_reason in (
        (
            "producer",
            "retry_count",
            2,
            "envelope:unexpected-producer-field:retry_count",
        ),
        (
            "selection",
            "execution_order",
            "serial",
            "envelope:unexpected-membership-field:execution_order",
        ),
    ):
        tampered = deepcopy(envelope)
        tampered[section][key] = value
        payload = {k: v for k, v in tampered.items() if k != "envelope_identity"}
        tampered["envelope_identity"] = _identity(SELECTION_ENVELOPE_SCHEMA, payload)
        checked = validate_native_consumer_bundle(tampered, {})
        assert checked["valid"] is False
        assert expected_reason in checked["reasons"]

    tampered = deepcopy(envelope)
    tampered["selection"]["members"][0]["isolated_process"] = True
    payload = {k: v for k, v in tampered.items() if k != "envelope_identity"}
    tampered["envelope_identity"] = _identity(SELECTION_ENVELOPE_SCHEMA, payload)
    checked = validate_native_consumer_bundle(tampered, {})
    assert checked["valid"] is False
    assert "envelope:unexpected-member-field:isolated_process" in checked["reasons"]


def test_consumer_bundle_rejects_unsupported_native_schema_even_when_rehashed() -> None:
    from hashmarks.verification_selection import SELECTION_ENVELOPE_SCHEMA, _identity

    identity = "sha256:" + "a" * 64
    envelope, _contract = _bundle(identity)
    tampered = deepcopy(envelope)
    tampered["schema"] = "hashmarks.verification-selection-envelope.v999"
    payload = {
        key: value for key, value in tampered.items() if key != "envelope_identity"
    }
    tampered["envelope_identity"] = _identity(SELECTION_ENVELOPE_SCHEMA, payload)
    checked = validate_native_consumer_bundle(tampered, {})
    assert checked["valid"] is False
    assert "envelope:unsupported-envelope-schema" in checked["reasons"]


def test_invalid_bundle_never_emits_normalized_projection() -> None:
    identity = "sha256:" + "a" * 64
    envelope, contract = _bundle(identity)
    envelope["repository"]["codemap_generation"] = True
    checked = validate_native_consumer_bundle(envelope, contract)
    assert checked["valid"] is False
    assert "envelope:invalid-codemap-generation" in checked["reasons"]
    assert checked["normalized"] is None


def test_native_handoff_validator_fails_closed_for_nonportable_payload(
    repository_qualification_handoff,
) -> None:
    tampered = deepcopy(repository_qualification_handoff)
    tampered["nonportable"] = float("nan")
    result = validate_native_qualification_handoff(tampered)
    assert result["valid"] is False
    assert "handoff-not-canonical-json" in result["reasons"]
    assert result["handoff_identity"] is None
