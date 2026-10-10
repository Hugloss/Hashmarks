"""Stage admitted SCIP records before the existing atomic index publication."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

from hashmarks.paths import normalize_relative_path

from .scip_relationship_adapter import scip_occurrence_payload, scip_source_snapshot
from .semantic_relationship_model import CLAIM_LIMIT, content_identity

if TYPE_CHECKING:
    from .engine import CodeMap
    from .scip_adapter import ScipOccurrence


@dataclass
class ScipImportRows:
    definitions: list[dict[str, Any]] = field(default_factory=list)
    references: list[dict[str, Any]] = field(default_factory=list)
    unlocated: list[dict[str, Any]] = field(default_factory=list)
    skipped: int = 0
    unlocated_omitted: int = 0


def _reference(
    codemap: CodeMap,
    occurrence: ScipOccurrence,
    path: str,
    revision: str | None,
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    candidates = [
        row
        for row in cast("list[dict[str, Any]]", codemap._session_symbols_for_path(path))
        if int(row["start_line"]) <= occurrence.line <= int(row["end_line"])
    ]
    candidates.sort(
        key=lambda row: (
            int(row["end_line"]) - int(row["start_line"]),
            -int(row["start_line"]),
        )
    )
    return {
        "path": path,
        "source": str(candidates[0]["qualname"]) if candidates else None,
        "target_symbol": occurrence.symbol,
        "target_name": occurrence.display_name,
        "line": occurrence.line,
        "occurrence_metadata": {
            "locator": occurrence.locator,
            "occurrence_roles": occurrence.occurrence_roles,
        },
        "source_snapshot": scip_source_snapshot(
            scip_occurrence_payload(occurrence, revision, provenance)
        ),
    }


def scip_reference_rows(references: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Retain bounded occurrence evidence inside the existing grouped edge key."""
    grouped: dict[tuple[str, str, int], dict[str, Any]] = {}
    occurrences: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    for row in references:
        key = (row["path"], row["target_symbol"], row["line"])
        grouped[key] = {
            key: value for key, value in row.items() if key != "occurrence_metadata"
        }
        occurrences.setdefault(key, []).append(row["occurrence_metadata"])
    for key, row in grouped.items():
        supplied = occurrences[key]
        distinct = {
            json.dumps(value, sort_keys=True, separators=(",", ":")): value
            for value in supplied
        }
        retained = [distinct[identity] for identity in sorted(distinct)[:CLAIM_LIMIT]]
        omitted = len(distinct) - len(retained)
        row["occurrence_metadata"] = {
            "source_snapshot": row.pop("source_snapshot"),
            "state": "supplied",
            "occurrences": retained,
            "received": len(supplied),
            "retained": len(retained),
            "duplicates": len(supplied) - len(distinct),
            "omitted": omitted,
            "truncated": bool(omitted),
            "negative_evidence_admissible": False,
        }
    return [grouped[key] for key in sorted(grouped)]


def _definition(
    occurrence: ScipOccurrence,
    path: str,
    revision: str | None,
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "path": path,
        "symbol": occurrence.symbol,
        "display_name": occurrence.display_name,
        "line": occurrence.line,
        "end_line": occurrence.end_line,
        "relationships_json": json.dumps(
            scip_occurrence_payload(occurrence, revision, provenance),
            sort_keys=True,
            separators=(",", ":"),
        ),
        "relationships_truncated": occurrence.relationships_truncated,
    }


def collect_scip_rows(
    codemap: CodeMap,
    producer: str,
    occurrences: Sequence[ScipOccurrence],
    provenance: Mapping[str, Any],
) -> ScipImportRows:
    rows = ScipImportRows()
    for occurrence in occurrences:
        try:
            path = normalize_relative_path(occurrence.path, allow_root=False)
        except ValueError:
            rows.skipped += 1
            continue
        member = codemap._session_file_row(path)
        if (
            member is None
            or member["evidence_visibility"] == "deny"
            or codemap.policy.decide(path).evidence_visibility.value == "deny"
        ):
            rows.skipped += 1
            continue
        _append_occurrence(codemap, producer, occurrence, member, provenance, rows)
    return rows


def _append_occurrence(
    codemap: CodeMap,
    producer: str,
    occurrence: ScipOccurrence,
    member: Mapping[str, Any],
    provenance: Mapping[str, Any],
    rows: ScipImportRows,
) -> None:
    path = member["path"]
    if occurrence.relationship_only:
        if len(rows.unlocated) >= CLAIM_LIMIT:
            rows.unlocated_omitted += 1
        else:
            rows.unlocated.append(
                {
                    **_definition(
                        occurrence, path, member.get("file_digest"), provenance
                    ),
                    "producer": producer,
                }
            )
    elif occurrence.definition:
        rows.definitions.append(
            _definition(occurrence, path, member.get("file_digest"), provenance)
        )
    else:
        rows.references.append(
            _reference(codemap, occurrence, path, member.get("file_digest"), provenance)
        )


def publish_scip_claim_metadata(
    codemap: CodeMap, producer: str, rows: ScipImportRows, provenance: Mapping[str, Any]
) -> None:
    snapshot = codemap._evidence_snapshot("scip", producer)
    assert snapshot is not None
    snapshot.update(
        {
            "relationship_provenance": dict(provenance),
            "unlocated_relationship_claims": rows.unlocated,
            "unlocated_relationship_omitted": rows.unlocated_omitted,
            "relationship_import_excluded": rows.skipped,
            "relationship_capture_identity": content_identity(
                {
                    "producer": producer,
                    "definitions": rows.definitions,
                    "references": rows.references,
                    "unlocated": rows.unlocated,
                    "provenance": dict(provenance),
                }
            ),
        }
    )
    codemap.store.set_meta(
        codemap._evidence_key("scip", producer),
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")),
    )
