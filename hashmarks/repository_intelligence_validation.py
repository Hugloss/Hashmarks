from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from .codemap.decision_contract import DecisionPacketContract
from .codemap.diagnostic_source_revision import (
    DIAGNOSTIC_SOURCE_REVISION_EVIDENCE_SCHEMA,
    normalize_source_revision_claims,
    validated_diagnostic_source_revision_evidence,
)
from .codemap.repository_delta import EXTERNAL_DIAGNOSTIC_OBSERVATION_SCHEMA
from .operation_contract import operation_schema
from .producer_identity import native_producer_implementation_identity

REPOSITORY_INTELLIGENCE_CONFORMANCE_SCHEMA = (
    "hashmarks.repository-intelligence-consumer-conformance.v1"
)
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_CHANGE_IMPACT_SCHEMA = operation_schema("change_impact")
_DECISION_PACKET_SCHEMA = operation_schema("task_decision_packet")
_DECISION_BRIEF_SCHEMA = operation_schema("task_decision_brief")
_OWNERSHIP_RELATION_SCHEMA = operation_schema("ownership_relation_graph")
_TASK_ACTION_MAP_SCHEMA = operation_schema("task_action_map")

_CURRENT_EVIDENCE_KINDS: dict[str, str] = {
    _DECISION_PACKET_SCHEMA: "decision",
    _DECISION_BRIEF_SCHEMA: "decision",
    "hashmarks.task-context-plan.v1": "context",
    "hashmarks.agent-work-context.v1": "context",
    _CHANGE_IMPACT_SCHEMA: "impact",
    "hashmarks.verification-plan.v1": "verification",
    _OWNERSHIP_RELATION_SCHEMA: "ownership",
    _TASK_ACTION_MAP_SCHEMA: "action-map",
    "hashmarks.repository-intelligence-snapshot.v1": "repository-snapshot",
    "hashmarks.repository-intelligence-delta.v1": "repository-delta",
    EXTERNAL_DIAGNOSTIC_OBSERVATION_SCHEMA: "diagnostic-observation",
    DIAGNOSTIC_SOURCE_REVISION_EVIDENCE_SCHEMA: "diagnostic-source-revision",
    operation_schema("evidence_comparison", "diagnostics"): "diagnostic-delta",
    "hashmarks.external-observation-freshness.v1": "observation-freshness",
}


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _is_generation(value: object) -> bool:
    return type(value) is int and value >= 0


def _strings(value: object) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and bool(item) for item in value
    )


def _payload_identity(schema: str, payload: Mapping[str, object]) -> str:
    raw = json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    digest = hashlib.sha256(schema.encode("utf-8") + b"\0" + raw).hexdigest()
    return "sha256:" + digest


def _require_authority(
    payload: Mapping[str, object],
    *,
    authority: str,
    reasons: list[str],
) -> None:
    if payload.get("authority") != authority:
        reasons.append("authority-mismatch")
    if payload.get("execution_effect") != "none":
        reasons.append("execution-effect-not-none")


def _decision_identity_projection(
    payload: Mapping[str, object],
    identity: Mapping[str, object],
    reasons: list[str],
) -> dict[str, object]:
    if identity.get("schema") != "hashmarks.worker-packet-identity.v1":
        reasons.append("unsupported-decision-identity-schema")
    generation = identity.get("codemap_generation")
    if not _is_generation(generation):
        reasons.append("invalid-codemap-generation")
    if payload.get("canonical_generation") != generation:
        reasons.append("canonical-generation-mismatch")
    repository_identity = identity.get("repository_identity")
    if not isinstance(repository_identity, str) or not repository_identity:
        reasons.append("missing-repository-identity")
    if not _is_sha256(identity.get("decision_generation")):
        reasons.append("invalid-decision-generation")
    return {
        "repository_identity": repository_identity,
        "codemap_generation": generation,
    }


def _decision_packet(
    payload: Mapping[str, object],
    reasons: list[str],
) -> dict[str, object]:
    try:
        contract = DecisionPacketContract.parse(payload)
    except (TypeError, ValueError) as exc:
        reasons.append(f"invalid-decision-packet:{exc}")
        return {}
    identity = payload.get("identity")
    if not isinstance(identity, Mapping):
        reasons.append("invalid-decision-identity")
        return {}
    normalized = _decision_identity_projection(payload, identity, reasons)
    if payload.get("authority") != "repository-observation-only":
        reasons.append("authority-mismatch")
    return {**normalized, "stale": contract.stale}


