from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from hashmarks.client import RepositoryObservation
from hashmarks.observation import ObservationState
from hashmarks.paths import normalize_relative_path

if TYPE_CHECKING:
    from .engine import CodeMap


@dataclass
class _CoverageBindingChanges:
    direct_changed: set[str] = field(default_factory=set)
    member_only: set[str] = field(default_factory=set)
    member_added: set[str] = field(default_factory=set)
    member_removed: set[str] = field(default_factory=set)
    member_state_changed: set[str] = field(default_factory=set)
    locator_changed: set[str] = field(default_factory=set)

    def bound_to(self, bound_members: set[str]) -> "_CoverageBindingChanges":
        direct_changed = self.direct_changed & bound_members
        return _CoverageBindingChanges(
            direct_changed=direct_changed,
            member_only=(self.member_only & bound_members) - direct_changed,
            member_added=self.member_added & bound_members,
            member_removed=self.member_removed & bound_members,
            member_state_changed=self.member_state_changed & bound_members,
            locator_changed=self.locator_changed & bound_members,
        )

    def classified_paths(self) -> set[str]:
        return (
            self.direct_changed
            | self.member_only
            | self.member_added
            | self.member_removed
            | self.member_state_changed
            | self.locator_changed
        )


class RepositoryEvidenceCoverageMixin:
    """Classify repository change evidence against opaque evidence bindings."""

    @staticmethod
    def _binding_rows(packet: Mapping[str, object]) -> list[Mapping[str, object]]:
        rows = packet.get("bindings")
        return (
            [row for row in rows if isinstance(row, Mapping)]
            if isinstance(rows, list)
            else []
        )

    @classmethod
    def _coverage_binding_paths(
        cls, packet: Mapping[str, object]
    ) -> tuple[set[str], set[str]]:
        evidence_paths: set[str] = set()
        dependency_paths: set[str] = set()
        for binding in cls._binding_rows(packet):
            evidence = binding.get("evidence")
            if isinstance(evidence, list):
                evidence_paths.update(
                    str(row.get("path") or "")
                    for row in evidence
                    if isinstance(row, Mapping) and row.get("path")
                )
            dependencies = binding.get("dependencies")
            if isinstance(dependencies, list):
                dependency_paths.update(
                    str(row.get("path") or "")
                    for row in dependencies
                    if isinstance(row, Mapping) and row.get("path")
                )
        return evidence_paths, dependency_paths

    @staticmethod
    def _changed_binding_index(
        binding_delta: Mapping[str, object] | None,
    ) -> dict[str, Mapping[str, object]]:
        if not isinstance(binding_delta, Mapping):
            return {}
        bindings = binding_delta.get("bindings")
        changed = bindings.get("changed") if isinstance(bindings, Mapping) else None
        if not isinstance(changed, list):
            return {}
        return {
            str(row.get("binding_id")): row
            for row in changed
            if isinstance(row, Mapping) and row.get("binding_id")
        }

    @staticmethod
    def _binding_paths(
        binding: Mapping[str, object],
    ) -> tuple[set[str], set[str]]:
        evidence = binding.get("evidence")
        dependencies = binding.get("dependencies")
        evidence_paths = (
            {
                str(row.get("path") or "")
                for row in evidence
                if isinstance(row, Mapping) and row.get("path")
            }
            if isinstance(evidence, list)
            else set()
        )
        dependency_paths = (
            {
                str(row.get("path") or "")
                for row in dependencies
                if isinstance(row, Mapping) and row.get("path")
            }
            if isinstance(dependencies, list)
            else set()
        )
        return evidence_paths, dependency_paths

    @staticmethod
    def _member_binding_impact_reasons(
        detail: Mapping[str, object],
    ) -> set[str]:
        member = detail.get("member_evidence")
        member_changes = member.get("changes") if isinstance(member, Mapping) else None
        if not isinstance(member_changes, list):
            return set()
        reasons: set[str] = set()
        for change in member_changes:
            if not isinstance(change, Mapping):
                continue
            transition = str(change.get("state") or "changed")
            reasons.add(
                {
                    "removed": "bound-member-removed",
                    "added": "bound-member-added",
                    "state-changed": "bound-member-observation-state-changed",
                }.get(transition, "bound-member-changed")
            )
        return reasons

    @classmethod
    def _direct_binding_impact_reasons(
        cls,
        detail: Mapping[str, object],
    ) -> set[str]:
        reasons = cls._member_binding_impact_reasons(detail)
        direct = detail.get("direct_evidence")
        if isinstance(direct, Mapping) and direct.get("state") == "changed":
            direct_changes = direct.get("changes")
            scopes = (
                {
                    str(change.get("scope") or "lines")
                    for change in direct_changes
                    if isinstance(change, Mapping)
                }
                if isinstance(direct_changes, list)
                else {"lines"}
            )
            if "member" in scopes:
                reasons.add("bound-member-content-changed")
            if "lines" in scopes:
                reasons.add("bound-range-content-changed")

        locator = detail.get("locator_evidence")
        if isinstance(locator, Mapping) and locator.get("state") == "changed":
            reasons.add("bound-locator-changed")

        declared = detail.get("declared_dependencies")
        if isinstance(declared, Mapping) and declared.get("state") == "affected":
            reasons.add("declared-dependency-changed")

        definition = detail.get("definition")
        if isinstance(definition, Mapping) and definition.get("state") == "changed":
            reasons.add("binding-definition-changed")
        return reasons

    @staticmethod
    def _relationship_binding_impact_reasons(
        detail: Mapping[str, object],
    ) -> set[str]:
        relationships = detail.get("relationship_evidence")
        if not isinstance(relationships, Mapping):
            return set()

        reasons: set[str] = set()
        facts = relationships.get("facts")
        if isinstance(facts, Mapping) and facts.get("state") == "changed":
            reasons.add("relationship-evidence-changed")

        locators = relationships.get("locators")
        if isinstance(locators, Mapping) and locators.get("state") == "changed":
            reasons.add("relationship-locator-changed")

        observation = relationships.get("observation")
        if (
            isinstance(observation, Mapping)
            and observation.get("changed") is True
            and relationships.get("comparability")
            == "observation-configuration-changed"
        ):
            reasons.add("relationship-observation-config-changed")
        return reasons

    @classmethod
    def _binding_impact_reasons(
        cls,
        detail: Mapping[str, object],
    ) -> set[str]:
        return cls._direct_binding_impact_reasons(
            detail
        ) | cls._relationship_binding_impact_reasons(detail)

    @classmethod
    def _binding_impacts(
        cls,
        packet: Mapping[str, object],
        changed_paths: set[str],
        binding_delta: Mapping[str, object] | None,
    ) -> list[dict[str, object]]:
        changed_bindings = cls._changed_binding_index(binding_delta)
        result: list[dict[str, object]] = []
        for binding in cls._binding_rows(packet):
            binding_id = str(binding.get("binding_id") or "")
            evidence_paths, dependency_paths = cls._binding_paths(binding)
            detail = changed_bindings.get(binding_id)
            reasons = (
                cls._binding_impact_reasons(detail) if detail is not None else set()
            )
            if detail is None and changed_paths & evidence_paths:
                reasons.add("bound-member-precision-unknown")
            if (
                changed_paths & dependency_paths
                and "declared-dependency-changed" not in reasons
            ):
                reasons.add("declared-dependency-path-changed")
            if reasons:
                result.append(
                    {
                        "binding_id": binding_id,
                        "reasons": sorted(reasons),
                    }
                )
        return sorted(result, key=lambda row: str(row["binding_id"]))

    @staticmethod
    def _change_set(
        changed_paths: Sequence[str] | None,
        change_set_complete: bool | None,
        repository_observation: RepositoryObservation | None,
    ) -> tuple[list[str], bool, dict[str, object]]:
        if repository_observation is not None:
            observed = sorted(
                {
                    normalize_relative_path(path, allow_root=False)
                    for path in repository_observation.dirty_paths
                }
            )
            supplied = (
                sorted(
                    {
                        normalize_relative_path(path, allow_root=False)
                        for path in changed_paths
                    }
                )
                if changed_paths is not None
                else observed
            )
            if supplied != observed:
                raise ValueError(
                    "changed_paths must match repository_observation.dirty_paths"
                )
            complete = bool(
                repository_observation.paths_complete
                and repository_observation.dirty_path_count == len(observed)
                and repository_observation.state is not ObservationState.UNKNOWN
            )
            if (
                change_set_complete is not None
                and bool(change_set_complete) != complete
            ):
                raise ValueError(
                    "change_set_complete conflicts with repository_observation"
                )
            return (
                observed,
                complete,
                {
                    "source": "repository-observer",
                    "state": repository_observation.state.value,
                    "generation": repository_observation.generation,
                    "paths_complete": repository_observation.paths_complete,
                    "dirty_path_count": repository_observation.dirty_path_count,
                    **(
                        {"reason": repository_observation.reason}
                        if repository_observation.reason
                        else {}
                    ),
                },
            )

        if changed_paths is None:
            raise ValueError(
                "changed_paths is required when repository_observation is not supplied"
            )
        changed = sorted(
            {normalize_relative_path(path, allow_root=False) for path in changed_paths}
        )
        complete = bool(change_set_complete)
        return (
            changed,
            complete,
            {
                "source": "caller-asserted",
                "paths_complete": complete,
            },
        )

    @staticmethod
    def _validate_coverage_packets(
        bindings_packet: Mapping[str, object],
        binding_delta: Mapping[str, object] | None,
    ) -> None:
        if bindings_packet.get("schema") != "hashmarks.repository-evidence-bindings.v1":
            raise ValueError("bindings_packet must be repository evidence bindings")
        if (
            binding_delta is not None
            and binding_delta.get("schema")
            != "hashmarks.repository-evidence-binding-delta.v1"
        ):
            raise ValueError(
                "binding_delta must be a repository evidence binding delta"
            )
        if binding_delta is None:
            return
        identities = binding_delta.get("bindings_identity")
        after_identity = (
            identities.get("after") if isinstance(identities, Mapping) else None
        )
        if after_identity != bindings_packet.get("bindings_identity"):
            raise ValueError("binding_delta after identity must match bindings_packet")

    @staticmethod
    def _delta_evidence_paths(
        binding: Mapping[str, object],
        field_name: str,
    ) -> set[str]:
        evidence = binding.get(field_name)
        changes = evidence.get("changes") if isinstance(evidence, Mapping) else None
        if not isinstance(changes, list):
            return set()
        result: set[str] = set()
        for change in changes:
            if not isinstance(change, Mapping):
                continue
            locator = change.get("evidence")
            if isinstance(locator, list) and locator:
                result.add(str(locator[0]))
        return result

    @classmethod
    def _coverage_binding_changes(
        cls,
        binding_delta: Mapping[str, object] | None,
    ) -> _CoverageBindingChanges:
        changes = _CoverageBindingChanges()
        for binding in cls._changed_binding_index(binding_delta).values():
            changes.direct_changed.update(
                cls._delta_evidence_paths(binding, "direct_evidence")
            )
            changes.locator_changed.update(
                cls._delta_evidence_paths(binding, "locator_evidence")
            )

            member = binding.get("member_evidence")
            member_changes = (
                member.get("changes") if isinstance(member, Mapping) else None
            )
            if not isinstance(member_changes, list):
                continue
            for change in member_changes:
                if not isinstance(change, Mapping):
                    continue
                locator = change.get("evidence")
                if not isinstance(locator, list) or not locator:
                    continue
                path = str(locator[0])
                target = {
                    "added": changes.member_added,
                    "removed": changes.member_removed,
                    "state-changed": changes.member_state_changed,
                }.get(str(change.get("state") or "changed"), changes.member_only)
                target.add(path)
        return changes

    @classmethod
    def _coverage_classification(
        cls,
        bindings_packet: Mapping[str, object],
        changed_set: set[str],
        *,
        complete: bool,
        binding_delta: Mapping[str, object] | None,
    ) -> dict[str, object]:
        evidence_paths, dependency_paths = cls._coverage_binding_paths(bindings_packet)
        bound_members = changed_set & evidence_paths
        declared_dependencies_changed = (changed_set & dependency_paths) - bound_members
        outside = changed_set - evidence_paths - dependency_paths
        changes = cls._coverage_binding_changes(binding_delta).bound_to(bound_members)
        precision_unknown = bound_members - changes.classified_paths()
        return {
            "changed_inside_bound_evidence": sorted(changes.direct_changed),
            "changed_elsewhere_in_bound_member": sorted(changes.member_only),
            "bound_members_added": sorted(changes.member_added),
            "bound_members_removed": sorted(changes.member_removed),
            "bound_member_observation_state_changed": sorted(
                changes.member_state_changed
            ),
            "bound_locator_changed": sorted(changes.locator_changed),
            "bound_member_precision_unknown": sorted(precision_unknown),
            "declared_dependencies_changed": sorted(declared_dependencies_changed),
            "outside_declared_bindings": sorted(outside) if complete else [],
            "outside_declared_bindings_candidates": (
                sorted(outside) if not complete else []
            ),
        }

    def repository_evidence_coverage(
        self,
        bindings_packet: Mapping[str, object],
        *,
        changed_paths: Sequence[str] | None = None,
        change_set_complete: bool | None = None,
        repository_observation: RepositoryObservation | None = None,
        binding_delta: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        """Classify changes while preserving change-set authority and precision."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._validate_coverage_packets(bindings_packet, binding_delta)
        changed, complete, change_set = self._change_set(
            changed_paths, change_set_complete, repository_observation
        )
        changed_set = set(changed)
        classification = self._coverage_classification(
            bindings_packet,
            changed_set,
            complete=complete,
            binding_delta=binding_delta,
        )
        payload: dict[str, object] = {
            "schema": "hashmarks.repository-evidence-coverage.v1",
            "changed_paths": changed,
            "change_set": change_set,
            "classification": classification,
            "binding_impacts": self._binding_impacts(
                bindings_packet, changed_set, binding_delta
            ),
            "precision": {
                "bound_range": "known" if binding_delta is not None else "unknown",
                "reason": (
                    "binding-delta-supplied"
                    if binding_delta is not None
                    else "path-change-set-cannot-prove-range-impact"
                ),
            },
            "coverage": {
                "state": "complete" if complete else "incomplete",
                "outside_classification": "known" if complete else "unknown",
                "source": str(change_set["source"]),
                "reason": (
                    "complete-change-set"
                    if complete
                    else "change-set-completeness-not-proven"
                ),
            },
            "authority": "repository-intelligence-only",
            "execution_effect": "none",
        }
        payload["coverage_identity"] = "sha256:" + self._packet_digest(
            "hashmarks.repository-evidence-coverage.v1", payload
        )
        return payload
