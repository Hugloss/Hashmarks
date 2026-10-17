from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from hashmarks.client import (
    IdentityClient,
    prepare_default_state_dir,
)
from hashmarks.file_store import FileDigestStore
from hashmarks.paths import canonical_host_path

from .change_impact import _ImpactOwnerReuse
from .change_intelligence import ChangeIntelligenceMixin
from .context_cache import ContextCache
from .cross_repository_evidence import CrossRepositoryEvidenceMixin
from .decision_session import (
    DecisionScope,
    ReadScopeOwner,
)
from .dependency_resolution_delta import DependencyResolutionDeltaMixin
from .dependency_resolution_derivation import DependencyResolutionDerivationMixin
from .dependency_resolution_evidence import DependencyResolutionEvidenceMixin
from .evidence_correlation import RepositoryCorrelation
from .evidence_graph import RepositoryRelationships
from .evidence_profiles import EvidenceProfilesMixin
from .evidence_verification import RepositoryVerification
from .find_engine import RepositorySearch
from .freshness_map import EvidenceFreshnessMapMixin
from .import_resolution import RepositoryImports
from .indexing_lifecycle import (
    _MAX_INDEX_BYTES,
    RepositoryIndex,
)
from .intelligence_economics import IntelligenceEconomicsMixin
from .native_evidence import RepositoryNativeEvidence
from .ownership_graph import RepositoryOwnership
from .post_change import PostChangeMixin
from .providers import SourceRangeProvider, TreeSitterRangeProvider
from .query_surface import QuerySurfaceMixin
from .repository_context import RepositoryContext
from .repository_declaration_derivation import RepositoryDeclarationDerivationMixin
from .repository_declaration_discovery import RepositoryDeclarationDiscoveryMixin
from .repository_declarations import RepositoryDeclarationsMixin
from .repository_delta import RepositoryDeltaMixin, _SnapshotReuse
from .repository_evidence_bindings import RepositoryBindings
from .repository_file_discovery import RepositoryFiles
from .repository_index_store import (
    ArtifactStore,
    WorkspaceMapStore,
    default_artifact_db,
)
from .repository_intelligence_query import RepositoryIntelligenceQueryMixin
from .repository_observation import RepositoryObservationSource
from .repository_source import RepositorySource
from .repository_tasks import RepositoryTasks
from .structural_locality import RepositoryStructure

# Generic repository evidence families. These are query-formulation hints only:
# they never name project-specific files, never grant authority, and are emitted
# only when candidate-visible task wording supplies a family cue.  The purpose is
# to bridge ordinary task language to semantically named repository control
# surfaces (for example PRIVACY.md or CI_CD_CONTRACT.md) without globally boosting
# documentation.


@dataclass(frozen=True)
class _CodeMapPaths:
    """Prepared control paths for the composition root, never repository identity."""

    workspace: Path
    state_dir: Path
    artifact_db: Path
    policy_path: Path | None
    internal_state_path: str | None

    @classmethod
    def prepare(
        cls,
        workspace: str | Path,
        state_dir: str | Path | None,
        artifact_db: str | Path | None,
        policy_path: str | Path | None,
    ) -> _CodeMapPaths:
        root = canonical_host_path(workspace)
        state = (
            prepare_default_state_dir(root)
            if state_dir is None
            else canonical_host_path(root / state_dir)
        )
        state.mkdir(parents=True, exist_ok=True)
        try:
            internal = state.relative_to(root).as_posix().strip("/")
        except ValueError:
            internal = None
        artifacts = (
            default_artifact_db(root)
            if artifact_db is None
            else canonical_host_path(artifact_db)
        )
        policy = (
            None if policy_path is None else canonical_host_path(root / policy_path)
        )
        return cls(root, state, artifacts, policy, internal)


