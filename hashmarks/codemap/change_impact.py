from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, cast

from hashmarks.paths import normalize_relative_path

from .decision_session import diagnostic_producer
from .model import EvidenceVisibility
from .project_impact_codec import compact_project_impact
from .repository_domains import RepositoryDomain, classify_repository_path

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .engine import CodeMap


class ChangeImpactMixin:
    def _refresh_declared_project_impact(
        self, normalized: tuple[str, ...]
    ) -> dict[str, object] | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        fresh, freshness_reason = self._evidence_fresh(
            "project", "declared-project-links"
        )
        if (
            fresh
            or not freshness_reason
            or not freshness_reason.startswith("manifest changed: ")
        ):
            return None
        changed_manifests = self._evidence_manifest_changes(
            "project", "declared-project-links"
        )
        declared_file = ".hashmarks-project-links.toml"
        reported = set(normalized)
        shared_only = bool(changed_manifests) and all(
            rel != declared_file
            and rel in reported
            and self._declared_project_shared_input(rel)
            for rel in changed_manifests
        )
        if shared_only and self._rebind_declared_project_freshness():
            return {
                "producer": "declared-project-links",
                "reason": "caller-reported-shared-input-changed",
                "changed": changed_manifests[0],
                "changed_manifests": list(changed_manifests),
                "mode": "freshness-rebind",
                "warnings": [],
            }
        if declared_file not in changed_manifests or declared_file not in reported:
            return None
        for provider in self.project_graph_providers:
            if provider.name == "declared-project-links" and provider.detect(
                self.workspace
            ):
                refreshed = self.enrich_projects(("declared-project-links",))
                return {
                    "producer": "declared-project-links",
                    "reason": "caller-reported-declaration-changed",
                    "changed": declared_file,
                    "changed_manifests": list(changed_manifests),
                    "mode": "topology-recollect",
                    "warnings": list(refreshed.get("warnings") or ()),
                }
        return None

    def _change_impact_surface_state(
        self,
        normalized: tuple[str, ...],
        *,
        max_depth: int,
        impact_limit_per_surface: int,
        effective_project_impact_limit: int,
    ):
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        surfaces: dict[str, list[dict[str, object]]] = {
            key: []
            for key in (
                "implementation",
                "contract",
                "verification",
                "build_config",
                "orientation",
                "other",
            )
        }
        seen: set[tuple[str, str]] = set()
        impacted_projects: set[str] = set()
        project_roots: set[str] = set()
        project_depths: dict[str, int] = {}
        project_edges: dict[tuple[str, str, str, str], dict[str, object]] = {}

        def roles(path: str) -> tuple[str, ...]:
            domains = set(classify_repository_path(path))
            out: list[str] = []
            if RepositoryDomain.TEST in domains:
                out.append("verification")
            if domains & {RepositoryDomain.CONTRACT, RepositoryDomain.OWNERSHIP}:
                out.append("contract")
            if domains & {
                RepositoryDomain.BUILD,
                RepositoryDomain.CONFIG,
                RepositoryDomain.PLAN,
                RepositoryDomain.SCRIPT,
            }:
                out.append("build_config")
            if domains & {RepositoryDomain.ARCHITECTURE, RepositoryDomain.DOC}:
                out.append("orientation")
            if (
                RepositoryDomain.SOURCE in domains
                and RepositoryDomain.TEST not in domains
            ):
                out.append("implementation")
            return tuple(dict.fromkeys(out)) or ("other",)

        def visible(path: str) -> bool:
            row = self._session_file_row(path)
            return (
                row is not None
                and EvidenceVisibility(str(row["evidence_visibility"]))
                is not EvidenceVisibility.DENY
            )

        def add(
            path: str,
            *,
            depth: int,
            reason: str,
            relation: str | None = None,
            force_role: str | None = None,
            verification: dict[str, object] | None = None,
        ) -> None:
            if not path or path in normalized or not visible(path):
                return
            role_values = (force_role,) if force_role is not None else roles(path)
            for role in role_values:
                if (
                    role not in surfaces
                    or len(surfaces[role]) >= impact_limit_per_surface
                ):
                    continue
                key = (role, path)
                if key in seen:
                    if verification:
                        for existing in surfaces[role]:
                            if str(existing.get("path") or "") == path:
                                existing["verify"] = verification
                                existing["selected"] = True
                                break
                    continue
                row: dict[str, object] = {
                    "path": path,
                    "depth": int(depth),
                    "via": reason,
                }
                if relation:
                    row["relation"] = relation
                if verification:
                    row["verify"] = verification
                    row["selected"] = True
                surfaces[role].append(row)
                seen.add(key)

        for changed in normalized:
            root_projects = {
                str(row.get("project_id") or "")
                for row in self._fresh_projects_for_path(changed)[:1]
                if str(row.get("project_id") or "")
            }
            if root_projects:
                fragment = self._fresh_project_dependents_with_provenance(
                    root_projects,
                    max_depth=max_depth,
                    limit=effective_project_impact_limit,
                )
                project_roots.update(
                    str(value) for value in fragment.get("roots", []) if value
                )
                for row in fragment.get("affected", []):
                    if isinstance(row, dict):
                        project, depth = (
                            str(row.get("project") or ""),
                            int(row.get("depth") or 0),
                        )
                        if project and depth > 0:
                            project_depths[project] = min(
                                depth, project_depths.get(project, depth)
                            )
                for row in fragment.get("edges", []):
                    if isinstance(row, dict):
                        key = (
                            str(row.get("from") or ""),
                            str(row.get("to") or ""),
                            str(row.get("kind") or ""),
                            str(row.get("producer") or ""),
                        )
                        if key[0] and key[1]:
                            project_edges[key] = dict(row)
            try:
                impact = self.change_impact(
                    changed,
                    max_depth=max_depth,
                    limit_per_surface=impact_limit_per_surface,
                )
            except KeyError:
                continue
            impacted_projects.update(
                str(value) for value in impact.get("affected_projects", [])
            )
            impact_surfaces = impact.get("surfaces")
            if isinstance(impact_surfaces, dict):
                for role, rows in impact_surfaces.items():
                    if role not in surfaces or not isinstance(rows, list):
                        continue
                    for row in rows:
                        if isinstance(row, dict):
                            add(
                                str(row.get("path") or ""),
                                depth=int(row.get("depth") or 1),
                                reason="reverse-impact",
                                relation=str(row.get("relation") or "") or None,
                                force_role=role,
                            )
        return (
            surfaces,
            impacted_projects,
            project_roots,
            project_depths,
            project_edges,
            roles,
            visible,
            add,
        )

    def _change_impact_owner_chain(
        self, task: str, action: dict[str, object], normalized: tuple[str, ...], visible
    ):
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        owner_chain_key = None
        if self._decision_session_depth > 0:
            bounds = action.get("bounds")
            limit = int(bounds.get("limit", 20)) if isinstance(bounds, dict) else 20
            per_role = int(bounds.get("per_role", 3)) if isinstance(bounds, dict) else 3
            generation = int(
                self._decision_session_generation or self.store.generation()
            )
            owner_chain_key = (generation, task, limit, per_role)
            cached = self._decision_change_impact_owner_chain_cache.get(owner_chain_key)
            if cached is not None:
                self._decision_session_stats["impact_owner_chain_hit"] += 1
                return deepcopy(cached)
            self._decision_session_stats["impact_owner_chain_miss"] += 1

        ownership = action.get("ownership_resolution")
        owner_edges = (
            ownership.get("owner_path") if isinstance(ownership, dict) else None
        )
        edit = action.get("edit") if isinstance(action.get("edit"), dict) else None
        edit_path = str(edit.get("path") or "") if edit else ""
        verify = (
            action.get("verify") if isinstance(action.get("verify"), dict) else None
        )
        verify_path = str(verify.get("path") or "") if verify else ""
        if (
            (not isinstance(owner_edges, list) or not owner_edges)
            and edit_path
            and verify_path
        ):
            starts = [verify_path]
            if verify_path.endswith("_test.go"):
                parent = Path(verify_path).parent
                siblings = [
                    candidate
                    for candidate in self.store.paths_under(parent.as_posix())
                    if candidate.endswith(".go")
                    and not candidate.endswith("_test.go")
                    and Path(candidate).parent == parent
                    and visible(candidate)
                ]
                if len(siblings) == 1:
                    starts.insert(0, siblings[0])
            for start in starts:
                try:
                    reconstructed = self.ownership_relation_graph(
                        task, start, max_depth=3
                    )
                except (KeyError, PermissionError, ValueError):
                    continue
                candidate_edges = reconstructed.get("owner_path")
                if (
                    str(reconstructed.get("selected") or "") == edit_path
                    and isinstance(candidate_edges, list)
                    and candidate_edges
                ):
                    owner_edges = candidate_edges
                    break
        chain: list[str] = []
        relations: dict[tuple[str, str], str] = {}
        if isinstance(owner_edges, list):
            for index, edge in enumerate(owner_edges):
                if not isinstance(edge, dict):
                    continue
                source, target = str(edge.get("from") or ""), str(edge.get("to") or "")
                if index == 0 and source:
                    chain.append(source)
                if target:
                    chain.append(target)
                if source and target:
                    relations[(source, target)] = str(edge.get("relation") or "related")
        result = (edit_path, verify, verify_path, chain, relations)
        if owner_chain_key is not None:
            self._decision_change_impact_owner_chain_cache[owner_chain_key] = deepcopy(
                result
            )
        return result

    @diagnostic_producer
    def task_change_impact(
        self,
        task: str,
        changed_paths: Sequence[str | Path],
        *,
        limit: int = 20,
        per_role: int = 3,
        impact_limit_per_surface: int = 6,
        max_depth: int = 4,
        project_impact_limit: int | None = None,
        project_impact_encoding: str = "verbose",
    ) -> dict[str, object]:
        """Expose bounded changed-code impact and verification relevance.

        This is repository evidence only.  The external consumer reports paths it
        changed; Hashmarks incrementally reconciles those paths, composes the
        existing reverse-impact surface with the already-proven task ownership
        path and verification authority, and returns only affected path facts.
        It does not choose a repair, execute tests, judge the patch, or schedule
        follow-up work.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if impact_limit_per_surface < 1:
            raise ValueError("impact_limit_per_surface must be >= 1")
        if max_depth < 1:
            raise ValueError("max_depth must be >= 1")
        if project_impact_limit is not None and project_impact_limit < 1:
            raise ValueError("project_impact_limit must be >= 1")
        if project_impact_encoding not in {"verbose", "compact"}:
            raise ValueError("project_impact_encoding must be verbose or compact")
        effective_project_impact_limit = (
            impact_limit_per_surface
            if project_impact_limit is None
            else project_impact_limit
        )
        normalized = tuple(
            dict.fromkeys(
                normalize_relative_path(path, allow_root=False)
                for path in changed_paths
            )
        )
        if not normalized:
            raise ValueError(
                "changed_paths must contain at least one repository-relative path"
            )

        # A standalone CLI/service call may arrive before a warm map exists.
        # Establish the repository map once, then keep the post-change refresh
        # bounded to the caller-reported paths.
        self._ensure_map_ready()
        sync_result = self.sync(normalized)

        # Declared project links are topology owned by the repository.  A
        # caller-reported edit to one of that provider's freshness-bound shared
        # inputs invalidates the old snapshot by design.  Recollect only this
        # cheap declarative provider so post-change impact can bind the same
        # declared topology to the current input bytes.  Other native/project
        # providers remain untouched.
        declared_refresh = self._refresh_declared_project_impact(normalized)

        action = self.task_action_map(task, limit=limit, per_role=per_role)
        (
            surfaces,
            impacted_projects,
            project_roots,
            project_depths,
            project_edges,
            roles,
            visible,
            add,
        ) = self._change_impact_surface_state(
            normalized,
            max_depth=max_depth,
            impact_limit_per_surface=impact_limit_per_surface,
            effective_project_impact_limit=effective_project_impact_limit,
        )
        edit_path, verify, verify_path, chain, edge_relations = (
            self._change_impact_owner_chain(task, action, normalized, visible)
        )
        for changed in normalized:
            if changed not in chain:
                continue
            changed_index = chain.index(changed)
            for index in range(changed_index - 1, -1, -1):
                path = chain[index]
                add(
                    path,
                    depth=changed_index - index,
                    reason="task-owner-path",
                    relation=edge_relations.get((path, chain[index + 1])),
                )

        changed_hits_task = edit_path in normalized or any(
            path in normalized for path in chain
        )
        if changed_hits_task and verify is not None:
            plan = self.verification_plan(
                verify_path,
                symbol=str(verify.get("verification_test_symbol") or "")
                or str(verify.get("name") or "")
                or None,
                qualname=str(verify.get("qualname") or "") or None,
            )
            verification_meta: dict[str, object] = {
                "available": bool(plan.get("available"))
            }
            for key in ("runner", "scope", "confidence"):
                if key in plan:
                    verification_meta[key] = plan[key]
            add(
                verify_path,
                depth=1,
                reason="task-selected-verification",
                force_role="verification",
                verification=verification_meta,
            )

        changed_roles = [
            {"path": path, "roles": list(roles(path))}
            for path in normalized
            if visible(path)
        ]
        compact_surfaces = {key: rows for key, rows in surfaces.items() if rows}
        result: dict[str, object] = {
            "schema": "hashmarks.task-change-impact.v1",
            "generation": sync_result.generation,
            "changed": changed_roles,
            "surfaces": compact_surfaces,
            "bounds": {
                "depth": max_depth,
                "per_surface": impact_limit_per_surface,
                "project_impact": effective_project_impact_limit,
            },
            "authority": "advisory",
            "owner": "external",
            # Surface rows are intentionally bounded by depth/per-surface limits.
            # Never let a consumer interpret the absence of additional rows as
            # proof that no additional impact exists outside those bounds.
            "completeness": "not-claimed",
        }
        if impacted_projects:
            result["projects"] = sorted(impacted_projects)
        if project_depths:
            complete_projects = set(project_depths) >= impacted_projects
            verbose_project_impact = {
                "roots": sorted(project_roots),
                "affected": [
                    {"project": project, "depth": project_depths[project]}
                    for project in sorted(
                        project_depths, key=lambda value: (project_depths[value], value)
                    )
                ],
                "edges": [project_edges[key] for key in sorted(project_edges)],
                "reported_affected": len(project_depths),
                "total_affected": len(impacted_projects),
                "complete": complete_projects,
            }
            result["project_impact"] = (
                compact_project_impact(verbose_project_impact)
                if project_impact_encoding == "compact"
                else verbose_project_impact
            )
        if declared_refresh is not None:
            if not declared_refresh.get("warnings"):
                declared_refresh.pop("warnings", None)
            result["project_refresh"] = declared_refresh
        return result
