from __future__ import annotations

from collections.abc import Mapping


def _group_rows(packet: Mapping[str, object]) -> list[Mapping[str, object]]:
    groups = packet.get("groups", [])
    if not isinstance(groups, list):
        return []
    return [row for row in groups if isinstance(row, Mapping)]


def _groups_by_id(packet: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    return {str(row["group_id"]): row for row in _group_rows(packet)}


def _declarations(group: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    rows = group.get("declarations", [])
    if not isinstance(rows, list):
        return {}
    return {
        str(row["declaration_id"]): row for row in rows if isinstance(row, Mapping)
    }


def _value_signature(row: Mapping[str, object]) -> tuple[object, object, object]:
    return (
        row.get("value_state"),
        row.get("value"),
        row.get("candidate_values"),
    )


def _changed_declaration_ids(
    old: Mapping[str, Mapping[str, object]],
    new: Mapping[str, Mapping[str, object]],
    *,
    field: str,
) -> list[str]:
    shared = set(old) & set(new)
    return sorted(
        declaration_id
        for declaration_id in shared
        if old[declaration_id].get(field) != new[declaration_id].get(field)
    )


def _value_changed_declaration_ids(
    old: Mapping[str, Mapping[str, object]],
    new: Mapping[str, Mapping[str, object]],
) -> list[str]:
    shared = set(old) & set(new)
    return sorted(
        declaration_id
        for declaration_id in shared
        if _value_signature(old[declaration_id])
        != _value_signature(new[declaration_id])
    )


def _group_change(
    group_id: str,
    old: Mapping[str, object],
    new: Mapping[str, object],
) -> dict[str, object]:
    old_declarations = _declarations(old)
    new_declarations = _declarations(new)
    value_changed = _value_changed_declaration_ids(
        old_declarations,
        new_declarations,
    )
    definition_changed = _changed_declaration_ids(
        old_declarations,
        new_declarations,
        field="declaration_definition_identity",
    )
    observation_changed = [
        declaration_id
        for declaration_id in _changed_declaration_ids(
            old_declarations,
            new_declarations,
            field="declaration_observation_identity",
        )
        if declaration_id not in value_changed
        and declaration_id not in definition_changed
    ]
    return {
        "group_id": group_id,
        "semantic_subject_changed": old.get("semantic_subject_identity")
        != new.get("semantic_subject_identity"),
        "definition_changed": old.get("group_definition_identity")
        != new.get("group_definition_identity"),
        "added_declaration_ids": sorted(
            set(new_declarations) - set(old_declarations)
        ),
        "removed_declaration_ids": sorted(
            set(old_declarations) - set(new_declarations)
        ),
        "definition_changed_declaration_ids": definition_changed,
        "value_changed_declaration_ids": value_changed,
        "observation_changed_declaration_ids": observation_changed,
        "comparison_changed": old.get("comparison") != new.get("comparison"),
        "absence_changed": old.get("absence") != new.get("absence"),
        "correspondence_changed": old.get("correspondence")
        != new.get("correspondence"),
        "coverage_changed": old.get("coverage") != new.get("coverage"),
    }


def _subject_index(
    packet: Mapping[str, object],
) -> dict[str, list[Mapping[str, object]]]:
    index: dict[str, list[Mapping[str, object]]] = {}
    for group in _group_rows(packet):
        identity = str(group.get("semantic_subject_identity") or "")
        index.setdefault(identity, []).append(group)
    for rows in index.values():
        rows.sort(key=lambda row: str(row.get("group_id") or ""))
    return index


def _transition(
    old: Mapping[str, object],
    new: Mapping[str, object],
    field: str,
) -> dict[str, object] | None:
    before = old.get(field)
    after = new.get(field)
    if before == after:
        return None
    return {"before": before, "after": after}


def _semantic_subject_change(
    identity: str,
    old: Mapping[str, object],
    new: Mapping[str, object],
) -> dict[str, object] | None:
    old_declarations = _declarations(old)
    new_declarations = _declarations(new)
    change: dict[str, object] = {
        "semantic_subject_identity": identity,
        "semantic_namespace": new.get("semantic_namespace"),
        "previous_group_id": old.get("group_id"),
        "current_group_id": new.get("group_id"),
        "group_id_changed": old.get("group_id") != new.get("group_id"),
        "added_declaration_ids": sorted(
            set(new_declarations) - set(old_declarations)
        ),
        "removed_declaration_ids": sorted(
            set(old_declarations) - set(new_declarations)
        ),
        "value_changed_declaration_ids": _value_changed_declaration_ids(
            old_declarations,
            new_declarations,
        ),
        "producer_changed_declaration_ids": _changed_declaration_ids(
            old_declarations,
            new_declarations,
            field="producer",
        ),
        "evidence_state_changed_declaration_ids": _changed_declaration_ids(
            old_declarations,
            new_declarations,
            field="evidence_state",
        ),
    }
    for field in ("comparison", "absence", "correspondence", "coverage"):
        transition = _transition(old, new, field)
        if transition is not None:
            change[f"{field}_transition"] = transition

    unchanged_values = {
        False,
        (),
        "",
        None,
    }
    meaningful = any(
        value not in unchanged_values and value != []
        for key, value in change.items()
        if key
        not in {
            "semantic_subject_identity",
            "semantic_namespace",
            "previous_group_id",
            "current_group_id",
        }
    )
    return change if meaningful else None


def _semantic_subject_delta(
    previous: Mapping[str, object],
    current: Mapping[str, object],
) -> dict[str, object]:
    before = _subject_index(previous)
    after = _subject_index(current)
    before_ids = set(before)
    after_ids = set(after)
    ambiguous: list[dict[str, object]] = []
    changed: list[dict[str, object]] = []

    for identity in sorted(before_ids & after_ids):
        old_rows = before[identity]
        new_rows = after[identity]
        if len(old_rows) != 1 or len(new_rows) != 1:
            ambiguous.append(
                {
                    "semantic_subject_identity": identity,
                    "previous_group_ids": [
                        str(row.get("group_id") or "") for row in old_rows
                    ],
                    "current_group_ids": [
                        str(row.get("group_id") or "") for row in new_rows
                    ],
                    "reason": "semantic-subject-not-unique",
                }
            )
            continue
        change = _semantic_subject_change(identity, old_rows[0], new_rows[0])
        if change is not None:
            changed.append(change)

    return {
        "added": sorted(after_ids - before_ids),
        "removed": sorted(before_ids - after_ids),
        "ambiguous": ambiguous,
        "changed": changed,
    }


def declaration_delta(
    previous: Mapping[str, object],
    current: Mapping[str, object],
    *,
    repository_evidence_delta: Mapping[str, object],
) -> dict[str, object]:
    before = _groups_by_id(previous)
    after = _groups_by_id(current)
    changed: list[dict[str, object]] = []
    for group_id in sorted(set(before) & set(after)):
        old = before[group_id]
        new = after[group_id]
        if old.get("group_observation_identity") == new.get(
            "group_observation_identity"
        ):
            continue
        changed.append(_group_change(group_id, old, new))

    return {
        "schema": "hashmarks.repository-declarations-delta.v1",
        "added_group_ids": sorted(set(after) - set(before)),
        "removed_group_ids": sorted(set(before) - set(after)),
        "changed_groups": changed,
        "semantic_subjects": _semantic_subject_delta(previous, current),
        "repository_evidence": repository_evidence_delta,
        "interpretation": "factual-only",
    }