def _decision_brief(
    payload: Mapping[str, object],
    reasons: list[str],
) -> dict[str, object]:
    stale = payload.get("stale")
    if type(stale) is not bool:
        reasons.append("invalid-stale-state")
    if not _is_sha256(payload.get("decision_generation")):
        reasons.append("invalid-decision-generation")
    return {"stale": stale}


def _context_plan(
    payload: Mapping[str, object], reasons: list[str]
) -> dict[str, object]:
    if payload.get("ranking_effect") != "none":
        reasons.append("ranking-effect-not-none")
    if not isinstance(payload.get("task"), str) or not str(payload.get("task")).strip():
        reasons.append("invalid-task")
    if (
        not isinstance(payload.get("query"), str)
        or not str(payload.get("query")).strip()
    ):
        reasons.append("invalid-query")
    budget = payload.get("token_budget")
    if type(budget) is not int or budget < 1:
        reasons.append("invalid-token-budget")
    limit = payload.get("limit")
    if type(limit) is not int or limit < 1:
        reasons.append("invalid-limit")
    return {}


def _work_context(
    payload: Mapping[str, object], reasons: list[str]
) -> dict[str, object]:
    if type(payload.get("safe")) is not bool:
        reasons.append("invalid-safe-state")
    for field in ("required_roles", "missing_roles"):
        if not _strings(payload.get(field)):
            reasons.append(f"invalid-{field.replace('_', '-')}")
    return {}


def _change_impact(
    payload: Mapping[str, object], reasons: list[str]
) -> dict[str, object]:
    generation = payload.get("generation")
    if not _is_generation(generation):
        reasons.append("invalid-generation")
    if payload.get("authority") != "advisory":
        reasons.append("authority-mismatch")
    if payload.get("owner") != "external":
        reasons.append("owner-not-external")
    if payload.get("completeness") != "not-claimed":
        reasons.append("completeness-overclaim")
    return {"codemap_generation": generation}


def _verification_plan(
    payload: Mapping[str, object],
    reasons: list[str],
) -> dict[str, object]:
    path = payload.get("path")
    if not isinstance(path, str) or not path.strip():
        reasons.append("invalid-verification-path")
    available = payload.get("available")
    if type(available) is not bool:
        reasons.append("invalid-availability")
        return {}
    if available:
        argv = payload.get("argv")
        if not _strings(argv) or not argv:
            reasons.append("invalid-verification-argv")
        working_directory = payload.get("working_directory")
        if not isinstance(working_directory, str) or not working_directory:
            reasons.append("invalid-working-directory")
    return {"available": available}


def _ownership_graph(
    payload: Mapping[str, object],
    reasons: list[str],
) -> dict[str, object]:
    if payload.get("relation_authority") != (
        "imports-and-calls-are-evidence-not-ownership-truth"
    ):
        reasons.append("ownership-relation-authority-mismatch")
    complete = payload.get("completeness")
    if complete not in {"complete", "incomplete"}:
        reasons.append("invalid-ownership-completeness")
    negative = payload.get("negative_evidence_admissible")
    unique = payload.get("uniqueness_admissible")
    if type(negative) is not bool or type(unique) is not bool:
        reasons.append("invalid-ownership-admissibility")
    elif complete == "complete" and not (negative and unique):
        reasons.append("complete-ownership-withheld-admissibility")
    elif complete == "incomplete" and (negative or unique):
        reasons.append("incomplete-ownership-overclaims-admissibility")
    return {}


def _action_map(payload: Mapping[str, object], reasons: list[str]) -> dict[str, object]:
    authority = payload.get("ownership_authority")
    if not isinstance(authority, Mapping):
        reasons.append("missing-ownership-authority")
        return {}
    if authority.get("schema") != "hashmarks.ownership-authority.v1":
        reasons.append("unsupported-ownership-authority-schema")
    if authority.get("authority") != "repository-ownership-only":
        reasons.append("ownership-authority-mismatch")
    if authority.get("consumer_action") != "external":
        reasons.append("consumer-action-not-external")
    if not _is_sha256(authority.get("authority_proof_identity")):
        reasons.append("invalid-ownership-authority-proof")
    return {}


