from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from hashmarks.paths import normalize_relative_path

from .decision_session import diagnostic_producer
from .model import EvidenceVisibility
from .project_impact_codec import compact_project_impact
from .repository_domains import RepositoryDomain, classify_repository_path

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .engine import CodeMap


@dataclass(frozen=True)
class ChangeImpactOptions:
    """Bounds and encoding for one caller-reported change-impact projection."""

    impact_limit_per_surface: int = 6
    max_depth: int = 4
    project_impact_limit: int | None = None
    project_impact_encoding: str = "verbose"

    def validate(self) -> None:
        if self.impact_limit_per_surface < 1:
            raise ValueError("impact_limit_per_surface must be >= 1")
        if self.max_depth < 1:
            raise ValueError("max_depth must be >= 1")
        if self.project_impact_limit is not None and self.project_impact_limit < 1:
            raise ValueError("project_impact_limit must be >= 1")
        if self.project_impact_encoding not in {"verbose", "compact"}:
            raise ValueError("project_impact_encoding must be verbose or compact")

    @property
    def effective_project_impact_limit(self) -> int:
        return (
            self.impact_limit_per_surface
            if self.project_impact_limit is None
            else self.project_impact_limit
        )


@dataclass(frozen=True)
class _ImpactCandidate:
    path: str
    depth: int
    reason: str
    relation: str | None = None
    force_role: str | None = None
    verification: dict[str, object] | None = None


