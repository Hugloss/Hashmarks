from __future__ import annotations

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


def _candidate_identity(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "path": str(row.get("path") or ""),
        "name": row.get("name"),
        "qualname": row.get("qualname"),
        "canonical_rank": int(row.get("canonical_rank") or 0),
        "roles": list(row.get("roles") or []),
    }


def _decision_status(state: OwnershipDecisionState) -> str:
    if state.edit is None:
        return "unresolved"
    if state.ambiguous:
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


def ownership_authority_contract(
    trace: Mapping[str, object],
) -> dict[str, object]:
    status = str(trace.get("status") or "unresolved")
    selected_path = _trace_selected_path(trace)
    safe = status == "resolved" and bool(selected_path)
    reason = "unique-owner-established" if safe else _trace_unresolved_reason(trace)
    return {
        "schema": AUTHORITY_SCHEMA,
        "status": status,
        "owner_resolved": safe,
        "resolved_owner": selected_path if safe else None,
        "candidate_owner": selected_path or None,
        "reason": reason,
        "authority": "repository-ownership-only",
        "consumer_action": "external",
    }
