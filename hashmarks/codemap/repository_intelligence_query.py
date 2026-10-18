from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, get_args

from hashmarks.evidence_presentation import (
    present_repository_evidence,
    validate_presentation,
)
from hashmarks.operation_contract import operation_response, operation_schema

from .change_impact import ChangeImpactOptions
from .decision_session import ReadScopeOwner, diagnostic_producer
from .evidence_profiles import (
    EVIDENCE_PROFILE_DEFAULT_OPTIONS,
    EvidenceProfileProjection,
)
from .freshness_map import FreshnessMapOptions
from .repository_observation import packet_digest
from .watch_continuity import watch_status_projection

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from .cross_repository_evidence import RepositoryCrossRepository
    from .decision_session import DecisionScope
    from .intelligence_economics import RepositoryEconomics
    from .repository_changes import RepositoryChanges
    from .structural_locality import RepositoryStructure

QuerySurface = Literal[
    "change-intelligence",
    "verification-explanation",
    "freshness",
    "snapshot",
    "profile",
    "delta",
    "cross-repository",
    "economics",
]
QUERY_SURFACES = get_args(QuerySurface)


@dataclass(frozen=True, slots=True)
class RepositoryIntelligenceQueryOptions:
    """Optional inputs and bounds for one repository-intelligence query."""

    member_path: str | None = None
    profile: str = "compact"
    presentation: str = "none"
    negative_members: Sequence[str | Path] = ()
    previous_map: Mapping[str, object] | None = None
    previous_snapshot: Mapping[str, object] | None = None
    limit: int = 20
    per_role: int = 3
    impact_limit_per_surface: int = 4
    max_depth: int = 3
    project_impact_limit: int = 12


REPOSITORY_INTELLIGENCE_QUERY_DEFAULT_OPTIONS = RepositoryIntelligenceQueryOptions()


