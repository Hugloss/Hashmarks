from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from hashmarks.client import (
    IdentityClient,
    prepare_default_state_dir,
)
from hashmarks.file_store import FileDigestStore
from hashmarks.paths import canonical_host_path

from .context_cache import ContextCache
from .cross_repository_evidence import RepositoryCrossRepository
from .decision_session import (
    DecisionScope,
)
from .evidence_correlation import RepositoryCorrelation
from .evidence_graph import RepositoryRelationships
from .evidence_verification import RepositoryVerification
from .find_engine import RepositorySearch
from .import_resolution import RepositoryImports
from .indexing_lifecycle import (
    _MAX_INDEX_BYTES,
    RepositoryIndex,
)
from .intelligence_economics import RepositoryEconomics
from .native_evidence import RepositoryNativeEvidence
from .ownership_graph import RepositoryOwnership
from .providers import SourceRangeProvider, TreeSitterRangeProvider
from .repository_changes import RepositoryChanges
from .repository_context import RepositoryContext
from .repository_declarations import RepositoryDeclarations
from .repository_dependencies import RepositoryDependencies
from .repository_evidence_bindings import RepositoryBindings
from .repository_file_discovery import RepositoryFiles
from .repository_index_store import (
    ArtifactStore,
    WorkspaceMapStore,
    default_artifact_db,
)
from .repository_intelligence_query import RepositoryViews
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


class CodeMap:
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
        with ExitStack() as resources:
            self._open_resources(paths, resources)
            self._compose_components(range_provider, max_index_bytes)
            self._resources = resources.pop_all()

    def _open_resources(self, paths: _CodeMapPaths, resources: ExitStack) -> None:
        self.workspace = paths.workspace
        self.state_dir = paths.state_dir
        self.store = WorkspaceMapStore(self.state_dir / "codemap.sqlite3")
        resources.callback(self.store.close)
        self.store.bind_workspace(
            self.workspace,
            allow_unbound_existing=paths.internal_state_path is not None,
        )
        self.file_store = FileDigestStore(self.state_dir / "identity.sqlite3")
        resources.callback(self.file_store.close)
        # Protocol v3 is the compatibility fence. Reuse one stateless IPC client
        # so repository observations validate daemon compatibility once rather
        # than spending an extra status round-trip on every freshness sample.
        self._observation_source = RepositoryObservationSource(
            IdentityClient(self.workspace, state_dir=self.state_dir, timeout=0.1)
        )
        self.artifacts = ArtifactStore(paths.artifact_db)
        resources.callback(self.artifacts.close)
        self._files = RepositoryFiles(
            self.workspace,
            internal_state_path=paths.internal_state_path,
            policy_path=paths.policy_path,
        )
        self._context_cache = ContextCache(self.state_dir)
        resources.callback(self._context_cache.close)

    def _compose_components(
        self, range_provider: SourceRangeProvider | None, max_index_bytes: int
    ) -> None:
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
        self._reads = DecisionScope(self.index)
        self._source = RepositorySource(self.index, self.reads)
        self._imports = RepositoryImports(self.source)
        self._native = RepositoryNativeEvidence(self.source)
        self._relationships = RepositoryRelationships(self._imports, self.native)
        self._structure = RepositoryStructure(
            self.source, self._imports, self.native, self.relationships
        )
        self._search = RepositorySearch(self.native)
        self._context = RepositoryContext(
            self.source, self.search, self.relationships, self._context_cache
        )
        self._ownership = RepositoryOwnership(
            self.source, self._imports, self.structure, self.search
        )
        self._verification = RepositoryVerification(self._imports)
        self._bindings = RepositoryBindings(self.source)
        self._declarations = RepositoryDeclarations(self.bindings)
        self._tasks = RepositoryTasks(
            self.search,
            self.ownership,
            self.verification,
            self.relationships,
            self.context,
            declarations=self.declarations,
        )
        self._correlation = RepositoryCorrelation(self.bindings)
        self._dependencies = RepositoryDependencies(
            self.source, self._imports, self.correlation
        )
        self._changes = RepositoryChanges(self.tasks, self.relationships)
        self._cross_repository = RepositoryCrossRepository(self.changes)
        self._economics = RepositoryEconomics(self.changes)
        self._views = RepositoryViews(
            self.changes, self.cross_repository, self.economics, self.structure
        )

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

    @property
    def declarations(self) -> RepositoryDeclarations:
        return self._declarations

    @property
    def dependencies(self) -> RepositoryDependencies:
        return self._dependencies

    @property
    def changes(self) -> RepositoryChanges:
        return self._changes

    @property
    def cross_repository(self) -> RepositoryCrossRepository:
        return self._cross_repository

    @property
    def economics(self) -> RepositoryEconomics:
        return self._economics

    @property
    def views(self) -> RepositoryViews:
        return self._views

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
        self._resources.close()
