from __future__ import annotations

from typing import TYPE_CHECKING, cast

from .change_impact import ChangeImpactOptions

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from .engine import CodeMap

_QUERY_SURFACES = (
    "change-intelligence",
    "verification-explanation",
    "freshness",
    "snapshot",
    "profile",
    "delta",
    "cross-repository",
    "economics",
)


class RepositoryIntelligenceQueryMixin:
    """Thin deterministic facade over existing repository-intelligence producers.

    This mixin owns no repository fact, ranking, freshness state, or historical
    state. It only normalizes one bounded query contract and delegates to the
    existing producer that already owns the requested semantics.
    """

    def repository_intelligence_query(
        self,
        surface: str,
        task: str,
        changed_paths: Sequence[str | Path] = (),
        *,
        member_path: str | None = None,
        profile: str = "compact",
        negative_members: Sequence[str | Path] = (),
        previous_map: Mapping[str, object] | None = None,
        previous_snapshot: Mapping[str, object] | None = None,
        limit: int = 20,
        per_role: int = 3,
        impact_limit_per_surface: int = 4,
        max_depth: int = 3,
        project_impact_limit: int = 12,
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if surface not in _QUERY_SURFACES:
            raise ValueError(f"surface must be one of {list(_QUERY_SURFACES)}")
        if not task.strip():
            raise ValueError("task must not be empty")

        if surface == "verification-explanation":
            result = self.explain_verification_selection(
                task,
                member_path,
                limit=limit,
                candidate_limit=16,
            )
        else:
            if not changed_paths:
                raise ValueError(
                    f"changed_paths must not be empty for surface {surface}"
                )
            common = {
                "limit": limit,
                "per_role": per_role,
                "impact_limit_per_surface": impact_limit_per_surface,
                "max_depth": max_depth,
            }
            if surface == "change-intelligence":
                result = self.change_intelligence_brief(task, changed_paths, **common)
            elif surface == "freshness":
                result = self.evidence_freshness_map(
                    task,
                    changed_paths,
                    negative_members=negative_members,
                    previous_map=previous_map,
                    **common,
                )
            elif surface == "snapshot":
                result = self.repository_intelligence_snapshot(
                    task, changed_paths, **common
                )
            elif surface == "profile":
                result = self.repository_intelligence_profile(
                    task,
                    changed_paths,
                    profile=profile,
                    **common,
                )
            elif surface == "economics":
                result = self.intelligence_economics_receipt(
                    task,
                    changed_paths,
                    previous_snapshot=previous_snapshot,
                    **common,
                )
            elif surface == "delta":
                if previous_snapshot is None:
                    raise ValueError("previous_snapshot is required for surface delta")
                result = self.repository_intelligence_delta(
                    task,
                    changed_paths,
                    previous_snapshot=previous_snapshot,
                    **common,
                )
            else:
                result = self.cross_repository_evidence_packet(
                    task,
                    changed_paths,
                    limit=limit,
                    per_role=per_role,
                    options=ChangeImpactOptions(
                        impact_limit_per_surface=impact_limit_per_surface,
                        max_depth=max_depth,
                        project_impact_limit=project_impact_limit,
                        project_impact_encoding="compact",
                    ),
                )

        producer_schema = str(result.get("schema") or "")
        envelope: dict[str, object] = {
            "schema": "hashmarks.repository-intelligence-query.v1",
            "surface": surface,
            "producer_schema": producer_schema,
            "result": result,
            "storage": "derived-not-persisted",
            "authority": "repository-intelligence-only",
            "execution_effect": "none",
        }
        envelope["query_identity"] = "sha256:" + self._packet_digest(
            "hashmarks.repository-intelligence-query.v1",
            envelope,
        )
        return envelope
