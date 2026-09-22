from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from hashmarks.ownership_decision import authority_proof_identity

SURFACE_NAMES = {
    "action-map",
    "task-action-brief",
    "task-decision-packet",
    "task-decision-brief",
    "task-evidence",
    "mcp-task-evidence",
}


def authority_contract_from_surface(
    surface: str,
    payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    if surface not in SURFACE_NAMES:
        raise ValueError(f"unsupported authority surface: {surface}")
    direct = payload.get("ownership_authority")
    if isinstance(direct, Mapping):
        return direct
    retrieval = payload.get("retrieval")
    if isinstance(retrieval, Mapping):
        nested = retrieval.get("ownership_authority")
        if isinstance(nested, Mapping):
            return nested
    ownership = payload.get("ownership")
    if isinstance(ownership, Mapping):
        nested = ownership.get("contract")
        if isinstance(nested, Mapping):
            return nested
    raise ValueError(f"{surface} does not expose an ownership authority contract")


def surface_authority_observation(
    surface: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    contract = authority_contract_from_surface(surface, payload)
    proof = str(contract.get("authority_proof_identity") or "")
    if not proof:
        raise ValueError(f"{surface} authority contract has no proof identity")
    return {
        "surface": surface,
        "authority_proof_identity": proof,
        "owner_resolved": bool(contract.get("owner_resolved")),
        "resolved_owner": contract.get("resolved_owner"),
        "candidate_owner": contract.get("candidate_owner"),
        "proof_complete": bool(contract.get("proof_complete")),
    }


def canonical_authority_observation(
    trace: Mapping[str, Any],
    *,
    repository_identity: str,
    task_identity: str,
    policy_identity: str,
    generation_identity: str,
) -> dict[str, Any]:
    for label, value in (
        ("repository_identity", repository_identity),
        ("task_identity", task_identity),
        ("policy_identity", policy_identity),
        ("generation_identity", generation_identity),
    ):
        if not value:
            raise ValueError(f"{label} must be non-empty")
    semantic_proof = authority_proof_identity(trace)
    scope = {
        "repository_identity": repository_identity,
        "task_identity": task_identity,
        "policy_identity": policy_identity,
        "generation_identity": generation_identity,
        "semantic_authority_proof_identity": semantic_proof,
    }
    return {
        **scope,
        "authority_proof_identity": _scoped_identity(scope),
    }


def _scoped_identity(scope: Mapping[str, Any]) -> str:
    import hashlib
    import json

    encoded = json.dumps(
        scope, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def convergence_observations(
    payloads: Sequence[tuple[str, Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    return [surface_authority_observation(name, payload) for name, payload in payloads]
