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
from .observation import ChangeSnapshot, ChangeTracker, ObservationState, UnstableObservationError
from .snapshot import Snapshot, SnapshotDiff
from .specs import Directory, File, Glob, InputSpec, InputValue, patterns_from_inputs, validate_input_values

__all__ = [
    "__version__",
    "CodeMap",
    "Digest",
    "RepositoryIdentity",
    "RepositoryIdentityMode",
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
]


def __getattr__(name: str):
    """Lazily expose CodeMap without loading its larger analysis graph on identity imports."""
    if name == "CodeMap":
        from .codemap import CodeMap

        return CodeMap
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
