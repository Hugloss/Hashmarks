"""Source-oracle checks over returned facts, separate from product producers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from hashmarks.codemap.task_evidence_initial import (
    decode_initial_collection,
    decode_initial_packet,
)
from hashmarks.operation_contract import operation_schema


def _values(
    value: object, components: list[str], *, initial_tables: bool = False
) -> list[object]:
    if not components:
        return [value]
    component, *remaining = components
    if component == "*":
        if not isinstance(value, (list, dict)):
            return []
        children = value.values() if isinstance(value, dict) else value
        return [
            item
            for child in children
            for item in _values(child, remaining, initial_tables=initial_tables)
        ]
    if isinstance(value, Mapping) and component in value:
        child = value[component]
        encoding = value.get(component + "_encoding")
        if initial_tables and isinstance(encoding, dict):
            child = decode_initial_collection(child, encoding)
        return _values(child, remaining, initial_tables=initial_tables)
    if isinstance(value, list) and component.isdecimal():
        index = int(component)
        return (
            _values(value[index], remaining, initial_tables=initial_tables)
            if index < len(value)
            else []
        )
    return []


def pointer_values(packet: object, pointer: str) -> list[object]:
    """RFC 6901 pointers plus explicit wildcard collection for oracle checks."""
    if (
        isinstance(packet, dict)
        and packet.get("schema") == operation_schema("task_evidence", "initial")
        and "encoding" in packet
    ):
        packet = decode_initial_packet(packet)
    if pointer == "":
        return [packet]
    if not pointer.startswith("/"):
        raise ValueError("fact pointer must be empty or start with /")
    components = [
        part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")
    ]
    return _values(
        packet,
        components,
        initial_tables=isinstance(packet, Mapping)
        and packet.get("schema") == operation_schema("task_evidence", "initial"),
    )


def _json_equal(value: object, expected: object) -> bool:
    """Oracle comparisons preserve JSON types, including bool/int/float."""
    if type(value) is not type(expected):
        return False
    if isinstance(value, dict) and isinstance(expected, dict):
        return value.keys() == expected.keys() and all(
            _json_equal(item, expected[key]) for key, item in value.items()
        )
    if isinstance(value, list) and isinstance(expected, list):
        return len(value) == len(expected) and all(
            _json_equal(a, b) for a, b in zip(value, expected, strict=True)
        )
    return value == expected


def _matches_record(value: object, expected: object) -> bool:
    return (
        isinstance(value, Mapping)
        and isinstance(expected, dict)
        and bool(expected)
        and all(
            key in value and _json_equal(value[key], item)
            for key, item in expected.items()
        )
    )


def _includes_scoped_record(values: list[object], expected: object) -> bool:
    if (
        not isinstance(expected, dict)
        or set(expected) != {"scope", "pointer", "record"}
        or not isinstance(expected["pointer"], str)
        or not all(
            isinstance(expected[key], dict) and expected[key]
            for key in ("scope", "record")
        )
    ):
        raise ValueError(
            "scoped source fact requires a scope, child pointer and record"
        )
    return any(
        _matches_record(scope, expected["scope"])
        and any(
            _matches_record(child, expected["record"])
            for child in pointer_values(scope, expected["pointer"])
        )
        for scope in values
    )


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
        "equals": lambda: len(values) == 1 and _json_equal(values[0], expected),
        "includes": lambda: any(_json_equal(value, expected) for value in values),
        "includes_record": lambda: any(
            any(_matches_record(value, record_expected) for value in record_values)
            for _, record_expected, record_values in records
        ),
        "includes_scoped_record": lambda: _includes_scoped_record(values, expected),
        "all_equal": lambda: (
            bool(values) and all(_json_equal(value, expected) for value in values)
        ),
        "excludes": lambda: (
            bool(values) and all(not _json_equal(value, expected) for value in values)
        ),
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
