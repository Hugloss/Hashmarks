from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import TYPE_CHECKING

from .evidence_context import validate_evidence_context
from .qualification_units import (
    native_qualification_handoff,
    validate_native_qualification_handoff,
)
from .validation_inputs import require_mapping_for_validation
from .verification_selection import (
    VerificationSelectionEnvelopeState,
    downstream_consumption_contract,
    validate_downstream_consumption_contract,
    validate_verification_selection_envelope,
    verification_member,
    verification_membership,
    verification_selection_envelope,
)

if TYPE_CHECKING:
    from pathlib import Path

CONSUMER_CONFORMANCE_SCHEMA = "hashmarks.consumer-conformance.v1"
CONSUMER_VECTOR_SCHEMA = "hashmarks.consumer-conformance-vector.v1"


def _bundle_producer_identity(envelope: Mapping[str, object]) -> object:
    producer = envelope.get("producer")
    return (
        producer.get("implementation_identity")
        if isinstance(producer, Mapping)
        else None
    )


def _bundle_handoff_reasons(
    handoff: Mapping[str, object] | None,
    producer_identity: object,
) -> list[str]:
    if handoff is None:
        return []
    if not isinstance(handoff, Mapping):
        state = validate_native_qualification_handoff(handoff)
        return [f"handoff:{reason}" for reason in state.get("reasons", [])]
    state = validate_native_qualification_handoff(handoff)
    reasons = [f"handoff:{reason}" for reason in state.get("reasons", [])]
    handoff_producer = handoff.get("producer")
    handoff_identity = (
        handoff_producer.get("implementation_identity")
        if isinstance(handoff_producer, Mapping)
        else None
    )
    if handoff_identity != producer_identity:
        reasons.append("envelope-handoff-producer-mismatch")
    return reasons


def validate_native_consumer_bundle(
    envelope: Mapping[str, object],
    contract: Mapping[str, object],
    *,
    handoff: Mapping[str, object] | None = None,
    expected_producer_implementation_identity: str | None = None,
    require_fresh: bool = False,
) -> dict[str, object]:
    """Validate Hashmarks-issued evidence without reproducing producer identity generation."""
    envelope, envelope_root_reasons = require_mapping_for_validation(
        envelope, reason="invalid-envelope"
    )
    contract, contract_root_reasons = require_mapping_for_validation(
        contract, reason="invalid-contract"
    )
    envelope_state = validate_verification_selection_envelope(envelope)
    contract_state = validate_downstream_consumption_contract(envelope, contract)
    producer_identity = _bundle_producer_identity(envelope)
    reasons = [
        *envelope_root_reasons,
        *contract_root_reasons,
        *(f"envelope:{reason}" for reason in envelope_state.get("reasons", [])),
        *(f"contract:{reason}" for reason in contract_state.get("reasons", [])),
        *_bundle_handoff_reasons(handoff, producer_identity),
    ]
    if (
        expected_producer_implementation_identity is not None
        and producer_identity != expected_producer_implementation_identity
    ):
        reasons.append("producer-implementation-identity-not-expected")
    repository = envelope.get("repository")
    repository_binding = repository if isinstance(repository, Mapping) else {}
    if require_fresh and repository_binding.get("stale") is not False:
        reasons.append("fresh-evidence-required")
    producer = envelope.get("producer")
    producer_binding = producer if isinstance(producer, Mapping) else {}
    selection = envelope.get("selection")
    selection_binding = selection if isinstance(selection, Mapping) else {}
    normalized = {
        "producer": {
            "name": producer_binding.get("name"),
            "version": producer_binding.get("version"),
            "implementation_identity": producer_identity,
        },
        "repository_identity": repository_binding.get("repository_identity"),
        "source_identity": repository_binding.get("source_identity"),
        "codemap_generation": repository_binding.get("codemap_generation"),
        "identity_generation": repository_binding.get("identity_generation"),
        "stale": repository_binding.get("stale"),
        "members": list(selection_binding.get("members", []))
        if isinstance(selection_binding.get("members"), list)
        else [],
        "membership_identity": selection_binding.get("membership_identity"),
        "selection_identity": envelope.get("envelope_identity"),
        "repository_provenance_identity": envelope.get("envelope_identity"),
    }
    valid = not reasons
    return {
        "schema": CONSUMER_CONFORMANCE_SCHEMA,
        "valid": valid,
        "reasons": list(dict.fromkeys(reasons)),
        "producer_implementation_identity": producer_identity,
        "identity_semantics": "opaque-hashmarks-issued",
        "normalized": normalized if valid else None,
        "authority": "repository-intelligence-only",
        "execution_authority": "external",
        "result_authority": "external",
        "certification_authority": "external",
    }


