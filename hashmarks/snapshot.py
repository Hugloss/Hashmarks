from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .schema import SNAPSHOT_SCHEMA

if TYPE_CHECKING:
    from .digest import Digest


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
