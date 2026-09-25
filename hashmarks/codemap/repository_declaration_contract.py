from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

MAX_GROUPS = 128
MAX_DECLARATIONS = 256
MAX_EXPECTED_PER_GROUP = 256
MAX_REQUEST_BYTES = 1_048_576
MAX_PACKET_BYTES = 1_048_576

GROUP_KEYS = frozenset(
    {"group_id", "concept", "scope", "correspondence", "declarations", "coverage"}
)
DECLARATION_KEYS = frozenset(
    {
        "declaration_id",
        "value_state",
        "value",
        "candidate_values",
        "producer",
        "evidence",
    }
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


def encoded_json_bytes(value: object, *, name: str) -> int:
    try:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain JSON-compatible values") from exc
    return len(payload)


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
    if not isinstance(basis, dict) or not basis:
        raise ValueError("correspondence.basis must be a non-empty object")
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
        required_text(value, name="expected declaration id") for value in expected_raw
    ]
    if len(set(expected)) != len(expected):
        raise ValueError("coverage.expected_declaration_ids contains duplicates")

    scope = json_value(row.get("scope", {}), name="coverage.scope")
    provenance = json_value(row.get("provenance", {}), name="coverage.provenance")
    if not isinstance(scope, dict):
        raise ValueError("coverage.scope must be an object")
    if not isinstance(provenance, dict) or not provenance:
        raise ValueError("coverage.provenance must be a non-empty object")
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
        f"declaration:{len(group_id)}:{group_id}:{len(declaration_id)}:{declaration_id}"
    )


def _normalized_evidence(row: Mapping[str, object]) -> list[dict[str, object]]:
    evidence = row.get("evidence")
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)):
        raise ValueError("declaration evidence must be a list")
    if not evidence:
        raise ValueError("each declaration requires exact repository evidence")
    if any(not isinstance(item, Mapping) for item in evidence):
        raise ValueError("each declaration evidence item must be an object")
    return [dict(item) for item in evidence if isinstance(item, Mapping)]


def _normalized_ambiguous_value(
    row: Mapping[str, object],
) -> dict[str, object]:
    if "value" in row:
        raise ValueError("ambiguous declaration must not declare value")
    candidates = row.get("candidate_values")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        raise ValueError("ambiguous declaration requires candidate_values list")
    if len(candidates) < 2:
        raise ValueError("ambiguous declaration requires at least two candidate values")
    normalized = [
        json_value(value, name="candidate value") for value in candidates
    ]
    by_identity = {
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ): value
        for value in normalized
    }
    if len(by_identity) < 2:
        raise ValueError(
            "ambiguous declaration requires at least two distinct candidate values"
        )
    return {
        "candidate_values": [by_identity[key] for key in sorted(by_identity)]
    }