def validate_native_evidence_context_bundle(
    evidence_receipt: Mapping[str, object],
    provenance: Mapping[str, object],
    *,
    expected_producer_implementation_identity: str | None = None,
) -> dict[str, object]:
    """Validate producer-owned evidence context without reproducing its hash semantics.

    Downstream consumers supply the producer identity they admitted. Hashmarks owns
    context canonicalization and identity validation; execution remains external.
    """
    evidence_receipt, receipt_root_reasons = require_mapping_for_validation(
        evidence_receipt, reason="invalid-evidence-receipt"
    )
    provenance, provenance_root_reasons = require_mapping_for_validation(
        provenance, reason="invalid-provenance"
    )
    state = validate_evidence_context(
        evidence_receipt,
        provenance,
        producer_implementation_identity=expected_producer_implementation_identity,
    )
    reasons = [
        *receipt_root_reasons,
        *provenance_root_reasons,
        *(str(reason) for reason in state.get("reasons", [])),
    ]
    return {
        "schema": "hashmarks.evidence-context-consumer-conformance.v1",
        "valid": not reasons,
        "reasons": reasons,
        "context_identity": state.get("context_identity"),
        "identity_semantics": "opaque-hashmarks-issued",
        "execution_authority": "external",
        "result_authority": "external",
        "certification_authority": "external",
    }


def _synthetic_envelope(producer_identity: str) -> dict[str, object]:
    membership = verification_membership(
        [verification_member("tests/test_consumer.py", test_symbol="test_contract")]
    )
    return verification_selection_envelope(
        VerificationSelectionEnvelopeState(
            repository_identity="sha256:" + "1" * 64 + ":1",
            source_identity="sha256:" + "2" * 64,
            codemap_generation=1,
            identity_generation=1,
            stale=False,
            membership=membership,
            owner_evidence={"status": "resolved"},
            evidence_hashes={"ownership": "sha256:" + "3" * 64},
            producer_implementation_identity=producer_identity,
        )
    )


def _consumer_conformance_vectors_from_handoff(
    handoff: Mapping[str, object],
) -> tuple[dict[str, object], ...]:
    """Project one immutable native handoff into consumer conformance vectors."""
    a_identity = "sha256:" + "a" * 64
    b_identity = "sha256:" + "b" * 64
    envelope_a = _synthetic_envelope(a_identity)
    envelope_b = _synthetic_envelope(b_identity)
    contract_a = downstream_consumption_contract(envelope_a)
    contract_b = downstream_consumption_contract(envelope_b)
    native_identity = str(handoff["producer"]["implementation_identity"])
    native_envelope = _synthetic_envelope(native_identity)
    native_contract = downstream_consumption_contract(native_envelope)

    def invalid_generation_vector(
        name: str, field: str, value: object, reason: str
    ) -> dict[str, object]:
        tampered = deepcopy(native_envelope)
        repository = tampered["repository"]
        assert isinstance(repository, dict)
        repository[field] = value
        result = validate_native_consumer_bundle(tampered, native_contract)
        return {
            "schema": CONSUMER_VECTOR_SCHEMA,
            "name": name,
            "expected_valid": False,
            "expected_reason": f"envelope:{reason}",
            "normalized_projection_allowed": False,
            "result": result,
        }

    return (
        {
            "schema": CONSUMER_VECTOR_SCHEMA,
            "name": "same-version-a-with-a",
            "expected_valid": True,
            "result": validate_native_consumer_bundle(
                envelope_a,
                contract_a,
                expected_producer_implementation_identity=a_identity,
            ),
        },
        {
            "schema": CONSUMER_VECTOR_SCHEMA,
            "name": "same-version-a-envelope-b-contract",
            "expected_valid": False,
            "result": validate_native_consumer_bundle(envelope_a, contract_b),
        },
        {
            "schema": CONSUMER_VECTOR_SCHEMA,
            "name": "native-envelope-contract-handoff",
            "expected_valid": True,
            "result": validate_native_consumer_bundle(
                native_envelope,
                native_contract,
                handoff=handoff,
                expected_producer_implementation_identity=native_identity,
            ),
        },
        {
            "schema": CONSUMER_VECTOR_SCHEMA,
            "name": "native-producer-pin-rejects-other-same-version-build",
            "expected_valid": False,
            "result": validate_native_consumer_bundle(
                native_envelope,
                native_contract,
                expected_producer_implementation_identity=b_identity,
            ),
        },
        invalid_generation_vector(
            "boolean-codemap-generation",
            "codemap_generation",
            True,
            "invalid-codemap-generation",
        ),
        invalid_generation_vector(
            "boolean-identity-generation",
            "identity_generation",
            False,
            "invalid-identity-generation",
        ),
        invalid_generation_vector(
            "negative-codemap-generation",
            "codemap_generation",
            -1,
            "invalid-codemap-generation",
        ),
        invalid_generation_vector(
            "negative-identity-generation",
            "identity_generation",
            -1,
            "invalid-identity-generation",
        ),
        invalid_generation_vector(
            "overflow-codemap-generation",
            "codemap_generation",
            1 << 53,
            "invalid-codemap-generation",
        ),
        invalid_generation_vector(
            "overflow-identity-generation",
            "identity_generation",
            1 << 53,
            "invalid-identity-generation",
        ),
    )


