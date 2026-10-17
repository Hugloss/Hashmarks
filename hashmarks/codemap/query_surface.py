from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from hashmarks.operation_contract import operation_response, operation_schema
from hashmarks.paths import normalize_relative_path

from .decision_session import ReadScopeOwner, decision_scoped
from .model import EvidenceVisibility
from .repository_domains import RepositoryDomain, classify_repository_path
from .watch_continuity import watch_status_projection

if TYPE_CHECKING:
    from .engine import CodeMap


_CHANGE_IMPACT_SURFACES = (
    "implementation",
    "contract",
    "verification",
    "build_config",
    "orientation",
    "other",
)


def _change_impact_roles(path: str) -> tuple[str, ...]:
    domains = set(classify_repository_path(path))
    roles: list[str] = []
    if RepositoryDomain.TEST in domains:
        roles.append("verification")
    if domains & {RepositoryDomain.CONTRACT, RepositoryDomain.OWNERSHIP}:
        roles.append("contract")
    if domains & {
        RepositoryDomain.BUILD,
        RepositoryDomain.CONFIG,
        RepositoryDomain.PLAN,
        RepositoryDomain.SCRIPT,
    }:
        roles.append("build_config")
    if domains & {RepositoryDomain.ARCHITECTURE, RepositoryDomain.DOC}:
        roles.append("orientation")
    if RepositoryDomain.SOURCE in domains and RepositoryDomain.TEST not in domains:
        roles.append("implementation")
    return tuple(dict.fromkeys(roles)) or ("other",)


@dataclass
class _ChangeImpactAccumulator:
    roots: set[str]
    limit_per_surface: int
    surfaces: dict[str, list[dict[str, object]]] = field(
        default_factory=lambda: {key: [] for key in _CHANGE_IMPACT_SURFACES}
    )
    seen: set[tuple[str, str]] = field(default_factory=set)

    def add(
        self,
        path: str,
        *,
        depth: int,
        provenance: str,
        relation: str | None = None,
    ) -> None:
        if path in self.roots:
            return
        domains = [domain.value for domain in classify_repository_path(path)]
        for role in _change_impact_roles(path):
            key = (role, path)
            if key in self.seen or len(self.surfaces[role]) >= self.limit_per_surface:
                continue
            row: dict[str, object] = {
                "path": path,
                "depth": depth,
                "domains": domains,
                "provenance": provenance,
            }
            if relation is not None:
                row["relation"] = relation
            self.surfaces[role].append(row)
            self.seen.add(key)


