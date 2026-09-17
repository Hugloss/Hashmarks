from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

from hashmarks.paths import normalize_relative_path

from .decision_session import diagnostic_producer
from .project_impact_codec import expand_project_impact

if TYPE_CHECKING:
    from pathlib import Path

    from .engine import CodeMap


class EvidenceFreshnessMapMixin:
    """Derived freshness projection over existing repository-intelligence facts.

    This surface owns no freshness state. It samples the existing generation,
    revision, verification, ownership, impact, and project-provenance authorities
    and gives consumers stable evidence identities that can be compared across
    admitted repository states.
    """

    @staticmethod
    def _freshness_state(stale: bool | None) -> str:
        if stale is True:
            return "invalidated"
        if stale is False:
            return "current"
        return "unknown"

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

    @staticmethod
    def _prior_entries(
        previous_map: Mapping[str, object] | None,
    ) -> list[Mapping[str, object]]:
        if not isinstance(previous_map, Mapping):
            return []
        entries = previous_map.get("entries")
        if not isinstance(entries, list):
            return []
        return [row for row in entries if isinstance(row, Mapping)]

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

    @diagnostic_producer
    def evidence_freshness_map(
        self,
        task: str,
        changed_paths: Sequence[str | Path],
        *,
        negative_members: Sequence[str | Path] = (),
        previous_map: Mapping[str, object] | None = None,
        limit: int = 20,
        per_role: int = 3,
        impact_limit_per_surface: int = 4,
        max_depth: int = 3,
    ) -> dict[str, object]:
        """Return current and prior freshness without persisting duplicate truth."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        impact = self.task_change_impact(
            task,
            changed_paths,
            limit=limit,
            per_role=per_role,
            impact_limit_per_surface=impact_limit_per_surface,
            max_depth=max_depth,
            project_impact_encoding="compact",
        )
        action = self.task_action_map(task, limit=limit, per_role=per_role)
        verify = (
            action.get("verify") if isinstance(action.get("verify"), Mapping) else None
        )
        selected_member = str(verify.get("path") or "") if verify else ""
        selected_explanation = self.explain_verification_selection(
            task,
            selected_member or None,
            limit=limit,
            candidate_limit=16,
        )
        generation, identity_generation, stale = self._generation_status()
        continuity_state = self._freshness_state(stale)
        repository_identity = self._repository_packet_identity()
        task_identity = self._packet_digest("hashmarks.task.v1", {"task": task})

        ownership = self._ownership_projection(action)
        changed_rows = (
            impact.get("changed") if isinstance(impact.get("changed"), list) else []
        )
        revisions = self._freshness_changed_revisions(changed_rows)
        surfaces = (
            impact.get("surfaces")
            if isinstance(impact.get("surfaces"), Mapping)
            else {}
        )

        entries: list[dict[str, object]] = []

        ownership_fact = {
            "repository_identity": repository_identity,
            "task_identity": task_identity,
            "ownership": ownership,
        }
        entries.append(
            {
                "kind": "ownership",
                "state": continuity_state,
                "evidence_identity": self._freshness_identity(
                    "ownership", ownership_fact
                ),
                "facts": ownership,
            }
        )

        impact_fact = {
            "repository_identity": repository_identity,
            "task_identity": task_identity,
            "changed_revisions": revisions,
            "surfaces": surfaces,
            "bounds": dict(impact.get("bounds") or {}),
        }
        entries.append(
            {
                "kind": "impact",
                "state": continuity_state,
                "evidence_identity": self._freshness_identity("impact", impact_fact),
                "changed_revisions": revisions,
            }
        )

        verification_fact = {
            "repository_identity": repository_identity,
            "task_identity": task_identity,
            "member": selected_member or None,
            "reason": selected_explanation.get("reason"),
            "facts": selected_explanation.get("facts") or [],
        }
        entries.append(
            {
                "kind": "verification-membership",
                "state": continuity_state,
                "evidence_identity": self._freshness_identity(
                    "verification-membership", verification_fact
                ),
                "member": selected_member or None,
                "reason": selected_explanation.get("reason"),
            }
        )

        for raw_member in negative_members:
            member = normalize_relative_path(raw_member, allow_root=False)
            explanation = self.explain_verification_selection(
                task,
                member,
                limit=limit,
                candidate_limit=16,
            )
            status = str(explanation.get("status") or "insufficient-evidence")
            if status == "selected":
                state = "invalidated"
                reason = "member-is-selected"
            elif status == "insufficient-evidence":
                state = (
                    "unknown" if continuity_state != "invalidated" else "invalidated"
                )
                reason = str(explanation.get("reason") or "insufficient-evidence")
            else:
                state = continuity_state
                reason = str(explanation.get("reason") or "not-selected")
            negative_fact = {
                "repository_identity": repository_identity,
                "task_identity": task_identity,
                "member": member,
                "status": status,
                "reason": reason,
                "facts": explanation.get("facts") or [],
            }
            entries.append(
                {
                    "kind": "negative-verification-evidence",
                    "member": member,
                    "state": state,
                    "evidence_identity": self._freshness_identity(
                        "negative-verification", negative_fact
                    ),
                    "reason": reason,
                }
            )

        project_impact = impact.get("project_impact")
        if isinstance(project_impact, Mapping):
            expanded = expand_project_impact(project_impact)
            producers = sorted(
                {
                    str(edge.get("producer") or "")
                    for edge in expanded.get("edges", [])
                    if isinstance(edge, Mapping) and edge.get("producer")
                }
            )
            dependency_rows: list[dict[str, object]] = []
            dependency_state = "current"
            for producer in producers:
                fresh, reason = self._evidence_fresh("project", producer)
                if not fresh:
                    dependency_state = "invalidated"
                dependency_rows.append(
                    {
                        "producer": producer,
                        "state": "current" if fresh else "invalidated",
                        **({"reason": reason} if reason else {}),
                    }
                )
            project_fact = {
                "repository_identity": repository_identity,
                "task_identity": task_identity,
                "project_impact": dict(project_impact),
                "dependencies": dependency_rows,
            }
            entries.append(
                {
                    "kind": "cross-repository",
                    "state": "dependent"
                    if dependency_state == "current"
                    else dependency_state,
                    "dependency_state": dependency_state,
                    "evidence_identity": self._freshness_identity(
                        "cross-repository", project_fact
                    ),
                    "dependencies": dependency_rows,
                }
            )

        current_by_key = {self._prior_key(row): row for row in entries}
        prior: list[dict[str, object]] = []
        for old in self._prior_entries(previous_map):
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
                    state = "invalidated"
                    reason = "evidence-no-longer-supported-by-current-map"
                else:
                    state = "unknown"
                    reason = "evidence-kind-not-requested-in-current-map"
            elif old_identity and old_identity == current_identity:
                state = "current"
                reason = "evidence-identity-unchanged"
            else:
                state = "invalidated"
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

        payload: dict[str, object] = {
            "schema": "hashmarks.evidence-freshness-map.v1",
            "repository": {
                "repository_identity": repository_identity,
                "codemap_generation": generation,
                "identity_generation": identity_generation,
                "continuity": continuity_state,
            },
            "task_identity": task_identity,
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
                "repository_identity": repository_identity,
                "task_identity": task_identity,
                "entries": entries,
            },
        )
        return payload
