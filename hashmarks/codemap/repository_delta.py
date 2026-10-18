from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from hashmarks.paths import normalize_relative_path

from .change_impact import ChangeImpactOptions
from .decision_session import ReadScopeOwner, diagnostic_producer
from .diagnostic_observation import (
    DIAGNOSTIC_DELTA_SCHEMA as DIAGNOSTIC_DELTA_SCHEMA,
)
from .diagnostic_observation import (
    RepositoryGenerationBinding as RepositoryGenerationBinding,
)
from .freshness_map import FreshnessMapOptions
from .repository_observation import (
    evidence_identity,
    packet_digest,
    repository_observer_packet,
)

REPOSITORY_DELTA_DEFAULT_OPTIONS = ChangeImpactOptions(
    impact_limit_per_surface=4,
    max_depth=3,
)

if TYPE_CHECKING:
    from pathlib import Path

    from .decision_session import ReadScope
    from .repository_changes import RepositoryChanges


@dataclass
class _SnapshotReuse:
    """Disposable snapshot reuse bound to one read scope."""

    scope: ReadScope | None = None
    entries: dict[
        tuple[int, str, tuple[str, ...], int, int, int, int], dict[str, object]
    ] = field(default_factory=dict)


REPOSITORY_SNAPSHOT_SCHEMA = "hashmarks.repository-intelligence-snapshot.v1"
REPOSITORY_DELTA_SCHEMA = "hashmarks.repository-intelligence-delta.v1"