def consumer_conformance_vectors(root: Path) -> tuple[dict[str, object], ...]:
    """Return deterministic interoperability vectors for downstream consumers."""
    handoff = native_qualification_handoff(root.resolve())
    return _consumer_conformance_vectors_from_handoff(handoff)


def validate_native_repository_evidence_bundle(
    envelope: Mapping[str, object],
    contract: Mapping[str, object],
    evidence_receipt: Mapping[str, object],
    provenance: Mapping[str, object],
    *,
    expected_producer_implementation_identity: str | None = None,
) -> dict[str, object]:
    """Validate verification-selection and evidence-context as one producer-bound bundle.

    The two contracts remain independently versioned.  This validator only proves
    that both were issued by the same admitted Hashmarks implementation and refer
    to the same repository identity/generation; it creates no execution authority.
    """
    envelope, envelope_root_reasons = require_mapping_for_validation(
        envelope, reason="invalid-envelope"
    )
    contract, contract_root_reasons = require_mapping_for_validation(
        contract, reason="invalid-contract"
    )
    evidence_receipt, receipt_root_reasons = require_mapping_for_validation(
        evidence_receipt, reason="invalid-evidence-receipt"
    )
    provenance, provenance_root_reasons = require_mapping_for_validation(
        provenance, reason="invalid-provenance"
    )
    selection = validate_native_consumer_bundle(
        envelope,
        contract,
        expected_producer_implementation_identity=expected_producer_implementation_identity,
    )
    producer_identity = selection.get("producer_implementation_identity")
    context = validate_native_evidence_context_bundle(
        evidence_receipt,
        provenance,
        expected_producer_implementation_identity=(
            str(producer_identity)
            if isinstance(producer_identity, str)
            else expected_producer_implementation_identity
        ),
    )
    reasons = [
        *envelope_root_reasons,
        *contract_root_reasons,
        *receipt_root_reasons,
        *provenance_root_reasons,
        *(f"selection:{reason}" for reason in selection.get("reasons", [])),
        *(f"context:{reason}" for reason in context.get("reasons", [])),
    ]
    repository = envelope.get("repository")
    envelope_repository = repository if isinstance(repository, Mapping) else {}
    if envelope_repository.get("repository_identity") != evidence_receipt.get(
        "repository_identity"
    ):
        reasons.append("cross-contract-repository-identity-mismatch")
    if envelope_repository.get("codemap_generation") != evidence_receipt.get(
        "codemap_generation"
    ):
        reasons.append("cross-contract-codemap-generation-mismatch")
    return {
        "schema": "hashmarks.repository-evidence-consumer-conformance.v1",
        "valid": not reasons,
        "reasons": list(dict.fromkeys(str(reason) for reason in reasons)),
        "producer_implementation_identity": producer_identity,
        "verification_membership_identity": (
            envelope.get("selection", {}).get("membership_identity")
            if isinstance(envelope.get("selection"), Mapping)
            else None
        ),
        "context_identity": context.get("context_identity"),
        "authority": "repository-intelligence-only",
        "execution_authority": "external",
        "result_authority": "external",
        "certification_authority": "external",
    }
