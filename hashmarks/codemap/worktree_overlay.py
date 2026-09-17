from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from hashmarks.client import default_runtime_dir
from hashmarks.paths import canonical_host_path

from .engine import CodeMap

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .model import SearchHit


@dataclass(frozen=True)
class OverlayStats:
    worker_id: str
    base_workspace: str
    worktree_workspace: str
    changed_paths: tuple[str, ...]
    overlay_generation: int
    parsed_artifacts: int
    reused_artifacts: int

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": "hashmarks.worktree-overlay-stats.v1",
            "worker_id": self.worker_id,
            "base_workspace": self.base_workspace,
            "worktree_workspace": self.worktree_workspace,
            "changed_paths": list(self.changed_paths),
            "overlay_generation": self.overlay_generation,
            "parsed_artifacts": self.parsed_artifacts,
            "reused_artifacts": self.reused_artifacts,
        }


class WorktreeOverlay:
    """Changed-path CodeMap delta layered over one canonical base authority.

    The overlay indexes only paths reported as different in one worker worktree.
    Unchanged evidence remains owned by ``base``. Queries mask changed base paths
    and fuse the worker-local delta ahead of unchanged canonical evidence.
    """

    def __init__(self, base: CodeMap, worktree: str | Path, *, worker_id: str) -> None:
        if not worker_id.strip():
            raise ValueError("worker_id must be non-empty")
        self.base = base
        self.worktree = canonical_host_path(worktree)
        if self.worktree == base.workspace:
            raise ValueError(
                "worktree overlay must use a workspace distinct from the canonical base"
            )
        digest = hashlib.sha256(worker_id.encode("utf-8")).hexdigest()[:16]
        state_dir = default_runtime_dir(self.worktree) / f"codemap-overlay-{digest}"
        # Parsed artifacts are content-addressed and safe to share; mutable map
        # state is worker-local and never shared between overlays.
        self.overlay = CodeMap(
            self.worktree,
            state_dir=state_dir,
            artifact_db=base.artifacts.db_path,
        )
        self.worker_id = worker_id
        self._changed: tuple[str, ...] = ()
        self._stats: OverlayStats | None = None

    def __enter__(self) -> WorktreeOverlay:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        self.overlay.close()

    @staticmethod
    def _normalize_paths(paths: Iterable[str | Path]) -> tuple[str, ...]:
        values: list[str] = []
        for value in paths:
            rel = Path(value).as_posix().strip("/")
            if not rel or rel == "." or rel.startswith("../") or "/../" in f"/{rel}/":
                raise ValueError(f"invalid overlay path: {value!s}")
            if rel not in values:
                values.append(rel)
        return tuple(values)

    def sync(self, changed_paths: Iterable[str | Path]) -> OverlayStats:
        changed = self._normalize_paths(changed_paths)
        if not changed:
            raise ValueError("changed_paths must not be empty")
        result = self.overlay.sync(changed)
        self._changed = changed
        self._stats = OverlayStats(
            worker_id=self.worker_id,
            base_workspace=str(self.base.workspace),
            worktree_workspace=str(self.worktree),
            changed_paths=changed,
            overlay_generation=result.generation,
            parsed_artifacts=result.parsed_artifacts,
            reused_artifacts=result.reused_artifacts,
        )
        return self._stats

    def stats(self) -> dict[str, object]:
        if self._stats is None:
            raise RuntimeError("overlay has not been synced")
        return self._stats.as_dict()

    def find_task(self, task: str, *, limit: int = 20) -> tuple[SearchHit, ...]:
        if self._stats is None:
            raise RuntimeError("overlay has not been synced")
        changed = set(self._changed)
        overlay_hits = list(self.overlay.find_task(task, limit=limit))
        base_hits = [
            hit
            for hit in self.base.find_task(task, limit=limit)
            if hit.path not in changed
        ]
        result: list[SearchHit] = []
        seen: set[str] = set()
        # Worker-local changed evidence shadows canonical evidence for the same path.
        for hit in overlay_hits + base_hits:
            if hit.path in seen:
                continue
            seen.add(hit.path)
            result.append(hit)
            if len(result) >= limit:
                break
        return tuple(result)
