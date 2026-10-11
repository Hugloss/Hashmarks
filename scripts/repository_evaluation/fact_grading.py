"""Source-oracle checks over returned facts, separate from product producers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _values(value: object, components: list[str]) -> list[object]:
    if not components:
        return [value]
    component, *remaining = components
    if component == "*":
        if not isinstance(value, (list, dict)):
            return []
        children = value.values() if isinstance(value, dict) else value
        return [item for child in children for item in _values(child, remaining)]
    if isinstance(value, Mapping) and component in value:
        return _values(value[component], remaining)
    if isinstance(value, list) and component.isdecimal():
        index = int(component)
        return _values(value[index], remaining) if index < len(value) else []
    return []


def pointer_values(packet: object, pointer: str) -> list[object]:
    """RFC 6901 pointers plus explicit wildcard collection for oracle checks."""
    if pointer == "":
        return [packet]
    if not pointer.startswith("/"):
        raise ValueError("fact pointer must be empty or start with /")
    components = [
        part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")
    ]
    return _values(packet, components)


def _check(packet: object, rule: Mapping[str, Any]) -> dict[str, object]:
    pointer, predicate = str(rule["pointer"]), str(rule["predicate"])
    values = pointer_values(packet, pointer)
    expected = rule["value"]
    alternatives = rule.get("alternative_records", [])
    if alternatives and (predicate != "includes_record" or rule.get("authority_check")):
        raise ValueError("alternative records are only positive source-fact checks")
    records = [(pointer, expected, values)]
    for alternative in alternatives:
        alternative_pointer = alternative["pointer"]
        records.append(
            (
                alternative_pointer,
                alternative["value"],
                pointer_values(packet, alternative_pointer),
            )
        )
    predicates = {
        "equals": lambda: len(values) == 1 and values[0] == expected,
        "includes": lambda: any(value == expected for value in values),
        "includes_record": lambda: any(
            isinstance(record_expected, dict)
            and bool(record_expected)
            and any(
                isinstance(value, Mapping)
                and all(
                    key in value and value[key] == item
                    for key, item in record_expected.items()
                )
                for value in record_values
            )
            for _, record_expected, record_values in records
        ),
        "all_equal": lambda: (
            bool(values) and all(value == expected for value in values)
        ),
        "excludes": lambda: bool(values) and all(value != expected for value in values),
    }
    if predicate not in predicates:
        raise ValueError(f"unsupported fact predicate: {predicate}")
    return {
        "id": str(rule["id"]),
        "pointer": pointer,
        "predicate": predicate,
        "expected": expected,
        "observed": values,
        "alternative_records": [
            {
                "pointer": record_pointer,
                "expected": record_expected,
                "observed": record_values,
            }
            for record_pointer, record_expected, record_values in records[1:]
        ],
        "classification": "PASS"
        if predicates[predicate]()
        else "FAIL"
        if any(record_values for _, _, record_values in records)
        else "INCOMPLETE",
        "authority_check": rule.get("authority_check") is True,
    }


def grade_facts(
    case_id: str, result: Mapping[str, Any], rule: Mapping[str, Any]
) -> dict[str, object]:
    packet = result.get("packet")
    checks = rule.get("checks")
    if not isinstance(packet, dict) or not isinstance(checks, list) or not checks:
        raise ValueError(
            f"{case_id}: fact grading requires a packet and non-empty checks"
        )
    ids = [check["id"] for check in checks]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{case_id}: duplicate fact checks")
    rows = [_check(packet, check) for check in checks]
    states = {row["classification"] for row in rows}
    classification = (
        "OTHER_FAILURE"
        if "FAIL" in states
        else "INCOMPLETE"
        if "INCOMPLETE" in states
        else "PASS"
    )
    return {
        "id": case_id,
        "classification": classification,
        "failure_stage": "CORRECT"
        if classification == "PASS"
        else "SOURCE_FACT_MISMATCH",
        "checks": rows,
        "authority_violations": sum(
            row["authority_check"] is True and row["classification"] == "FAIL"
            for row in rows
        ),
    }
