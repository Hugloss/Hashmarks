"""Task-local composition of repository observations, never a solution executor."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .decision_session import ReadScopeOwner
from .evidence_packet import TaskEvidencePacketMixin
from .relationships import TaskRelationshipsMixin
from .task_action_projection import TaskActionProjectionMixin
from .task_action_types import _TaskActionReuse, _TaskObservationReuse
from .task_entry_points import TaskEntryPointsMixin
from .task_freshness import TaskFreshnessMixin
from .task_receipts import TaskReceiptsMixin
from .task_verification import TaskVerificationMixin

if TYPE_CHECKING:
    from .decision_session import DecisionScope
    from .evidence_graph import RepositoryRelationships
    from .evidence_verification import RepositoryVerification
    from .find_engine import RepositorySearch
    from .ownership_graph import RepositoryOwnership
    from .repository_context import RepositoryContext


class RepositoryTasks(
    TaskEvidencePacketMixin,
    TaskFreshnessMixin,
    TaskActionProjectionMixin,
    TaskEntryPointsMixin,
    TaskVerificationMixin,
    TaskReceiptsMixin,
    TaskRelationshipsMixin,
    ReadScopeOwner,
):
    """Compose one task observation and supplied ownership/verification values."""

    def __init__(
        self,
        search: RepositorySearch,
        ownership: RepositoryOwnership,
        verification: RepositoryVerification,
        relationships: RepositoryRelationships,
        context: RepositoryContext,
    ) -> None:
        self.source = source = search.source
        self.context = context
        self.structure = ownership.structure
        self.search = search
        self.ownership = ownership
        self.verification = verification
        self.repository_relationships = relationships
        self.imports = ownership.imports
        self.files = source.files
        self.index = source.index
        self.store = source.store
        self.workspace = source.workspace
        self._task_authority_paths_cache: dict[
            tuple[int, str, int], tuple[str, ...]
        ] = {}
        self._task_recent_authority_paths: dict[tuple[str, int], tuple[str, ...]] = {}
        self._task_action_reuse = _TaskActionReuse()
        self._task_observation_reuse = _TaskObservationReuse()

    @property
    def reads(self) -> DecisionScope:
        return self.source.reads
