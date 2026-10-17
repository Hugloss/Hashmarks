from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from hashmarks.paths import normalize_relative_path

from .decision_session import ReadScopeOwner, decision_scoped
from .watch_continuity import watch_status_projection

if TYPE_CHECKING:
    from .engine import CodeMap


class QuerySurfaceMixin(ReadScopeOwner):
    @decision_scoped
    def change_impact(
        self, query: str, *, max_depth: int = 4, limit_per_surface: int = 20
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        return dict(
            self.tasks._observe_change_relationships(
                query, max_depth=max_depth, limit_per_surface=limit_per_surface
            )
        )

    @decision_scoped
    def derived_graph(self, path: str | None = None) -> dict[str, object]:
        """Expose dependency-tracked derived CodeMap surfaces for diagnostics.

        Retrieval does not consume this graph yet; 0.10.8 records identities and
        dependencies only so later invalidation work has a measured foundation.
        """
        self = cast("CodeMap", self)
        self.reads.ready()
        normalized = (
            None if path is None else normalize_relative_path(path, allow_root=False)
        )
        if normalized is not None:
            self.source.ensure_current(normalized)
        nodes = self.store.derived_nodes(normalized)
        return {
            "schema": "hashmarks.codemap-derived-graph.v1",
            "generation": self.store.generation(),
            "path": normalized,
            "nodes": nodes,
        }

    def status(self) -> dict[str, object]:
        self = cast("CodeMap", self)
        watch_record = self.index.watch_continuity()
        generation, identity_generation, stale = (
            self.reads.generation_status_with_watch(None, watch_record)
        )
        return {
            "schema": "hashmarks.codemap-status.v1",
            "workspace": str(self.workspace),
            "state_dir": str(self.state_dir),
            "generation": generation,
            "identity_generation_at_sync": identity_generation,
            "daemon_generation_changed": stale,
            "workspace_fingerprint": self.store.meta("workspace_fingerprint"),
            "last_sync_unix": None
            if self.store.meta("last_sync_unix") is None
            else float(self.store.meta("last_sync_unix") or 0),
            "artifact_db": str(self.artifacts.db_path),
            "artifact_count": self.artifacts.count(),
            "build": self.index._codemap_build_state(),
            "last_index_economics": (
                json.loads(self.store.meta("sync.economics") or "null")
                if self.store.meta("sync.economics")
                else None
            ),
            "precision_providers": [
                self.index.range_provider.status().as_dict(),
                self.structure.search_provider.status().as_dict(),
                {
                    "name": self.native.producers.typescript.name,
                    "available": self.native.producers.typescript.detect(
                        self.workspace
                    ),
                    "version": None,
                    "detail": None,
                },
                *[
                    {
                        "name": provider.name,
                        "available": provider.detect(self.workspace),
                        "version": None,
                        "detail": None,
                    }
                    for provider in self.native.producers.projects
                ],
            ],
            "native_evidence": self.native.status(),
            "watcher": watch_status_projection(watch_record),
            **self.store.stats(),
        }
