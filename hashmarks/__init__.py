"""Hashmarks: freshness-bound repository intelligence.

The top-level API intentionally exposes only repository/content identity and
repository-intelligence primitives. Agent workflow, execution, result caching,
and certification belong to external consumers and execution systems.
"""

from ._version import __version__
from .digest import Digest, hash_bytes, hash_file
from .graph import IdentityCycleError, IdentityGraph
from .identity import RepositoryIdentity, RepositoryIdentityMode
from .inputs import InputManifest, resolve_inputs
from .observation import (
    ChangeSnapshot,
    ChangeTracker,
    ObservationState,
    UnstableObservationError,
)
from .snapshot import Snapshot, SnapshotDiff
from .specs import (
    Directory,
    File,
    Glob,
    InputSpec,
    InputValue,
    patterns_from_inputs,
    validate_input_values,
)

__all__ = [
    "__version__",
    "CodeMap",
    "Digest",
    "RepositoryIdentity",
    "RepositoryIdentityMode",
    "RepositoryDeclarationProvider",
    "RepositoryDeclarationProviderContext",
    "RepositoryDeclarationProviderError",
    "RepositoryDeclarationProviderResult",
    "IdentityCycleError",
    "IdentityGraph",
    "InputManifest",
    "InputSpec",
    "InputValue",
    "File",
    "Directory",
    "Glob",
    "Snapshot",
    "SnapshotDiff",
    "ChangeSnapshot",
    "ChangeTracker",
    "ObservationState",
    "UnstableObservationError",
    "hash_bytes",
    "hash_file",
    "resolve_inputs",
    "patterns_from_inputs",
    "validate_input_values",
    "native_producer_implementation_identity",
    "validate_native_consumer_bundle",
    "validate_repository_intelligence_evidence",
]


def __getattr__(name: str):
    """Lazily expose CodeMap APIs without loading the analysis graph eagerly."""
    if name == "CodeMap":
        from .codemap import CodeMap

        return CodeMap
    if name == "native_producer_implementation_identity":
        from .producer_identity import native_producer_implementation_identity

        return native_producer_implementation_identity
    if name == "validate_native_consumer_bundle":
        from .consumer_conformance import validate_native_consumer_bundle

        return validate_native_consumer_bundle
    if name == "validate_repository_intelligence_evidence":
        from .repository_intelligence_validation import (
            validate_repository_intelligence_evidence,
        )

        return validate_repository_intelligence_evidence
    if name in {
        "RepositoryDeclarationProvider",
        "RepositoryDeclarationProviderContext",
        "RepositoryDeclarationProviderError",
        "RepositoryDeclarationProviderResult",
    }:
        from .codemap import (
            RepositoryDeclarationProvider,
            RepositoryDeclarationProviderContext,
            RepositoryDeclarationProviderError,
            RepositoryDeclarationProviderResult,
        )

        return {
            "RepositoryDeclarationProvider": RepositoryDeclarationProvider,
            "RepositoryDeclarationProviderContext": RepositoryDeclarationProviderContext,
            "RepositoryDeclarationProviderError": RepositoryDeclarationProviderError,
            "RepositoryDeclarationProviderResult": RepositoryDeclarationProviderResult,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