class RepositoryViews(ReadScopeOwner):
    """Thin deterministic facade over existing repository-intelligence producers.

    This mixin owns no repository fact, ranking, freshness state, or historical
    state. It only normalizes one bounded query contract and delegates to the
    existing producer that already owns the requested semantics.
    """

    def __init__(
        self,
        changes: RepositoryChanges,
        cross_repository: RepositoryCrossRepository,
        economics: RepositoryEconomics,
        structure: RepositoryStructure,
    ) -> None:
        if any(
            owner.reads is not changes.reads
            for owner in (cross_repository, economics, structure)
        ):
            raise ValueError("View inputs must share one repository read scope")
        self.changes = changes
        self.cross_repository = cross_repository
        self.economics = economics
        self.structure = structure
        self.tasks = changes.tasks
        self.index = changes.index
        self.native = changes.native
        self.workspace = changes.workspace

    @property
    def reads(self) -> DecisionScope:
        return self.changes.reads

    @diagnostic_producer
    def profile(
        self,
        task: str,
        changed_paths: Sequence[str | Path],
        *,
        profile: str = "compact",
        limit: int = 20,
        per_role: int = 3,
        options: ChangeImpactOptions | None = None,
    ) -> dict[str, object]:
        options = options or EVIDENCE_PROFILE_DEFAULT_OPTIONS
        """Project one bounded F3 snapshot at compact, standard, or audit density."""
        snapshot = self.changes.snapshot(
            task,
            changed_paths,
            limit=limit,
            per_role=per_role,
            impact_limit_per_surface=options.impact_limit_per_surface,
            max_depth=options.max_depth,
        )
        return EvidenceProfileProjection.from_snapshot(snapshot, profile=profile)

    def status(self) -> dict[str, object]:
        index_facts = self.index.status()
        watch_record = self.index.watch_continuity()
        generation, identity_generation, stale = (
            self.reads.generation_status_with_watch(None, watch_record)
        )
        packet = {
            **index_facts,
            "schema": "hashmarks.codemap-status.v1",
            "generation": generation,
            "identity_generation_at_sync": identity_generation,
            "daemon_generation_changed": stale,
            "precision_providers": [
                self.index.range_provider.status().as_dict(),
                self.structure.search_provider.status().as_dict(),
                {
                    "name": self.native.producers.typescript.name,
                    "available": self.native.producers.typescript.detect(
                        self.workspace
                    ),
                    "version": None,
                    "detail": None,
                },
                *[
                    {
                        "name": provider.name,
                        "available": provider.detect(self.workspace),
                        "version": None,
                        "detail": None,
                    }
                    for provider in self.native.producers.projects
                ],
            ],
            "native_evidence": self.native.status(),
            "watcher": watch_status_projection(watch_record),
        }

        if (
            index_facts["generation"] != generation
            or self.index.publication_binding()[0] != generation
        ):
            raise RuntimeError("CodeMap generation changed during status observation")
        return packet

    @operation_response("repository_intelligence_query")
    def query(
        self,
        surface: str,
        task: str,
        changed_paths: Sequence[str | Path] = (),
        *,
        options: RepositoryIntelligenceQueryOptions = (
            REPOSITORY_INTELLIGENCE_QUERY_DEFAULT_OPTIONS
        ),
    ) -> dict[str, object]:
        validate_presentation(options.presentation)
        if surface not in QUERY_SURFACES:
            raise ValueError(f"surface must be one of {list(QUERY_SURFACES)}")
        if not task.strip():
            raise ValueError("task must not be empty")

        if surface == "verification-explanation":
            result = self.tasks.explain_verification_selection(
                task,
                options.member_path,
                limit=options.limit,
                candidate_limit=16,
            )
        else:
            if not changed_paths:
                raise ValueError(
                    f"changed_paths must not be empty for surface {surface}"
                )
            common = {
                "limit": options.limit,
                "per_role": options.per_role,
                "impact_limit_per_surface": options.impact_limit_per_surface,
                "max_depth": options.max_depth,
            }
            impact_options = ChangeImpactOptions(
                impact_limit_per_surface=options.impact_limit_per_surface,
                max_depth=options.max_depth,
            )
            producers = {
                "change-intelligence": lambda: self.changes.brief(
                    task, changed_paths, **common
                ),
                "freshness": lambda: self.changes.freshness_map(
                    task,
                    changed_paths,
                    negative_members=options.negative_members,
                    previous_map=options.previous_map,
                    options=FreshnessMapOptions(
                        limit=options.limit,
                        per_role=options.per_role,
                        impact_limit_per_surface=options.impact_limit_per_surface,
                        max_depth=options.max_depth,
                    ),
                ),
                "snapshot": lambda: self.changes.snapshot(
                    task, changed_paths, **common
                ),
                "profile": lambda: self.profile(
                    task,
                    changed_paths,
                    profile=options.profile,
                    limit=options.limit,
                    per_role=options.per_role,
                    options=impact_options,
                ),
                "economics": lambda: self.economics.receipt(
                    task,
                    changed_paths,
                    previous_snapshot=options.previous_snapshot,
                    limit=options.limit,
                    per_role=options.per_role,
                    options=impact_options,
                ),
                "cross-repository": lambda: self.cross_repository.packet(
                    task,
                    changed_paths,
                    limit=options.limit,
                    per_role=options.per_role,
                    options=ChangeImpactOptions(
                        impact_limit_per_surface=options.impact_limit_per_surface,
                        max_depth=options.max_depth,
                        project_impact_limit=options.project_impact_limit,
                        project_impact_encoding="compact",
                    ),
                ),
            }
            if surface == "delta":
                if options.previous_snapshot is None:
                    raise ValueError("previous_snapshot is required for surface delta")
                result = self.changes.delta(
                    task,
                    changed_paths,
                    previous_snapshot=options.previous_snapshot,
                    limit=options.limit,
                    per_role=options.per_role,
                    options=impact_options,
                )
            else:
                result = producers[surface]()

        return repository_query_response(
            surface, result, presentation=options.presentation
        )


def repository_query_response(
    surface: str, result: Mapping[str, object], *, presentation: str = "none"
) -> dict[str, object]:
    """Build the query envelope from one frozen producer response."""
    validate_presentation(presentation)
    if surface not in QUERY_SURFACES:
        raise ValueError(f"surface must be one of {list(QUERY_SURFACES)}")
    envelope: dict[str, object] = {
        "schema": operation_schema("repository_intelligence_query"),
        "surface": surface,
        "producer_schema": result.get("schema"),
        "result": dict(result),
        "storage": "derived-not-persisted",
        "authority": "repository-intelligence-only",
        "execution_effect": "none",
    }
    if presentation != "none":
        envelope["presentation"] = present_repository_evidence(
            result, format=presentation
        )
    envelope["query_identity"] = "sha256:" + packet_digest(
        operation_schema("repository_intelligence_query"), envelope
    )
    return envelope
