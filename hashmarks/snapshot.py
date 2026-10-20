from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from .schema import SNAPSHOT_SCHEMA

if TYPE_CHECKING:
    from .digest import Digest
    from .inputs import InputManifest


@dataclass(frozen=True, slots=True)
class SnapshotDiff:
    changed: bool
    reason: str
    old_digest: str
    new_digest: str
    observed_paths: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "changed": self.changed,
            "reason": self.reason,
            "old_digest": self.old_digest,
            "new_digest": self.new_digest,
            "observed_paths": list(self.observed_paths),
        }


@dataclass(frozen=True, slots=True)
class Snapshot:
    digest: Digest
    manifest_fingerprint: str
    generation: int | None = None
    observed_paths: tuple[str, ...] = ()
    mode: str = "local"
    schema: str = SNAPSHOT_SCHEMA

    @property
    def hash(self) -> str:
        return self.digest.hash

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "hash": self.digest.hash,
            "size": self.digest.size,
            "manifest": self.manifest_fingerprint,
            "generation": self.generation,
            "observed_paths": list(self.observed_paths),
            "mode": self.mode,
        }

    def diff(self, previous: Snapshot) -> SnapshotDiff:
        changed = self.digest != previous.digest
        if not changed:
            reason = "canonical input identity unchanged"
        elif self.observed_paths:
            reason = (
                "canonical input identity changed after observed filesystem changes"
            )
        else:
            reason = "canonical input identity changed"
        return SnapshotDiff(
            changed=changed,
            reason=reason,
            old_digest=previous.digest.as_key(),
            new_digest=self.digest.as_key(),
            observed_paths=self.observed_paths,
        )


@dataclass(frozen=True, slots=True)
class InputMember:
    """One physical member observed by the canonical selected-input traversal."""

    path: str
    kind: Literal["file", "directory", "symlink"]
    revision: str
    regular_file_bytes: int = 0
    executable: bool | None = None
    link_target: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "kind": self.kind,
            "revision": self.revision,
            "regular_file_bytes": self.regular_file_bytes,
            "executable": self.executable,
            "link_target": self.link_target,
        }


@dataclass(frozen=True, slots=True)
class InputCounts:
    """Counts of physical selected paths, including each hardlink path separately."""

    file_count: int
    directory_count: int
    symlink_count: int
    regular_file_bytes: int

    @property
    def entry_count(self) -> int:
        return self.file_count + self.directory_count + self.symlink_count

    def as_dict(self) -> dict[str, int]:
        return {
            "entry_count": self.entry_count,
            "file_count": self.file_count,
            "directory_count": self.directory_count,
            "symlink_count": self.symlink_count,
            "regular_file_bytes": self.regular_file_bytes,
        }


@dataclass(frozen=True, slots=True)
class InputObservation:
    """Identity and complete inventory from one reconciled selected-input read.

    ``snapshot.digest.size`` retains its Merkle-encoding meaning. Actual regular
    file bytes are in ``counts.regular_file_bytes``. Completeness concerns only
    the resolved roots and exclusions in this observation, not a whole repository.
    """

    snapshot: Snapshot
    manifest: InputManifest
    excluded_paths: tuple[str, ...]
    members: tuple[InputMember, ...]
    counts: InputCounts
    freshness: str
    walk_ignore_names: tuple[str, ...]
    mandatory_exclude_names: tuple[str, ...]
    internal_excluded_paths: tuple[str, ...]
    schema: str = "hashmarks.input-observation.v1"
    completeness: Literal["complete"] = "complete"

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "snapshot": self.snapshot.as_dict(),
            "scope": {
                "roots": list(self.manifest.paths),
                "excluded_paths": list(self.excluded_paths),
                "walk_ignore_names": list(self.walk_ignore_names),
                "mandatory_exclude_names": list(self.mandatory_exclude_names),
                "internal_excluded_paths": list(self.internal_excluded_paths),
            },
            "members": [member.as_dict() for member in self.members],
            "counts": self.counts.as_dict(),
            "completeness": self.completeness,
            "freshness": self.freshness,
            "authority": "repository-evidence-only",
            "execution_effect": "none",
        }


@dataclass(frozen=True, slots=True)
class DirectoryObservation:
    """Directory contents identity and physical counts from one local read.

    ``inputs`` retains the ordinary ``snapshot('*')`` identity scope. Physical
    counts also include walk-ignored descendants; they describe materialization,
    never additional hashed membership. Caller exclusions apply to both scopes.
    """

    inputs: InputObservation
    materialization_counts: InputCounts