class RepositoryDeltaMixin(ReadScopeOwner):
    """Bounded semantic snapshots and deltas over repository intelligence.

    Callers retain earlier producer snapshots and supply them after later
    repository state is admitted. Existing ownership, impact, verification, and
    freshness authority yields changed facts and compact summaries without
    a historical repository store.
    """

    @staticmethod
    def _delta_mapping(value: object, *, field: str) -> Mapping[str, object]:
        if not isinstance(value, Mapping):
            raise ValueError(f"{field} must be an object")
        return value

    def _snapshot_paths(
        self, changed_paths: Sequence[str | Path]
    ) -> dict[str, dict[str, object]]:
        if TYPE_CHECKING:
            self = cast("RepositoryChanges", self)
        paths = tuple(
            dict.fromkeys(
                normalize_relative_path(path, allow_root=False)
                for path in changed_paths
            )
        )
        if not paths:
            raise ValueError(
                "changed_paths must contain at least one repository-relative path"
            )
        symbols_by_path = self.store.symbols_for_paths_many(paths, limit_per_path=32)
        edges_by_path = self.reads.edges_for_paths_many(paths, limit_per_path=32)
        rows: dict[str, dict[str, object]] = {}
        for path in paths:
            member, _raw = self.source.member(path)
            revision = (
                str(member.get("member_revision") or "")
                if member.get("state") == "known-present"
                else None
            )
            symbols = sorted(
                (
                    {
                        **{
                            key: str(symbol[key])
                            for key in ("name", "qualname", "kind")
                            if symbol.get(key) is not None
                            and str(symbol.get(key) or "")
                        },
                        "identity": evidence_identity(
                            "hashmarks.symbol-evidence.v1",
                            {
                                "path": path,
                                **{
                                    key: str(symbol[key])
                                    for key in ("name", "qualname", "kind")
                                    if symbol.get(key) is not None
                                    and str(symbol.get(key) or "")
                                },
                            },
                        ),
                        "provenance": {
                            "source": "codemap-symbol-index",
                            "path": path,
                        },
                    }
                    for symbol in symbols_by_path.get(path, ())
                ),
                key=lambda row: (
                    row.get("qualname", ""),
                    row.get("name", ""),
                    row.get("kind", ""),
                ),
            )
            dependencies = sorted(
                (
                    {
                        **{
                            key: str(edge[key])
                            for key in ("source", "kind", "target", "confidence")
                            if edge.get(key) is not None and str(edge.get(key) or "")
                        },
                        "identity": evidence_identity(
                            "hashmarks.relationship-evidence.v1",
                            {
                                "path": path,
                                **{
                                    key: str(edge[key])
                                    for key in (
                                        "source",
                                        "kind",
                                        "target",
                                        "confidence",
                                    )
                                    if edge.get(key) is not None
                                    and str(edge.get(key) or "")
                                },
                            },
                        ),
                        "provenance": {
                            "source": "codemap-edge-index",
                            "path": path,
                        },
                    }
                    for edge in edges_by_path.get(path, ())
                    if edge.get("kind") and edge.get("target")
                ),
                key=lambda row: (
                    row.get("kind", ""),
                    row.get("source", ""),
                    row.get("target", ""),
                    row.get("confidence", ""),
                ),
            )
            rows[path] = {
                "member_state": member["state"],
                "revision": revision,
                "symbols": symbols,
                "dependencies": dependencies,
            }
        return rows

    @staticmethod
    def _snapshot_verification(brief: Mapping[str, object]) -> dict[str, object] | None:
        verification = brief.get("verification")
        if not isinstance(verification, Mapping):
            return None
        return {
            key: deepcopy(verification[key])
            for key in ("member", "test_symbol", "reason", "facts")
            if key in verification
        }

    @staticmethod
    def _snapshot_freshness(
        freshness: Mapping[str, object],
    ) -> dict[str, dict[str, object]]:
        entries = freshness.get("entries")
        if not isinstance(entries, list):
            return {}
        rows: dict[str, dict[str, object]] = {}
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            kind = str(entry.get("kind") or "")
            if not kind:
                continue
            member = str(entry.get("member") or "")
            key = kind if not member else f"{kind}:{member}"
            rows[key] = {
                field: deepcopy(entry[field])
                for field in ("state", "evidence_identity", "member", "reason")
                if field in entry
            }
        return rows

    @staticmethod
    def external_observation_freshness(
        observation: Mapping[str, object],
        *,
        current_repository_identity: str,
        current_generation: int,
        changed_paths: Sequence[str] = (),
        dependency_paths: Sequence[str] = (),
        change_set_complete: object = False,
    ) -> dict[str, object]:
        """Scoped external freshness; disjoint partial changes prove no absence."""
        if not isinstance(change_set_complete, bool):
            raise ValueError("change_set_complete must be a boolean")
        raw_scope = observation.get("scope_paths")
        scope = set(map(str, raw_scope)) if isinstance(raw_scope, list) else set()
        dependencies = set(map(str, dependency_paths))
        changed = set(map(str, changed_paths))
        intersection = sorted(changed & (scope | dependencies))
        observed_repo = observation.get("repository_identity")
        repository_changed = observed_repo != current_repository_identity
        generation_changed = observation.get("codemap_generation") != current_generation
        if not repository_changed and not generation_changed:
            state, reason = "current", "repository-and-generation-unchanged"
        elif not (scope or dependencies):
            state = "stale"
            reason = "repository-changed-without-declared-observation-scope"
        elif intersection:
            state, reason = "stale", "relevant-repository-evidence-changed"
        elif not change_set_complete:
            state, reason = "unknown", "change-set-completeness-unproven"
        elif not changed:
            state, reason = "unknown", "changed-endpoint-without-path-change-evidence"
        else:
            state = "current"
            reason = "declared-complete-change-set-outside-observation-scope"
        completeness = "caller-claimed-complete" if change_set_complete else "unknown"
        return {
            "schema": "hashmarks.external-observation-freshness.v1",
            "state": state,
            "reason": reason,
            "repository_changed": repository_changed,
            "generation_changed": generation_changed,
            "observation_scope": sorted(scope),
            "dependency_scope": sorted(dependencies),
            "changed_paths": sorted(changed),
            "change_set_completeness": completeness,
            "intersection": intersection,
            "authority": "observation-freshness-only",
            "freshness_scope": "repository-correspondence-only",
            "producer_freshness": "unknown",
            "execution_effect": "none",
        }

    @diagnostic_producer
    def snapshot(
        self,
        task: str,
        changed_paths: Sequence[str | Path],
        *,
        limit: int = 20,
        per_role: int = 3,
        impact_limit_per_surface: int = 4,
        max_depth: int = 3,
    ) -> dict[str, object]:
        """Capture bounded repository meaning for an explicit change set.

        Inside one explicit ``decision_session()``, identical snapshot requests
        reuse the already-derived immutable repository-intelligence composition.
        The cache is generation-bound and disposable; callers always receive a
        deep copy so mutation cannot become shared authority.
        """
        if TYPE_CHECKING:
            self = cast("RepositoryChanges", self)
        snapshot_key = None
        if self.reads.depth > 0:
            if self._snapshot_reuse.scope is not self.reads.scope:
                self._snapshot_reuse.entries.clear()
                self._snapshot_reuse.scope = self.reads.scope
            scope = self.reads.scope
            assert scope is not None
            generation = scope.generation
            snapshot_key = (
                generation,
                task,
                tuple(str(path) for path in changed_paths),
                int(limit),
                int(per_role),
                int(impact_limit_per_surface),
                int(max_depth),
            )
            cached = self._snapshot_reuse.entries.get(snapshot_key)
            if cached is not None:
                self.reads.count("snapshot_hit")
                with self.reads.session(
                    expected_generation=self._repository_generation(cached)
                ):
                    return deepcopy(cached)
            self.reads.count("snapshot_miss")

        brief = self.brief(
            task,
            changed_paths,
            limit=limit,
            per_role=per_role,
            impact_limit_per_surface=impact_limit_per_surface,
            max_depth=max_depth,
        )
        with self.reads.session(expected_generation=self._repository_generation(brief)):
            freshness = self.freshness_map(
                task,
                changed_paths,
                options=FreshnessMapOptions(
                    limit=limit,
                    per_role=per_role,
                    impact_limit_per_surface=impact_limit_per_surface,
                    max_depth=max_depth,
                ),
            )
            payload: dict[str, object] = {
                "schema": REPOSITORY_SNAPSHOT_SCHEMA,
                "observer": repository_observer_packet(),
                "repository": deepcopy(brief["repository"]),
                "task_identity": brief["task_identity"],
                "paths": self._snapshot_paths(changed_paths),
                "affected": deepcopy(brief.get("affected") or {}),
                "ownership": deepcopy(brief.get("ownership")),
                "verification": self._snapshot_verification(brief),
                "freshness": self._snapshot_freshness(freshness),
                "bounds": deepcopy(brief.get("bounds") or {}),
                "completeness": {
                    "state": "complete",
                    "scope": "bounded-explicit-change-set",
                    "dynamic_runtime_relationships": "unknown",
                },
                "storage": "derived-not-persisted",
                "authority": "repository-intelligence-only",
                "execution_effect": "none",
            }
            if "project_impact" in brief:
                payload["project_impact"] = deepcopy(brief["project_impact"])
            payload["snapshot_identity"] = "sha256:" + packet_digest(
                REPOSITORY_SNAPSHOT_SCHEMA, payload
            )
            if snapshot_key is not None:
                self._snapshot_reuse.entries[snapshot_key] = deepcopy(payload)
            return payload

    def _validate_previous_snapshot(
        self,
        task: str,
        previous_snapshot: Mapping[str, object],
    ) -> tuple[Mapping[str, object], str]:
        if TYPE_CHECKING:
            self = cast("RepositoryChanges", self)
        if previous_snapshot.get("schema") != REPOSITORY_SNAPSHOT_SCHEMA:
            raise ValueError(
                "previous_snapshot must be a hashmarks.repository-intelligence-snapshot.v1 packet"
            )
        repository = self._delta_mapping(
            previous_snapshot.get("repository"), field="previous_snapshot.repository"
        )
        repository_identity = str(repository.get("repository_identity") or "")
        if repository_identity != self.reads.repository_identity():
            raise ValueError("previous_snapshot repository-mismatch")
        expected_task = packet_digest("hashmarks.task.v1", {"task": task})
        if str(previous_snapshot.get("task_identity") or "") != expected_task:
            raise ValueError("previous_snapshot task-mismatch")
        identity = previous_snapshot.get("snapshot_identity")
        expected_identity = "sha256:" + packet_digest(
            REPOSITORY_SNAPSHOT_SCHEMA,
            {
                key: value
                for key, value in previous_snapshot.items()
                if key != "snapshot_identity"
            },
        )
        if not isinstance(identity, str) or identity != expected_identity:
            raise ValueError("previous_snapshot snapshot identity mismatch")
        return repository, repository_identity

    @classmethod
    def _leaf_changes(
        cls,
        previous: object,
        current: object,
        path: tuple[str, ...] = (),
    ) -> list[dict[str, object]]:
        if isinstance(previous, Mapping) and isinstance(current, Mapping):
            changes: list[dict[str, object]] = []
            for key in sorted(set(previous) | set(current)):
                child = (*path, str(key))
                if key not in current:
                    changes.append({"path": list(child), "delete": True})
                elif key not in previous:
                    changes.append(
                        {"path": list(child), "value": deepcopy(current[key])}
                    )
                else:
                    changes.extend(
                        cls._leaf_changes(previous[key], current[key], child)
                    )
            return changes
        if isinstance(previous, list) and isinstance(current, list):
            if previous == current:
                return []
            return [{"path": list(path), "value": deepcopy(current)}]
        if previous != current:
            return [{"path": list(path), "value": deepcopy(current)}]
        return []

    @staticmethod
    def _path_index(snapshot: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
        rows = snapshot.get("paths")
        if not isinstance(rows, Mapping):
            return {}
        return {
            str(path): row for path, row in rows.items() if isinstance(row, Mapping)
        }

    @staticmethod
    def _row_set(
        row: Mapping[str, object] | None, key: str
    ) -> set[tuple[tuple[str, str], ...]]:
        if not isinstance(row, Mapping):
            return set()
        values = row.get(key)
        if not isinstance(values, list):
            return set()
        return {
            tuple(
                sorted(
                    (str(k), str(v))
                    for k, v in item.items()
                    if k not in {"identity", "provenance"}
                )
            )
            for item in values
            if isinstance(item, Mapping)
        }

    @staticmethod
    def _decode_row(value: tuple[tuple[str, str], ...]) -> dict[str, str]:
        return dict(value)

    def _semantic_changes(
        self,
        previous: Mapping[str, object],
        current: Mapping[str, object],
    ) -> dict[str, object]:
        before = self._path_index(previous)
        after = self._path_index(current)
        symbols_added: list[dict[str, object]] = []
        symbols_removed: list[dict[str, object]] = []
        dependencies_added: list[dict[str, object]] = []
        dependencies_removed: list[dict[str, object]] = []
        for path in sorted(set(before) | set(after)):
            old_symbols = self._row_set(before.get(path), "symbols")
            new_symbols = self._row_set(after.get(path), "symbols")
            old_dependencies = self._row_set(before.get(path), "dependencies")
            new_dependencies = self._row_set(after.get(path), "dependencies")
            symbols_added.extend(
                {"path": path, **self._decode_row(value)}
                for value in sorted(new_symbols - old_symbols)
            )
            symbols_removed.extend(
                {"path": path, **self._decode_row(value)}
                for value in sorted(old_symbols - new_symbols)
            )
            dependencies_added.extend(
                {"path": path, **self._decode_row(value)}
                for value in sorted(new_dependencies - old_dependencies)
            )
            dependencies_removed.extend(
                {"path": path, **self._decode_row(value)}
                for value in sorted(old_dependencies - new_dependencies)
            )
        possible_moves: list[dict[str, object]] = []
        removed_by_symbol = {
            (row.get("qualname") or row.get("name"), row.get("kind")): row
            for row in symbols_removed
        }
        for added in symbols_added:
            key = (added.get("qualname") or added.get("name"), added.get("kind"))
            removed = removed_by_symbol.get(key)
            if removed is not None and removed["path"] != added["path"]:
                possible_moves.append(
                    {
                        "name": added.get("qualname") or added.get("name"),
                        "kind": added.get("kind"),
                        "from": removed["path"],
                        "to": added["path"],
                        "state": "possible",
                        "provenance": "same-qualified-name-and-kind",
                        "identity_authority": False,
                    }
                )
        result: dict[str, object] = {}
        for key, rows in (
            ("symbols_added", symbols_added),
            ("symbols_removed", symbols_removed),
            ("possible_symbol_moves", possible_moves),
            ("dependencies_added", dependencies_added),
            ("dependencies_removed", dependencies_removed),
        ):
            if rows:
                result[key] = rows
        for key, changed in (
            (
                "ownership_changed",
                previous.get("ownership") != current.get("ownership"),
            ),
            ("impact_changed", previous.get("affected") != current.get("affected")),
            (
                "verification_changed",
                previous.get("verification") != current.get("verification"),
            ),
            (
                "freshness_changed",
                previous.get("freshness") != current.get("freshness"),
            ),
            (
                "project_provenance_changed",
                previous.get("project_impact") != current.get("project_impact"),
            ),
        ):
            if changed:
                result[key] = True
        return result

    @diagnostic_producer
    def delta(
        self,
        task: str,
        changed_paths: Sequence[str | Path],
        *,
        previous_snapshot: Mapping[str, object],
        limit: int = 20,
        per_role: int = 3,
        options: ChangeImpactOptions | None = None,
    ) -> dict[str, object]:
        options = options or REPOSITORY_DELTA_DEFAULT_OPTIONS
        """Return changed repository-intelligence facts between admitted states."""
        if TYPE_CHECKING:
            self = cast("RepositoryChanges", self)
        self._validate_previous_snapshot(task, previous_snapshot)
        current = self.snapshot(
            task,
            changed_paths,
            limit=limit,
            per_role=per_role,
            impact_limit_per_surface=options.impact_limit_per_surface,
            max_depth=options.max_depth,
        )
        return self._compare_snapshots(task, previous_snapshot, current)

    def _compare_snapshots(
        self,
        task: str,
        previous_snapshot: Mapping[str, object],
        current: Mapping[str, object],
    ) -> dict[str, object]:
        """Compare explicit qualified values without observing a second endpoint."""
        previous_repository, repository_identity = self._validate_previous_snapshot(
            task, previous_snapshot
        )
        self._validate_previous_snapshot(task, current)
        current_repository = self._delta_mapping(
            current.get("repository"), field="current.repository"
        )
        changes = self._leaf_changes(previous_snapshot, current)
        changes = [row for row in changes if row.get("path") != ["snapshot_identity"]]
        changed_sections = sorted(
            {
                str(path[0])
                for row in changes
                if isinstance(path := row.get("path"), list) and path
            }
        )
        previous_observer = self._delta_mapping(
            previous_snapshot.get("observer"), field="previous_snapshot.observer"
        )
        current_observer = self._delta_mapping(
            current.get("observer"), field="current.observer"
        )
        previous_completeness = self._delta_mapping(
            previous_snapshot.get("completeness"),
            field="previous_snapshot.completeness",
        )
        current_completeness = self._delta_mapping(
            current.get("completeness"), field="current.completeness"
        )
        payload: dict[str, object] = {
            "schema": REPOSITORY_DELTA_SCHEMA,
            "repository_identity": repository_identity,
            "task_identity": current["task_identity"],
            "from": {
                "snapshot_identity": previous_snapshot["snapshot_identity"],
                "codemap_generation": previous_repository.get("codemap_generation"),
            },
            "to": {
                "snapshot_identity": current["snapshot_identity"],
                "codemap_generation": current_repository.get("codemap_generation"),
            },
            "changes": changes,
            "changed_sections": changed_sections,
            "semantic": self._semantic_changes(previous_snapshot, current),
            "observer": {
                "before": previous_observer.get("identity"),
                "after": current_observer.get("identity"),
                "changed": previous_observer.get("identity")
                != current_observer.get("identity"),
            },
            "completeness": {
                "before": deepcopy(previous_completeness),
                "after": deepcopy(current_completeness),
                "changed": previous_completeness != current_completeness,
            },
            "storage": "derived-not-persisted",
            "authority": "repository-intelligence-only",
            "execution_effect": "none",
        }
        payload["delta_identity"] = "sha256:" + packet_digest(
            REPOSITORY_DELTA_SCHEMA, payload
        )
        return payload