def _validate_observer(
    observer: object,
    reasons: list[str],
) -> None:
    if not isinstance(observer, Mapping):
        reasons.append("missing-observer")
        return
    if observer.get("schema") != "hashmarks.repository-observer.v1":
        reasons.append("unsupported-observer-schema")
    if not _is_sha256(observer.get("identity")):
        reasons.append("invalid-observer-identity")


def _repository_binding(
    repository: object,
    reasons: list[str],
) -> dict[str, object]:
    if not isinstance(repository, Mapping):
        reasons.append("missing-repository")
        return {
            "repository_identity": None,
            "codemap_generation": None,
            "stale": None,
        }
    repository_identity = repository.get("repository_identity")
    generation = repository.get("codemap_generation")
    stale = repository.get("stale")
    if not isinstance(repository_identity, str) or not repository_identity:
        reasons.append("missing-repository-identity")
    if not _is_generation(generation):
        reasons.append("invalid-codemap-generation")
    if type(stale) is not bool:
        reasons.append("invalid-stale-state")
    return {
        "repository_identity": repository_identity,
        "codemap_generation": generation,
        "stale": stale,
    }


def _repository_snapshot(
    payload: Mapping[str, object],
    reasons: list[str],
) -> dict[str, object]:
    _require_authority(
        payload, authority="repository-intelligence-only", reasons=reasons
    )
    if not _is_sha256(payload.get("snapshot_identity")):
        reasons.append("invalid-snapshot-identity")
    _validate_observer(payload.get("observer"), reasons)
    return _repository_binding(payload.get("repository"), reasons)


def _repository_delta(
    payload: Mapping[str, object],
    reasons: list[str],
) -> dict[str, object]:
    _require_authority(
        payload, authority="repository-intelligence-only", reasons=reasons
    )
    if not _is_sha256(payload.get("delta_identity")):
        reasons.append("invalid-delta-identity")
    repository_identity = payload.get("repository_identity")
    if not isinstance(repository_identity, str) or not repository_identity:
        reasons.append("missing-repository-identity")
    to_generation = None
    for side in ("from", "to"):
        binding = payload.get(side)
        if not isinstance(binding, Mapping):
            reasons.append(f"missing-{side}-binding")
            continue
        if not _is_sha256(binding.get("snapshot_identity")):
            reasons.append(f"invalid-{side}-snapshot-identity")
        generation = binding.get("codemap_generation")
        if not _is_generation(generation):
            reasons.append(f"invalid-{side}-generation")
        if side == "to":
            to_generation = generation
    return {
        "repository_identity": repository_identity,
        "codemap_generation": to_generation,
    }


def _diagnostic_binding(
    payload: Mapping[str, object], reasons: list[str], *, generation_field: str
) -> dict[str, object]:
    repository_identity = payload.get("repository_identity")
    generation = payload.get(generation_field)
    if not isinstance(repository_identity, str) or not repository_identity:
        reasons.append("missing-repository-identity")
    if not _is_generation(generation):
        reasons.append("invalid-codemap-generation")
    return {
        "repository_identity": repository_identity,
        "codemap_generation": generation,
    }


def _diagnostic_observation(
    payload: Mapping[str, object],
    reasons: list[str],
) -> dict[str, object]:
    _require_authority(payload, authority="observation-only", reasons=reasons)
    binding = _diagnostic_binding(
        payload, reasons, generation_field="codemap_generation"
    )
    diagnostics = payload.get("diagnostics")
    if not isinstance(diagnostics, list):
        reasons.append("invalid-diagnostics")
    elif payload.get("diagnostic_count") != len(diagnostics):
        reasons.append("diagnostic-count-mismatch")
    try:
        claims = normalize_source_revision_claims(
            payload.get("source_revisions"), payload.get("scope_paths", ())
        )
    except (TypeError, ValueError):
        reasons.append("invalid-source-revisions")
        claims = None
    return {
        **binding,
        **({"source_revisions": claims} if "source_revisions" in payload else {}),
    }


def _diagnostic_revision_evidence(
    payload: Mapping[str, object], reasons: list[str]
) -> dict[str, object]:
    _require_authority(
        payload,
        authority="descriptive-source-revision-correspondence-only",
        reasons=reasons,
    )
    binding = _diagnostic_binding(
        payload, reasons, generation_field="diagnostic_generation"
    )
    try:
        projection = validated_diagnostic_source_revision_evidence(payload)
    except (TypeError, ValueError):
        reasons.append("invalid-diagnostic-source-revision-evidence")
        projection = {}
    return {**binding, **projection}