@dataclass
class _ImpactState:
    """Request-local bounds and accumulated repository impact evidence."""

    owner: CodeMap
    changed: tuple[str, ...]
    per_surface_limit: int
    surfaces: dict[str, list[dict[str, object]]] = field(
        default_factory=lambda: {
            role: []
            for role in (
                "implementation",
                "contract",
                "verification",
                "build_config",
                "orientation",
                "other",
            )
        }
    )
    seen: set[tuple[str, str]] = field(default_factory=set)
    impacted_projects: set[str] = field(default_factory=set)
    project_roots: set[str] = field(default_factory=set)
    project_depths: dict[str, int] = field(default_factory=dict)
    project_edges: dict[tuple[str, str, str, str], dict[str, object]] = field(
        default_factory=dict
    )

    @staticmethod
    def roles(path: str) -> tuple[str, ...]:
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

    def visible(self, path: str) -> bool:
        row = self.owner._session_file_row(path)
        return (
            row is not None
            and EvidenceVisibility(str(row["evidence_visibility"]))
            is not EvidenceVisibility.DENY
        )

    def _promote_verification(
        self, role: str, path: str, verification: dict[str, object]
    ) -> None:
        for existing in self.surfaces[role]:
            if str(existing.get("path") or "") == path:
                existing["verify"] = verification
                existing["selected"] = True
                break

    def add(self, candidate: _ImpactCandidate) -> None:
        path = candidate.path
        if not path or path in self.changed or not self.visible(path):
            return
        roles = (
            (candidate.force_role,)
            if candidate.force_role is not None
            else self.roles(path)
        )
        for role in roles:
            if (
                role not in self.surfaces
                or len(self.surfaces[role]) >= self.per_surface_limit
            ):
                continue
            key = (role, path)
            if key in self.seen:
                if candidate.verification:
                    self._promote_verification(role, path, candidate.verification)
                continue
            row: dict[str, object] = {
                "path": path,
                "depth": int(candidate.depth),
                "via": candidate.reason,
            }
            if candidate.relation:
                row["relation"] = candidate.relation
            if candidate.verification:
                row["verify"] = candidate.verification
                row["selected"] = True
            self.surfaces[role].append(row)
            self.seen.add(key)

    def merge_project_fragment(self, fragment: dict[str, Any]) -> None:
        self.project_roots.update(
            str(value) for value in fragment.get("roots", []) if value
        )
        for row in fragment.get("affected", []):
            if not isinstance(row, dict):
                continue
            project = str(row.get("project") or "")
            depth = int(row.get("depth") or 0)
            if project and depth > 0:
                self.project_depths[project] = min(
                    depth, self.project_depths.get(project, depth)
                )
        for row in fragment.get("edges", []):
            if not isinstance(row, dict):
                continue
            key = (
                str(row.get("from") or ""),
                str(row.get("to") or ""),
                str(row.get("kind") or ""),
                str(row.get("producer") or ""),
            )
            if key[0] and key[1]:
                self.project_edges[key] = dict(row)

    def merge_reverse_impact(self, impact: dict[str, Any]) -> None:
        self.impacted_projects.update(
            str(value) for value in impact.get("affected_projects", [])
        )
        impact_surfaces = impact.get("surfaces")
        if not isinstance(impact_surfaces, dict):
            return
        for role, rows in impact_surfaces.items():
            if role not in self.surfaces or not isinstance(rows, list):
                continue
            for row in rows:
                if isinstance(row, dict):
                    self.add(
                        _ImpactCandidate(
                            str(row.get("path") or ""),
                            int(row.get("depth") or 1),
                            "reverse-impact",
                            relation=str(row.get("relation") or "") or None,
                            force_role=role,
                        )
                    )

    def project_impact(self, encoding: str) -> dict[str, object] | None:
        if not self.project_depths:
            return None
        verbose: dict[str, object] = {
            "roots": sorted(self.project_roots),
            "affected": [
                {"project": project, "depth": self.project_depths[project]}
                for project in sorted(
                    self.project_depths,
                    key=lambda value: (self.project_depths[value], value),
                )
            ],
            "edges": [self.project_edges[key] for key in sorted(self.project_edges)],
            "reported_affected": len(self.project_depths),
            "total_affected": len(self.impacted_projects),
            "complete": set(self.project_depths) >= self.impacted_projects,
        }
        return compact_project_impact(verbose) if encoding == "compact" else verbose


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
                    "warnings": list(
                        cast("Sequence[object]", refreshed.get("warnings") or ())
                    ),
                }
        return None

    def _change_impact_surface_state(
        self,
        normalized: tuple[str, ...],
        *,
        max_depth: int,
        impact_limit_per_surface: int,
        effective_project_impact_limit: int,
    ) -> _ImpactState:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        state = _ImpactState(self, normalized, impact_limit_per_surface)
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
                state.merge_project_fragment(fragment)
            try:
                impact = self.change_impact(
                    changed,
                    max_depth=max_depth,
                    limit_per_surface=impact_limit_per_surface,
                )
            except KeyError:
                continue
            state.merge_reverse_impact(impact)
        return state

    def _change_impact_owner_cache_key(
        self, task: str, action: dict[str, object]
    ) -> tuple[int, str, int, int] | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if self._decision_session_depth <= 0:
            return None
        bounds = action.get("bounds")
        limit = int(bounds.get("limit", 20)) if isinstance(bounds, dict) else 20
        per_role = int(bounds.get("per_role", 3)) if isinstance(bounds, dict) else 3
        generation = int(self._decision_session_generation or self.store.generation())
        return generation, task, limit, per_role

    def _same_package_go_owner(self, verify_path: str, visible) -> str | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        parent = Path(verify_path).parent
        siblings = [
            candidate
            for candidate in self.store.paths_under(parent.as_posix())
            if candidate.endswith(".go")
            and not candidate.endswith("_test.go")
            and Path(candidate).parent == parent
            and visible(candidate)
        ]
        return siblings[0] if len(siblings) == 1 else None

    def _reconstruct_change_impact_owner_edges(
        self, task: str, edit_path: str, verify_path: str, visible
    ) -> list[dict[str, object]] | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        starts = [verify_path]
        if verify_path.endswith("_test.go"):
            same_package = self._same_package_go_owner(verify_path, visible)
            if same_package is not None:
                starts.insert(0, same_package)
        for start in starts:
            try:
                reconstructed = self.ownership_relation_graph(task, start, max_depth=3)
            except (KeyError, PermissionError, ValueError):
                continue
            candidate_edges = reconstructed.get("owner_path")
            if (
                str(reconstructed.get("selected") or "") == edit_path
                and isinstance(candidate_edges, list)
                and candidate_edges
            ):
                return candidate_edges
        return None

    @staticmethod
    def _owner_chain_from_edges(
        owner_edges: object,
    ) -> tuple[list[str], dict[tuple[str, str], str]]:
        chain: list[str] = []
        relations: dict[tuple[str, str], str] = {}
        if not isinstance(owner_edges, list):
            return chain, relations
        for index, edge in enumerate(owner_edges):
            if not isinstance(edge, dict):
                continue
            source = str(edge.get("from") or "")
            target = str(edge.get("to") or "")
            if index == 0 and source:
                chain.append(source)
            if target:
                chain.append(target)
            if source and target:
                relations[(source, target)] = str(edge.get("relation") or "related")
        return chain, relations

    def _change_impact_owner_chain(self, task: str, action: dict[str, object], visible):
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        cache_key = self._change_impact_owner_cache_key(task, action)
        if cache_key is not None:
            cached = self._decision_change_impact_owner_chain_cache.get(cache_key)
            if cached is not None:
                self._decision_session_stats["impact_owner_chain_hit"] += 1
                return deepcopy(cached)
            self._decision_session_stats["impact_owner_chain_miss"] += 1

        ownership = action.get("ownership_resolution")
        owner_edges = (
            ownership.get("owner_path") if isinstance(ownership, dict) else None
        )
        raw_edit = action.get("edit")
        edit = raw_edit if isinstance(raw_edit, dict) else None
        edit_path = str(edit.get("path") or "") if edit else ""
        raw_verify = action.get("verify")
        verify = raw_verify if isinstance(raw_verify, dict) else None
        verify_path = str(verify.get("path") or "") if verify else ""
        if (
            (not isinstance(owner_edges, list) or not owner_edges)
            and edit_path
            and verify_path
        ):
            owner_edges = self._reconstruct_change_impact_owner_edges(
                task, edit_path, verify_path, visible
            )
        chain, relations = self._owner_chain_from_edges(owner_edges)
        result = (edit_path, verify, verify_path, chain, relations)
        if cache_key is not None:
            self._decision_change_impact_owner_chain_cache[cache_key] = deepcopy(result)
        return result

    @staticmethod
    def _apply_owner_path_impact(
        state: _ImpactState,
        chain: list[str],
        edge_relations: dict[tuple[str, str], str],
    ) -> None:
        for changed in state.changed:
            if changed not in chain:
                continue
            changed_index = chain.index(changed)
            for index in range(changed_index - 1, -1, -1):
                path = chain[index]
                state.add(
                    _ImpactCandidate(
                        path,
                        changed_index - index,
                        "task-owner-path",
                        relation=edge_relations.get((path, chain[index + 1])),
                    )
                )

    def _apply_selected_verification_impact(
        self,
        state: _ImpactState,
        edit_path: str,
        verify: dict[str, object] | None,
        verify_path: str,
        chain: list[str],
    ) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        changed_hits_task = edit_path in state.changed or any(
            path in state.changed for path in chain
        )
        if not changed_hits_task or verify is None:
            return
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
        state.add(
            _ImpactCandidate(
                verify_path,
                1,
                "task-selected-verification",
                force_role="verification",
                verification=verification_meta,
            )
        )

    @staticmethod
    def _project_change_impact(
        state: _ImpactState,
        generation: int,
        options: ChangeImpactOptions,
        declared_refresh: dict[str, object] | None,
    ) -> dict[str, object]:
        changed_roles = [
            {"path": path, "roles": list(state.roles(path))}
            for path in state.changed
            if state.visible(path)
        ]
        result: dict[str, object] = {
            "schema": "hashmarks.task-change-impact.v1",
            "generation": generation,
            "changed": changed_roles,
            "surfaces": {key: rows for key, rows in state.surfaces.items() if rows},
            "bounds": {
                "depth": options.max_depth,
                "per_surface": options.impact_limit_per_surface,
                "project_impact": options.effective_project_impact_limit,
            },
            "authority": "advisory",
            "owner": "external",
            "completeness": "not-claimed",
        }
        if state.impacted_projects:
            result["projects"] = sorted(state.impacted_projects)
        project_impact = state.project_impact(options.project_impact_encoding)
        if project_impact is not None:
            result["project_impact"] = project_impact
        if declared_refresh is not None:
            if not declared_refresh.get("warnings"):
                declared_refresh.pop("warnings", None)
            result["project_refresh"] = declared_refresh
        return result

    @diagnostic_producer
    def task_change_impact(
        self,
        task: str,
        changed_paths: Sequence[str | Path],
        *,
        limit: int = 20,
        per_role: int = 3,
        options: ChangeImpactOptions = ChangeImpactOptions(),
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
        options.validate()
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
        state = self._change_impact_surface_state(
            normalized,
            max_depth=options.max_depth,
            impact_limit_per_surface=options.impact_limit_per_surface,
            effective_project_impact_limit=options.effective_project_impact_limit,
        )
        edit_path, verify, verify_path, chain, edge_relations = (
            self._change_impact_owner_chain(task, action, state.visible)
        )
        self._apply_owner_path_impact(state, chain, edge_relations)
        self._apply_selected_verification_impact(
            state, edit_path, verify, verify_path, chain
        )
        return self._project_change_impact(
            state, sync_result.generation, options, declared_refresh
        )
