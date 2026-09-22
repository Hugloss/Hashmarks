from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

TRACE_SCHEMA = "hashmarks.ownership-decision-trace.v1"
AUTHORITY_SCHEMA = "hashmarks.ownership-authority.v1"


@dataclass(frozen=True)
class OwnershipDecisionState:
    edit: Mapping[str, object] | None
    competing: Sequence[Mapping[str, object]]
    structural_owner: Mapping[str, object] | None
    ambiguous: bool
    ambiguity_reason: str
    owner_eligible: bool = True
    authority_basis: str | None = None


def _candidate_identity(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "path": str(row.get("path") or ""),
        "name": row.get("name"),
        "qualname": row.get("qualname"),
        "canonical_rank": int(row.get("canonical_rank") or 0),
        "roles": list(row.get("roles") or []),
    }


def _decision_status(state: OwnershipDecisionState) -> str:
    if (
        state.edit is None
        or not state.owner_eligible
    ):
        return "unresolved"
    structural = state.structural_owner or {}
    selected = str(structural.get("selected") or "")
    edit_path = str(state.edit.get("path") or "")
    if state.ambiguous and selected != edit_path:
        return "ambiguous"
    return "resolved"


def _confidence(state: OwnershipDecisionState, status: str) -> str:
    if status == "unresolved":
        return "none"
    if status == "ambiguous":
        return "low"
    return "high" if state.structural_owner is not None else "medium"


def _rejection_reason(
    row: Mapping[str, object],
    *,
    ambiguous: bool,
) -> str:
    roles = set(row.get("roles") or [])
    if ambiguous:
        return "not-authoritative-while-ambiguity-remains"
    if "verify" in roles:
        return "verification-evidence-not-edit-authority"
    if "contract" in roles:
        return "lower-ranked-contract-or-config-alternative"
    return "lower-ranked-alternative"


def ownership_decision_trace(
    state: OwnershipDecisionState,
) -> dict[str, object]:
    status = _decision_status(state)
    selected = _candidate_identity(state.edit) if state.edit is not None else None
    candidates: list[dict[str, object]] = []
    if selected is not None:
        candidates.append(
            {
                **selected,
                "disposition": "selected" if status == "resolved" else "provisional",
                "rejection_reason": None,
            }
        )
    candidates.extend(
        {
            **_candidate_identity(row),
            "disposition": "rejected" if status == "resolved" else "competing",
            "rejection_reason": _rejection_reason(
                row,
                ambiguous=status != "resolved",
            ),
        }
        for row in state.competing
    )
    structural = dict(state.structural_owner or {})
    return {
        "schema": TRACE_SCHEMA,
        "status": status,
        "confidence": _confidence(state, status),
        "selected": selected,
        "candidates": candidates,
        "structural_evidence": {
            "selected": structural.get("selected"),
            "via": structural.get("via"),
            "owner_path": structural.get("owner_path", []),
        },
        "ambiguity": {
            "ambiguous": state.ambiguous,
            "reason": state.ambiguity_reason,
        },
        "authority_basis": state.authority_basis,
        "evidence_state": {
            "retrieved": state.edit is not None,
            "inferred": bool(state.edit and state.edit.get("structural_projection")),
            "structural": state.structural_owner is not None,
            "admissible": status == "resolved",
            "proven": status == "resolved",
        },
    }


def _trace_selected_path(trace: Mapping[str, object]) -> str:
    selected = trace.get("selected")
    if not isinstance(selected, Mapping):
        return ""
    return str(selected.get("path") or "")


def _trace_unresolved_reason(trace: Mapping[str, object]) -> str:
    ambiguity = trace.get("ambiguity")
    if not isinstance(ambiguity, Mapping):
        return "ownership-unresolved"
    return str(ambiguity.get("reason") or "ownership-unresolved")

def _stable_identity(schema: str, payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        {"schema": schema, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def authority_proof_identity(trace: Mapping[str, object]) -> str:
    """Identify proof-bearing semantics without presentation/retrieval controls."""
    return _stable_identity(
        "hashmarks.ownership-authority-proof.v1",
        {
            "status": trace.get("status"),
            "selected": trace.get("selected"),
            "structural_evidence": trace.get("structural_evidence"),
            "ambiguity": trace.get("ambiguity"),
            "authority_basis": trace.get("authority_basis"),
            "evidence_state": trace.get("evidence_state"),
        },
    )


def presentation_identity(
    proof_identity: str,
    *,
    limit: int,
    per_role: int,
    compact: bool,
) -> str:
    """Identify bounded rendering separately from repository authority proof."""
    return _stable_identity(
        "hashmarks.ownership-presentation.v1",
        {
            "authority_proof_identity": proof_identity,
            "limit": limit,
            "per_role": per_role,
            "compact": compact,
        },
    )


def bounded_presentation_contract(
    proof_identity: str,
    *,
    total_candidates: int,
    returned_candidates: int,
    limit: int,
    per_role: int,
    compact: bool,
) -> dict[str, object]:
    """Describe bounded output without changing the underlying authority proof."""
    if min(total_candidates, returned_candidates, limit, per_role) < 0:
        raise ValueError("presentation bounds and candidate counts must be non-negative")
    if returned_candidates > total_candidates:
        raise ValueError("returned candidates cannot exceed total candidates")
    complete = returned_candidates >= total_candidates
    return {
        "schema": "hashmarks.ownership-presentation.v1",
        "authority_proof_identity": proof_identity,
        "presentation_identity": presentation_identity(
            proof_identity,
            limit=limit,
            per_role=per_role,
            compact=compact,
        ),
        "total_candidates": total_candidates,
        "returned_candidates": returned_candidates,
        "complete": complete,
        "truncated": not complete,
    }

def ownership_authority_contract(
    trace: Mapping[str, object],
) -> dict[str, object]:
    status = str(trace.get("status") or "unresolved")
    selected_path = _trace_selected_path(trace)
    safe = status == "resolved" and bool(selected_path)
    reason = "unique-owner-established" if safe else _trace_unresolved_reason(trace)
    proof_identity = authority_proof_identity(trace)
    return {
        "schema": AUTHORITY_SCHEMA,
        "status": status,
        "owner_resolved": safe,
        "resolved_owner": selected_path if safe else None,
        "candidate_owner": selected_path or None,
        "reason": reason,
        "authority": "repository-ownership-only",
        "consumer_action": "external",
        "proof_complete": safe,
        "authority_proof_identity": proof_identity,
        "evidence_state": trace.get("evidence_state"),
    }


def project_owner_candidate(
    source: Mapping[str, object],
) -> tuple[Mapping[str, object] | None, Mapping[str, object] | None, bool]:
    """Separate repository candidate evidence from admitted edit authority."""
    value = source.get("edit")
    candidate = value if isinstance(value, Mapping) else None
    authority = source.get("ownership_authority")
    resolved = isinstance(authority, Mapping) and bool(authority.get("owner_resolved"))
    return (candidate if resolved else None, candidate, resolved)


def ownership_candidate_path(source: Mapping[str, object]) -> str | None:
    """Return the candidate path without implying admitted edit authority."""
    value = source.get("edit")
    candidate = value if isinstance(value, Mapping) else {}
    return str(candidate.get("path") or "") or None
