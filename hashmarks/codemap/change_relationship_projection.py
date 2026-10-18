from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict

from .repository_domains import RepositoryDomain, classify_repository_path


class ChangeRelationshipObservation(TypedDict):
    schema: str
    query: str
    generation: object
    identity_generation: object
    stale: object
    roots: list[str]
    surfaces: dict[str, list[dict[str, object]]]
    affected_projects: object
    root_projects: object
    bounds: dict[str, int]
    evidence: str
    authority: str


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


def _change_impact_depths(
    roots: set[str],
    levels: list[list[str]],
) -> dict[str, int]:
    depth_by_path: dict[str, int] = dict.fromkeys(roots, 0)
    for depth, level in enumerate(levels, start=1):
        for path in level:
            depth_by_path.setdefault(path, depth)
    return depth_by_path


def _change_impact_relation(row: dict[str, object]) -> str | None:
    provenance_rows = row.get("provenance")
    if (
        isinstance(provenance_rows, list)
        and provenance_rows
        and isinstance(provenance_rows[0], dict)
    ):
        return str(provenance_rows[0].get("relation") or "") or None
    return None


def project_change_relationships(
    query: str,
    value: dict[str, object],
    adjacency: dict[str, object],
    *,
    max_depth: int,
    limit_per_surface: int,
) -> ChangeRelationshipObservation:
    root_values, level_values = value["roots"], value["levels"]
    assert isinstance(root_values, list) and isinstance(level_values, list)
    assert all(isinstance(level, list) for level in level_values)
    roots = {str(path) for path in root_values}
    levels = [list(map(str, level)) for level in level_values]
    depth_by_path = _change_impact_depths(roots, levels)
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

    adjacent = adjacency["adjacent"]
    assert isinstance(adjacent, list)
    for row in adjacent:
        if not isinstance(row, dict):
            continue
        accumulator.add(
            str(row.get("path") or ""),
            depth=1,
            provenance="task-graph-adjacency",
            relation=_change_impact_relation(row),
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
