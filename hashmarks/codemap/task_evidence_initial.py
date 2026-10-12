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


def _encode_rows(container: dict[str, Any], key: str, columns: list[str]) -> None:
    rows = container.get(key)
    if not isinstance(rows, list):
        return
    if not all(isinstance(row, dict) and set(row) == set(columns) for row in rows):
        return
    container[key + "_encoding"] = {"kind": "columns-rows.v1", "columns": columns}
    container[key] = [[row[column] for column in columns] for row in rows]


def _encode_task_matches(relevance: dict[str, Any]) -> None:
    matches = relevance.get("task_matches")
    if isinstance(matches, dict):
        _encode_rows(
            matches, "matches", ["path", "matched_term_count", "evidence_visibility"]
        )


def _encode_candidate_rows(relevance: dict[str, Any]) -> None:
    rows = relevance.get("candidates")
    if (
        not isinstance(rows, list)
        or not rows
        or not all(isinstance(row, dict) for row in rows)
    ):
        return
    columns = sorted(set.intersection(*(set(row) for row in rows)))
    if not columns:
        return
    relevance["candidates_encoding"] = {
        "kind": "columns-rows-with-extras.v1",
        "columns": columns,
    }
    relevance["candidates"] = [
        [
            *[row[column] for column in columns],
            {key: value for key, value in row.items() if key not in columns},
        ]
        for row in rows
    ]


def decode_initial_collection(
    rows: Any, encoding: dict[str, Any]
) -> list[dict[str, Any]]:
    """Read the explicit lossless table contract without guessing missing fields."""
    columns = encoding.get("columns")
    kind = encoding.get("kind")
    if (
        kind not in {"columns-rows.v1", "columns-rows-with-extras.v1"}
        or not isinstance(columns, list)
        or not all(isinstance(column, str) for column in columns)
        or len(set(columns)) != len(columns)
        or not isinstance(rows, list)
    ):
        raise ValueError("invalid initial collection encoding")
    decoded = []
    extras = kind == "columns-rows-with-extras.v1"
    for row in rows:
        if not isinstance(row, list) or len(row) != len(columns) + int(extras):
            raise ValueError("initial collection row differs from declared columns")
        record = dict(zip(columns, row[: len(columns)], strict=True))
        if extras:
            if not isinstance(row[-1], dict) or set(row[-1]) & set(columns):
                raise ValueError("initial collection extras overwrite declared fields")
            record.update(row[-1])
        decoded.append(record)
    return decoded


def _encode_class_declarations(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        declarations = row.get("class_declarations")
        if isinstance(declarations, dict):
            _encode_rows(
                declarations,
                "declarations",
                ["path", "symbol", "start_line", "end_line"],
            )


def _project_verification(
    verification: dict[str, Any], omissions: dict[str, Any]
) -> None:
    verification["selected"] = _locator(verification.get("selected"))
    relevance = verification.get("relevance")
    if isinstance(relevance, dict):
        _encode_task_matches(relevance)
        relevance["selected"] = _locator(relevance.get("selected"))
        candidates = relevance.get("candidates", [])
        # A selected verifier is not a completeness claim. Preserve every
        # already-bounded alternative rather than silently dropping the test
        # that answers the caller's question. Locators retain relationship and
        # freshness qualifiers; only declared display fields are omitted.
        projected = candidates
        relevance["candidates"] = [_locator(row) for row in projected]
        _encode_candidate_rows(relevance)
        omissions["collections"]["/verification/relevance/candidates"] = {
            "observed_in_source_packet": len(candidates),
            "returned": len(projected),
            "omitted": len(candidates) - len(projected),
        }


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
    owner = ownership.get("owner")
    if isinstance(owner, dict):
        owner_row = next(
            (row for row in rows if row.get("path") == owner.get("path")), None
        )
        if owner_row is not None and owner_row not in retained:
            retained.append(owner_row)
    retrieval["results"] = retained
    _encode_class_declarations(retained)
    omissions["collections"]["/retrieval/results"] = {
        "observed_in_source_packet": len(rows),
        "returned": len(retained),
        "omitted": len(rows) - len(retained),
    }
    _project_verification(result["verification"], omissions)
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
