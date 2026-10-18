"""Caller-selected repository changes and generation-bound endpoint observations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from .change_impact import _ImpactOwnerReuse
from .change_intelligence import ChangeIntelligenceMixin
from .decision_session import decision_scoped
from .freshness_map import EvidenceFreshnessMapMixin
from .post_change import PostChangeMixin
from .repository_delta import RepositoryDeltaMixin, _SnapshotReuse

if TYPE_CHECKING:
    from .decision_session import DecisionScope
    from .evidence_graph import RepositoryRelationships
    from .repository_tasks import RepositoryTasks


class RepositoryChanges(
    RepositoryDeltaMixin,
    ChangeIntelligenceMixin,
    EvidenceFreshnessMapMixin,
    PostChangeMixin,
):
    """Observe change impact, snapshots and freshness without consumer policy.

    Snapshot and impact reuse belongs to this owner and one exact read scope.
    Callers select changed paths and comparison endpoints; this component does
    not choose patches, execute verification or control repository lifecycle.
    """

    def __init__(
        self, tasks: RepositoryTasks, relationships: RepositoryRelationships
    ) -> None:
        if relationships.reads is not tasks.reads:
            raise ValueError("Change inputs must share one repository read scope")
        self.tasks = tasks
        self.source = tasks.source
        self.relationships = relationships
        self.native = relationships.native
        self.ownership = tasks.ownership
        self.verification = tasks.verification
        self.index = self.source.index
        self.store = self.source.store
        self.workspace = self.source.workspace
        self._snapshot_reuse = _SnapshotReuse()
        self._impact_owner_reuse = _ImpactOwnerReuse()

    @property
    def reads(self) -> DecisionScope:
        return self.source.reads

    @staticmethod
    def _impact_generation(impact: Mapping[str, object]) -> int:
        generation = impact.get("generation")
        if type(generation) is not int:
            raise RuntimeError("change impact has no qualified repository generation")
        return generation

    @staticmethod
    def _repository_generation(packet: Mapping[str, object]) -> int:
        repository = packet.get("repository")
        if not isinstance(repository, Mapping):
            raise RuntimeError("change observation has no repository binding")
        generation = repository.get("codemap_generation")
        if type(generation) is not int:
            raise RuntimeError(
                "change observation has no qualified repository generation"
            )
        return generation

    @decision_scoped
    def impact(
        self, query: str, *, max_depth: int = 4, limit_per_surface: int = 20
    ) -> dict[str, object]:
        return dict(
            self.tasks._observe_change_relationships(
                query, max_depth=max_depth, limit_per_surface=limit_per_surface
            )
        )
