from __future__ import annotations

import hashlib
import json
import time
from typing import TYPE_CHECKING, Any, cast

from hashmarks.paths import normalize_relative_path

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .engine import CodeMap


FRESHNESS_STATES = frozenset({"current", "stale", "unknown"})


def freshness_state(stale: bool | None) -> str:
    """Return the canonical serialized freshness state."""
    if stale is True:
        return "stale"
    if stale is False:
        return "current"
    return "unknown"


class EvidenceFreshnessMixin:
    """Own evidence snapshot identity, manifest freshness, and freshness status semantics."""

    def _evidence_key(self, kind: str, producer: str) -> str:
        return f"native_evidence:{kind}:{producer}"

    def _manifest_digest(self, relpath: str) -> str | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        try:
            rel = normalize_relative_path(relpath, allow_root=False)
        except ValueError:
            return None
        path = self.workspace / rel
        if path.is_symlink() or not path.is_file():
            return None
        try:
            data = path.read_bytes()
        except OSError:
            return None
        return hashlib.sha256(data).hexdigest()

    def _record_evidence_snapshot(
        self,
        kind: str,
        producer: str,
        *,
        bind_generation: bool,
        manifests: Iterable[str] = (),
    ) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        manifest_rows: dict[str, str | None] = {}
        for raw in manifests:
            try:
                rel = normalize_relative_path(raw, allow_root=False)
            except ValueError:
                continue
            manifest_rows[rel] = self._manifest_digest(rel)
        value = {
            "generation": self.store.generation(),
            "bind_generation": bool(bind_generation),
            "manifests": manifest_rows,
            "recorded_unix": time.time(),
        }
        self.store.set_meta(
            self._evidence_key(kind, producer),
            json.dumps(value, sort_keys=True, separators=(",", ":")),
        )

    def _evidence_snapshot(self, kind: str, producer: str) -> dict[str, object] | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        raw = self.store.meta(self._evidence_key(kind, producer))
        if not raw:
            return None
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None

    def _evidence_manifest_changes(self, kind: str, producer: str) -> tuple[str, ...]:
        value = self._evidence_snapshot(kind, producer)
        if value is None:
            return ()
        manifests = value.get("manifests") or {}
        if not isinstance(manifests, dict):
            return ()
        return tuple(
            str(rel)
            for rel, expected in manifests.items()
            if self._manifest_digest(str(rel)) != expected
        )

    def _declared_project_shared_input(self, relpath: str) -> bool:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        for row in self.store.project_nodes():
            if str(row.get("producer") or "") != "declared-project-links":
                continue
            if str(row.get("kind") or "") != "shared-input":
                continue
            raw_metadata = row.get("metadata")
            metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
            if str(metadata.get("path") or row.get("root") or "") == relpath:
                return True
        return False

    def _rebind_declared_project_freshness(self) -> bool:
        value = self._evidence_snapshot("project", "declared-project-links")
        if value is None or bool(value.get("bind_generation", False)):
            return False
        manifests = value.get("manifests") or {}
        if not isinstance(manifests, dict) or not manifests:
            return False
        self._record_evidence_snapshot(
            "project",
            "declared-project-links",
            bind_generation=False,
            manifests=tuple(str(rel) for rel in manifests),
        )
        return True

    def _generation_snapshot_fresh(
        self, value: dict[str, object]
    ) -> tuple[bool, str | None]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        try:
            recorded_generation = int(cast(Any, value.get("generation")))
        except (TypeError, ValueError):
            return False, "invalid generation snapshot"
        current_generation = self.store.generation()
        if recorded_generation != current_generation:
            return (
                False,
                f"CodeMap generation changed ({recorded_generation} -> {current_generation})",
            )
        return True, None

    def _evidence_fresh(self, kind: str, producer: str) -> tuple[bool, str | None]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        value = self._evidence_snapshot(kind, producer)
        if value is None:
            return False, "no freshness snapshot"
        if bool(value.get("bind_generation", False)):
            fresh, reason = self._generation_snapshot_fresh(value)
            if not fresh:
                return fresh, reason
        manifests = value.get("manifests") or {}
        if not isinstance(manifests, dict):
            return False, "invalid manifest snapshot"
        for rel, expected in manifests.items():
            if self._manifest_digest(str(rel)) != expected:
                return False, f"manifest changed: {rel}"
        return True, None

    def _fresh_native_file_edges(self) -> list[dict]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        cache: dict[str, bool] = {}
        out: list[dict] = []
        for row in self.store.native_file_edges():
            producer = str(row.get("producer") or "")
            if producer not in cache:
                cache[producer] = self._evidence_fresh("native-file", producer)[0]
            if cache[producer]:
                out.append(row)
        return out

    def _fresh_native_file_edges_from(self, path: str) -> list[dict]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        return [
            row
            for row in self.store.native_file_edges_from(path)
            if self._evidence_fresh("native-file", str(row.get("producer") or ""))[0]
        ]

    def _fresh_native_definitions(self, query: str, *, limit: int = 100) -> list[dict]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        return [
            row
            for row in self.store.native_definitions(query, limit=limit)
            if self._evidence_fresh("scip", str(row.get("producer") or ""))[0]
        ]

    def _fresh_native_refs(self, query: str, *, limit: int = 200) -> list[dict]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        return [
            row
            for row in self.store.native_refs(query, limit=limit)
            if self._evidence_fresh("scip", str(row.get("producer") or ""))[0]
        ]

    def _fresh_native_edges_from(
        self, path: str, source: str | None = None, *, limit: int = 200
    ) -> list[dict]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        return [
            row
            for row in self.store.native_edges_from(path, source, limit=limit)
            if self._evidence_fresh("scip", str(row.get("producer") or ""))[0]
        ]

    def _fresh_project_nodes(self) -> list[dict]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        cache: dict[str, bool] = {}
        out: list[dict] = []
        for row in self.store.project_nodes():
            producer = str(row.get("producer") or "")
            if producer not in cache:
                cache[producer] = self._evidence_fresh("project", producer)[0]
            if cache[producer]:
                out.append(row)
        return out

    def _fresh_project_edges(self) -> list[dict]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        cache: dict[str, bool] = {}
        out: list[dict] = []
        for row in self.store.project_edges():
            producer = str(row.get("producer") or "")
            if producer not in cache:
                cache[producer] = self._evidence_fresh("project", producer)[0]
            if cache[producer]:
                out.append(row)
        return out

    def _fresh_projects_for_path(self, path: str) -> list[dict]:
        clean = path.strip("/")
        matches = []
        for row in self._fresh_project_nodes():
            root = str(row["root"]).strip("/")
            if root in {"", "."} or clean == root or clean.startswith(root + "/"):
                matches.append(row)
        matches.sort(key=lambda row: len(str(row["root"])), reverse=True)
        return matches

    def _fresh_project_dependents(
        self, project_ids: set[str], max_depth: int = 12
    ) -> set[str]:
        reverse: dict[str, set[str]] = {}
        for edge in self._fresh_project_edges():
            reverse.setdefault(str(edge["target"]), set()).add(str(edge["source"]))
        seen = set(project_ids)
        frontier = set(project_ids)
        for _ in range(max_depth):
            nxt: set[str] = set()
            for project_id in frontier:
                nxt.update(reverse.get(project_id, ()))
            nxt -= seen
            if not nxt:
                break
            seen.update(nxt)
            frontier = nxt
        return seen

    def _fresh_project_dependents_with_provenance(
        self, project_ids: set[str], *, max_depth: int = 12, limit: int = 12
    ) -> dict[str, object]:
        """Return a bounded reverse-project graph fragment with provenance.

        This is a projection over the existing fresh project graph, not a new
        graph or ranker. ``source`` depends on ``target``; reverse traversal
        from changed roots discovers dependent projects.
        """
        if limit < 1:
            return {"roots": sorted(project_ids), "affected": [], "edges": []}
        reverse = self._reverse_project_edges()

        seen = set(project_ids)
        frontier = sorted(project_ids)
        affected: list[dict[str, object]] = []
        edges: list[dict[str, object]] = []
        edge_keys: set[tuple[str, str, str, str]] = set()
        for depth in range(1, max_depth + 1):
            nxt: list[str] = []
            for current in frontier:
                for edge in reverse.get(current, ()):
                    source = str(edge.get("source") or "")
                    if not source or source in seen:
                        continue
                    seen.add(source)
                    affected.append({"project": source, "depth": depth})
                    self._append_compact_project_edge(edge, source, edges, edge_keys)
                    if len(affected) >= limit:
                        return {
                            "roots": sorted(project_ids),
                            "affected": affected,
                            "edges": edges,
                        }
                    nxt.append(source)
            if not nxt:
                break
            frontier = sorted(nxt)
        return {"roots": sorted(project_ids), "affected": affected, "edges": edges}

    def _reverse_project_edges(self) -> dict[str, list[dict[str, object]]]:
        reverse: dict[str, list[dict[str, object]]] = {}
        for raw in self._fresh_project_edges():
            edge = dict(raw)
            reverse.setdefault(str(edge.get("target") or ""), []).append(edge)
        for rows in reverse.values():
            rows.sort(
                key=lambda row: (
                    str(row.get("source") or ""),
                    str(row.get("kind") or ""),
                    str(row.get("producer") or ""),
                )
            )
        return reverse

    @staticmethod
    def _append_compact_project_edge(
        edge: dict[str, object],
        source: str,
        edges: list[dict[str, object]],
        edge_keys: set[tuple[str, str, str, str]],
    ) -> None:
        target = str(edge.get("target") or "")
        kind = str(edge.get("kind") or "declared")
        producer = str(edge.get("producer") or "")
        compact: dict[str, object] = {
            "from": source,
            "to": target,
            "kind": kind,
            "producer": producer,
        }
        confidence = str(edge.get("confidence") or "")
        if confidence and confidence != "declared":
            compact["confidence"] = confidence
        key = (source, target, kind, producer)
        if key not in edge_keys:
            edge_keys.add(key)
            edges.append(compact)

    def _native_evidence_status(self) -> list[dict[str, object]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        prefix = "native_evidence:"
        rows: list[dict[str, object]] = []
        for key, _raw in self.store.meta_items(prefix=prefix):
            suffix = key[len(prefix) :]
            kind, _, producer = suffix.partition(":")
            fresh, reason = self._evidence_fresh(kind, producer)
            rows.append(
                {"kind": kind, "producer": producer, "fresh": fresh, "reason": reason}
            )
        rows.sort(key=lambda row: (str(row["kind"]), str(row["producer"])))
        return rows
