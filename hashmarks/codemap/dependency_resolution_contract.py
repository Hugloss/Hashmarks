from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from hashmarks.operation_contract import operation_schema

SCHEMA_V3 = "hashmarks.dependency-resolution.v3"
DERIVATION_SCHEMA_V1 = "hashmarks.dependency-resolution-derivation.v1"
EXPLAIN_SCHEMA_V1 = operation_schema("dependency_codemap", "explain")
DELTA_SCHEMA_V3 = operation_schema("dependency_codemap", "compare")
QUALIFICATION_SEMANTICS_V3 = "hashmarks.dependency-resolution-qualification.v3"
EVIDENCE_AUTHORITIES = {
    "selection",
    "resolution-graph",
    "resolved-inventory",
    "module-ownership",
}
COVERAGE_KINDS = EVIDENCE_AUTHORITIES
_MAX_TEXT_CHARS = 4096

_FIELDS = {
    "snapshot": frozenset(
        "schema producer scope contexts roots evidence_sources components selections "
        "inventory relationships coverage repository_inputs module_ownership".split()
    ),
    "evidence source": frozenset(
        "source_id kind authorities context completeness truncation producer_digest".split()
    ),
    "component": frozenset("component_id name ecosystem".split()),
    "selection": frozenset(
        "node_id component_id version source marker contexts evidence_sources".split()
    ),
    "inventory": frozenset("node_id context evidence_sources".split()),
    "relationship": frozenset(
        "source target kind context effective_scope marker evidence_sources".split()
    ),
    "root": frozenset("node_id context evidence_sources".split()),
    "module ownership": frozenset(
        "module context owners completeness evidence_sources state authority "
        "producer_authority".split()
    ),
    "coverage": frozenset(
        "context kind completeness truncation evidence_sources".split()
    ),
    "repository input": frozenset("path member_revision".split()),
    "correlation request": frozenset("correlations path_mappings".split()),
    "correlation row": frozenset(
        "module context completeness truncation anchors".split()
    ),
}


def reject_unknown_fields(value: Mapping[str, object], *, label: str) -> None:
    unknown = sorted(set(value) - _FIELDS[label])
    if unknown:
        raise ValueError(f"unknown dependency {label} field: {unknown[0]}")


def normalized_text(value: object, *, label: str, required: bool = False) -> str:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    text = (value or "").strip()
    if required and not text:
        raise ValueError(f"{label} must not be empty")
    if len(text) > _MAX_TEXT_CHARS:
        raise ValueError(f"{label} exceeds {_MAX_TEXT_CHARS} characters")
    return text


def object_rows(value: object, *, label: str, limit: int) -> list[Mapping[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{label} must be a sequence")
    if len(value) > limit:
        raise ValueError(f"{label} exceeds {limit} entries")
    rows: list[Mapping[str, object]] = []
    for row in value:
        if not isinstance(row, Mapping):
            raise ValueError(f"each {label} entry must be an object")
        rows.append(cast("Mapping[str, object]", row))
    return rows
