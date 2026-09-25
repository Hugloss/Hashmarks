from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from hashmarks.paths import normalize_relative_path

from .change_impact import ChangeImpactOptions
from .decision_session import diagnostic_producer
from .evidence_freshness import freshness_state
from .project_impact_codec import expand_project_impact

if TYPE_CHECKING:
    from pathlib import Path

    from .engine import CodeMap


@dataclass(frozen=True, slots=True)
class _FreshnessScope:
    repository_identity: str
    task_identity: str
    continuity_state: str


@dataclass(frozen=True, slots=True)
class FreshnessMapOptions:
    """Bounds shared by one evidence-freshness projection."""

    limit: int = 20
    per_role: int = 3
    impact_limit_per_surface: int = 4
    max_depth: int = 3


class EvidenceFreshnessMapMixin:
    """Derived freshness projection over existing repository-intelligence facts.

    This surface owns no freshness state. It samples the existing generation,
    revision, verification, ownership, impact, and project-provenance authorities
    and gives consumers stable evidence identities that can be compared across
    admitted repository states.
    """

    def _freshness_identity(self, kind: str, payload: object) -> str:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        return "sha256:" + self._packet_digest(
            f"hashmarks.evidence-freshness.{kind}.v1",
            payload,
        )

    @staticmethod
    def _ownership_projection(action: Mapping[str, object]) -> dict[str, object] | None:
        ownership = action.get("ownership_resolution")
        if not isinstance(ownership, Mapping):
            return None
        return {
            key: ownership[key]
            for key in ("status", "selected", "via", "owner_path")
            if key in ownership
        }

    def _freshness_changed_revisions(
        self,
        changed_rows: Sequence[object],
    ) -> list[dict[str, object]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        paths = [
            str(row.get("path") or "")
            for row in changed_rows
            if isinstance(row, Mapping) and row.get("path")
        ]
        revisions: list[dict[str, object]] = []
        for path in paths:
            file_row = self._session_file_row(path)
            revisions.append(
                {
                    "path": path,
                    "revision": (
                        None
                        if file_row is None or not file_row["file_digest"]
                        else str(file_row["file_digest"])
                    ),
                }
            )
        return revisions

    def _prior_entries(
        self,
        previous_map: Mapping[str, object] | None,
        *,
        expected_task_identity: str,
    ) -> list[Mapping[str, object]]:
        if previous_map is None:
            return []
        if not isinstance(previous_map, Mapping):
            raise ValueError("previous_map must be an object")
        if previous_map.get("schema") != "hashmarks.evidence-freshness-map.v1":
            raise ValueError(
                "previous_map must be a hashmarks.evidence-freshness-map.v1 packet"
            )
        repository = previous_map.get("repository")
        if not isinstance(repository, Mapping):
            raise ValueError("previous_map.repository must be an object")
        repository_identity = str(repository.get("repository_identity") or "")
        if repository_identity != self._repository_packet_identity():
            raise ValueError("previous_map repository-mismatch")
        task_identity = str(previous_map.get("task_identity") or "")
        if task_identity != expected_task_identity:
            raise ValueError("previous_map task-mismatch")
        entries = previous_map.get("entries")
        if not isinstance(entries, list) or any(
            not isinstance(row, Mapping) for row in entries
        ):
            raise ValueError("previous_map.entries must be a list of objects")
        identity = previous_map.get("freshness_map_identity")
        expected_identity = self._freshness_identity(
            "map",
            {
                "repository_identity": repository_identity,
                "task_identity": task_identity,
                "entries": entries,
            },
        )
        if not isinstance(identity, str) or identity != expected_identity:
            raise ValueError("previous_map freshness identity mismatch")
        return list(entries)

    @staticmethod
    def _prior_key(row: Mapping[str, object]) -> tuple[str, str | None]:
        kind = str(row.get("kind") or "")
        member = (
            str(row.get("member"))
            if kind == "negative-verification-evidence"
            and row.get("member") is not None
            else None
        )
        return kind, member

    def _ownership_freshness_entry(
        self,
        scope: _FreshnessScope,
        ownership: dict[str, object] | None,
    ) -> dict[str, object]:
        fact = {
            "repository_identity": scope.repository_identity,
            "task_identity": scope.task_identity,
            "ownership": ownership,
        }
        return {
            "kind": "ownership",
            "state": scope.continuity_state,
            "evidence_identity": self._freshness_identity("ownership", fact),
            "facts": ownership,
        }

    def _impact_freshness_entry(
        self,
        scope: _FreshnessScope,
        impact: Mapping[str, object],
    ) -> dict[str, object]:
        changed = impact.get("changed")
        revisions = self._freshness_changed_revisions(
            changed if isinstance(changed, list) else []
        )
        raw_surfaces = impact.get("surfaces")
        surfaces = raw_surfaces if isinstance(raw_surfaces, Mapping) else {}
        raw_bounds = impact.get("bounds")
        bounds = raw_bounds if isinstance(raw_bounds, Mapping) else {}
        fact = {
            "repository_identity": scope.repository_identity,
            "task_identity": scope.task_identity,
            "changed_revisions": revisions,
            "surfaces": surfaces,
            "bounds": dict(bounds),
        }
        return {
            "kind": "impact",
            "state": scope.continuity_state,
            "evidence_identity": self._freshness_identity("impact", fact),
            "changed_revisions": revisions,
        }

    def _verification_freshness_entry(
        self,
        scope: _FreshnessScope,
        selected_member: str,
        selected_explanation: Mapping[str, object],
    ) -> dict[str, object]:
        fact = {
            "repository_identity": scope.repository_identity,
            "task_identity": scope.task_identity,
            "member": selected_member or None,
            "reason": selected_explanation.get("reason"),
            "facts": selected_explanation.get("facts") or [],
        }
        return {
            "kind": "verification-membership",
            "state": scope.continuity_state,
            "evidence_identity": self._freshness_identity(
                "verification-membership", fact
            ),
            "member": selected_member or None,
            "reason": selected_explanation.get("reason"),
        }

    def _negative_verification_freshness_entry(
        self,
        scope: _FreshnessScope,
        task: str,
        raw_member: str | Path,
        limit: int,
    ) -> dict[str, object]:
        member = normalize_relative_path(raw_member, allow_root=False)
        explanation = self.explain_verification_selection(
            task,
            member,
            limit=limit,
            candidate_limit=16,
        )
        status = str(explanation.get("status") or "insufficient-evidence")
        if status == "selected":
            state = "stale"
            reason = "member-is-selected"
        elif status == "insufficient-evidence":
            state = "unknown" if scope.continuity_state != "stale" else "stale"
            reason = str(explanation.get("reason") or "insufficient-evidence")
        else:
            state = scope.continuity_state
            reason = str(explanation.get("reason") or "not-selected")
        fact = {
            "repository_identity": scope.repository_identity,
            "task_identity": scope.task_identity,
            "member": member,
            "status": status,
            "reason": reason,
            "facts": explanation.get("facts") or [],
        }
        return {
            "kind": "negative-verification-evidence",
            "member": member,
            "state": state,
            "evidence_identity": self._freshness_identity(
                "negative-verification", fact
            ),
            "reason": reason,
        }

    def _cross_repository_freshness_entry(
        self,
        scope: _FreshnessScope,
        project_impact: object,
    ) -> dict[str, object] | None:
        if not isinstance(project_impact, Mapping):
            return None
        expanded = expand_project_impact(project_impact)
        producers = sorted(
            {
                str(edge.get("producer") or "")
                for edge in expanded.get("edges", [])
                if isinstance(edge, Mapping) and edge.get("producer")
            }
        )
        dependencies: list[dict[str, object]] = []
        dependency_state = "current"
        for producer in producers:
            fresh, reason = self._evidence_fresh("project", producer)
            if not fresh:
                dependency_state = "stale"
            dependencies.append(
                {
                    "producer": producer,
                    "state": "current" if fresh else "stale",
                    **({"reason": reason} if reason else {}),
                }
            )
        fact = {
            "repository_identity": scope.repository_identity,
            "task_identity": scope.task_identity,
            "project_impact": dict(project_impact),
            "dependencies": dependencies,
        }
        return {
            "kind": "cross-repository",
            "state": "dependent" if dependency_state == "current" else dependency_state,
            "dependency_state": dependency_state,
            "evidence_identity": self._freshness_identity("cross-repository", fact),
            "dependencies": dependencies,
        }

    def _prior_freshness_rows(
        self,
        entries: Sequence[Mapping[str, object]],
        previous_map: Mapping[str, object] | None,
        *,
        task_identity: str,
    ) -> list[dict[str, object]]:
        current_by_key = {self._prior_key(row): row for row in entries}
        prior: list[dict[str, object]] = []
        for old in self._prior_entries(
            previous_map,
            expected_task_identity=task_identity,
        ):
            key = self._prior_key(old)
            current = current_by_key.get(key)
            old_identity = str(old.get("evidence_identity") or "")
            current_identity = (
                str(current.get("evidence_identity") or "") if current else ""
            )
            if current is None:
                if key[0] in {
                    "ownership",
                    "impact",
                    "verification-membership",
                    "cross-repository",
                }:
                    state = "stale"
                    reason = "evidence-no-longer-supported-by-current-map"
                else:
                    state = "unknown"
                    reason = "evidence-kind-not-requested-in-current-map"
            elif old_identity and old_identity == current_identity:
                state = "current"
                reason = "evidence-identity-unchanged"
            else:
                state = "stale"
                reason = "evidence-identity-changed"
            prior.append(
                {
                    "kind": key[0],
                    **({"member": key[1]} if key[1] is not None else {}),
                    "evidence_identity": old_identity or None,
                    "state": state,
                    "reason": reason,
                }
            )
        return prior

    @diagnostic_producer
    def evidence_freshness_map(
        self,
        task: str,
        changed_paths: Sequence[str | Path],
        *,
        negative_members: Sequence[str | Path] = (),
        previous_map: Mapping[str, object] | None = None,
        options: FreshnessMapOptions = FreshnessMapOptions(),
    ) -> dict[str, object]:
        """Return current and prior freshness without persisting duplicate truth."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        impact = self.task_change_impact(
            task,
            changed_paths,
            limit=options.limit,
            per_role=options.per_role,
            options=ChangeImpactOptions(
                impact_limit_per_surface=options.impact_limit_per_surface,
                max_depth=options.max_depth,
                project_impact_encoding="compact",
            ),
        )
        action = self.task_action_map(
            task,
            limit=options.limit,
            per_role=options.per_role,
        )
        verify = (
            action.get("verify") if isinstance(action.get("verify"), Mapping) else None
        )
        selected_member = str(verify.get("path") or "") if verify else ""
        selected_explanation = self.explain_verification_selection(
            task,
            selected_member or None,
            limit=options.limit,
            candidate_limit=16,
        )
        generation, identity_generation, stale = self._generation_status()
        scope = _FreshnessScope(
            repository_identity=self._repository_packet_identity(),
            task_identity=self._packet_digest("hashmarks.task.v1", {"task": task}),
            continuity_state=freshness_state(stale),
        )

        entries = [
            self._ownership_freshness_entry(
                scope,
                self._ownership_projection(action),
            ),
            self._impact_freshness_entry(scope, impact),
            self._verification_freshness_entry(
                scope,
                selected_member,
                selected_explanation,
            ),
        ]
        entries.extend(
            self._negative_verification_freshness_entry(
                scope,
                task,
                raw_member,
                options.limit,
            )
            for raw_member in negative_members
        )

        cross_repository = self._cross_repository_freshness_entry(
            scope, impact.get("project_impact")
        )
        if cross_repository is not None:
            entries.append(cross_repository)

        prior = self._prior_freshness_rows(
            entries,
            previous_map,
            task_identity=scope.task_identity,
        )
        payload: dict[str, object] = {
            "schema": "hashmarks.evidence-freshness-map.v1",
            "repository": {
                "repository_identity": scope.repository_identity,
                "codemap_generation": generation,
                "identity_generation": identity_generation,
                "continuity": scope.continuity_state,
            },
            "task_identity": scope.task_identity,
            "entries": entries,
            "authority": "repository-intelligence-only",
            "storage": "derived-not-persisted",
            "execution_effect": "none",
        }
        if prior:
            payload["prior"] = prior
        payload["freshness_map_identity"] = self._freshness_identity(
            "map",
            {
                "repository_identity": scope.repository_identity,
                "task_identity": scope.task_identity,
                "entries": entries,
            },
        )
        return payload
