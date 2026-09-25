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
    def _dependency_index(
        binding: Mapping[str, object],
    ) -> dict[str, Mapping[str, object]]:
        rows = binding.get("dependencies")
        if not isinstance(rows, list):
            return {}
        return {
            str(row["path"]): row
            for row in rows
            if isinstance(row, Mapping) and row.get("path")
        }

    @classmethod
    def _dependency_delta(
        cls,
        before: Mapping[str, object],
        after: Mapping[str, object],
    ) -> dict[str, object]:
        old = cls._dependency_index(before)
        new = cls._dependency_index(after)
        added = sorted(set(new) - set(old))
        removed = sorted(set(old) - set(new))
        observation_changes: list[dict[str, object]] = []
        for path in sorted(set(old) & set(new)):
            previous = old[path]
            current = new[path]
            member_changed = previous.get("member_revision") != current.get(
                "member_revision"
            )
            state_changed = previous.get("state") != current.get("state")
            if member_changed or state_changed:
                observation_changes.append(
                    {
                        "path": path,
                        "state": "changed",
                        "member_changed": member_changed,
                        "observation_state_changed": state_changed,
                    }
                )
        return {
            "state": (
                "affected"
                if observation_changes
                else "definition-changed"
                if added or removed
                else "unaffected"
            ),
            "definition": {
                "state": "changed" if added or removed else "preserved",
                "added": added,
                "removed": removed,
            },
            "observations": {
                "state": "changed" if observation_changes else "unchanged",
                "changes": observation_changes,
            },
        }

    @staticmethod
    def _relationship_observation_config(value: object) -> dict[str, object]:
        if not isinstance(value, Mapping):
            return {
                "state": "unknown",
                "scope_paths": [],
                "limit_per_path": None,
                "completeness": "unknown",
            }
        bounds = value.get("bounds")
        return {
            "state": str(value.get("state") or "unknown"),
            "scope_paths": sorted(
                str(path)
                for path in (
                    value.get("scope_paths")
                    if isinstance(value.get("scope_paths"), list)
                    else []
                )
            ),
            "limit_per_path": (
                bounds.get("limit_per_path") if isinstance(bounds, Mapping) else None
            ),
            "completeness": str(value.get("completeness") or "unknown"),
        }

    @staticmethod
    def _observer_identity(packet: Mapping[str, object]) -> str:
        observer = packet.get("observer")
        return (
            str(observer.get("identity") or "") if isinstance(observer, Mapping) else ""
        )

    @staticmethod
    def _repository_identity(packet: Mapping[str, object]) -> str:
        repository = packet.get("repository")
        return (
            str(repository.get("repository_identity") or "")
            if isinstance(repository, Mapping)
            else ""
        )

    @classmethod
    def _direct_locator_evidence_changes(
        cls,
        old: Mapping[tuple[str, str, int, int, int], Mapping[str, object]],
        new: Mapping[tuple[str, str, int, int, int], Mapping[str, object]],
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        direct_changes: list[dict[str, object]] = []
        locator_changes: list[dict[str, object]] = []
        for key in sorted(set(old) & set(new)):
            previous = old[key]
            current = new[key]
            scope = key[0]
            previous_direct = (
                previous.get("member_revision")
                if scope == "member"
                else previous.get("span_identity")
            )
            current_direct = (
                current.get("member_revision")
                if scope == "member"
                else current.get("span_identity")
            )
            if previous_direct and current_direct and previous_direct != current_direct:
                direct_changes.append(
                    {
                        "scope": scope,
                        "evidence": cls._evidence_locator(key),
                        "state": "changed",
                        "before": previous_direct,
                        "after": current_direct,
                    }
                )
            if scope != "lines":
                continue
            previous_locator = str(previous.get("locator_state") or "unknown")
            current_locator = str(current.get("locator_state") or "unknown")
            if previous_locator != current_locator:
                locator_changes.append(
                    {
                        "evidence": cls._evidence_locator(key),
                        "state": "changed",
                        "before": previous_locator,
                        "after": current_locator,
                    }
                )
        return direct_changes, locator_changes

    @classmethod
    def _member_evidence_changes(
        cls,
        old: Mapping[tuple[str, str, int, int, int], Mapping[str, object]],
        new: Mapping[tuple[str, str, int, int, int], Mapping[str, object]],
    ) -> list[dict[str, object]]:
        changes: list[dict[str, object]] = []
        for key in sorted(set(old) & set(new)):
            previous = old[key]
            current = new[key]
            previous_state = str(
                previous.get("member_state") or previous.get("state") or "unknown"
            )
            current_state = str(
                current.get("member_state") or current.get("state") or "unknown"
            )
            previous_revision = previous.get("member_revision")
            current_revision = current.get("member_revision")
            revision_changed = (
                bool(previous_revision)
                and bool(current_revision)
                and previous_revision != current_revision
            )
            state_changed = previous_state != current_state
            if not revision_changed and not state_changed:
                continue
            if previous_state == "known-present" and current_state == "known-absent":
                transition = "removed"
            elif previous_state == "known-absent" and current_state == "known-present":
                transition = "added"
            elif state_changed:
                transition = "state-changed"
            else:
                transition = "changed"
            changes.append(
                {
                    "scope": key[0],
                    "evidence": cls._evidence_locator(key),
                    "state": transition,
                    "revision_changed": revision_changed,
                    "observation_state_changed": state_changed,
                    "before_state": previous_state,
                    "after_state": current_state,
                }
            )
        return changes

    @staticmethod
    def _comparable_relationship_evidence(
        old: Mapping[str, Mapping[str, object]],
        new: Mapping[str, Mapping[str, object]],
    ) -> dict[str, object]:
        added = [deepcopy(new[key]) for key in sorted(set(new) - set(old))]
        removed = [deepcopy(old[key]) for key in sorted(set(old) - set(new))]
        locator_changes = [
            {
                "identity": key,
                "path": new[key].get("path"),
                "before_line": old[key].get("line"),
                "after_line": new[key].get("line"),
            }
            for key in sorted(set(old) & set(new))
            if old[key].get("line") != new[key].get("line")
        ]
        changed = bool(added or removed or locator_changes)
        return {
            "state": "changed" if changed else "unchanged",
            "comparability": "comparable",
            "facts": {
                "state": "changed" if added or removed else "unchanged",
                "added": added,
                "removed": removed,
            },
            "locators": {
                "state": "changed" if locator_changes else "unchanged",
                "changes": locator_changes,
            },
        }

    @classmethod
    def _relationship_evidence_delta(
        cls,
        before: Mapping[str, object],
        after: Mapping[str, object],
        *,
        observer_changed: bool,
    ) -> dict[str, object]:
        before_relationships = before.get("relationships")
        after_relationships = after.get("relationships")
        before_config = cls._relationship_observation_config(before_relationships)
        after_config = cls._relationship_observation_config(after_relationships)
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
        old = (
            {
                str(row.get("identity")): row
                for row in before_rows
                if isinstance(row, Mapping) and row.get("identity")
            }
            if isinstance(before_rows, list)
            else {}
        )
        new = (
            {
                str(row.get("identity")): row
                for row in after_rows
                if isinstance(row, Mapping) and row.get("identity")
            }
            if isinstance(after_rows, list)
            else {}
        )

        if (
            not observer_changed
            and before_config == after_config
            and before_config["state"] == "observed"
        ):
            evidence = cls._comparable_relationship_evidence(old, new)
        elif (
            before_config["state"] == "not-requested"
            and after_config["state"] == "not-requested"
        ):
            evidence = {
                "state": "not-observed",
                "comparability": "not-observed",
                "facts": {"state": "not-observed", "added": [], "removed": []},
                "locators": {"state": "not-observed", "changes": []},
            }
        else:
            evidence = {
                "state": "unknown",
                "comparability": (
                    "observer-changed"
                    if observer_changed
                    else "observation-configuration-changed"
                ),
                "facts": {"state": "unknown", "added": [], "removed": []},
                "locators": {"state": "unknown", "changes": []},
            }

        return {
            **evidence,
            "completeness": str(after_config["completeness"]),
            "observation": {
                "changed": observer_changed or before_config != after_config,
                "before": before_config,
                "after": after_config,
            },
        }

    @classmethod
    def _binding_change(
        cls,
        before: Mapping[str, object],
        after: Mapping[str, object],
        *,
        observer_changed: bool,
    ) -> dict[str, object]:
        old = cls._evidence_index(before)
        new = cls._evidence_index(after)
        direct_changes, locator_changes = cls._direct_locator_evidence_changes(old, new)
        member_changes = cls._member_evidence_changes(old, new)
        dependency_delta = cls._dependency_delta(before, after)
        dependency_observations = dependency_delta.get("observations")
        dependency_changes = (
            dependency_observations.get("changes")
            if isinstance(dependency_observations, Mapping)
            else []
        )
        relationship_evidence = cls._relationship_evidence_delta(
            before,
            after,
            observer_changed=observer_changed,
        )
        definition_changed = before.get("binding_definition_identity") != after.get(
            "binding_definition_identity"
        )
        changed = bool(
            direct_changes
            or locator_changes
            or member_changes
            or dependency_changes
            or relationship_evidence["state"] == "changed"
            or definition_changed
        )
        return {
            "state": "changed" if changed else "preserved",
            "direct_evidence": {
                "state": "changed" if direct_changes else "preserved",
                "changes": direct_changes,
            },
            "locator_evidence": {
                "state": "changed" if locator_changes else "preserved",
                "changes": locator_changes,
            },
            "member_evidence": {
                "state": "changed" if member_changes else "preserved",
                "changes": member_changes,
            },
            "declared_dependencies": dependency_delta,
            "relationship_evidence": relationship_evidence,
            "definition": {
                "state": "changed" if definition_changed else "preserved",
                "before": before.get("binding_definition_identity"),
                "after": after.get("binding_definition_identity"),
            },
        }

    def _validate_binding_delta_input(
        self,
        packet: Mapping[str, object],
        *,
        name: str,
    ) -> None:
        if packet.get("schema") != "hashmarks.repository-evidence-bindings.v1":
            raise ValueError(f"{name} must be a repository evidence bindings packet")
        identity = packet.get("bindings_identity")
        expected_identity = "sha256:" + self._packet_digest(
            "hashmarks.repository-evidence-bindings.v1",
            {key: value for key, value in packet.items() if key != "bindings_identity"},
        )
        if not isinstance(identity, str) or identity != expected_identity:
            raise ValueError(f"{name} bindings identity mismatch")

    def repository_evidence_binding_delta(
        self,
        before: Mapping[str, object],
        after: Mapping[str, object],
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        for name, packet in (("before", before), ("after", after)):
            self._validate_binding_delta_input(packet, name=name)
        before_repository = self._repository_identity(before)
        after_repository = self._repository_identity(after)
        if not before_repository or before_repository != after_repository:
            raise ValueError("repository evidence bindings repository-mismatch")
        before_observer = self._observer_identity(before)
        after_observer = self._observer_identity(after)
        observer_changed = before_observer != after_observer
        old = self._binding_index(before)
        new = self._binding_index(after)
        added = sorted(set(new) - set(old))
        removed = sorted(set(old) - set(new))
        common = sorted(set(old) & set(new))
        changed: list[dict[str, object]] = []
        preserved: list[str] = []
        for binding_id in common:
            row = self._binding_change(
                old[binding_id],
                new[binding_id],
                observer_changed=observer_changed,
            )
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
            "observer": {
                "before": before_observer or None,
                "after": after_observer or None,
                "changed": observer_changed,
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
