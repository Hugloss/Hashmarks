from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

from .change_impact import ChangeImpactOptions
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

    @staticmethod
    def _cross_project_impact(
        project_impact: object,
    ) -> tuple[
        dict[str, object], list[str], list[dict[str, object]], list[dict[str, object]]
    ]:
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
        return expanded, roots, dependents, relationships

    @staticmethod
    def _cross_freshness_projection(
        freshness: Mapping[str, object],
    ) -> dict[str, object]:
        cross_freshness = next(
            (
                row
                for row in freshness.get("entries", [])
                if isinstance(row, Mapping) and row.get("kind") == "cross-repository"
            ),
            None,
        )
        if isinstance(cross_freshness, Mapping):
            return {
                key: cross_freshness[key]
                for key in (
                    "state",
                    "dependency_state",
                    "evidence_identity",
                    "dependencies",
                )
                if key in cross_freshness
            }
        return {"state": "unknown", "dependency_state": "unknown"}

    @staticmethod
    def _cross_unresolved_evidence(
        project_impact: object,
        expanded: Mapping[str, object],
        ownership_projection: object,
        verification: Mapping[str, object],
    ) -> list[dict[str, object]]:
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
        return unresolved

    @staticmethod
    def _cross_ownership_projection(
        action: Mapping[str, object],
    ) -> dict[str, object] | None:
        ownership = action.get("ownership_resolution")
        if not isinstance(ownership, Mapping):
            return None
        return {
            key: ownership[key]
            for key in ("status", "selected", "via", "owner_path")
            if key in ownership
        }

    def _cross_verification_evidence(
        self, task: str, action: Mapping[str, object], limit: int
    ) -> tuple[dict[str, object], Mapping[str, object]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        verify = action.get("verify")
        verify_row = verify if isinstance(verify, Mapping) else {}
        member = str(verify_row.get("path") or "")
        explanation = self.explain_verification_selection(
            task, member or None, limit=limit, candidate_limit=16
        )
        return {
            "member": member or None,
            "test_symbol": verify_row.get("verification_test_symbol")
            if verify
            else None,
            "status": explanation.get("status"),
            "reason": explanation.get("reason"),
            "explanation_identity": explanation.get("explanation_identity"),
        }, explanation

    @diagnostic_producer
    def cross_repository_evidence_packet(
        self,
        task: str,
        changed_paths: Sequence[str | Path],
        *,
        limit: int = 20,
        per_role: int = 3,
        options: ChangeImpactOptions = ChangeImpactOptions(
            impact_limit_per_surface=4,
            max_depth=3,
            project_impact_limit=12,
            project_impact_encoding="compact",
        ),
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if options.project_impact_limit is None or options.project_impact_limit < 1:
            raise ValueError("project_impact_limit must be >= 1")

        impact = self.task_change_impact(
            task,
            changed_paths,
            limit=limit,
            per_role=per_role,
            options=ChangeImpactOptions(
                impact_limit_per_surface=options.impact_limit_per_surface,
                max_depth=options.max_depth,
                project_impact_limit=options.project_impact_limit,
                project_impact_encoding="compact",
            ),
        )
        action = self.task_action_map(task, limit=limit, per_role=per_role)
        freshness = self.evidence_freshness_map(
            task,
            changed_paths,
            limit=limit,
            per_role=per_role,
            impact_limit_per_surface=options.impact_limit_per_surface,
            max_depth=options.max_depth,
        )

        project_impact = impact.get("project_impact")
        expanded, roots, dependents, relationships = self._cross_project_impact(
            project_impact
        )

        ownership_projection = self._cross_ownership_projection(action)
        verification_projection, verification = self._cross_verification_evidence(
            task, action, limit
        )

        freshness_projection = self._cross_freshness_projection(freshness)
        unresolved = self._cross_unresolved_evidence(
            project_impact, expanded, ownership_projection, verification
        )

        payload: dict[str, object] = {
            "schema": "hashmarks.cross-repository-evidence-packet.v1",
            "source": {
                "repository_identity": (
                    freshness.get("repository", {}).get("repository_identity")
                    if isinstance(freshness.get("repository"), Mapping)
                    else None
                ),
                "project_identities": roots,
                "changed_paths": [
                    str(row.get("path") or "")
                    for row in impact.get("changed", [])
                    if isinstance(row, Mapping) and row.get("path")
                ],
            },
            "task_identity": freshness.get("task_identity"),
            "dependents": dependents,
            "relationships": relationships,
            "affected_ownership_surface": {
                "ownership": ownership_projection,
                "surfaces": {
                    key: list(value)
                    for key, value in (
                        impact.get("surfaces", {}).items()
                        if isinstance(impact.get("surfaces"), Mapping)
                        else ()
                    )
                    if value
                },
            },
            "verification": verification_projection,
            "freshness": freshness_projection,
            "unresolved": unresolved,
            "bounds": {
                "depth": options.max_depth,
                "per_surface": options.impact_limit_per_surface,
                "project_impact": options.project_impact_limit,
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
