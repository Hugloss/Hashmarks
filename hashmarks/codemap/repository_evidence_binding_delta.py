from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from .engine import CodeMap


class RepositoryEvidenceBindingDeltaMixin:
    """Compare repository evidence binding packets without consumer policy."""

    @staticmethod
    def _binding_index(packet: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
        rows = packet.get("bindings")
        if not isinstance(rows, list):
            return {}
        return {
            str(row["binding_id"]): row
            for row in rows
            if isinstance(row, Mapping) and row.get("binding_id")
        }

    @staticmethod
    def _evidence_index(
        binding: Mapping[str, object],
    ) -> dict[tuple[str, str, int, int, int], Mapping[str, object]]:
        rows = binding.get("evidence")
        if not isinstance(rows, list):
            return {}
        result: dict[tuple[str, str, int, int, int], Mapping[str, object]] = {}
        occurrences: dict[tuple[str, str, int, int], int] = {}
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            scope = str(row.get("scope") or "lines")
            try:
                locator = (
                    scope,
                    str(row.get("path") or ""),
                    int(row.get("start_line") or 0),
                    int(row.get("end_line") or 0),
                )
            except (TypeError, ValueError):
                continue
            occurrence = occurrences.get(locator, 0)
            occurrences[locator] = occurrence + 1
            result[(*locator, occurrence)] = row
        return result

    @staticmethod
    def _evidence_locator(key: tuple[str, str, int, int, int]) -> list[object]:
        scope, path, start, end, _occurrence = key
        return [path] if scope == "member" else [path, start, end]

    @staticmethod
    def _dependency_index(binding: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
        rows = binding.get("dependencies")
        if not isinstance(rows, list):
            return {}
        return {
            str(row["path"]): row
            for row in rows
            if isinstance(row, Mapping) and row.get("path")
        }

    @classmethod
    def _dependency_changes(cls, before: Mapping[str, object], after: Mapping[str, object]) -> list[dict[str, object]]:
        old = cls._dependency_index(before)
        new = cls._dependency_index(after)
        changes: list[dict[str, object]] = []
        for path in sorted(set(old) | set(new)):
            previous = old.get(path)
            current = new.get(path)
            if previous is None:
                changes.append({"path": path, "state": "added"})
            elif current is None:
                changes.append({"path": path, "state": "removed"})
            elif (
                previous.get("member_revision") != current.get("member_revision")
                or previous.get("state") != current.get("state")
            ):
                changes.append({
                    "path": path,
                    "state": "changed",
                    "member_changed": previous.get("member_revision") != current.get("member_revision"),
                    "observation_state_changed": previous.get("state") != current.get("state"),
                })
        return changes

    @classmethod
    def _binding_change(cls, before: Mapping[str, object], after: Mapping[str, object]) -> dict[str, object]:
        old = cls._evidence_index(before)
        new = cls._evidence_index(after)
        keys = sorted(set(old) | set(new))
        changes: list[dict[str, object]] = []
        for key in keys:
            previous = old.get(key)
            current = new.get(key)
            if previous is None:
                changes.append({"evidence": cls._evidence_locator(key), "state": "added"})
                continue
            if current is None:
                changes.append({"evidence": cls._evidence_locator(key), "state": "removed"})
                continue
            scope = key[0]
            direct_changed = (
                previous.get("member_revision") != current.get("member_revision")
                if scope == "member"
                else previous.get("span_identity") != current.get("span_identity")
            )
            member_changed = (
                previous.get("member_revision") != current.get("member_revision")
            )
            state_changed = previous.get("state") != current.get("state")
            if direct_changed or state_changed:
                changes.append(
                    {
                        "scope": scope,
                        "evidence": cls._evidence_locator(key),
                        "state": "changed",
                        "direct_content_changed": direct_changed,
                        "member_changed": member_changed,
                        "observation_state_changed": state_changed,
                    }
                )
        dependency_changes = cls._dependency_changes(before, after)
        before_relationships = before.get("relationships")
        after_relationships = after.get("relationships")
        before_rows = (
            before_relationships.get("relationships")
            if isinstance(before_relationships, Mapping)
            else []
        )
        after_rows = (
            after_relationships.get("relationships")
            if isinstance(after_relationships, Mapping)
            else []
        )
        old_relationships = {
            str(row.get("identity")): row
            for row in before_rows
            if isinstance(row, Mapping) and row.get("identity")
        } if isinstance(before_rows, list) else {}
        new_relationships = {
            str(row.get("identity")): row
            for row in after_rows
            if isinstance(row, Mapping) and row.get("identity")
        } if isinstance(after_rows, list) else {}
        relationship_added = [
            deepcopy(new_relationships[key])
            for key in sorted(set(new_relationships) - set(old_relationships))
        ]
        relationship_removed = [
            deepcopy(old_relationships[key])
            for key in sorted(set(old_relationships) - set(new_relationships))
        ]
        relationship_changed = bool(relationship_added or relationship_removed)
        relationship_observation_changed = before_relationships != after_relationships
        member_changes = [
            {
                "scope": key[0],
                "evidence": cls._evidence_locator(key),
                "state": "changed",
                "member_changed": True,
            }
            for key in keys
            if key in old
            and key in new
            and old[key].get("member_revision") != new[key].get("member_revision")
        ]
        return {
            "state": (
                "changed"
                if (
                    changes
                    or member_changes
                    or dependency_changes
                    or relationship_changed
                    or before.get("binding_definition_identity")
                    != after.get("binding_definition_identity")
                )
                else "preserved"
            ),
            "direct_evidence": {
                "state": "changed" if changes else "preserved",
                "changes": changes,
            },
            "member_evidence": {
                "state": "changed" if member_changes else "preserved",
                "changes": member_changes,
            },
            "declared_dependencies": {
                "state": "affected" if dependency_changes else "unaffected",
                "changes": dependency_changes,
            },
            "relationship_evidence": {
                "state": "changed" if relationship_changed else "unchanged",
                "added": relationship_added,
                "removed": relationship_removed,
                "completeness": (
                    after_relationships.get("completeness", "unknown")
                    if isinstance(after_relationships, Mapping)
                    else "unknown"
                ),
                "observation": {
                    "changed": relationship_observation_changed,
                    "before": deepcopy(before_relationships),
                    "after": deepcopy(after_relationships),
                },
            },
            "definition": {
                "state": (
                    "preserved"
                    if before.get("binding_definition_identity")
                    == after.get("binding_definition_identity")
                    else "changed"
                ),
                "before": before.get("binding_definition_identity"),
                "after": after.get("binding_definition_identity"),
            },
        }

    def repository_evidence_binding_delta(
        self,
        before: Mapping[str, object],
        after: Mapping[str, object],
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        for name, packet in (("before", before), ("after", after)):
            if packet.get("schema") != "hashmarks.repository-evidence-bindings.v1":
                raise ValueError(f"{name} must be a repository evidence bindings packet")
        old = self._binding_index(before)
        new = self._binding_index(after)
        added = sorted(set(new) - set(old))
        removed = sorted(set(old) - set(new))
        common = sorted(set(old) & set(new))
        changed: list[dict[str, object]] = []
        preserved: list[str] = []
        for binding_id in common:
            row = self._binding_change(old[binding_id], new[binding_id])
            if row["state"] == "preserved":
                preserved.append(binding_id)
            else:
                changed.append({"binding_id": binding_id, **row})
        payload: dict[str, object] = {
            "schema": "hashmarks.repository-evidence-binding-delta.v1",
            "repository": {
                "before": deepcopy(before.get("repository")),
                "after": deepcopy(after.get("repository")),
            },
            "bindings_identity": {
                "before": before.get("bindings_identity"),
                "after": after.get("bindings_identity"),
            },
            "bindings": {
                "added": added,
                "removed": removed,
                "preserved": preserved,
                "changed": changed,
            },
            "authority": "repository-intelligence-only",
            "execution_effect": "none",
        }
        payload["delta_identity"] = "sha256:" + self._packet_digest(
            "hashmarks.repository-evidence-binding-delta.v1", payload
        )
        return payload
