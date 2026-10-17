"""Bounded contributing-path freshness for task authority observations."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from .repository_tasks import RepositoryTasks


class TaskFreshnessMixin:
    def prepare(
        self, task: str, limit: int, *, probe_on_miss: bool = True
    ) -> tuple[str, ...]:
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        if not isinstance(task, str) or type(limit) is not int or limit < 1:
            return ()
        if self.reads.depth > 0 or self.store.meta("sync.build_state") == "BUILDING":
            return ()
        generation = self.store.generation()
        key = (generation, task, int(limit))
        cached, retrieval_recent = self.search.retrieval_freshness_inputs(task, limit)
        authority_paths = self._task_authority_paths_cache.get(key, ())
        recent_key = (task, int(limit))
        recent_authority_paths = tuple(
            sorted(
                {
                    *self._task_recent_authority_paths.get(recent_key, ()),
                    *retrieval_recent,
                }
            )
        )
        if cached is None and not authority_paths and not recent_authority_paths:
            if not probe_on_miss:
                return ()
            # Cache/history pressure must not make an old task permanently weaker
            # than cold truth. Authority-producing decisions may probe canonical
            # retrieval before their decision session opens; this remains read-only
            # evidence selection. Task evidence deliberately does not use this path:
            # it owns an independent closing freshness fence and must preserve the
            # selected stale evidence rather than silently reselect it.
            cached = self.search._find_task_evidence_impl(
                task, limit=limit, ensure_ready=False
            )

        active_paths = {
            *(hit.path for hit in (cached.hits if cached else ())),
            *authority_paths,
        }
        active_stale = tuple(
            sorted(path for path in active_paths if not self.index.is_current(path))
        )
        # The preflight may be the first decision for this task after an
        # unsignaled disappearance. Preserve only stale task-local paths before
        # reconciliation retires their rows; they remain non-authoritative.
        recent_authority_paths = self._remember_task_resurrection_paths(
            recent_key, recent_authority_paths, active_stale
        )
        self.source.reconcile_contributors(active_stale)

        # Missing/symlink tombstones do no work. Exact regular-file return pays
        # one admitted path-scoped sync, closing delete/recreate and symlink ABA
        # without a watcher or repository-wide polling.
        restored = self._reconcile_authority_restoration(recent_authority_paths)
        return tuple(sorted({*active_stale, *restored}))

    def _remember_task_resurrection_paths(
        self,
        recent_key: tuple[str, int],
        recent_paths: tuple[str, ...],
        stale_paths: tuple[str, ...],
    ) -> tuple[str, ...]:
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        if not stale_paths:
            return recent_paths
        remembered = tuple(sorted({*recent_paths, *stale_paths}))
        self._task_recent_authority_paths[recent_key] = remembered
        if len(self._task_recent_authority_paths) > 256:
            # Preserve only the task proving stale authority so the pressure
            # event cannot erase the resurrection fence it just established.
            self._task_recent_authority_paths.clear()
            self._task_recent_authority_paths[recent_key] = remembered
        return remembered

    def remember_paths(self, task: str, paths: Iterable[str], *, limit: int) -> None:
        """Retain supplied contributing paths for later freshness checks only."""
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        authority_paths = set(paths)
        generation = self.store.generation()
        if len(self._task_authority_paths_cache) >= 256:
            self._task_authority_paths_cache = {
                key: value
                for key, value in self._task_authority_paths_cache.items()
                if key[0] == generation
            }
            if len(self._task_authority_paths_cache) >= 256:
                self._task_authority_paths_cache.clear()
        self._task_authority_paths_cache[(generation, task, int(limit))] = tuple(
            sorted(authority_paths)
        )
        recent_key = (task, int(limit))
        previous = self._task_recent_authority_paths.get(recent_key, ())
        self._task_recent_authority_paths[recent_key] = tuple(
            sorted({*previous, *authority_paths})
        )
        if len(self._task_recent_authority_paths) > 256:
            self._task_recent_authority_paths.clear()

    def _reconcile_authority_restoration(
        self, recent: tuple[str, ...]
    ) -> tuple[str, ...]:
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        restored = self.source.restored_contributors(recent)
        if restored:
            self.index.sync(restored)
        return restored
