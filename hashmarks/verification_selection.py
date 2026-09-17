from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ._version import __version__
from .generation_domain import is_valid_generation, require_generation
from .paths import normalize_relative_path
from .producer_identity import native_producer_implementation_identity
from .validation_inputs import require_mapping_for_validation

MEMBER_SCHEMA = "hashmarks.verification-member.v1"
MEMBERSHIP_SCHEMA = "hashmarks.verification-membership.v1"
SELECTION_ENVELOPE_SCHEMA = "hashmarks.verification-selection-envelope.v2"
DOWNSTREAM_CONTRACT_SCHEMA = "hashmarks.downstream-verification-contract.v2"
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class VerificationSelectionEnvelopeState:
    repository_identity: str
    source_identity: str
    codemap_generation: int
    identity_generation: int | None
    stale: bool | None
    membership: Mapping[str, object]
    owner_evidence: Mapping[str, object] | None
    evidence_hashes: Mapping[str, str]
    producer_implementation_identity: str | None = None


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _identity(domain: str, value: object) -> str:
    digest = hashlib.sha256(
        domain.encode("utf-8") + b"\0" + _canonical_bytes(value)
    ).hexdigest()
    return f"sha256:{digest}"


def _implementation_identity(value: str | None) -> str:
    identity = value or native_producer_implementation_identity()
    if not _SHA256.fullmatch(identity):
        raise ValueError(
            "producer implementation identity must be sha256:<64 lowercase hex>"
        )
    return identity


def verification_member(
    path: str,
    *,
    test_symbol: str | None = None,
) -> dict[str, object]:
    normalized_path = normalize_relative_path(path, allow_root=False)
    normalized_symbol = (
        test_symbol.strip()
        if isinstance(test_symbol, str) and test_symbol.strip()
        else None
    )
    identity_payload = {
        "schema": MEMBER_SCHEMA,
        "path": normalized_path,
        "test_symbol": normalized_symbol,
    }
    return {
        **identity_payload,
        "member_id": _identity(MEMBER_SCHEMA, identity_payload),
    }


def _normalize_verification_member(
    raw: Mapping[str, object],
) -> dict[str, object]:
    path = raw.get("path")
    if not isinstance(path, str) or not path.strip():
        raise ValueError("verification member path must be nonblank")
    symbol = raw.get("test_symbol")
    if symbol is not None and not isinstance(symbol, str):
        raise ValueError("verification member test_symbol must be a string or null")
    return verification_member(path, test_symbol=symbol)


