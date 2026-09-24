from __future__ import annotations

from collections.abc import Mapping

SCHEMA_V3 = "hashmarks.dependency-resolution.v3"
EVIDENCE_AUTHORITIES = {
    "selection",
    "resolution-graph",
    "resolved-inventory",
    "module-ownership",
}
COVERAGE_KINDS = EVIDENCE_AUTHORITIES

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
}


def reject_unknown_fields(value: Mapping[str, object], *, label: str) -> None:
    unknown = sorted(set(value) - _FIELDS[label])
    if unknown:
        raise ValueError(f"unknown dependency {label} field: {unknown[0]}")
