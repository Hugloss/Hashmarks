"""Pure initial disclosure of an already observed task packet.

This profile bounds presentation, never the producer's ownership or reference
decision. The full packet identity and an omission ledger permit comparison
with a later full observation; they are not durable replay state.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from hashmarks.operation_contract import operation_schema, validate_operation_response

_LOCATOR_OMISSIONS = (
    "canonical_rank",
    "canonical_score",
    "name",
    "signature",
    "namespace_overlap",
    "namespace_terms",
    "task_anchor_count",
    "task_anchor_terms",
    "runner_available",
)


def _locator(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    omitted = set(_LOCATOR_OMISSIONS)
    if not value.get("qualname") and not value.get("symbol"):
        omitted.remove("name")
    return {key: item for key, item in value.items() if key not in omitted}


def _encode_task_matches(relevance: dict[str, Any]) -> None:
    matches = relevance.get("task_matches")
    if not isinstance(matches, dict) or not isinstance(matches.get("matches"), list):
        return
    columns = ["path", "matched_term_count", "evidence_visibility"]
    rows = matches["matches"]
    if not all(isinstance(row, dict) and set(row) == set(columns) for row in rows):
        return
    matches["matches_encoding"] = {"kind": "columns-rows.v1", "columns": columns}
    matches["matches"] = [[row[key] for key in columns] for row in rows]


def initial_task_evidence(packet: dict[str, Any]) -> dict[str, Any]:
    """Project existing facts, retaining qualifiers and accounting for detail loss."""
    validate_operation_response("task_evidence", packet)
    result = deepcopy(packet)
    result["schema"] = operation_schema("task_evidence", "initial")
    result["source_evidence_identity"] = result.pop("evidence_packet_identity")
    omissions: dict[str, Any] = {
        "locator_fields": list(_LOCATOR_OMISSIONS),
        "locator_scopes": [
            "/ownership/owner",
            "/ownership/candidate",
            "/ownership/ambiguity/alternatives/*",
            "/verification/selected",
            "/verification/relevance/selected",
            "/verification/relevance/candidates/*",
        ],
        "sections": [],
        "collections": {},
    }
    ownership = result["ownership"]
    for key in ("owner", "candidate"):
        ownership[key] = _locator(ownership.get(key))
    ambiguity = ownership.get("ambiguity")
    if isinstance(ambiguity, dict) and isinstance(ambiguity.get("alternatives"), list):
        ambiguity["alternatives"] = [_locator(row) for row in ambiguity["alternatives"]]
    source = ownership.get("source_evidence")
    if isinstance(source, dict) and "content" in source:
        source.pop("content")
        omissions["sections"].append("/ownership/source_evidence/content")
    retrieval = result["retrieval"]
    rows = retrieval["results"]
    # Preserve the canonical first three and already admitted declaration
    # supplements. No authority or retrieval decision is made by this profile.
    retained = rows[:3] + [row for row in rows[3:] if row.get("supplement")][:2]
    retrieval["results"] = retained
    omissions["collections"]["/retrieval/results"] = {
        "observed_in_source_packet": len(rows),
        "returned": len(retained),
        "omitted": len(rows) - len(retained),
    }
    verification = result["verification"]
    verification["selected"] = _locator(verification.get("selected"))
    relevance = verification.get("relevance")
    if isinstance(relevance, dict):
        _encode_task_matches(relevance)
        relevance["selected"] = _locator(relevance.get("selected"))
        candidates = relevance.get("candidates", [])
        selected = relevance.get("selected")
        projected = candidates[:1]
        if isinstance(selected, dict) and not any(
            row.get("path") == selected.get("path") for row in projected
        ):
            projected = [selected]
        relevance["candidates"] = [_locator(row) for row in projected]
        omissions["collections"]["/verification/relevance/candidates"] = {
            "observed_in_source_packet": len(candidates),
            "returned": len(projected),
            "omitted": len(candidates) - sum(row in candidates for row in projected),
        }
    if "related" in result:
        result.pop("related")
        omissions["sections"].append("/related")
    result["initial_projection"] = {
        "authority": "projection-only",
        "omissions": omissions,
        "expansion": {
            "operation": "task_evidence",
            "result_mode": "default",
            "identity_check": "compare-full-packet-identity; changed source may differ",
        },
        "negative_evidence_from_omissions": "not-admissible",
    }
    return result
