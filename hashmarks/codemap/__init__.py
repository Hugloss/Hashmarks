"""Derived repository intelligence.

CodeMap is deliberately not imported by Hashmarks' identity hot path. Import it
explicitly or use the CLI when repository orientation, search, evidence, or
change analysis is needed.
"""

from .change_impact import ChangeImpactOptions
from .engine import CodeMap
from .model import (
    ContextDisclosure,
    ContextPack,
    EvidenceVisibility,
    SearchHit,
    SyncResult,
)
from .policy import ContextPolicy
from .post_change import PostChangeOptions
from .project_impact_codec import (
    COMPACT_PROJECT_IMPACT_SCHEMA,
    compact_project_impact,
    expand_project_impact,
)
from .repository_declaration_provider import (
    RepositoryDeclarationProvider,
    RepositoryDeclarationProviderContext,
    RepositoryDeclarationProviderError,
    RepositoryDeclarationProviderResult,
)
from .repository_intelligence_query import RepositoryIntelligenceQueryOptions
from .service import CodeMapService, CodeMapServiceClient, default_codemap_socket
from .structural_locality import structural_locality_delta
from .worktree_overlay import WorktreeOverlay

__all__ = [
    "CodeMap",
    "ChangeImpactOptions",
    "PostChangeOptions",
    "RepositoryIntelligenceQueryOptions",
    "RepositoryDeclarationProvider",
    "RepositoryDeclarationProviderContext",
    "RepositoryDeclarationProviderError",
    "RepositoryDeclarationProviderResult",
    "CodeMapService",
    "CodeMapServiceClient",
    "default_codemap_socket",
    "EvidenceVisibility",
    "ContextDisclosure",
    "ContextPack",
    "ContextPolicy",
    "SearchHit",
    "SyncResult",
    "WorktreeOverlay",
    "structural_locality_delta",
    "COMPACT_PROJECT_IMPACT_SCHEMA",
    "compact_project_impact",
    "expand_project_impact",
]