def _diagnostic_delta(
    payload: Mapping[str, object],
    reasons: list[str],
) -> dict[str, object]:
    _require_authority(payload, authority="observation-only", reasons=reasons)
    return {}


def _observation_freshness(
    payload: Mapping[str, object],
    reasons: list[str],
) -> dict[str, object]:
    _require_authority(payload, authority="observation-freshness-only", reasons=reasons)
    state = payload.get("state")
    if state not in {"current", "stale"}:
        reasons.append("invalid-freshness-state")
    return {"freshness_state": state, "stale": state != "current"}


_VALIDATORS = {
    _DECISION_PACKET_SCHEMA: _decision_packet,
    _DECISION_BRIEF_SCHEMA: _decision_brief,
    "hashmarks.task-context-plan.v1": _context_plan,
    "hashmarks.agent-work-context.v1": _work_context,
    _CHANGE_IMPACT_SCHEMA: _change_impact,
    "hashmarks.verification-plan.v1": _verification_plan,
    _OWNERSHIP_RELATION_SCHEMA: _ownership_graph,
    _TASK_ACTION_MAP_SCHEMA: _action_map,
    "hashmarks.repository-intelligence-snapshot.v1": _repository_snapshot,
    "hashmarks.repository-intelligence-delta.v1": _repository_delta,
    EXTERNAL_DIAGNOSTIC_OBSERVATION_SCHEMA: _diagnostic_observation,
    DIAGNOSTIC_SOURCE_REVISION_EVIDENCE_SCHEMA: _diagnostic_revision_evidence,
    operation_schema("evidence_comparison", "diagnostics"): _diagnostic_delta,
    "hashmarks.external-observation-freshness.v1": _observation_freshness,
}


def validate_repository_intelligence_evidence(
    payload: Mapping[str, object],
    *,
    expected_schema: str | None = None,
    require_fresh: bool = False,
) -> dict[str, object]:
    """Validate current Hashmarks repository-intelligence evidence for consumers.

    Hashmarks owns schema recognition and producer-semantic validation.  The
    returned projection never grants execution, result, retry, scheduling, or
    certification authority; consumers retain those decisions.
    """

    if not isinstance(payload, Mapping):
        return {
            "schema": REPOSITORY_INTELLIGENCE_CONFORMANCE_SCHEMA,
            "valid": False,
            "reasons": ["invalid-evidence-root"],
            "normalized": None,
            "execution_authority": "external",
            "result_authority": "external",
            "certification_authority": "external",
        }

    root = dict(payload)
    schema = root.get("schema")
    reasons: list[str] = []
    if not isinstance(schema, str) or not schema:
        reasons.append("missing-evidence-schema")
        schema = ""
    if expected_schema is not None and schema != expected_schema:
        reasons.append("unexpected-evidence-schema")

    kind = _CURRENT_EVIDENCE_KINDS.get(schema)
    validator = _VALIDATORS.get(schema)
    if kind is None or validator is None:
        reasons.append("unsupported-evidence-schema")
        projection: dict[str, object] = {}
    else:
        projection = validator(root, reasons)

    try:
        payload_identity = _payload_identity(schema, root) if schema else None
    except (TypeError, ValueError):
        reasons.append("nonportable-evidence-payload")
        payload_identity = None

    stale = projection.get("stale")
    if require_fresh and stale is not False:
        reasons.append("fresh-evidence-required")

    valid = not reasons
    normalized = None
    if valid:
        normalized = {
            "evidence_schema": schema,
            "evidence_kind": kind,
            "producer_implementation_identity": (
                native_producer_implementation_identity()
            ),
            "payload_identity": payload_identity,
            "repository_identity": projection.get("repository_identity"),
            "codemap_generation": projection.get("codemap_generation"),
            "stale": stale,
            "freshness_state": projection.get("freshness_state"),
            "available": projection.get("available"),
            **{
                field: projection[field]
                for field in (
                    "source_revisions",
                    "source_revision_rows",
                    "source_revision_coverage",
                )
                if field in projection
            },
        }

    return {
        "schema": REPOSITORY_INTELLIGENCE_CONFORMANCE_SCHEMA,
        "valid": valid,
        "reasons": list(dict.fromkeys(reasons)),
        "normalized": normalized,
        "authority": "repository-intelligence-only",
        "execution_authority": "external",
        "result_authority": "external",
        "certification_authority": "external",
    }
