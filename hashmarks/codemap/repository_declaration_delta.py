from __future__ import annotations

from collections.abc import Mapping


def declaration_delta(
    previous: Mapping[str, object],
    current: Mapping[str, object],
    *,
    repository_evidence_delta: Mapping[str, object],
) -> dict[str, object]:
    before = {
        str(row["group_id"]): row
        for row in previous.get("groups", [])
        if isinstance(row, Mapping)
    }
    after = {
        str(row["group_id"]): row
        for row in current.get("groups", [])
        if isinstance(row, Mapping)
    }
    changed: list[dict[str, object]] = []
    for group_id in sorted(set(before) & set(after)):
        old = before[group_id]
        new = after[group_id]
        if old.get("group_observation_identity") == new.get(
            "group_observation_identity"
        ):
            continue

        old_declarations = {
            str(row["declaration_id"]): row
            for row in old.get("declarations", [])
            if isinstance(row, Mapping)
        }
        new_declarations = {
            str(row["declaration_id"]): row
            for row in new.get("declarations", [])
            if isinstance(row, Mapping)
        }
        shared = set(old_declarations) & set(new_declarations)
        value_changed = sorted(
            declaration_id
            for declaration_id in shared
            if _value_signature(old_declarations[declaration_id])
            != _value_signature(new_declarations[declaration_id])
        )
        definition_changed = sorted(
            declaration_id
            for declaration_id in shared
            if old_declarations[declaration_id].get("declaration_definition_identity")
            != new_declarations[declaration_id].get("declaration_definition_identity")
        )
        observation_changed = sorted(
            declaration_id
            for declaration_id in shared
            if old_declarations[declaration_id].get("declaration_observation_identity")
            != new_declarations[declaration_id].get("declaration_observation_identity")
            and declaration_id not in value_changed
            and declaration_id not in definition_changed
        )
        changed.append(
            {
                "group_id": group_id,
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
        )
    return {
        "schema": "hashmarks.repository-declarations-delta.v1",
        "added_group_ids": sorted(set(after) - set(before)),
        "removed_group_ids": sorted(set(before) - set(after)),
        "changed_groups": changed,
        "repository_evidence": repository_evidence_delta,
        "interpretation": "factual-only",
    }


def _value_signature(row: Mapping[str, object]) -> tuple[object, object, object]:
    return (
        row.get("value_state"),
        row.get("value"),
        row.get("candidate_values"),
    )