def _normalized_value_fields(
    row: Mapping[str, object], value_state: str
) -> dict[str, object]:
    if value_state == "resolved":
        if "value" not in row:
            raise ValueError("resolved declaration requires value")
        if "candidate_values" in row:
            raise ValueError("resolved declaration must not declare candidate_values")
        return {"value": json_value(row["value"], name="declaration value")}
    if value_state == "ambiguous":
        return _normalized_ambiguous_value(row)
    if "value" in row or "candidate_values" in row:
        raise ValueError(
            "unresolved declaration must not declare value or candidate_values"
        )
    return {}


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
    if not isinstance(producer, dict) or not producer:
        raise ValueError("producer must be a non-empty object")

    binding_id = _binding_id(group_id, declaration_id)
    result = {
        "declaration_id": declaration_id,
        "value_state": value_state,
        "producer": producer,
        "semantic_value_authority": "provider-claimed",
        "binding_id": binding_id,
        **_normalized_value_fields(row, value_state),
    }
    binding = {"binding_id": binding_id, "evidence": _normalized_evidence(row)}
    return result, binding


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
    unsupported = sorted(
        str(row["declaration_id"])
        for row in declarations
        if row.get("evidence_state") != "known-present"
    )
    if unsupported:
        return {
            "state": "ambiguous",
            "reason": "repository-evidence-not-current",
            "unqualified_declaration_ids": unsupported,
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
    present = {
        str(row["declaration_id"])
        for row in declarations
        if row.get("evidence_state") == "known-present"
    }
    unseen = sorted(expected - present)
    unexpected = sorted(present - expected) if expected else []
    if not expected:
        return {
            "state": "unknown",
            "missing_declaration_ids": [],
            "unseen_expected_declaration_ids": [],
            "unexpected_declaration_ids": unexpected,
            "reason": "expected-membership-not-declared",
        }
    if not unseen:
        return {
            "state": "known-present",
            "missing_declaration_ids": [],
            "unseen_expected_declaration_ids": [],
            "unexpected_declaration_ids": unexpected,
        }
    if coverage.get("state") == "complete" and coverage.get("truncation") == "complete":
        return {
            "state": "known-absent",
            "missing_declaration_ids": unseen,
            "unseen_expected_declaration_ids": [],
            "unexpected_declaration_ids": unexpected,
        }
    return {
        "state": "unknown",
        "missing_declaration_ids": [],
        "unseen_expected_declaration_ids": unseen,
        "unexpected_declaration_ids": unexpected,
        "reason": "coverage-does-not-authorize-negative-evidence",
    }


def _normalize_group(
    raw_group: Mapping[str, object],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    reject_unknown(raw_group, allowed=GROUP_KEYS, name="declaration group")
    group_id = required_text(raw_group.get("group_id"), name="group_id")
    concept = json_value(raw_group.get("concept"), name="concept")
    scope = json_value(raw_group.get("scope", {}), name="scope")
    if not isinstance(concept, dict) or not concept:
        raise ValueError("concept must be a non-empty object")
    if not isinstance(scope, dict):
        raise ValueError("scope must be an object")

    raw_declarations = raw_group.get("declarations")
    if not isinstance(raw_declarations, Sequence) or isinstance(
        raw_declarations, (str, bytes)
    ):
        raise ValueError("declarations must be a list")
    pairs = [
        normalize_declaration(raw_declaration, group_id=group_id)
        for raw_declaration in raw_declarations
    ]
    declarations = [declaration for declaration, _binding in pairs]
    declaration_ids = [str(row["declaration_id"]) for row in declarations]
    if len(set(declaration_ids)) != len(declaration_ids):
        raise ValueError(f"duplicate declaration_id in group {group_id}")

    group = {
        "group_id": group_id,
        "concept": concept,
        "scope": scope,
        "correspondence": normalize_correspondence(raw_group.get("correspondence", {})),
        "coverage": normalize_coverage(raw_group.get("coverage", {})),
        "declarations": declarations,
    }
    return group, [binding for _declaration, binding in pairs]


def normalize_request(
    groups: Sequence[Mapping[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if not isinstance(groups, Sequence) or isinstance(groups, (str, bytes)):
        raise ValueError("groups must be a sequence")
    if len(groups) > MAX_GROUPS:
        raise ValueError(f"groups exceeds {MAX_GROUPS} entries")
    if encoded_json_bytes(groups, name="groups") > MAX_REQUEST_BYTES:
        raise ValueError(f"groups exceeds {MAX_REQUEST_BYTES} encoded bytes")
    if any(not isinstance(raw_group, Mapping) for raw_group in groups):
        raise ValueError("each declaration group must be an object")

    pairs = [
        _normalize_group(raw_group)
        for raw_group in groups
        if isinstance(raw_group, Mapping)
    ]
    normalized_groups = [group for group, _bindings in pairs]
    group_ids = [str(group["group_id"]) for group in normalized_groups]
    if len(set(group_ids)) != len(group_ids):
        raise ValueError("duplicate group_id")

    bindings = [
        binding for _group, group_bindings in pairs for binding in group_bindings
    ]
    if len(bindings) > MAX_DECLARATIONS:
        raise ValueError(f"declaration request exceeds {MAX_DECLARATIONS} declarations")
    return normalized_groups, bindings
