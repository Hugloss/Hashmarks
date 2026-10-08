"""Typed, provenance-preserving presentation of existing repository observations.

No source reads, secondary semantics, or agent policy. The canonical producer
packet stays available next to this bounded *presentation* projection.
"""

from __future__ import annotations

from collections.abc import Mapping

FAMILIES = (
    "source_change",
    "relationship_change",
    "dependency_change",
    "diagnostic_observation",
    "verification_evidence",
    "correspondence",
    "evidence_qualification",
)
FORMATS = frozenset({"none", "structured", "compact", "text"})
_MAX_PRESENTED_ROWS = 48


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _add(
    grouped: dict[str, list[dict[str, object]]],
    family: str,
    assertion: str,
    kind: str,
    value: object,
    *,
    basis: str,
) -> None:
    if family not in FAMILIES:
        raise ValueError("unknown evidence family")
    row = _mapping(value)
    entry: dict[str, object] = {
        "kind": kind,
        "assertion": assertion,
        "basis": basis,
    }
    for key in ("path", "name", "qualname", "from", "to", "reason", "state", "component_id"):
        if key in row and key != "kind":
            entry[key] = row[key]
    if isinstance(value, bool):
        entry["projection_changed"] = value
    grouped[family].append(entry)


def _delta(
    grouped: dict[str, list[dict[str, object]]], payload: Mapping[str, object]
) -> None:
    semantic = _mapping(payload.get("semantic"))
    for key, family, kind in (
        ("symbols_added", "source_change", "symbol_added"),
        ("symbols_removed", "source_change", "symbol_removed"),
        ("dependencies_added", "relationship_change", "dependency_edge_added"),
        ("dependencies_removed", "relationship_change", "dependency_edge_removed"),
    ):
        rows = semantic.get(key)
        if isinstance(rows, list):
            for row in rows:
                _add(
                    grouped,
                    family,
                    "observed_change",
                    kind,
                    row,
                    basis="repository-delta",
                )
    moves = semantic.get("possible_symbol_moves")
    if isinstance(moves, list):
        for row in moves:
            _add(
                grouped,
                "correspondence",
                "candidate_correspondence",
                "possible_symbol_move",
                row,
                basis="same-name-kind-candidate",
            )
    _delta_qualifications(grouped, semantic, payload)



def _delta_qualifications(
    grouped: dict[str, list[dict[str, object]]],
    semantic: Mapping[str, object],
    payload: Mapping[str, object],
) -> None:
    for key, family in (
        ("ownership_changed", "relationship_change"),
        ("impact_changed", "relationship_change"),
        ("verification_changed", "verification_evidence"),
        ("freshness_changed", "evidence_qualification"),
        ("project_provenance_changed", "evidence_qualification"),
    ):
        if semantic.get(key) is True:
            _add(
                grouped,
                family,
                "observed_change",
                key,
                True,
                basis="projection-difference",
            )
    qualification = _mapping(payload.get("completeness"))
    if qualification.get("changed") is True:
        _add(
            grouped,
            "evidence_qualification",
            "observed_change",
            "completeness_changed",
            True,
            basis="explicit-completeness-transition",
        )
    observer = _mapping(payload.get("observer"))
    if observer.get("changed") is True:
        _add(
            grouped,
            "evidence_qualification",
            "observed_change",
            "observer_capability_changed",
            True,
            basis="observer-identity-transition",
        )



def _snapshot_members(
    grouped: dict[str, list[dict[str, object]]], payload: Mapping[str, object]
) -> None:
    paths = _mapping(payload.get("paths"))
    for path, value in sorted(paths.items()):
        row = _mapping(value)
        if row.get("revision") is not None:
            _add(
                grouped,
                "evidence_qualification",
                "observed_fact",
                "member_revision_observed",
                {"path": path},
                basis="repository-snapshot",
            )



def _snapshot_affected(
    grouped: dict[str, list[dict[str, object]]], payload: Mapping[str, object]
) -> None:
    affected = _mapping(payload.get("affected"))
    for role, rows in sorted(affected.items()):
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, Mapping) and row.get("path"):
                    _add(
                        grouped,
                        "relationship_change",
                        "observed_fact",
                        "related_surface:" + str(role),
                        row,
                        basis="bounded-repository-impact",
                    )



