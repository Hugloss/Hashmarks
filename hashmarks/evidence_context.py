from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING

from .freshness import FRESHNESS_STATES
from .generation_domain import require_generation
from .producer_identity import native_producer_implementation_identity
from .validation_inputs import require_mapping_for_validation

if TYPE_CHECKING:
    from collections.abc import Mapping

EVIDENCE_CONTEXT_SCHEMA = "hashmarks.evidence-context.v1"
_SHA = re.compile(r"^sha256:[0-9a-f]{64}$")


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
    if freshness not in FRESHNESS_STATES:
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



def describe_evidence_binding_reacquisition(
    packet: Mapping[str, object], *, binding_id: str
) -> dict[str, object]:
    """Describe how to reobserve a bound scope, without reusing its freshness.

    This is a transport descriptor, not a retrievable packet cache, a session
    cursor, or proof of repository equivalence. The consumer must explicitly
    request a new repository_evidence observation and compare producer packets.
    """
    from .operation_contract import operation_schema
    from .paths import normalize_relative_path

    if packet.get("schema") != operation_schema("repository_evidence", "observation"):
        raise ValueError("reacquisition requires native repository evidence bindings")
    if packet.get("authority") != "repository-intelligence-only":
        raise ValueError("unqualified evidence binding authority")
    rows = packet.get("bindings")
    if not isinstance(rows, list) or len(rows) > 256:
        raise ValueError("reacquisition requires bounded binding rows")
    matches = [
        row for row in rows
        if isinstance(row, dict) and row.get("binding_id") == binding_id
    ]
    if len(matches) != 1:
        raise ValueError("reacquisition requires one exact binding")
    binding = matches[0]
    scopes = []
    for row in binding.get("evidence", []):
        if not isinstance(row, dict) or row.get("scope") not in ("member", "lines"):
            raise ValueError("invalid evidence scope")
        path = row.get("path")
        if not isinstance(path, str) or normalize_relative_path(path, allow_root=False) != path:
            raise ValueError("invalid reacquisition path")
        scope = {"scope": row["scope"], "path": path}
        if row["scope"] == "lines":
            start, end = row.get("start_line"), row.get("end_line")
            if type(start) is not int or type(end) is not int or start < 1 or end < start:
                raise ValueError("invalid reacquisition span")
            scope.update(start_line=start, end_line=end)
        scopes.append(scope)
    dependencies = binding.get("dependencies", [])
    if not isinstance(dependencies, list):
        raise ValueError("invalid evidence dependencies")
    paths = sorted({row["path"] for row in dependencies})
    relations = binding.get("relationships", {})
    if not isinstance(relations, dict) or relations.get("state") not in ("observed", "not-requested"):
        raise ValueError("invalid relationship observation state")
    limit = relations.get("bounds", {}).get("limit_per_path")
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("invalid relationship observation bound")
    repository = packet.get("repository", {})
    if not isinstance(repository, dict):
        raise ValueError("invalid repository binding")
    return {
        "schema": "hashmarks.evidence-binding-reacquisition.v1",
        "source_packet_identity": packet.get("bindings_identity"),
        "binding_definition_identity": binding.get("binding_definition_identity"),
        "binding_observation_identity": binding.get("binding_observation_identity"),
        "repository": dict(repository),
        "requery": {
            "binding_id": binding_id, "evidence": scopes,
            "dependency_paths": paths,
            "include_relationships": relations["state"] == "observed",
            "relationship_limit_per_path": limit,
        },
        "authority": "consumer-reacquisition-description-only",
        "current_freshness_proven": False,
        "execution_effect": "none",
    }
