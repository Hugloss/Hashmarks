from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import TYPE_CHECKING, cast

from hashmarks.paths import normalize_relative_path

from .decision_session import diagnostic_producer

if TYPE_CHECKING:
    from pathlib import Path

    from .engine import CodeMap


OBSERVATION_STATES = frozenset(
    {"known-present", "known-absent", "unknown", "incomplete", "stale", "unsupported"}
)


def _observer_descriptor() -> dict[str, object]:
    """Describe the observer capability separately from repository identity."""
    return {
        "producer": "hashmarks",
        "surface": "repository-intelligence",
        "schema": "hashmarks.repository-observer.v1",
        "capabilities": [
            "affected",
            "dependencies",
            "freshness",
            "ownership",
            "symbols",
            "verification",
        ],
    }


class RepositoryDeltaMixin:
    """Bounded semantic snapshots and deltas over repository intelligence.

    F3 owns no historical repository store.  A caller retains the earlier
    producer snapshot and supplies it back after a later repository state has
    been admitted.  Hashmarks derives the current snapshot from existing
    ownership/impact/verification/freshness authority and emits only changed
    facts plus compact semantic summaries.
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
            self = cast("CodeMap", self)
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
        edges_by_path = self._session_edges_for_paths_many(paths, limit_per_path=32)
        rows: dict[str, dict[str, object]] = {}
        for path in paths:
            file_row = self._session_file_row(path)
            revision = (
                None
                if file_row is None or not file_row["file_digest"]
                else str(file_row["file_digest"])
            )
            symbols = sorted(
                (
                    {
                        key: str(symbol[key])
                        for key in ("name", "qualname", "kind")
                        if symbol.get(key) is not None and str(symbol.get(key) or "")
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
                        key: str(edge[key])
                        for key in ("source", "kind", "target", "confidence")
                        if edge.get(key) is not None and str(edge.get(key) or "")
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

    @diagnostic_producer
    def repository_intelligence_snapshot(
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
            self = cast("CodeMap", self)
        snapshot_key = None
        if self._decision_session_depth > 0:
            generation = int(
                self._decision_session_generation or self.store.generation()
            )
            snapshot_key = (
                generation,
                task,
                tuple(str(path) for path in changed_paths),
                int(limit),
                int(per_role),
                int(impact_limit_per_surface),
                int(max_depth),
            )
            cached = self._decision_snapshot_cache.get(snapshot_key)
            if cached is not None:
                self._decision_session_stats["snapshot_hit"] += 1
                return deepcopy(cached)
            self._decision_session_stats["snapshot_miss"] += 1

        brief = self.change_intelligence_brief(
            task,
            changed_paths,
            limit=limit,
            per_role=per_role,
            impact_limit_per_surface=impact_limit_per_surface,
            max_depth=max_depth,
        )
        freshness = self.evidence_freshness_map(
            task,
            changed_paths,
            limit=limit,
            per_role=per_role,
            impact_limit_per_surface=impact_limit_per_surface,
            max_depth=max_depth,
        )
        observer = _observer_descriptor()
        payload: dict[str, object] = {
            "schema": "hashmarks.repository-intelligence-snapshot.v1",
            "observer": {
                **observer,
                "identity": "sha256:"
                + self._packet_digest("hashmarks.repository-observer.v1", observer),
            },
            "repository": deepcopy(brief["repository"]),
            "task_identity": brief["task_identity"],
            "paths": self._snapshot_paths(changed_paths),
            "affected": deepcopy(brief.get("affected") or {}),
            "ownership": deepcopy(brief.get("ownership")),
            "verification": self._snapshot_verification(brief),
            "freshness": self._snapshot_freshness(freshness),
            "bounds": deepcopy(brief.get("bounds") or {}),
            "completeness": {
                "state": "known-present",
                "scope": "bounded-explicit-change-set",
                "dynamic_runtime_relationships": "unknown",
            },
            "storage": "derived-not-persisted",
            "authority": "repository-intelligence-only",
            "execution_effect": "none",
        }
        if "project_impact" in brief:
            payload["project_impact"] = deepcopy(brief["project_impact"])
        payload["snapshot_identity"] = "sha256:" + self._packet_digest(
            "hashmarks.repository-intelligence-snapshot.v1", payload
        )
        if snapshot_key is not None:
            self._decision_snapshot_cache[snapshot_key] = deepcopy(payload)
        return payload

    def _validate_previous_snapshot(
        self,
        task: str,
        previous_snapshot: Mapping[str, object],
    ) -> tuple[Mapping[str, object], str]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if (
            previous_snapshot.get("schema")
            != "hashmarks.repository-intelligence-snapshot.v1"
        ):
            raise ValueError(
                "previous_snapshot must be a hashmarks.repository-intelligence-snapshot.v1 packet"
            )
        repository = self._delta_mapping(
            previous_snapshot.get("repository"), field="previous_snapshot.repository"
        )
        repository_identity = str(repository.get("repository_identity") or "")
        if repository_identity != self._repository_packet_identity():
            raise ValueError("previous_snapshot repository-mismatch")
        expected_task = self._packet_digest("hashmarks.task.v1", {"task": task})
        if str(previous_snapshot.get("task_identity") or "") != expected_task:
            raise ValueError("previous_snapshot task-mismatch")
        if not previous_snapshot.get("snapshot_identity"):
            raise ValueError("previous_snapshot must contain snapshot_identity")
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
            tuple(sorted((str(k), str(v)) for k, v in item.items()))
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
    def repository_intelligence_delta(
        self,
        task: str,
        changed_paths: Sequence[str | Path],
        *,
        previous_snapshot: Mapping[str, object],
        limit: int = 20,
        per_role: int = 3,
        impact_limit_per_surface: int = 4,
        max_depth: int = 3,
    ) -> dict[str, object]:
        """Return changed repository-intelligence facts between admitted states."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        previous_repository, repository_identity = self._validate_previous_snapshot(
            task, previous_snapshot
        )
        current = self.repository_intelligence_snapshot(
            task,
            changed_paths,
            limit=limit,
            per_role=per_role,
            impact_limit_per_surface=impact_limit_per_surface,
            max_depth=max_depth,
        )
        current_repository = self._delta_mapping(
            current.get("repository"), field="current.repository"
        )
        changes = self._leaf_changes(previous_snapshot, current)
        changes = [row for row in changes if row.get("path") != ["snapshot_identity"]]
        changed_sections = sorted(
            {
                str(row["path"][0])
                for row in changes
                if isinstance(row.get("path"), list) and row["path"]
            }
        )
        previous_observer = self._delta_mapping(
            previous_snapshot.get("observer"), field="previous_snapshot.observer"
        )
        current_observer = self._delta_mapping(
            current.get("observer"), field="current.observer"
        )
        previous_completeness = self._delta_mapping(
            previous_snapshot.get("completeness"), field="previous_snapshot.completeness"
        )
        current_completeness = self._delta_mapping(
            current.get("completeness"), field="current.completeness"
        )
        payload: dict[str, object] = {
            "schema": "hashmarks.repository-intelligence-delta.v1",
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
        payload["delta_identity"] = "sha256:" + self._packet_digest(
            "hashmarks.repository-intelligence-delta.v1", payload
        )
        return payload