def _snapshot(
    grouped: dict[str, list[dict[str, object]]], payload: Mapping[str, object]
) -> None:
    _snapshot_members(grouped, payload)
    verification = _mapping(payload.get("verification"))
    if verification.get("member"):
        _add(
            grouped,
            "verification_evidence",
            "observed_fact",
            "verification_candidate_observed",
            {"path": verification["member"], "reason": verification.get("reason")},
            basis="bounded-verification-relevance",
        )
    _snapshot_affected(grouped, payload)
    freshness = payload.get("freshness")
    if freshness is not None:
        _add(
            grouped,
            "evidence_qualification",
            "observed_fact",
            "freshness_observed",
            {},
            basis="bounded-freshness-map",
        )


def _diagnostic(
    grouped: dict[str, list[dict[str, object]]], payload: Mapping[str, object]
) -> None:
    diagnostics = _mapping(payload.get("diagnostics"))
    for field, kind in (
        ("added", "diagnostic_added"),
        ("removed", "diagnostic_missing_after"),
    ):
        rows = diagnostics.get(field)
        if isinstance(rows, list):
            for row in rows:
                _add(
                    grouped,
                    "diagnostic_observation",
                    "producer_claim",
                    kind,
                    row,
                    basis="external-diagnostic-identity-delta",
                )
    moves = diagnostics.get("possible_relocations")
    if isinstance(moves, list):
        for row in moves:
            _add(
                grouped,
                "correspondence",
                "candidate_correspondence",
                "possible_diagnostic_relocation",
                row,
                basis="external-diagnostic-correspondence",
            )


def _project_source(
    grouped: dict[str, list[dict[str, object]]],
    packet: Mapping[str, object],
    schema: object,
) -> bool:
    supported = False
    if schema == "hashmarks.repository-intelligence-delta.v1":
        _delta(grouped, packet)
        supported = True
    elif schema == "hashmarks.repository-intelligence-snapshot.v1":
        _snapshot(grouped, packet)
        supported = True
    elif schema == "hashmarks.evidence-profile.v1":
        evidence = _mapping(packet.get("evidence"))
        source = (
            _mapping(evidence.get("snapshot"))
            if packet.get("profile") == "audit"
            else evidence
        )
        _snapshot(grouped, source)
        supported = True
    elif schema == "hashmarks.diagnostic-observation-delta.v1":
        _diagnostic(grouped, packet)
        supported = True
    elif schema == "hashmarks.dependency-resolution-delta.v3":
        transitions = packet.get("component_selection_transitions")
        if isinstance(transitions, list):
            for row in transitions:
                _add(
                    grouped,
                    "dependency_change",
                    "observed_change",
                    "component_selection_transition",
                    row,
                    basis="qualified-dependency-endpoints",
                )
        supported = True
    return supported



def _present_groups(
    grouped: dict[str, list[dict[str, object]]], format: str
) -> list[dict[str, object]]:
    groups: list[dict[str, object]] = []
    for family in FAMILIES:
        entries = grouped[family]
        if not entries:
            continue
        if format == "structured":
            selected = entries[:_MAX_PRESENTED_ROWS]
        else:
            selected = entries[:5]
        groups.append(
            {
                "family": family,
                "count_observed_in_packet": len(entries),
                "findings": selected,
                "omitted_from_presentation": len(entries) - len(selected),
            }
        )
    return groups



def present_repository_evidence(
    packet: Mapping[str, object], *, format: str = "compact"
) -> dict[str, object]:
    """Render typed findings without changing canonical producer authority.

    An unsupported source schema returns explicit unsupported coverage rather
    than guessing from loosely matching field names.
    """
    if format not in FORMATS or format == "none":
        raise ValueError("presentation must be one of: structured, compact, text")
    schema = packet.get("schema")
    grouped: dict[str, list[dict[str, object]]] = {family: [] for family in FAMILIES}
    supported = _project_source(grouped, packet, schema)
    groups = _present_groups(grouped, format)
    result: dict[str, object] = {
        "source_schema": schema,
        "source_evidence_identity": (
            packet.get("delta_identity")
            or packet.get("snapshot_identity")
            or packet.get("profile_identity")
        ),
        "format": format,
        "supported": supported,
        "coverage": "projection-only" if supported else "unsupported",
        "groups": groups,
        "authority": "descriptive-only",
        "execution_effect": "none",
    }
    if format == "text":
        result["text"] = "\n".join(
            f"{group['family']}: {group['count_observed_in_packet']} observed "
            f"({group['omitted_from_presentation']} omitted from presentation)"
            for group in groups
        ) or ("No supported findings" if supported else "Unsupported evidence schema")
    return result
