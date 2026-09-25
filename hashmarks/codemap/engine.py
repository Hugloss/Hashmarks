from __future__ import annotations

from pathlib import Path

from hashmarks.client import (
    DaemonCompatibilityError,
    DaemonProtocolError,
    DaemonUnavailableError,
    IdentityClient,
    RepositoryObservation,
    default_state_dir,
    prepare_default_state_dir,
)
from hashmarks.file_store import FileDigestStore
from hashmarks.native_vitest import (  # noqa: F401 - evidence_graph uses these engine module attributes
    collect_vitest_vite_graph,
    local_vitest,
)
from hashmarks.paths import canonical_host_path, normalize_relative_path

from .change_intelligence import ChangeIntelligenceMixin
from .context_cache import ContextCache
from .cross_repository_evidence import CrossRepositoryEvidenceMixin
from .decision_session import DecisionSessionMixin
from .dependency_resolution_delta import DependencyResolutionDeltaMixin
from .dependency_resolution_evidence import DependencyResolutionEvidenceMixin
from .evidence_correlation import EvidenceCorrelationMixin
from .evidence_freshness import EvidenceFreshnessMixin
from .evidence_graph import EvidenceGraphMixin
from .evidence_packet import TaskEvidencePacketMixin
from .evidence_profiles import EvidenceProfilesMixin
from .evidence_verification import VerificationMixin
from .find_engine import FindEngineMixin
from .freshness_map import EvidenceFreshnessMapMixin
from .import_resolution import ImportResolutionMixin
from .index_watch import IndexWatchMixin
from .indexing_lifecycle import (
    _MAX_INDEX_BYTES,
    IndexingLifecycleMixin,
    _python_source_roots,
)
from .intelligence_economics import IntelligenceEconomicsMixin
from .model import (
    ContextPack,
    EvidenceVisibility,
    SearchHit,
)
from .ownership_analysis import OwnershipAnalysisMixin
from .ownership_graph import OwnershipGraphMixin
from .policy import ContextPolicy
from .post_change import PostChangeMixin
from .project_graph import default_project_graph_providers
from .providers import TreeSitterRangeProvider
from .pyright_type_server import PyrightTypeServerProvider
from .python_ast import estimate_tokens
from .query_surface import QuerySurfaceMixin
from .relationships import RelationshipsMixin
from .repository_context import ContextPlanningMixin
from .repository_declaration_discovery import RepositoryDeclarationDiscoveryMixin
from .repository_declarations import RepositoryDeclarationsMixin
from .repository_delta import RepositoryDeltaMixin
from .repository_evidence_binding_delta import RepositoryEvidenceBindingDeltaMixin
from .repository_evidence_bindings import RepositoryEvidenceBindingsMixin
from .repository_evidence_coverage import RepositoryEvidenceCoverageMixin
from .repository_file_discovery import RepositoryFileDiscoveryMixin
from .repository_index_store import (
    ArtifactStore,
    WorkspaceMapStore,
    default_artifact_db,
)
from .repository_intelligence_query import RepositoryIntelligenceQueryMixin
from .repository_task_action import TaskActionMixin
from .singleflight import SingleFlight
from .structural_locality import StructuralLocalityMixin
from .structural_search import AstGrepSearchProvider
from .task_retrieval import TaskRetrievalMixin
from .typescript_resolver import TypeScriptResolverProvider
from .verification_explanation import VerificationExplanationMixin
from .verification_plan import VerificationPlanMixin
from .work_context import WorkContextMixin

# Generic repository evidence families. These are query-formulation hints only:
# they never name project-specific files, never grant authority, and are emitted
# only when candidate-visible task wording supplies a family cue.  The purpose is
# to bridge ordinary task language to semantically named repository control
# surfaces (for example PRIVACY.md or CI_CD_CONTRACT.md) without globally boosting
# documentation.


