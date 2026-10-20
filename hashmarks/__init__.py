"""Hashmarks: freshness-bound repository intelligence.

The top-level API intentionally exposes only repository/content identity and
repository-intelligence primitives. Agent workflow, execution, result caching,
and certification belong to external consumers and execution systems.
"""

from typing import TYPE_CHECKING, Any

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
from .snapshot import (
    DirectoryObservation,
    InputCounts,
    InputMember,
    InputObservation,
    Snapshot,
    SnapshotDiff,
)
from .specs import (
    Directory,
    File,
    Glob,
    InputSpec,
    InputValue,
    patterns_from_inputs,
    validate_input_values,
)

if TYPE_CHECKING:
    from .codemap import (
        CodeMap as CodeMap,
    )
    from .codemap import (
        RepositoryDeclarationProvider as RepositoryDeclarationProvider,
    )
    from .codemap import (
        RepositoryDeclarationProviderContext as RepositoryDeclarationProviderContext,
    )
    from .codemap import (
        RepositoryDeclarationProviderError as RepositoryDeclarationProviderError,
    )
    from .codemap import (
        RepositoryDeclarationProviderResult as RepositoryDeclarationProviderResult,
    )
    from .consumer_conformance import (
        NativeVerificationMember as NativeVerificationMember,
    )
    from .consumer_conformance import (
        NativeVerificationSelectionProjection as NativeVerificationSelectionProjection,
    )
    from .consumer_conformance import (
        validate_native_consumer_bundle as validate_native_consumer_bundle,
    )
    from .producer_identity import (
        native_producer_implementation_identity as native_producer_implementation_identity,
    )
    from .repository_intelligence_validation import (
        validate_repository_intelligence_evidence as validate_repository_intelligence_evidence,
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
    "InputObservation",
    "DirectoryObservation",
    "InputMember",
    "InputCounts",
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
    "NativeVerificationMember",
    "NativeVerificationSelectionProjection",
    "validate_repository_intelligence_evidence",
]


def __getattr__(name: str) -> object:
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
    if name in {"NativeVerificationMember", "NativeVerificationSelectionProjection"}:
        from .consumer_conformance import (
            NativeVerificationMember,
            NativeVerificationSelectionProjection,
        )

        return {
            "NativeVerificationMember": NativeVerificationMember,
            "NativeVerificationSelectionProjection": NativeVerificationSelectionProjection,
        }[name]
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
