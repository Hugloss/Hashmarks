from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

from .decision_session import diagnostic_producer
from .project_impact_codec import expand_project_impact

if TYPE_CHECKING:
    from pathlib import Path

    from .engine import CodeMap


class CrossRepositoryEvidenceMixin:
    """Bounded cross-repository projection over existing Hashmarks authorities.

    This surface does not discover, clone, execute, schedule, or persist external
    repositories.  It composes already-admitted project-impact, ownership,
    verification, and freshness evidence into one consumer packet.
    """

    @diagnostic_producer
    def cross_repository_evidence_packet(
        self,
        task: str,
        changed_paths: Sequence[str | Path],
        *,
        limit: int = 20,
        per_role: int = 3,
        impact_limit_per_surface: int = 4,
        max_depth: int = 3,
        project_impact_limit: int = 12,
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if project_impact_limit < 1:
            raise ValueError("project_impact_limit must be >= 1")

        impact = self.task_change_impact(
            task,
            changed_paths,
            limit=limit,
            per_role=per_role,
            impact_limit_per_surface=impact_limit_per_surface,
            max_depth=max_depth,
            project_impact_limit=project_impact_limit,
            project_impact_encoding="compact",
        )
        action = self.task_action_map(task, limit=limit, per_role=per_role)
        freshness = self.evidence_freshness_map(
            task,
            changed_paths,
            limit=limit,
            per_role=per_role,
            impact_limit_per_surface=impact_limit_per_surface,
            max_depth=max_depth,
        )

        project_impact = impact.get("project_impact")
        expanded = (
            expand_project_impact(project_impact)
            if isinstance(project_impact, Mapping)
            else {"roots": [], "affected": [], "edges": [], "complete": False}
        )
        roots = [str(value) for value in expanded.get("roots", []) if value]
        dependents = [
            {
                "project_identity": str(row.get("project") or ""),
                "depth": int(row.get("depth") or 0),
            }
            for row in expanded.get("affected", [])
            if isinstance(row, Mapping) and row.get("project")
        ]
        relationships = [
            {key: row[key] for key in ("from", "to", "kind", "producer") if key in row}
            for row in expanded.get("edges", [])
            if isinstance(row, Mapping)
        ]

        ownership = action.get("ownership_resolution")
        ownership_projection = None
        if isinstance(ownership, Mapping):
            ownership_projection = {
                key: ownership[key]
                for key in ("status", "selected", "via", "owner_path")
                if key in ownership
            }

        verify = (
            action.get("verify") if isinstance(action.get("verify"), Mapping) else None
        )
        verification_member = str(verify.get("path") or "") if verify else ""
        verification = self.explain_verification_selection(
            task,
            verification_member or None,
            limit=limit,
            candidate_limit=16,
        )

        cross_freshness = next(
            (
                row
                for row in freshness.get("entries", [])
                if isinstance(row, Mapping) and row.get("kind") == "cross-repository"
            ),
            None,
        )
        freshness_projection: dict[str, object]
        if isinstance(cross_freshness, Mapping):
            freshness_projection = {
                key: cross_freshness[key]
                for key in (
                    "state",
                    "dependency_state",
                    "evidence_identity",
                    "dependencies",
                )
                if key in cross_freshness
            }
        else:
            freshness_projection = {"state": "unknown", "dependency_state": "unknown"}

        unresolved: list[dict[str, object]] = []
        if not isinstance(project_impact, Mapping):
            unresolved.append(
                {
                    "reason": "no-cross-repository-impact-supported",
                    "scope": "project-impact",
                }
            )
        elif expanded.get("complete") is not True:
            unresolved.append(
                {
                    "reason": "project-impact-not-complete",
                    "scope": "project-impact",
                }
            )
        if ownership_projection is None:
            unresolved.append({"reason": "ownership-unresolved", "scope": "ownership"})
        if verification.get("status") == "insufficient-evidence":
            unresolved.append(
                {
                    "reason": str(
                        verification.get("reason") or "insufficient-evidence"
                    ),
                    "scope": "verification",
                }
            )

        changed = [
            str(row.get("path") or "")
            for row in impact.get("changed", [])
            if isinstance(row, Mapping) and row.get("path")
        ]
        surfaces = (
            impact.get("surfaces")
            if isinstance(impact.get("surfaces"), Mapping)
            else {}
        )
        repository = (
            freshness.get("repository")
            if isinstance(freshness.get("repository"), Mapping)
            else {}
        )

        payload: dict[str, object] = {
            "schema": "hashmarks.cross-repository-evidence-packet.v1",
            "source": {
                "repository_identity": repository.get("repository_identity"),
                "project_identities": roots,
                "changed_paths": changed,
            },
            "task_identity": freshness.get("task_identity"),
            "dependents": dependents,
            "relationships": relationships,
            "affected_ownership_surface": {
                "ownership": ownership_projection,
                "surfaces": {
                    key: list(value) for key, value in surfaces.items() if value
                },
            },
            "verification": {
                "member": verification_member or None,
                "test_symbol": verify.get("verification_test_symbol")
                if verify
                else None,
                "status": verification.get("status"),
                "reason": verification.get("reason"),
                "explanation_identity": verification.get("explanation_identity"),
            },
            "freshness": freshness_projection,
            "unresolved": unresolved,
            "bounds": {
                "depth": max_depth,
                "per_surface": impact_limit_per_surface,
                "project_impact": project_impact_limit,
            },
            "authority": "repository-intelligence-only",
            "storage": "derived-not-persisted",
            "execution_effect": "none",
        }
        payload["packet_identity"] = "sha256:" + self._packet_digest(
            "hashmarks.cross-repository-evidence-packet.v1",
            payload,
        )
        return payload
