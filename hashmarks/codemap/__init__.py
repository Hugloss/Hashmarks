"""Repository-intelligence API; component imports never load the facade eagerly."""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .change_impact import ChangeImpactOptions as ChangeImpactOptions
    from .engine import CodeMap as CodeMap
    from .evidence_correlation import evidence_component_fits as evidence_component_fits
    from .evidence_correlation import (
        evidence_request_budget_fits as evidence_request_budget_fits,
    )
    from .evidence_correlation import (
        validate_evidence_locator_claim as validate_evidence_locator_claim,
    )
    from .model import ContextDisclosure as ContextDisclosure
    from .model import ContextPack as ContextPack
    from .model import EvidenceVisibility as EvidenceVisibility
    from .model import SearchHit as SearchHit
    from .model import SyncResult as SyncResult
    from .policy import ContextPolicy as ContextPolicy
    from .post_change import PostChangeOptions as PostChangeOptions
    from .project_impact_codec import (
        COMPACT_PROJECT_IMPACT_SCHEMA as COMPACT_PROJECT_IMPACT_SCHEMA,
    )
    from .project_impact_codec import compact_project_impact as compact_project_impact
    from .project_impact_codec import expand_project_impact as expand_project_impact
    from .repository_declaration_provider import (
        RepositoryDeclarationProvider as RepositoryDeclarationProvider,
    )
    from .repository_declaration_provider import (
        RepositoryDeclarationProviderContext as RepositoryDeclarationProviderContext,
    )
    from .repository_declaration_provider import (
        RepositoryDeclarationProviderError as RepositoryDeclarationProviderError,
    )
    from .repository_declaration_provider import (
        RepositoryDeclarationProviderResult as RepositoryDeclarationProviderResult,
    )
    from .repository_intelligence_query import (
        RepositoryIntelligenceQueryOptions as RepositoryIntelligenceQueryOptions,
    )
    from .semantic_relationship_delta import (
        semantic_relationship_delta as semantic_relationship_delta,
    )
    from .service import CodeMapService as CodeMapService
    from .service import CodeMapServiceClient as CodeMapServiceClient
    from .service import default_codemap_socket as default_codemap_socket
    from .structural_locality import (
        structural_locality_delta as structural_locality_delta,
    )
    from .worktree_overlay import WorktreeOverlay as WorktreeOverlay
    from .worktree_overlay import (
        WorktreeOverlayBaseChangedError as WorktreeOverlayBaseChangedError,
    )

_EXPORTS: dict[str, str] = {
    "CodeMap": "engine",
    "evidence_component_fits": "evidence_correlation",
    "evidence_request_budget_fits": "evidence_correlation",
    "validate_evidence_locator_claim": "evidence_correlation",
    "ChangeImpactOptions": "change_impact",
    "PostChangeOptions": "post_change",
    "RepositoryIntelligenceQueryOptions": "repository_intelligence_query",
    "RepositoryDeclarationProvider": "repository_declaration_provider",
    "RepositoryDeclarationProviderContext": "repository_declaration_provider",
    "RepositoryDeclarationProviderError": "repository_declaration_provider",
    "RepositoryDeclarationProviderResult": "repository_declaration_provider",
    "CodeMapService": "service",
    "CodeMapServiceClient": "service",
    "default_codemap_socket": "service",
    "EvidenceVisibility": "model",
    "ContextDisclosure": "model",
    "ContextPack": "model",
    "ContextPolicy": "policy",
    "SearchHit": "model",
    "SyncResult": "model",
    "WorktreeOverlay": "worktree_overlay",
    "WorktreeOverlayBaseChangedError": "worktree_overlay",
    "structural_locality_delta": "structural_locality",
    "semantic_relationship_delta": "semantic_relationship_delta",
    "COMPACT_PROJECT_IMPACT_SCHEMA": "project_impact_codec",
    "compact_project_impact": "project_impact_codec",
    "expand_project_impact": "project_impact_codec",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> object:
    """Load a requested public export without coupling every component to CodeMap."""
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f".{module}", __name__), name)
    globals()[name] = value
    return value
