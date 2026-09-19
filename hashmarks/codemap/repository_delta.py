from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from hashmarks.file_store import UnstableFileError
from hashmarks.paths import normalize_relative_path

from .decision_session import diagnostic_producer

if TYPE_CHECKING:
    from pathlib import Path

    from .engine import CodeMap



@dataclass(frozen=True, slots=True)
class RepositoryGenerationBinding:
    repository_identity: str
    codemap_generation: int


def _observer_descriptor() -> dict[str, object]:
    """Describe the observer capability separately from repository identity."""
    return {
        "producer": "hashmarks",
        "surface": "repository-intelligence",
        "schema": "hashmarks.repository-observer.v1",
        "capabilities": [
            "affected",
            "dependencies",
            "evidence-bindings",
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

    def _repository_observer_packet(self) -> dict[str, object]:
        """Return the canonical observer capability descriptor with stable identity."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        observer = _observer_descriptor()
        return {
            **observer,
            "identity": "sha256:"
            + self._packet_digest("hashmarks.repository-observer.v1", observer),
        }

    @staticmethod
    def _evidence_identity(schema: str, value: Mapping[str, object]) -> str:
        """Return a deterministic domain-separated identity for observer evidence."""
        import hashlib
        import json

        raw = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        digest = hashlib.sha256(schema.encode("utf-8") + b"\0" + raw).hexdigest()
        return f"sha256:{digest}"

    @staticmethod
    def _delta_mapping(value: object, *, field: str) -> Mapping[str, object]:
        if not isinstance(value, Mapping):
            raise ValueError(f"{field} must be an object")
        return value

    def _repository_member_observation(
        self,
        relpath: str,
        *,
        include_bytes: bool = False,
    ) -> tuple[dict[str, object], bytes | None]:
        """Observe one repository member through canonical policy/revision authority."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        rel = normalize_relative_path(relpath, allow_root=False)
        decision = self.policy.decide(rel)
        base: dict[str, object] = {"path": rel}

        if not decision.index or decision.evidence_visibility.value == "deny":
            return (
                {
                    **base,
                    "state": "unsupported",
                    "reason": "repository-evidence-denied",
                },
                None,
            )
        if not self._path_admitted_for_analysis(rel):
            return (
                {
                    **base,
                    "state": "unsupported",
                    "reason": "repository-evidence-not-admitted",
                },
                None,
            )

        cursor = self.workspace
        for part in rel.split("/"):
            cursor = cursor / part
            if cursor.is_symlink():
                return (
                    {
                        **base,
                        "state": "unsupported",
                        "reason": "symlink-evidence-not-observed",
                    },
                    None,
                )

        path = self.workspace / rel
        if not path.is_file():
            return (
                {
                    **base,
                    "state": "known-absent",
                    "reason": "member-not-present",
                },
                None,
            )

        row = self._session_file_row(rel)
        visibility = (
            str(row.get("evidence_visibility") or decision.evidence_visibility.value)
            if row is not None
            else decision.evidence_visibility.value
        )
        indexed_revision = (
            str(row.get("file_digest") or "") if row is not None else ""
        )

        if include_bytes and visibility != "source":
            return (
                {
                    **base,
                    "state": "unsupported",
                    "reason": "source-evidence-not-visible",
                    **(
                        {"member_revision": indexed_revision}
                        if indexed_revision
                        else {}
                    ),
                    "evidence_visibility": visibility,
                    "index_state": "indexed" if row is not None else "unindexed",
                },
                None,
            )

        try:
            if include_bytes:
                raw, digest = self.file_store.read_bytes_stable(path)
            elif row is None:
                digest = self.file_store.digest(
                    path,
                    workspace=self.workspace,
                    relative_path=rel,
                    force=True,
                )
                raw = None
            else:
                digest = None
                raw = None
        except FileNotFoundError:
            return (
                {
                    **base,
                    "state": "known-absent",
                    "reason": "member-not-present",
                },
                None,
            )
        except (OSError, UnstableFileError):
            return (
                {
                    **base,
                    "state": "unknown",
                    "reason": "member-read-unstable-or-unavailable",
                    **(
                        {"member_revision": indexed_revision}
                        if indexed_revision
                        else {}
                    ),
                    "evidence_visibility": visibility,
                    "index_state": "indexed" if row is not None else "unindexed",
                },
                None,
            )

        if row is not None:
            if digest is not None and digest.hash != indexed_revision:
                return (
                    {
                        **base,
                        "state": "unknown",
                        "reason": "member-revision-mismatch",
                        "member_revision": indexed_revision,
                        "evidence_visibility": visibility,
                        "index_state": "indexed",
                    },
                    None,
                )
            revision = indexed_revision
            index_state = "indexed"
        else:
            assert digest is not None
            revision = digest.hash
            index_state = "unindexed"

        return (
            {
                **base,
                "state": "known-present",
                "member_revision": revision,
                "evidence_visibility": visibility,
                "index_state": index_state,
            },
            raw,
        )

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
            member, _raw = self._repository_member_observation(path)
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
                        "identity": self._evidence_identity(
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
                        "identity": self._evidence_identity(
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
    def _diagnostic_identity(row: Mapping[str, object]) -> str:
        """Canonical diagnostic identity independent of aggregate count/order."""
        import hashlib
        import json

        identity_fields = {
            key: row.get(key)
            for key in ("tool", "rule", "path", "symbol", "line", "column", "message")
            if row.get(key) is not None
        }
        raw = json.dumps(
            identity_fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(raw).hexdigest()

    @classmethod
    def external_diagnostic_observation(
        cls,
        *,
        producer: str,
        binding: RepositoryGenerationBinding,
        diagnostics: Sequence[Mapping[str, object]],
        outcome: str,
        environment_identity: str | None = None,
        scope_paths: Sequence[str] = (),
    ) -> dict[str, object]:
        """Normalize externally produced diagnostics without executing the tool."""
        allowed_outcomes = {
            "pass",
            "fail",
            "not-run",
            "blocked-environment",
            "blocked-supply",
            "blocked-permission",
            "invalid-baseline",
            "stale",
        }
        if outcome not in allowed_outcomes:
            raise ValueError("unsupported external observation outcome")
        rows = []
        for raw in diagnostics:
            row = dict(raw)
            row["identity"] = cls._diagnostic_identity(row)
            rows.append(row)
        rows.sort(key=lambda row: str(row["identity"]))
        return {
            "schema": "hashmarks.external-diagnostic-observation.v1",
            "producer": producer,
            "repository_identity": binding.repository_identity,
            "codemap_generation": int(binding.codemap_generation),
            "environment_identity": environment_identity,
            "scope_paths": sorted({str(path) for path in scope_paths}),
            "outcome": outcome,
            "diagnostics": rows,
            "diagnostic_count": len(rows),
            "authority": "observation-only",
            "execution_effect": "none",
        }

    def verification_relationship_evidence(
        self,
        *,
        source: str,
        target: str,
        classification: str,
        relation_kind: str,
        provenance: str,
    ) -> dict[str, object]:
        """Describe an objective repository relationship without consumer policy."""
        if classification not in {"direct", "related", "unknown"}:
            raise ValueError("unsupported verification relationship classification")
        if not relation_kind.strip():
            raise ValueError("verification relationship kind must be nonblank")
        payload = {
            "source": source,
            "target": target,
            "classification": classification,
            "relation_kind": relation_kind,
            "provenance": provenance,
        }
        return {
            **payload,
            "evidence_identity": self._evidence_identity(
                "hashmarks.verification-relationship.v1", payload
            ),
            "authority": "repository-relationship-only",
            "execution_effect": "none",
        }

    @staticmethod
    def external_observation_freshness(
        observation: Mapping[str, object],
        *,
        current_repository_identity: str,
        current_generation: int,
        changed_paths: Sequence[str] = (),
        dependency_paths: Sequence[str] = (),
    ) -> dict[str, object]:
        """Evaluate scoped freshness without making every generation globally stale."""
        observed_repository = str(observation.get("repository_identity") or "")
        observed_generation = observation.get("codemap_generation")
        raw_scope = observation.get("scope_paths")
        scope = (
            {str(path) for path in raw_scope} if isinstance(raw_scope, list) else set()
        )
        relevant = scope | {str(path) for path in dependency_paths}
        changed = {str(path) for path in changed_paths}
        intersection = sorted(relevant & changed)
        repository_changed = observed_repository != current_repository_identity
        generation_changed = observed_generation != current_generation

        if not repository_changed and not generation_changed:
            state = "current"
            reason = "repository-and-generation-unchanged"
        elif not relevant:
            state = "stale"
            reason = "repository-changed-without-declared-observation-scope"
        elif intersection:
            state = "stale"
            reason = "relevant-repository-evidence-changed"
        else:
            state = "current"
            reason = "changed-paths-proven-outside-observation-scope"

        return {
            "schema": "hashmarks.external-observation-freshness.v1",
            "state": state,
            "reason": reason,
            "repository_changed": repository_changed,
            "generation_changed": generation_changed,
            "observation_scope": sorted(scope),
            "dependency_scope": sorted({str(path) for path in dependency_paths}),
            "changed_paths": sorted(changed),
            "intersection": intersection,
            "authority": "observation-freshness-only",
            "execution_effect": "none",
        }

    @staticmethod
    def diagnostic_observation_delta(
        before: Mapping[str, object],
        after: Mapping[str, object],
        *,
        changed_paths: Sequence[str] = (),
    ) -> dict[str, object]:
        """Compare diagnostic identities; counts alone are never delta authority."""

        def indexed(packet: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
            rows = packet.get("diagnostics")
            if not isinstance(rows, list):
                return {}
            return {
                str(row["identity"]): row
                for row in rows
                if isinstance(row, Mapping) and row.get("identity")
            }

        old = indexed(before)
        new = indexed(after)
        old_ids = set(old)
        new_ids = set(new)
        added_ids = sorted(new_ids - old_ids)
        removed_ids = sorted(old_ids - new_ids)
        scope = {str(path) for path in changed_paths}
        added = [deepcopy(new[identity]) for identity in added_ids]
        removed = [deepcopy(old[identity]) for identity in removed_ids]
        added_in_changed_scope = [
            row for row in added if str(row.get("path") or "") in scope
        ]
        return {
            "schema": "hashmarks.diagnostic-observation-delta.v1",
            "producer": after.get("producer"),
            "repository": {
                "before": before.get("repository_identity"),
                "after": after.get("repository_identity"),
                "changed": before.get("repository_identity")
                != after.get("repository_identity"),
            },
            "generation": {
                "before": before.get("codemap_generation"),
                "after": after.get("codemap_generation"),
            },
            "outcome": {
                "before": before.get("outcome"),
                "after": after.get("outcome"),
            },
            "diagnostics": {
                "before_count": len(old),
                "after_count": len(new),
                "added": added,
                "removed": removed,
                "unchanged_count": len(old_ids & new_ids),
                "added_in_changed_scope": added_in_changed_scope,
            },
            "authority": "observation-only",
            "execution_effect": "none",
        }

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
        payload: dict[str, object] = {
            "schema": "hashmarks.repository-intelligence-snapshot.v1",
            "observer": self._repository_observer_packet(),
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
            previous_snapshot.get("completeness"),
            field="previous_snapshot.completeness",
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
