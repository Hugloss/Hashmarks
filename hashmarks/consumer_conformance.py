from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import TYPE_CHECKING, NotRequired, TypedDict, cast

from ._version import __version__
from .evidence_context import validate_evidence_context
from .producer_identity import native_producer_implementation_identity
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


class NativeVerificationMember(TypedDict):
    schema: str
    path: str
    test_symbol: str | None
    member_id: str


class _NativeSelectionProducer(TypedDict):
    name: str
    version: str
    implementation_identity: str


class NativeVerificationSelectionProjection(TypedDict):
    """Detached producer-validated selection; consumer admission remains external."""

    producer: _NativeSelectionProducer
    repository_identity: str
    source_identity: str
    codemap_generation: int
    identity_generation: int | None
    stale: bool
    members: list[NativeVerificationMember]
    membership_identity: str
    selection_identity: str
    repository_provenance_identity: str
    producer_contract_identity: str
    evidence_hashes: dict[str, str]
    authority: str
    execution_layout: str


class NativeConsumerValidation(TypedDict):
    schema: str
    valid: bool
    reasons: list[str]
    producer_implementation_identity: NotRequired[object]
    identity_semantics: str
    normalized: NotRequired[Mapping[str, object] | None]
    context_identity: NotRequired[str | None]
    authority: NotRequired[str]
    execution_authority: str
    result_authority: str
    certification_authority: str


def _bundle_producer_identity(envelope: Mapping[str, object]) -> object:
    producer = envelope.get("producer")
    return (
        producer.get("implementation_identity")
        if isinstance(producer, Mapping)
        else None
    )


def _bundle_loaded_version_reasons(
    envelope: Mapping[str, object], producer_identity: object
) -> list[str]:
    """Qualify version provenance only for the implementation loaded here."""
    if producer_identity != native_producer_implementation_identity():
        return []
    producer = envelope.get("producer")
    if isinstance(producer, Mapping) and producer.get("version") != __version__:
        return ["producer-version-does-not-match-loaded-implementation"]
    return []


def _bundle_handoff_reasons(
    handoff: object,
    producer_identity: object,
) -> list[str]:
    if handoff is None:
        return []
    from .qualification_units import validate_native_qualification_handoff

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


def _normalized_bundle(
    envelope: Mapping[str, object], contract: Mapping[str, object]
) -> NativeVerificationSelectionProjection:
    """Detach one projection after native envelope and contract validation."""
    repository = cast(Mapping[str, object], envelope["repository"])
    selection = cast(Mapping[str, object], envelope["selection"])
    return NativeVerificationSelectionProjection(
        producer=deepcopy(cast(_NativeSelectionProducer, envelope["producer"])),
        repository_identity=cast(str, repository["repository_identity"]),
        source_identity=cast(str, repository["source_identity"]),
        codemap_generation=cast(int, repository["codemap_generation"]),
        identity_generation=cast(int | None, repository.get("identity_generation")),
        stale=cast(bool, repository["stale"]),
        members=deepcopy(cast(list[NativeVerificationMember], selection["members"])),
        membership_identity=cast(str, selection["membership_identity"]),
        selection_identity=cast(str, envelope["envelope_identity"]),
        repository_provenance_identity=cast(str, envelope["envelope_identity"]),
        producer_contract_identity=cast(str, contract["contract_identity"]),
        evidence_hashes=dict(cast(Mapping[str, str], envelope["evidence_hashes"])),
        authority=cast(str, contract["authority"]),
        execution_layout=cast(str, contract["execution_layout"]),
    )


def validate_native_consumer_bundle(
    envelope: object,
    contract: object = None,
    *,
    handoff: object = None,
    expected_producer_implementation_identity: str | None = None,
    require_fresh: bool = False,
) -> NativeConsumerValidation:
    """Validate Hashmarks-issued evidence without reproducing producer identity generation."""
    from .verification_collection import MEMBERSHIP_OBSERVATION_SCHEMA

    if (
        isinstance(envelope, Mapping)
        and envelope.get("schema") == MEMBERSHIP_OBSERVATION_SCHEMA
    ):
        from .verification_collection_observation import validate_membership_observation

        result = validate_membership_observation(
            envelope,
            expected_producer_implementation_identity=expected_producer_implementation_identity,
            require_fresh=require_fresh,
        )
        if contract is not None or handoff is not None:
            result["valid"] = False
            result["normalized"] = None
            result["reasons"].append(
                "membership-observation-does-not-use-legacy-contract-or-handoff"
            )
        return result
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
        *_bundle_loaded_version_reasons(envelope, producer_identity),
        *_bundle_handoff_reasons(handoff, producer_identity),
    ]
    if (
        expected_producer_implementation_identity is not None
        and producer_identity != expected_producer_implementation_identity
    ):
        reasons.append("producer-implementation-identity-not-expected")
    repository = envelope.get("repository")
    if require_fresh and (
        not isinstance(repository, Mapping) or repository.get("stale") is not False
    ):
        reasons.append("fresh-evidence-required")
    valid = not reasons
    return {
        "schema": CONSUMER_CONFORMANCE_SCHEMA,
        "valid": valid,
        "reasons": list(dict.fromkeys(reasons)),
        "producer_implementation_identity": producer_identity,
        "identity_semantics": "opaque-hashmarks-issued",
        "normalized": _normalized_bundle(envelope, contract) if valid else None,
        "authority": "repository-intelligence-only",
        "execution_authority": "external",
        "result_authority": "external",
        "certification_authority": "external",
    }


def validate_native_evidence_context_bundle(
    evidence_receipt: object,
    provenance: object,
    *,
    expected_producer_implementation_identity: str | None = None,
) -> NativeConsumerValidation:
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
    producer = handoff["producer"]
    assert isinstance(producer, Mapping)
    native_identity = str(producer["implementation_identity"])
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
    from .qualification_units import native_qualification_handoff

    handoff = native_qualification_handoff(root.resolve())
    return _consumer_conformance_vectors_from_handoff(handoff)


def validate_native_repository_evidence_bundle(
    envelope: object,
    contract: object,
    evidence_receipt: object,
    provenance: object,
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
    selection_binding = envelope.get("selection")
    return {
        "schema": "hashmarks.repository-evidence-consumer-conformance.v1",
        "valid": not reasons,
        "reasons": list(dict.fromkeys(str(reason) for reason in reasons)),
        "producer_implementation_identity": producer_identity,
        "verification_membership_identity": (
            selection_binding.get("membership_identity")
            if isinstance(selection_binding, Mapping)
            else None
        ),
        "context_identity": context.get("context_identity"),
        "authority": "repository-intelligence-only",
        "execution_authority": "external",
        "result_authority": "external",
        "certification_authority": "external",
    }
