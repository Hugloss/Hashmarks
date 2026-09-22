from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

RECEIPT_SCHEMA = "hashmarks.repository-quality-execution-receipt.v1"
_REQUIRED_IDENTITIES = (
    "repository_identity",
    "source_identity",
    "task_identity",
    "policy_identity",
    "generation_identity",
    "authority_proof_identity",
)


def _identity(payload: object) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def execution_receipt(
    *,
    case_id: str,
    corpus_identity: str,
    identities: Mapping[str, str],
    surfaces: Sequence[Mapping[str, Any]],
    mutations: Sequence[Mapping[str, Any]],
    external_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not case_id or not corpus_identity:
        raise ValueError("execution receipt requires case and corpus identity")
    missing = [name for name in _REQUIRED_IDENTITIES if not identities.get(name)]
    if missing:
        raise ValueError(f"execution receipt missing identities: {missing}")
    surface_rows = [dict(row) for row in surfaces]
    if not surface_rows:
        raise ValueError("execution receipt requires surface observations")
    mutation_rows = [dict(row) for row in mutations]
    if any(row.get("violation") is True for row in mutation_rows):
        raise ValueError("execution receipt cannot seal metamorphic violations")
    payload = {
        "schema": RECEIPT_SCHEMA,
        "case_id": case_id,
        "corpus_identity": corpus_identity,
        "identities": dict(identities),
        "surfaces": surface_rows,
        "mutations": mutation_rows,
        "external_evidence": dict(external_evidence or {}),
    }
    return {**payload, "receipt_identity": _identity(payload)}


def receipt_is_fresh(
    receipt: Mapping[str, Any],
    *,
    repository_identity: str,
    generation_identity: str,
) -> bool:
    identities = receipt.get("identities")
    if not isinstance(identities, Mapping):
        return False
    return (
        identities.get("repository_identity") == repository_identity
        and identities.get("generation_identity") == generation_identity
    )


def promotion_evidence_identity(receipt: Mapping[str, Any]) -> str:
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise ValueError("unsupported execution receipt schema")
    identity = str(receipt.get("receipt_identity") or "")
    if not identity:
        raise ValueError("execution receipt has no identity")
    return identity


def external_evidence_receipt(
    *,
    before_authority_proof_identity: str,
    after_authority_proof_identity: str,
    correlation_identity: str,
    conflicts: int,
) -> dict[str, Any]:
    if not before_authority_proof_identity or not after_authority_proof_identity:
        raise ValueError(
            "external evidence receipt requires before and after authority proof"
        )
    if not correlation_identity:
        raise ValueError("external evidence receipt requires correlation identity")
    if conflicts < 0:
        raise ValueError("external evidence conflict count must be non-negative")
    unchanged = before_authority_proof_identity == after_authority_proof_identity
    return {
        "correlation_identity": correlation_identity,
        "before_authority_proof_identity": before_authority_proof_identity,
        "after_authority_proof_identity": after_authority_proof_identity,
        "authority_unchanged": unchanged,
        "conflicts": conflicts,
        "repository_authority_promoted": not unchanged,
    }


def _validated_receipt_payload(receipt: Mapping[str, Any]) -> None:
    identity = str(receipt.get("receipt_identity") or "")
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise ValueError("unsupported execution receipt schema")
    if not identity:
        raise ValueError("execution receipt has no identity")
    payload = {
        key: value for key, value in receipt.items() if key != "receipt_identity"
    }
    if _identity(payload) != identity:
        raise ValueError("execution receipt identity mismatch")


def _validated_receipt_identities(receipt: Mapping[str, Any]) -> None:
    identities = receipt.get("identities")
    if not isinstance(identities, Mapping):
        raise ValueError("execution receipt identities are missing")
    missing = [name for name in _REQUIRED_IDENTITIES if not identities.get(name)]
    if missing:
        raise ValueError(f"execution receipt missing identities: {missing}")


def _validated_receipt_evidence(receipt: Mapping[str, Any]) -> None:
    surfaces = receipt.get("surfaces")
    if not isinstance(surfaces, Sequence) or isinstance(surfaces, (str, bytes)):
        raise ValueError("execution receipt surfaces are invalid")
    if not surfaces:
        raise ValueError("execution receipt requires surface observations")
    mutations = receipt.get("mutations")
    if not isinstance(mutations, Sequence) or isinstance(mutations, (str, bytes)):
        raise ValueError("execution receipt mutations are invalid")
    if any(
        isinstance(row, Mapping) and row.get("violation") is True for row in mutations
    ):
        raise ValueError("execution receipt contains metamorphic violations")


def validate_execution_receipt(receipt: Mapping[str, Any]) -> None:
    _validated_receipt_payload(receipt)
    _validated_receipt_identities(receipt)
    _validated_receipt_evidence(receipt)


def execution_receipt_health(
    receipts: Sequence[Mapping[str, Any]],
    *,
    repository_identity: str,
    generation_identity: str,
) -> dict[str, Any]:
    valid = 0
    fresh = 0
    invalid = 0
    stale = 0
    for receipt in receipts:
        try:
            validate_execution_receipt(receipt)
        except ValueError:
            invalid += 1
            continue
        valid += 1
        if receipt_is_fresh(
            receipt,
            repository_identity=repository_identity,
            generation_identity=generation_identity,
        ):
            fresh += 1
        else:
            stale += 1
    return {
        "receipts": len(receipts),
        "valid": valid,
        "invalid": invalid,
        "fresh": fresh,
        "stale": stale,
        "ready": bool(receipts) and invalid == 0 and stale == 0,
    }
