from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING

from .generation_domain import require_generation
from .producer_identity import native_producer_implementation_identity
from .validation_inputs import require_mapping_for_validation

if TYPE_CHECKING:
    from collections.abc import Mapping

EVIDENCE_CONTEXT_SCHEMA = "hashmarks.evidence-context.v1"
_SHA = re.compile(r"^sha256:[0-9a-f]{64}$")
_FRESHNESS_STATES = frozenset({"unknown", "current", "stale"})


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return (
        "sha256:"
        + hashlib.sha256(
            EVIDENCE_CONTEXT_SCHEMA.encode("utf-8") + b"\0" + encoded
        ).hexdigest()
    )


def evidence_context_identity(
    evidence_receipt: Mapping[str, object],
    provenance: Mapping[str, object],
    *,
    producer_implementation_identity: str | None = None,
) -> str:
    """Return producer-owned identity for compact repository evidence context."""
    producer = (
        producer_implementation_identity or native_producer_implementation_identity()
    )
    if not _SHA.fullmatch(producer):
        raise ValueError(
            "producer implementation identity must be sha256:<64 lowercase hex>"
        )
    evidence_identity = evidence_receipt.get("evidence_identity")
    repository_identity = evidence_receipt.get("repository_identity")
    if not isinstance(evidence_identity, str) or not evidence_identity:
        raise ValueError("evidence_identity must be a nonblank string")
    if not isinstance(repository_identity, str) or not repository_identity:
        raise ValueError("repository_identity must be a nonblank string")
    generation = require_generation(
        evidence_receipt.get("codemap_generation"), field="codemap_generation"
    )
    revision = provenance.get("revision")
    try:
        json.dumps(
            revision,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("revision must be strict JSON-portable") from exc
    freshness = provenance.get("freshness", "unknown")
    if freshness not in _FRESHNESS_STATES:
        raise ValueError("freshness must be one of unknown, current, stale")
    payload = {
        "schema": EVIDENCE_CONTEXT_SCHEMA,
        "evidence_identity": evidence_identity,
        "repository_identity": repository_identity,
        "codemap_generation": generation,
        "revision": revision,
        "freshness": freshness,
        "producer_implementation_identity": producer,
    }
    return _digest(payload)


def validate_evidence_context(
    evidence_receipt: Mapping[str, object],
    provenance: Mapping[str, object],
    *,
    producer_implementation_identity: str | None = None,
) -> dict[str, object]:
    """Validate an opaque context identity without transferring hash semantics downstream."""
    evidence_receipt, receipt_reasons = require_mapping_for_validation(
        evidence_receipt, reason="invalid-evidence-receipt"
    )
    provenance, provenance_reasons = require_mapping_for_validation(
        provenance, reason="invalid-provenance"
    )
    claimed_raw = provenance.get("context_identity")
    claimed = claimed_raw if isinstance(claimed_raw, str) else ""
    reasons: list[str] = [*receipt_reasons, *provenance_reasons]
    if not _SHA.fullmatch(claimed):
        reasons.append("missing-or-invalid-context-identity")
    try:
        expected = evidence_context_identity(
            evidence_receipt,
            provenance,
            producer_implementation_identity=producer_implementation_identity,
        )
    except (TypeError, ValueError):
        expected = None
        reasons.append("invalid-context-payload")
    if expected is not None and claimed and claimed != expected:
        reasons.append("context-identity-mismatch")
    return {
        "valid": not reasons,
        "reasons": list(dict.fromkeys(reasons)),
        "context_identity": claimed or None,
    }
