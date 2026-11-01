"""Producer-neutral dependency observation and explicit endpoint comparison."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

from hashmarks.file_store import UnstableFileError
from hashmarks.freshness import freshness_state

from .decision_session import ReadScopeOwner
from .dependency_consumers import DependencyConsumersMixin
from .dependency_resolution_delta import DependencyResolutionDeltaMixin
from .dependency_resolution_derivation import DependencyResolutionDerivationMixin
from .dependency_resolution_evidence import DependencyResolutionEvidenceMixin
from .dependency_resolution_query import dependency_inventory_assessment

if TYPE_CHECKING:
    from .decision_session import DecisionScope
    from .evidence_correlation import RepositoryCorrelation
    from .evidence_graph import RepositoryRelationships
    from .import_resolution import RepositoryImports
    from .repository_source import RepositorySource


class RepositoryDependencies(
    DependencyConsumersMixin,
    DependencyResolutionEvidenceMixin,
    DependencyResolutionDeltaMixin,
    DependencyResolutionDerivationMixin,
    ReadScopeOwner,
):
    """Own qualified dependency facts without resolver or execution authority.

    The internal observation, correlation, derivation and comparison modules
    belong to this component. Producers supply normalized claims; their format
    syntax terminates in adapters. Resources and repository authority are
    borrowed from Source rather than from the composition root.
    """

    def __init__(
        self,
        source: RepositorySource,
        imports: RepositoryImports,
        correlation: RepositoryCorrelation,
        relationships: RepositoryRelationships,
    ) -> None:
        if (
            imports.reads is not source.reads
            or correlation.reads is not source.reads
            or relationships.reads is not source.reads
        ):
            raise ValueError("Dependency inputs must share one repository read scope")
        self.source = source
        self.imports = imports
        self._repository_correlation = correlation
        self.relationships = relationships
        self.store = source.store

    @property
    def reads(self) -> DecisionScope:
        return self.source.reads

    def _assessment_source_input(self, row: Mapping[str, object]) -> dict[str, object]:
        packet = self.source.observe(str(row["path"]), max_bytes=8_388_608)
        member = cast("Mapping[str, object]", packet["member"])
        observed = (
            member.get("member_revision")
            if member["state"] == "known-present"
            else None
        )
        recorded = row["observed_member_revision"]
        claimed = row["claimed_member_revision"]
        return {
            "path": row["path"],
            "state": member["state"],
            "reason": member.get("reason"),
            "recorded_member_revision": recorded,
            "current_member_revision": observed,
            "freshness": (
                "stale"
                if member["state"] == "known-absent"
                or recorded is not None
                and observed is not None
                and recorded != observed
                else "current"
                if recorded is not None and recorded == observed
                else "unknown"
            ),
            "source_equivalence": (
                "unknown"
                if claimed is None or observed is None
                else "proven"
                if claimed == observed
                else "mismatch"
            ),
        }

    def assessment(self, observation: Mapping[str, object]) -> dict[str, object]:
        """Reobserve only retained dependency inputs and project inventory coverage.

        Exact source correspondence does not assert global CodeMap freshness or
        external producer authenticity. Missing claims never gain equivalence.
        """
        self._require_qualified_dependency_observation_v3(observation)
        generation_before = self.store.generation()
        binding = cast("Mapping[str, object]", observation["repository_binding"])
        same_repository = (
            binding["repository_identity"] == self.reads.repository_identity()
        )
        inputs = cast(
            "Sequence[Mapping[str, object]]", observation["repository_inputs"]
        )
        members = [self._assessment_source_input(row) for row in inputs]
        # Revalidation detects an earlier input changing while later inputs were
        # observed. Source owns admission, stable byte reads and revision meaning.
        for row, member in zip(inputs, members, strict=True):
            if self._assessment_source_input(row) != member:
                raise UnstableFileError("dependency inputs changed during assessment")
        generation, _identity_generation, stale = self.reads.generation_status()
        stable_generation = generation_before == generation
        scope_freshness = (
            "stale"
            if any(row["freshness"] == "stale" for row in members)
            else "current"
            if members and all(row["freshness"] == "current" for row in members)
            else "unknown"
        )
        if not stable_generation:
            scope_freshness = "unknown"
        equivalence = (
            "mismatch"
            if any(row["source_equivalence"] == "mismatch" for row in members)
            else "proven"
            if members and all(row["source_equivalence"] == "proven" for row in members)
            else "unknown"
        )
        available = bool(members) and all(
            row["state"] == "known-present" for row in members
        )
        inventory = dependency_inventory_assessment(observation)
        inventory["negative_evidence"] = (
            "admissible-within-declared-scope"
            if scope_freshness == "current"
            and equivalence == "proven"
            and available
            and inventory["completeness"] == "complete"
            else "not-admissible"
        )
        return {
            "schema": "hashmarks.dependency-resolution-assessment.v1",
            "observation_identity": observation["observation_identity"],
            "repository_binding": dict(binding),
            "repository_freshness": (
                freshness_state(stale)
                if same_repository
                and stable_generation
                and binding["codemap_generation"] == generation
                else "stale"
            ),
            "source_scope": {
                "scope": "explicit-repository-inputs",
                "freshness": scope_freshness,
                "source_equivalence": equivalence,
                "availability": "available" if available else "unavailable",
                "members": members,
            },
            "resolved_inventory": inventory,
            "authority": "repository-intelligence-only",
            "producer_authority": "caller-claimed",
            "execution_authority": "external",
            "result_authority": "external",
            "certification_authority": "external",
        }