class CodeMap(
    DependencyResolutionDeltaMixin,
    DependencyResolutionDerivationMixin,
    DependencyResolutionEvidenceMixin,
    ChangeIntelligenceMixin,
    EvidenceFreshnessMapMixin,
    RepositoryDeltaMixin,
    EvidenceProfilesMixin,
    CrossRepositoryEvidenceMixin,
    RepositoryIntelligenceQueryMixin,
    RepositoryDeclarationDerivationMixin,
    RepositoryDeclarationDiscoveryMixin,
    RepositoryDeclarationsMixin,
    IntelligenceEconomicsMixin,
    PostChangeMixin,
    QuerySurfaceMixin,
    ReadScopeOwner,
):
    """Derived repository-intelligence map.

    This subsystem is intentionally outside the Identity import graph. It may
    scan/parse/index in the background or on demand, but none of those actions
    participate in canonical identity or hot daemon response latency.
    """

    def __init__(
        self,
        workspace: str | Path = ".",
        *,
        state_dir: str | Path | None = None,
        artifact_db: str | Path | None = None,
        policy_path: str | Path | None = None,
        max_index_bytes: int = _MAX_INDEX_BYTES,
        range_provider: SourceRangeProvider | None = None,
    ) -> None:
        paths = _CodeMapPaths.prepare(workspace, state_dir, artifact_db, policy_path)
        self.workspace = paths.workspace
        self.state_dir = paths.state_dir
        store = WorkspaceMapStore(self.state_dir / "codemap.sqlite3")
        store.bind_workspace(
            self.workspace,
            allow_unbound_existing=paths.internal_state_path is not None,
        )
        self.store = store
        self.file_store = FileDigestStore(self.state_dir / "identity.sqlite3")
        # Protocol v3 is the compatibility fence. Reuse one stateless IPC client
        # so repository observations validate daemon compatibility once rather
        # than spending an extra status round-trip on every freshness sample.
        self._observation_source = RepositoryObservationSource(
            IdentityClient(self.workspace, state_dir=self.state_dir, timeout=0.1)
        )
        self.artifacts = ArtifactStore(paths.artifact_db)
        self._files = RepositoryFiles(
            self.workspace,
            internal_state_path=paths.internal_state_path,
            policy_path=paths.policy_path,
        )
        self._context_cache = ContextCache(self.state_dir)
        # Optional structural precision lives entirely in the CodeMap lane.
        # Missing tree-sitter support is expected and never affects Identity.
        range_producer = (
            TreeSitterRangeProvider.auto() if range_provider is None else range_provider
        )
        self._index = RepositoryIndex(
            self.files,
            self.store,
            self.file_store,
            self.artifacts,
            range_provider=range_producer,
            observation_source=self._observation_source,
            max_index_bytes=max_index_bytes,
        )
        self._reads = DecisionScope(self.index, self.store, self._observation_source)
        self._source = RepositorySource(
            self.files, self.index, self.reads, self.store, self.file_store
        )
        self._imports = RepositoryImports(
            self.files, self.source, self.reads, self.store
        )
        self._native = RepositoryNativeEvidence(
            self.files, self.source, self.reads, self.store
        )
        self._relationships = RepositoryRelationships(
            self.source, self.reads, self.store, self._imports, self.native
        )
        self._structure = RepositoryStructure(
            self.source, self._imports, self.native, self.relationships
        )
        self._search = RepositorySearch(self.source, self.native)
        self._context = RepositoryContext(
            self.source, self.search, self.relationships, self._context_cache
        )
        self._ownership = RepositoryOwnership(
            self.source, self._imports, self.structure, self.search
        )
        self._verification = RepositoryVerification(self.source, self._imports)
        self._tasks = RepositoryTasks(
            self.search,
            self.ownership,
            self.verification,
            self.relationships,
            self.context,
        )
        self._bindings = RepositoryBindings(self.source)
        self._correlation = RepositoryCorrelation(self.source, self.bindings)
        self._snapshot_reuse = _SnapshotReuse()
        self._impact_owner_reuse = _ImpactOwnerReuse()

    @property
    def files(self) -> RepositoryFiles:
        return self._files

    @property
    def index(self) -> RepositoryIndex:
        return self._index

    @property
    def reads(self) -> DecisionScope:
        return self._reads

    @property
    def source(self) -> RepositorySource:
        return self._source

    @property
    def native(self) -> RepositoryNativeEvidence:
        return self._native

    @property
    def relationships(self) -> RepositoryRelationships:
        return self._relationships

    @property
    def structure(self) -> RepositoryStructure:
        return self._structure

    @property
    def search(self) -> RepositorySearch:
        return self._search

    @property
    def context(self) -> RepositoryContext:
        return self._context

    @property
    def ownership(self) -> RepositoryOwnership:
        return self._ownership

    @property
    def verification(self) -> RepositoryVerification:
        return self._verification

    @property
    def tasks(self) -> RepositoryTasks:
        return self._tasks

    @property
    def bindings(self) -> RepositoryBindings:
        return self._bindings

    @property
    def correlation(self) -> RepositoryCorrelation:
        return self._correlation

    def __enter__(self) -> CodeMap:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._context_cache.close()
        self.store.close()
        self.artifacts.close()
        self.file_store.close()