class QuerySurfaceMixin(ReadScopeOwner):
    @operation_response("projects")
    @decision_scoped
    def projects(self) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self.reads.ready()
        return {
            "schema": operation_schema("projects"),
            **self.reads.freshness_fields(),
            "projects": self._fresh_project_nodes(),
            "edges": self._fresh_project_edges(),
            "native_file_edges": self._fresh_native_file_edges(),
            "last_enriched_unix": None
            if self.store.meta("project_graph_last_sync_unix") is None
            else float(self.store.meta("project_graph_last_sync_unix") or 0),
        }

    @operation_response("structural")
    @decision_scoped
    def structural(
        self, pattern: str, *, language: str | None = None, limit: int = 100
    ) -> dict[str, object]:
        """Syntax-aware search through an optional local ast-grep authority."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self.reads.ready()
        raw, warnings = self.structural_search_provider.search(
            self.workspace, pattern, language=language, limit=max(limit * 4, limit)
        )
        matches: list[dict[str, object]] = []
        for row in raw:
            raw_path = row.get("file")
            if not raw_path:
                continue
            try:
                rel = normalize_relative_path(
                    str(raw_path).replace("\\", "/"), allow_root=False
                )
            except ValueError:
                continue
            mapped = self.reads.file_row(rel)
            if mapped is None:
                continue
            visibility = EvidenceVisibility(str(mapped["evidence_visibility"]))
            # ast-grep's match text is implementation content, so outline-only
            # files are intentionally not disclosed by this operation.
            if visibility is not EvidenceVisibility.SOURCE:
                continue
            range_value = row.get("range") if isinstance(row.get("range"), dict) else {}
            start_value = (
                range_value.get("start") if isinstance(range_value, dict) else {}
            )
            end_value = range_value.get("end") if isinstance(range_value, dict) else {}
            matches.append(
                {
                    "path": rel,
                    "text": str(row.get("text") or ""),
                    "language": row.get("language"),
                    "range": [
                        int((start_value or {}).get("line", 0)) + 1,
                        int((end_value or {}).get("line", 0)) + 1,
                    ],
                    "producer": "ast-grep",
                }
            )
            if len(matches) >= limit:
                break
        return {
            "schema": operation_schema("structural"),
            **self.reads.freshness_fields(),
            "pattern": pattern,
            "available": self.structural_search_provider.available,
            "provider": self.structural_search_provider.status().as_dict(),
            "matches": matches,
            "warnings": list(warnings),
        }

    def _affected_roots(self, query: str) -> set[str]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        roots = self._query_paths(query)
        if roots:
            return roots
        try:
            rel_query = normalize_relative_path(query, allow_root=False)
        except ValueError:
            rel_query = None
        candidate = None if rel_query is None else self.workspace / rel_query
        if (
            rel_query is not None
            and candidate is not None
            and candidate.is_file()
            and not candidate.is_symlink()
        ):
            return {rel_query}
        raise KeyError(f"path or symbol not found: {query}")

    def _affected_levels(
        self,
        roots: set[str],
        *,
        max_depth: int,
    ) -> tuple[list[list[str]], set[str]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        levels = self._python_reverse_levels(roots, max_depth=max_depth)
        if levels is not None:
            seen = set(roots)
            for level in levels:
                seen.update(level)
            return levels, seen

        reverse = self._reverse_file_graph()

        seen = set(roots)
        frontier = set(roots)
        resolved: list[list[str]] = []
        for _ in range(max_depth):
            next_frontier: set[str] = set()
            for path in frontier:
                next_frontier.update(reverse.get(path, ()))
            next_frontier -= seen
            if not next_frontier:
                break
            resolved.append(sorted(next_frontier))
            seen.update(next_frontier)
            frontier = next_frontier
        return resolved, seen

    @operation_response("affected")
    @decision_scoped
    def affected(self, query: str, *, max_depth: int = 12) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self.reads.ready()
        roots = self._affected_roots(query)
        levels, seen = self._affected_levels(roots, max_depth=max_depth)
        affected = sorted(seen - roots)
        tests = [path for path in affected if self._is_test_path(path)]
        root_projects = {
            str(project["project_id"])
            for path in roots
            for project in self._fresh_projects_for_path(path)[:1]
        }
        impacted_projects = (
            self._fresh_project_dependents(root_projects, max_depth=max_depth)
            if root_projects
            else set()
        )
        return {
            "schema": operation_schema("affected"),
            "query": query,
            **self.reads.freshness_fields(),
            "roots": sorted(roots),
            "affected_files": affected,
            "tests": tests,
            "levels": levels,
            "root_projects": sorted(root_projects),
            "affected_projects": sorted(impacted_projects - root_projects),
            "evidence": "static import graph plus retained native/manifest project graph when available; advisory and conservative",
        }

    @operation_response("tests")
    @decision_scoped
    def tests(self, query: str, *, max_depth: int = 12) -> dict[str, object]:
        value = self.affected(query, max_depth=max_depth)
        return {
            "schema": operation_schema("tests"),
            "query": query,
            "generation": value["generation"],
            "identity_generation": value["identity_generation"],
            "stale": value["stale"],
            "roots": value["roots"],
            "tests": value["tests"],
            "affected_files": value["affected_files"],
            "evidence": value["evidence"],
        }

    @staticmethod
    def _change_impact_depths(
        roots: set[str],
        levels: list[list[str]],
    ) -> dict[str, int]:
        depth_by_path: dict[str, int] = dict.fromkeys(roots, 0)
        for depth, level in enumerate(levels, start=1):
            for path in level:
                depth_by_path.setdefault(path, depth)
        return depth_by_path

    def _change_impact_adjacency(
        self,
        query: str,
        roots: set[str],
        *,
        limit_per_surface: int,
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        adjacency_limit = max(12, limit_per_surface * 2)
        exact_path_roots = self._query_paths(query)
        if len(exact_path_roots) == 1 and exact_path_roots == roots:
            try:
                normalized_query = normalize_relative_path(query, allow_root=False)
            except ValueError:
                normalized_query = ""
            if normalized_query in roots:
                return self._path_graph_adjacency(
                    query,
                    roots,
                    limit=adjacency_limit,
                )
        return self.task_graph_adjacency(
            query,
            seed_limit=min(12, max(4, limit_per_surface)),
            limit=adjacency_limit,
        )

    @staticmethod
    def _change_impact_relation(row: dict[str, object]) -> str | None:
        provenance_rows = row.get("provenance")
        if (
            isinstance(provenance_rows, list)
            and provenance_rows
            and isinstance(provenance_rows[0], dict)
        ):
            return str(provenance_rows[0].get("relation") or "") or None
        return None

    @decision_scoped
    def change_impact(
        self, query: str, *, max_depth: int = 4, limit_per_surface: int = 20
    ) -> dict[str, object]:
        """Project proven change relationships into bounded repository surfaces.

        Reverse dependency reachability and the existing one-hop task graph are
        combined as separate provenance lanes. The API is additive navigation
        only: it does not alter ``find``/``find_task`` ranking or infer fuzzy
        relationships.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if limit_per_surface < 1:
            raise ValueError("limit_per_surface must be >= 1")
        value = self.affected(query, max_depth=max_depth)
        root_values, level_values = value["roots"], value["levels"]
        assert isinstance(root_values, list) and isinstance(level_values, list)
        assert all(isinstance(level, list) for level in level_values)
        roots = {str(path) for path in root_values}
        levels = [list(map(str, level)) for level in level_values]
        depth_by_path = self._change_impact_depths(roots, levels)
        accumulator = _ChangeImpactAccumulator(roots, limit_per_surface)

        for path in sorted(
            depth_by_path,
            key=lambda item: (depth_by_path[item], item),
        ):
            accumulator.add(
                path,
                depth=depth_by_path[path],
                provenance="reverse-file-graph",
            )

        adjacency = self._change_impact_adjacency(
            query,
            roots,
            limit_per_surface=limit_per_surface,
        )
        adjacent = adjacency["adjacent"]
        assert isinstance(adjacent, list)
        for row in adjacent:
            if not isinstance(row, dict):
                continue
            accumulator.add(
                str(row.get("path") or ""),
                depth=1,
                provenance="task-graph-adjacency",
                relation=self._change_impact_relation(row),
            )

        return {
            "schema": "hashmarks.codemap-change-impact.v1",
            "query": query,
            "generation": value["generation"],
            "identity_generation": value["identity_generation"],
            "stale": value["stale"],
            "roots": sorted(roots),
            "surfaces": accumulator.surfaces,
            "affected_projects": value["affected_projects"],
            "root_projects": value["root_projects"],
            "bounds": {
                "max_depth": max_depth,
                "limit_per_surface": limit_per_surface,
                "adjacency_max_hops": 1,
            },
            "evidence": str(value["evidence"]) + "; plus bounded task graph adjacency",
            "authority": "advisory-navigation-only",
        }

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
                self.structural_search_provider.status().as_dict(),
                {
                    "name": self.typescript_resolver.name,
                    "available": self.typescript_resolver.detect(self.workspace),
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
                    for provider in self.project_graph_providers
                ],
            ],
            "native_evidence": self._native_evidence_status(),
            "watcher": watch_status_projection(watch_record),
            **self.store.stats(),
        }