class CodeMap(
    TaskEvidencePacketMixin,
    DependencyResolutionDeltaMixin,
    DependencyResolutionEvidenceMixin,
    ChangeIntelligenceMixin,
    EvidenceFreshnessMapMixin,
    RepositoryDeltaMixin,
    EvidenceCorrelationMixin,
    RepositoryEvidenceBindingsMixin,
    RepositoryEvidenceBindingDeltaMixin,
    RepositoryEvidenceCoverageMixin,
    EvidenceProfilesMixin,
    CrossRepositoryEvidenceMixin,
    RepositoryIntelligenceQueryMixin,
    RepositoryDeclarationDiscoveryMixin,
    RepositoryDeclarationsMixin,
    IntelligenceEconomicsMixin,
    VerificationExplanationMixin,
    PostChangeMixin,
    TaskActionMixin,
    VerificationPlanMixin,
    VerificationMixin,
    RelationshipsMixin,
    ImportResolutionMixin,
    EvidenceFreshnessMixin,
    EvidenceGraphMixin,
    ContextPlanningMixin,
    OwnershipAnalysisMixin,
    StructuralLocalityMixin,
    QuerySurfaceMixin,
    WorkContextMixin,
    IndexWatchMixin,
    RepositoryFileDiscoveryMixin,
    IndexingLifecycleMixin,
    TaskRetrievalMixin,
    OwnershipGraphMixin,
    FindEngineMixin,
    DecisionSessionMixin,
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
    ) -> None:
        self.workspace = canonical_host_path(workspace)
        self.state_dir = (
            prepare_default_state_dir(self.workspace)
            if state_dir is None
            else self._resolve_state_dir(state_dir)
        )
        self.state_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._state_rel = (
                self.state_dir.relative_to(self.workspace).as_posix().strip("/")
            )
        except ValueError:
            self._state_rel = None
        store = WorkspaceMapStore(self.state_dir / "codemap.sqlite3")
        store.bind_workspace(
            self.workspace,
            allow_unbound_existing=self._state_rel is not None,
        )
        self.store = store
        self.file_store = FileDigestStore(self.state_dir / "identity.sqlite3")
        # Protocol v3 is the compatibility fence. Reuse one stateless IPC client
        # so repository observations validate daemon compatibility once rather
        # than spending an extra status round-trip on every freshness sample.
        self._identity_client = IdentityClient(
            self.workspace, state_dir=self.state_dir, timeout=0.1
        )
        artifact_path = (
            default_artifact_db(self.workspace)
            if artifact_db is None
            else canonical_host_path(artifact_db)
        )
        self.artifacts = ArtifactStore(artifact_path)
        config = None
        if policy_path is not None:
            config = Path(policy_path)
            if not config.is_absolute():
                config = self.workspace / config
            config = canonical_host_path(config)
        self._policy_config_path, self.policy = (
            config,
            ContextPolicy.load(self.workspace, config),
        )
        self.context_cache = ContextCache(self.state_dir)
        self._find_flight: SingleFlight[tuple[SearchHit, ...]] = SingleFlight()
        self._context_flight: SingleFlight[ContextPack] = SingleFlight()
        self.max_index_bytes = int(max_index_bytes)
        self._python_import_roots = _python_source_roots(self.workspace)
        # Optional structural precision lives entirely in the CodeMap lane.
        # Missing tree-sitter support is expected and never affects Identity.
        self.range_provider = TreeSitterRangeProvider.auto()
        self.structural_search_provider = AstGrepSearchProvider(self.workspace)
        self.project_graph_providers = default_project_graph_providers(
            self._visible_repository_manifests
        )
        self.typescript_resolver = TypeScriptResolverProvider()
        self.pyright_type_server = PyrightTypeServerProvider()
        self._reverse_file_graph_cache: tuple[int, dict[str, set[str]]] | None = None
        # Canonical task retrieval is composed by multiple additive CodeMap surfaces.
        # Keep a small generation-bound result cache so those surfaces reuse the exact
        # same selected evidence instead of replaying 2-3 query lanes each time.
        self._task_result_cache: dict[tuple[int, str, int], tuple[SearchHit, ...]] = {}
        # Structural ownership may select an authority path that is not present in
        # the canonical retrieval rows. Remember those selected paths separately
        # so an unsignaled byte change is reconciled before the next decision.
        self._task_authority_paths_cache: dict[
            tuple[int, str, int], tuple[str, ...]
        ] = {}
        # Retain a bounded task-local history of authority-contributing paths.
        # This is freshness evidence only: it lets a later ABA restoration or
        # path replacement be reconciled even after an intermediate decision
        # became unsafe and no longer selected the old owner.
        self._task_recent_authority_paths: dict[tuple[str, int], tuple[str, ...]] = {}
        self._init_decision_session_state()

    def _resolve_state_dir(self, state_dir: str | Path | None) -> Path:
        if state_dir is None:
            return default_state_dir(self.workspace)
        raw_state = Path(state_dir)
        if not raw_state.is_absolute():
            raw_state = self.workspace / raw_state
        return canonical_host_path(raw_state)

    def _init_decision_session_state(self) -> None:
        # Read-only generation-bound decision-session caches. These cache only
        # immutable evidence primitives, never final task decisions. Outside an
        # explicit decision_session() they are bypassed.
        self._decision_session_depth = 0
        self._decision_session_generation: int | None = None
        self._decision_session_observation: RepositoryObservation | None = None
        self._decision_symbols_cache: dict[
            tuple[int, str], list[dict[str, object]]
        ] = {}
        self._decision_file_row_cache: dict[
            tuple[int, str], dict[str, object] | None
        ] = {}
        self._decision_module_paths_cache: dict[tuple[int, str], tuple[str, ...]] = {}
        self._decision_exact_symbols_cache: dict[
            tuple[int, tuple[str, ...]], tuple[int, tuple[dict[str, object], ...]]
        ] = {}
        # Reverse-reference semantics are keyed by target_short in the store;
        # qualified aliases with the same short name therefore share one cache.
        self._decision_refs_cache: dict[
            tuple[int, str], tuple[int, tuple[dict[str, object], ...]]
        ] = {}
        self._decision_edges_from_cache: dict[
            tuple[int, str, str], tuple[int, tuple[dict[str, object], ...]]
        ] = {}
        self._decision_edges_for_path_cache: dict[
            tuple[int, str], tuple[int, tuple[dict[str, object], ...]]
        ] = {}
        self._decision_df_cache: dict[
            tuple[int, tuple[str, ...]], tuple[int, dict[str, int]]
        ] = {}
        self._decision_candidates_cache: dict[
            tuple[int, tuple[str, ...], int], list[dict[str, object]]
        ] = {}
        self._decision_repository_identity_cache: tuple[int, str] | None = None
        # Complete repository-intelligence snapshots are expensive compositions of
        # already generation-bound evidence. Reuse them only inside one explicit
        # decision session and only for an exact request identity.
        self._decision_snapshot_cache: dict[
            tuple[int, str, tuple[str, ...], int, int, int, int], dict[str, object]
        ] = {}
        # Complete task-action projections are expensive compositions over already
        # generation-bound retrieval/ownership evidence. Reuse only exact request
        # identities inside one explicit decision session.
        self._decision_task_action_cache: dict[
            tuple[int, str, int, int], dict[str, object]
        ] = {}
        # Owner-chain reconstruction can traverse the bounded ownership relation
        # graph repeatedly while several impact-derived surfaces share one task
        # action projection. Reuse only the exact generation/task/action-bounds
        # derivation inside one explicit decision session.
        self._decision_change_impact_owner_chain_cache: dict[
            tuple[int, str, int, int],
            tuple[
                str,
                dict[str, object] | None,
                str,
                list[str],
                dict[tuple[str, str], str],
            ],
        ] = {}
        self._decision_ownership_import_paths_cache: dict[
            tuple[int, str, str], tuple[str, ...]
        ] = {}
        self._decision_session_stats = {
            "task_result_hit": 0,
            "task_result_miss": 0,
            "symbols_hit": 0,
            "symbols_miss": 0,
            "file_row_hit": 0,
            "file_row_miss": 0,
            "module_paths_hit": 0,
            "module_paths_miss": 0,
            "exact_symbols_hit": 0,
            "exact_symbols_miss": 0,
            "refs_hit": 0,
            "refs_miss": 0,
            "edges_from_hit": 0,
            "edges_from_miss": 0,
            "edges_for_path_hit": 0,
            "edges_for_path_miss": 0,
            "df_hit": 0,
            "df_miss": 0,
            "candidates_hit": 0,
            "candidates_miss": 0,
            "snapshot_hit": 0,
            "snapshot_miss": 0,
            "task_action_hit": 0,
            "task_action_miss": 0,
            "impact_owner_chain_hit": 0,
            "impact_owner_chain_miss": 0,
            "ownership_import_paths_hit": 0,
            "ownership_import_paths_miss": 0,
        }
        self._decision_diagnostics_enabled = False
        self._decision_diagnostics_started_ns = 0
        self._decision_diagnostics_sequence = 0
        self._decision_diagnostics_stack: list[dict[str, object]] = []
        self._decision_diagnostics_spans: list[dict[str, object]] = []
        self._decision_diagnostics_producers: dict[str, dict[str, object]] = {}
        self._decision_diagnostics_last: dict[str, object] | None = None

    def __enter__(self) -> CodeMap:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        self.context_cache.close()
        self.store.close()
        self.artifacts.close()
        self.file_store.close()

    def _daemon_observation(self) -> RepositoryObservation | None:
        try:
            return self._identity_client.repository_observation()
        except (
            DaemonUnavailableError,
            DaemonCompatibilityError,
            DaemonProtocolError,
            OSError,
        ):
            return None

    def _internal_path(self, rel: str) -> bool:
        clean = rel.strip("/")
        state = self._state_rel
        return bool(state and (clean == state or clean.startswith(state + "/")))

    def outline(self, relpath: str) -> dict[str, object]:
        self._ensure_map_ready()
        rel = normalize_relative_path(relpath, allow_root=False)
        self._ensure_path_current(rel)
        row = self.store.outline(rel)
        if row is None:
            raise FileNotFoundError(f"not indexed: {rel}")
        visibility = EvidenceVisibility(str(row["evidence_visibility"]))
        if visibility is EvidenceVisibility.DENY:
            raise PermissionError(
                f"repository evidence denied by context policy: {rel}"
            )
        generation, identity_generation, stale = self._generation_status()
        return {
            "schema": "hashmarks.outline.v1",
            "path": rel,
            "language": row["language"],
            "file_digest": row["file_digest"],
            "full_tokens": row["full_tokens"],
            "outline_tokens": estimate_tokens(str(row["outline"])),
            "outline": row["outline"],
            "symbols": self._session_symbols_for_path(rel),
            "parse_error": row["parse_error"],
            "evidence_visibility": visibility.value,
            "generation": generation,
            "identity_generation": identity_generation,
            "stale": stale,
        }

    def _ensure_map_ready(
        self, *, _allow_incomplete: bool = False
    ) -> RepositoryObservation | None:
        # An active decision session already established repository readiness and
        # is generation-bound. Nested retrieval surfaces must reuse that exact
        # freshness sample rather than crossing the daemon boundary again.
        if self._decision_session_depth > 0:
            return self._decision_session_observation
        # A durable BUILDING marker means a prior sync did not finish. Query
        # paths must not silently turn that incomplete generation into fresh
        # authority by auto-rebuilding it; the caller/execution layer decides
        # when another sync attempt is appropriate.
        if self.store.meta("sync.build_state") == "BUILDING":
            if _allow_incomplete:
                return None
            raise RuntimeError(
                "CodeMap generation is incomplete (BUILDING); run sync() before querying repository intelligence"
            )
        # Context policy is live repository admission authority, not a
        # construction-time snapshot. Stable policy checks are one exact-file
        # read; semantic changes reconcile once before persisted evidence returns.
        self._reconcile_context_policy_for_query()
        self._reconcile_persisted_analysis_scope()
        if not self.store.has_files():
            self.sync()
            return self._daemon_observation()
        synced_raw = self.store.meta("identity_generation", "") or ""
        observation = self._daemon_observation()
        self._reconcile_daemon_generation(observation, synced_raw)
        return observation

    def _reconcile_daemon_generation(
        self, observation: RepositoryObservation | None, synced_raw: str
    ) -> None:
        if observation is not None and not synced_raw:
            # A daemon/barrier is now available but this map was built without
            # generation-bound freshness evidence. Reconcile in the evidence lane.
            self.sync()
            return
        if observation is None or not synced_raw:
            return
        synced = int(synced_raw)
        if observation.generation == synced:
            return
        if observation.can_incrementally_reconcile:
            self.sync(observation.dirty_paths)
            return
        self.sync()
