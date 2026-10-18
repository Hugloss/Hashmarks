"""Producer-neutral dependency observation and explicit endpoint comparison."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .decision_session import ReadScopeOwner
from .dependency_resolution_delta import DependencyResolutionDeltaMixin
from .dependency_resolution_derivation import DependencyResolutionDerivationMixin
from .dependency_resolution_evidence import DependencyResolutionEvidenceMixin

if TYPE_CHECKING:
    from .decision_session import DecisionScope
    from .evidence_correlation import RepositoryCorrelation
    from .import_resolution import RepositoryImports
    from .repository_source import RepositorySource


class RepositoryDependencies(
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
    ) -> None:
        if imports.reads is not source.reads or correlation.reads is not source.reads:
            raise ValueError("Dependency inputs must share one repository read scope")
        self.source = source
        self.imports = imports
        self._repository_correlation = correlation
        self.store = source.store

    @property
    def reads(self) -> DecisionScope:
        return self.source.reads