def verification_membership(
    members: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    if isinstance(members, (str, bytes)) or not members:
        raise ValueError("verification membership must be nonempty")
    normalized = [_normalize_verification_member(raw) for raw in members]
    member_ids = [str(member["member_id"]) for member in normalized]
    if len(member_ids) != len(set(member_ids)):
        raise ValueError("duplicate verification member")
    ordered = sorted(normalized, key=lambda row: str(row["member_id"]))
    payload: dict[str, object] = {
        "schema": MEMBERSHIP_SCHEMA,
        "members": ordered,
    }
    return {
        **payload,
        "membership_identity": _identity(MEMBERSHIP_SCHEMA, payload),
        "member_count": len(ordered),
    }


def verification_membership_from_selection(
    selected: Mapping[str, object] | None,
) -> dict[str, object] | None:
    if selected is None:
        return None
    path = selected.get("path")
    if not isinstance(path, str) or not path.strip():
        return None
    symbol = selected.get("verification_test_symbol")
    if symbol is None:
        symbol = selected.get("test_symbol")
    return verification_membership(
        [
            {
                "path": path,
                "test_symbol": symbol if isinstance(symbol, str) else None,
            }
        ]
    )


def verification_selection_envelope(
    state: VerificationSelectionEnvelopeState,
) -> dict[str, object]:
    if (
        not isinstance(state.repository_identity, str)
        or not state.repository_identity.strip()
    ):
        raise ValueError("repository_identity must be a nonblank string")
    if not isinstance(state.source_identity, str) or not state.source_identity.strip():
        raise ValueError("source_identity must be a nonblank string")
    codemap_generation = require_generation(
        state.codemap_generation, field="codemap_generation"
    )
    identity_generation = state.identity_generation
    if identity_generation is not None:
        identity_generation = require_generation(
            identity_generation, field="identity_generation"
        )
    if state.stale is not None and type(state.stale) is not bool:
        raise ValueError("stale must be boolean or null")
    membership_validation = validate_verification_membership(state.membership)
    if not membership_validation["valid"]:
        raise ValueError(
            "membership is invalid: "
            + ", ".join(str(reason) for reason in membership_validation["reasons"])
        )
    membership_identity = state.membership.get("membership_identity")
    if not isinstance(membership_identity, str) or not _SHA256.fullmatch(
        membership_identity
    ):
        raise ValueError(
            "membership must carry a sha256:<64 lowercase hex> membership_identity"
        )
    owner_evidence = dict(state.owner_evidence or {})
    try:
        _canonical_bytes(owner_evidence)
    except (TypeError, ValueError) as exc:
        raise ValueError("owner_evidence must be strict JSON-portable") from exc
    evidence_hashes: dict[str, str] = {}
    for key, value in sorted(state.evidence_hashes.items()):
        if not isinstance(key, str) or not key.strip():
            raise ValueError("evidence hash keys must be nonblank strings")
        if not isinstance(value, str) or not _SHA256.fullmatch(value):
            raise ValueError("evidence hashes must be sha256:<64 lowercase hex>")
        evidence_hashes[key] = value
    implementation_identity = _implementation_identity(
        state.producer_implementation_identity
    )
    payload: dict[str, object] = {
        "schema": SELECTION_ENVELOPE_SCHEMA,
        "producer": {
            "name": "hashmarks",
            "version": __version__,
            "implementation_identity": implementation_identity,
        },
        "repository": {
            "repository_identity": state.repository_identity,
            "source_identity": state.source_identity,
            "codemap_generation": codemap_generation,
            "identity_generation": identity_generation,
            # Unknown freshness must never become a positive freshness claim.
            "stale": state.stale is not False,
        },
        "owner_evidence": owner_evidence,
        "selection": dict(state.membership),
        "evidence_hashes": evidence_hashes,
    }
    return {
        **payload,
        "envelope_identity": _identity(SELECTION_ENVELOPE_SCHEMA, payload),
    }


def _unexpected_fields(
    value: Mapping[str, object], allowed: frozenset[str], prefix: str
) -> list[str]:
    return [f"unexpected-{prefix}-field:{key}" for key in sorted(set(value) - allowed)]


def validate_verification_membership(
    membership: Mapping[str, object],
) -> dict[str, object]:
    membership, root_reasons = require_mapping_for_validation(
        membership, reason="invalid-membership"
    )
    reasons: list[str] = [*root_reasons]
    reasons.extend(
        _unexpected_fields(
            membership,
            frozenset({"schema", "members", "membership_identity", "member_count"}),
            "membership",
        )
    )
    if membership.get("schema") != MEMBERSHIP_SCHEMA:
        reasons.append("unsupported-membership-schema")
    members = membership.get("members")
    if not isinstance(members, list) or not members:
        return {
            "valid": False,
            "reasons": list(dict.fromkeys([*reasons, "invalid-members"])),
        }
    for raw in members:
        if not isinstance(raw, Mapping):
            reasons.append("invalid-member-shape")
            continue
        reasons.extend(
            _unexpected_fields(
                raw, frozenset({"schema", "path", "test_symbol", "member_id"}), "member"
            )
        )
        if raw.get("schema") != MEMBER_SCHEMA:
            reasons.append("unsupported-member-schema")
    try:
        rebuilt = verification_membership(members)
    except (TypeError, ValueError) as exc:
        return {"valid": False, "reasons": [f"invalid-members:{exc}"]}
    if members != rebuilt["members"]:
        reasons.append("member-payload-identity-mismatch")
    if membership.get("membership_identity") != rebuilt["membership_identity"]:
        reasons.append("membership-identity-mismatch")
    member_count = membership.get("member_count")
    if type(member_count) is not int or member_count != rebuilt["member_count"]:
        reasons.append("member-count-mismatch")
    return {
        "valid": not reasons,
        "reasons": reasons,
        "membership_identity": rebuilt["membership_identity"],
    }


def _repository_validation_reasons(
    envelope: Mapping[str, object],
) -> list[str]:
    repository = envelope.get("repository")
    if not isinstance(repository, Mapping):
        return ["missing-repository"]
    reasons: list[str] = _unexpected_fields(
        repository,
        frozenset(
            {
                "repository_identity",
                "source_identity",
                "codemap_generation",
                "identity_generation",
                "stale",
            }
        ),
        "repository",
    )
    repository_identity = repository.get("repository_identity")
    if not isinstance(repository_identity, str) or not repository_identity.strip():
        reasons.append("missing-repository-identity")
    source_identity = repository.get("source_identity")
    if not isinstance(source_identity, str) or not source_identity.strip():
        reasons.append("missing-source-identity")
    if not is_valid_generation(repository.get("codemap_generation")):
        reasons.append("invalid-codemap-generation")
    identity_generation = repository.get("identity_generation")
    if identity_generation is not None and not is_valid_generation(identity_generation):
        reasons.append("invalid-identity-generation")
    if not isinstance(repository.get("stale"), bool):
        reasons.append("invalid-stale-state")
    return reasons


def _producer_validation_reasons(
    envelope: Mapping[str, object],
) -> list[str]:
    producer = envelope.get("producer")
    if not isinstance(producer, Mapping) or producer.get("name") != "hashmarks":
        return ["invalid-producer"]
    reasons = _unexpected_fields(
        producer, frozenset({"name", "version", "implementation_identity"}), "producer"
    )
    if (
        not isinstance(producer.get("version"), str)
        or not str(producer.get("version")).strip()
    ):
        reasons.append("missing-or-invalid-producer-version")
    identity = producer.get("implementation_identity")
    if not isinstance(identity, str) or not _SHA256.fullmatch(identity):
        reasons.append("missing-or-invalid-producer-implementation-identity")
    return reasons


def validate_verification_selection_envelope(
    envelope: Mapping[str, object],
) -> dict[str, object]:
    envelope, root_reasons = require_mapping_for_validation(
        envelope, reason="invalid-envelope"
    )
    envelope_reasons = [
        *root_reasons,
        *_unexpected_fields(
            envelope,
            frozenset(
                {
                    "schema",
                    "producer",
                    "repository",
                    "owner_evidence",
                    "selection",
                    "evidence_hashes",
                    "envelope_identity",
                }
            ),
            "envelope",
        ),
    ]
    if envelope.get("schema") != SELECTION_ENVELOPE_SCHEMA:
        envelope_reasons.append("unsupported-envelope-schema")
    selection = envelope.get("selection")
    if not isinstance(selection, Mapping):
        return {
            "valid": False,
            "reasons": list(dict.fromkeys([*envelope_reasons, "missing-selection"])),
        }
    membership_validation = validate_verification_membership(selection)
    reasons = [
        *envelope_reasons,
        *(str(reason) for reason in membership_validation.get("reasons", [])),
    ]
    owner_evidence = envelope.get("owner_evidence")
    if not isinstance(owner_evidence, Mapping):
        reasons.append("invalid-owner-evidence")
    else:
        try:
            _canonical_bytes(dict(owner_evidence))
        except (TypeError, ValueError):
            reasons.append("invalid-owner-evidence")

    evidence_hashes = envelope.get("evidence_hashes")
    if not isinstance(evidence_hashes, Mapping):
        reasons.append("invalid-evidence-hashes")
    else:
        for key, value in evidence_hashes.items():
            if not isinstance(key, str) or not key.strip():
                reasons.append("invalid-evidence-hash-key")
            if not isinstance(value, str) or not _SHA256.fullmatch(value):
                reasons.append("invalid-evidence-hash")

    payload = {
        key: value for key, value in envelope.items() if key != "envelope_identity"
    }
    expected: str | None
    try:
        expected = _identity(SELECTION_ENVELOPE_SCHEMA, payload)
    except (TypeError, ValueError):
        expected = None
        reasons.append("nonportable-envelope-payload")
    if expected is None or envelope.get("envelope_identity") != expected:
        reasons.append("envelope-identity-mismatch")
    reasons.extend(_repository_validation_reasons(envelope))
    reasons.extend(_producer_validation_reasons(envelope))
    return {
        "valid": not reasons,
        "reasons": list(dict.fromkeys(reasons)),
        "envelope_identity": expected,
        "membership_identity": membership_validation.get("membership_identity"),
    }


def downstream_consumption_contract(
    envelope: Mapping[str, object],
) -> dict[str, object]:
    validation = validate_verification_selection_envelope(envelope)
    if not validation["valid"]:
        raise ValueError(
            "verification selection envelope is invalid: "
            + ", ".join(str(reason) for reason in validation["reasons"])
        )
    producer = envelope["producer"]
    repository = envelope["repository"]
    selection = envelope["selection"]
    assert isinstance(producer, Mapping)
    assert isinstance(repository, Mapping)
    assert isinstance(selection, Mapping)
    payload: dict[str, object] = {
        "schema": DOWNSTREAM_CONTRACT_SCHEMA,
        "repository_identity": str(repository["repository_identity"]),
        "source_identity": str(repository["source_identity"]),
        "hashmarks_identity": f"hashmarks:{producer['version']}",
        "producer_implementation_identity": str(producer["implementation_identity"]),
        "selected_membership_identity": str(selection["membership_identity"]),
        "envelope_identity": str(envelope["envelope_identity"]),
        "provenance_hash": str(envelope["envelope_identity"]),
        "authority": "repository-intelligence-only",
        "execution_layout": "external",
    }
    payload["contract_identity"] = _identity(DOWNSTREAM_CONTRACT_SCHEMA, payload)
    return payload


def validate_downstream_consumption_contract(
    envelope: Mapping[str, object],
    contract: Mapping[str, object],
) -> dict[str, object]:
    envelope, envelope_root_reasons = require_mapping_for_validation(
        envelope, reason="invalid-envelope"
    )
    contract, contract_root_reasons = require_mapping_for_validation(
        contract, reason="invalid-contract"
    )
    envelope_validation = validate_verification_selection_envelope(envelope)
    if not envelope_validation["valid"]:
        return {
            "valid": False,
            "reasons": list(
                dict.fromkeys(
                    [
                        *envelope_root_reasons,
                        *contract_root_reasons,
                        "invalid-envelope",
                        *envelope_validation["reasons"],
                    ]
                )
            ),
        }
    expected = downstream_consumption_contract(envelope)
    reasons: list[str] = [*envelope_root_reasons, *contract_root_reasons]
    if (
        contract.get("producer_implementation_identity")
        != expected["producer_implementation_identity"]
    ):
        reasons.append("producer-implementation-identity-mismatch")
    if contract.get("envelope_identity") != expected["envelope_identity"]:
        reasons.append("envelope-contract-linkage-mismatch")
    if contract.get("contract_identity") != expected["contract_identity"]:
        reasons.append("contract-identity-mismatch")
    if dict(contract) != expected:
        reasons.append("contract-envelope-mismatch")
    return {"valid": not reasons, "reasons": list(dict.fromkeys(reasons))}
