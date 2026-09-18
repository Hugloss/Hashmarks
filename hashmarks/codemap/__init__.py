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
from .project_impact_codec import (
    COMPACT_PROJECT_IMPACT_SCHEMA,
    compact_project_impact,
    expand_project_impact,
)
from .service import CodeMapService, CodeMapServiceClient, default_codemap_socket
from .worktree_overlay import WorktreeOverlay

__all__ = [
    "CodeMap",
    "ChangeImpactOptions",
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
    "COMPACT_PROJECT_IMPACT_SCHEMA",
    "compact_project_impact",
    "expand_project_impact",
]
