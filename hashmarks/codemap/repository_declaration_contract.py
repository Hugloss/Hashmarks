from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

MAX_GROUPS = 128
MAX_DECLARATIONS = 256
MAX_EXPECTED_PER_GROUP = 256

GROUP_KEYS = frozenset(
    {"group_id", "concept", "scope", "correspondence", "declarations", "coverage"}
)
DECLARATION_KEYS = frozenset(
    {"declaration_id", "value_state", "value", "candidate_values", "producer", "evidence"}
)
CORRESPONDENCE_KEYS = frozenset({"state", "basis"})
COVERAGE_KEYS = frozenset(
    {"state", "truncation", "expected_declaration_ids", "scope", "provenance"}
)


def json_value(value: object, *, name: str) -> object:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain JSON-compatible values") from exc
    return json.loads(encoded)


def mapping(value: object, *, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def reject_unknown(
    raw: Mapping[str, object], *, allowed: frozenset[str], name: str
) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ValueError(f"{name} contains unknown fields: {', '.join(unknown)}")


def required_text(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def normalize_correspondence(raw: object) -> dict[str, object]:
    row = mapping(raw, name="correspondence")
    reject_unknown(row, allowed=CORRESPONDENCE_KEYS, name="correspondence")
    state = required_text(row.get("state"), name="correspondence.state")
    if state not in {"declared", "ambiguous", "unresolved"}:
        raise ValueError(
            "correspondence.state must be declared, ambiguous, or unresolved"
        )
    basis = json_value(row.get("basis", {}), name="correspondence.basis")
    if not isinstance(basis, dict):
        raise ValueError("correspondence.basis must be an object")
    return {"state": state, "basis": basis}


def normalize_coverage(raw: object) -> dict[str, object]:
    row = mapping(raw, name="coverage")
    reject_unknown(row, allowed=COVERAGE_KEYS, name="coverage")
    state = required_text(row.get("state"), name="coverage.state")
    truncation = required_text(row.get("truncation"), name="coverage.truncation")
    if state not in {"complete", "incomplete", "unknown"}:
        raise ValueError("coverage.state must be complete, incomplete, or unknown")
    if truncation not in {"complete", "truncated", "unknown"}:
        raise ValueError("coverage.truncation must be complete, truncated, or unknown")
    if state == "complete" and truncation != "complete":
        raise ValueError("complete declaration coverage requires truncation=complete")

    expected_raw = row.get("expected_declaration_ids", [])
    if not isinstance(expected_raw, Sequence) or isinstance(expected_raw, (str, bytes)):
        raise ValueError("coverage.expected_declaration_ids must be a list")
    if len(expected_raw) > MAX_EXPECTED_PER_GROUP:
        raise ValueError(
            "coverage.expected_declaration_ids exceeds "
            f"{MAX_EXPECTED_PER_GROUP} entries"
        )
    expected = [
        required_text(value, name="expected declaration id")
        for value in expected_raw
    ]
    if len(set(expected)) != len(expected):
        raise ValueError("coverage.expected_declaration_ids contains duplicates")

    scope = json_value(row.get("scope", {}), name="coverage.scope")
    provenance = json_value(row.get("provenance", {}), name="coverage.provenance")
    if not isinstance(scope, dict) or not isinstance(provenance, dict):
        raise ValueError("coverage scope/provenance must be objects")
    return {
        "state": state,
        "truncation": truncation,
        "expected_declaration_ids": sorted(expected),
        "scope": scope,
        "provenance": provenance,
        "authority": "provider-claimed",
    }


def _binding_id(group_id: str, declaration_id: str) -> str:
    return (
        f"declaration:{len(group_id)}:{group_id}:"
        f"{len(declaration_id)}:{declaration_id}"
    )


def normalize_declaration(
    raw: object, *, group_id: str
) -> tuple[dict[str, object], dict[str, object]]:
    row = mapping(raw, name="declaration")
    reject_unknown(row, allowed=DECLARATION_KEYS, name="declaration")
    declaration_id = required_text(row.get("declaration_id"), name="declaration_id")
    value_state = required_text(row.get("value_state"), name="value_state")
    if value_state not in {"resolved", "ambiguous", "unresolved"}:
        raise ValueError("value_state must be resolved, ambiguous, or unresolved")

    producer = json_value(row.get("producer", {}), name="producer")
    if not isinstance(producer, dict):
        raise ValueError("producer must be an object")
    evidence = row.get("evidence")
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)):
        raise ValueError("declaration evidence must be a list")
    if not evidence:
        raise ValueError("each declaration requires exact repository evidence")
    normalized_evidence: list[dict[str, object]] = []
    for item in evidence:
        if not isinstance(item, Mapping):
            raise ValueError("each declaration evidence item must be an object")
        normalized_evidence.append(dict(item))

    result: dict[str, object] = {
        "declaration_id": declaration_id,
        "value_state": value_state,
        "producer": producer,
        "semantic_value_authority": "provider-claimed",
    }
    if value_state == "resolved":
        if "value" not in row:
            raise ValueError("resolved declaration requires value")
        if "candidate_values" in row:
            raise ValueError("resolved declaration must not declare candidate_values")
        result["value"] = json_value(row["value"], name="declaration value")
    elif value_state == "ambiguous":
        if "value" in row:
            raise ValueError("ambiguous declaration must not declare value")
        candidates = row.get("candidate_values")
        if not isinstance(candidates, Sequence) or isinstance(
            candidates, (str, bytes)
        ):
            raise ValueError("ambiguous declaration requires candidate_values list")
        if len(candidates) < 2:
            raise ValueError(
                "ambiguous declaration requires at least two candidate values"
            )
        result["candidate_values"] = [
            json_value(value, name="candidate value") for value in candidates
        ]
    elif "value" in row or "candidate_values" in row:
        raise ValueError(
            "unresolved declaration must not declare value or candidate_values"
        )

    binding_id = _binding_id(group_id, declaration_id)
    result["binding_id"] = binding_id
    return result, {"binding_id": binding_id, "evidence": normalized_evidence}


def comparison(
    declarations: Sequence[Mapping[str, object]],
    correspondence: Mapping[str, object],
) -> dict[str, object]:
    if correspondence.get("state") != "declared":
        return {
            "state": "ambiguous",
            "reason": "correspondence-not-uniquely-declared",
            "distinct_values": [],
        }
    nonresolved = sorted(
        str(row["declaration_id"])
        for row in declarations
        if row.get("value_state") != "resolved"
    )
    if nonresolved:
        return {
            "state": "ambiguous",
            "reason": "one-or-more-values-not-resolved",
            "ambiguous_declaration_ids": nonresolved,
            "distinct_values": [],
        }
    if len(declarations) < 2:
        values = [declarations[0]["value"]] if declarations else []
        return {
            "state": "insufficient",
            "reason": "fewer-than-two-resolved-declarations",
            "distinct_values": values,
        }

    by_json: dict[str, object] = {}
    for row in declarations:
        value = row["value"]
        key = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        by_json.setdefault(key, value)
    distinct = [by_json[key] for key in sorted(by_json)]
    return {
        "state": "equivalent" if len(distinct) == 1 else "differing",
        "distinct_values": distinct,
    }


def absence(
    declarations: Sequence[Mapping[str, object]],
    coverage: Mapping[str, object],
) -> dict[str, object]:
    expected = set(coverage.get("expected_declaration_ids") or [])
    present = {str(row["declaration_id"]) for row in declarations}
    unseen = sorted(expected - present)
    if not expected:
        return {
            "state": "not-assessed",
            "missing_declaration_ids": [],
            "unseen_expected_declaration_ids": [],
        }
    if not unseen:
        return {
            "state": "none",
            "missing_declaration_ids": [],
            "unseen_expected_declaration_ids": [],
        }
    if coverage.get("state") == "complete" and coverage.get("truncation") == "complete":
        return {
            "state": "present",
            "missing_declaration_ids": unseen,
            "unseen_expected_declaration_ids": [],
        }
    return {
        "state": "unknown",
        "missing_declaration_ids": [],
        "unseen_expected_declaration_ids": unseen,
        "reason": "coverage-does-not-authorize-negative-evidence",
    }


def normalize_request(
    groups: Sequence[Mapping[str, object]],
) -> tuple[list[Mapping[str, object]], list[dict[str, object]]]:
    if not isinstance(groups, Sequence) or isinstance(groups, (str, bytes)):
        raise ValueError("groups must be a sequence")
    if len(groups) > MAX_GROUPS:
        raise ValueError(f"groups exceeds {MAX_GROUPS} entries")

    normalized_groups: list[Mapping[str, object]] = []
    bindings: list[dict[str, object]] = []
    seen_groups: set[str] = set()
    declaration_count = 0
    for raw_group in groups:
        if not isinstance(raw_group, Mapping):
            raise ValueError("each declaration group must be an object")
        reject_unknown(raw_group, allowed=GROUP_KEYS, name="declaration group")
        group_id = required_text(raw_group.get("group_id"), name="group_id")
        if group_id in seen_groups:
            raise ValueError(f"duplicate group_id: {group_id}")
        seen_groups.add(group_id)

        # Validate group-level semantics before repository evidence is read.
        concept = json_value(raw_group.get("concept"), name="concept")
        scope = json_value(raw_group.get("scope", {}), name="scope")
        if not isinstance(concept, dict) or not isinstance(scope, dict):
            raise ValueError("concept and scope must be objects")
        normalize_correspondence(raw_group.get("correspondence", {}))
        normalize_coverage(raw_group.get("coverage", {}))

        raw_declarations = raw_group.get("declarations")
        if not isinstance(raw_declarations, Sequence) or isinstance(
            raw_declarations, (str, bytes)
        ):
            raise ValueError("declarations must be a list")
        group_seen: set[str] = set()
        for raw_declaration in raw_declarations:
            normalized, binding = normalize_declaration(
                raw_declaration, group_id=group_id
            )
            declaration_id = str(normalized["declaration_id"])
            if declaration_id in group_seen:
                raise ValueError(
                    f"duplicate declaration_id in group {group_id}: {declaration_id}"
                )
            group_seen.add(declaration_id)
            bindings.append(binding)
            declaration_count += 1
        normalized_groups.append(raw_group)

    if declaration_count > MAX_DECLARATIONS:
        raise ValueError(
            f"declaration request exceeds {MAX_DECLARATIONS} declarations"
        )
    return normalized_groups, bindings
