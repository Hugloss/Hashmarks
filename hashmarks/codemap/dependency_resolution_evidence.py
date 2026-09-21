from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .engine import CodeMap

_SCHEMA = "hashmarks.dependency-resolution.v1"
_MAX_NODES = 4096
_MAX_EDGES = 16384
_MAX_ROOTS = 256
_MAX_INPUTS = 256
_MAX_ID_CHARS = 512
_MAX_TEXT_CHARS = 4096
_MAX_REQUEST_BYTES = 1_048_576
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "dependency resolution snapshot must contain JSON-compatible values"
        ) from exc


def _identity(domain: str, value: object) -> str:
    return "sha256:" + hashlib.sha256(
        domain.encode("utf-8") + b"\0" + _canonical(value)
    ).hexdigest()


def _identifier(value: object, *, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} must not be empty")
    if len(text) > _MAX_ID_CHARS:
        raise ValueError(f"{label} exceeds {_MAX_ID_CHARS} characters")
    return text


def _text(value: object, *, label: str, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{label} must not be empty")
    if len(text) > _MAX_TEXT_CHARS:
        raise ValueError(f"{label} exceeds {_MAX_TEXT_CHARS} characters")
    return text


def _objects(value: object, *, label: str, limit: int) -> list[Mapping[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{label} must be a sequence")
    if len(value) > limit:
        raise ValueError(f"{label} exceeds {limit} entries")
    rows: list[Mapping[str, object]] = []
    for row in value:
        if not isinstance(row, Mapping):
            raise ValueError(f"each {label} entry must be an object")
        rows.append(row)
    return rows


class DependencyResolutionEvidenceMixin:
    """Qualify producer-neutral dependency resolution observations.

    The producer supplies the graph. Hashmarks validates, identifies, compares,
    and binds it to existing repository evidence; it never runs a resolver,
    package manager, environment synchronizer, or dependency implementation scan.
    """

    def dependency_resolution_evidence(
        self,
        snapshot: Mapping[str, object],
    ) -> dict[str, object]:
        if not isinstance(snapshot, Mapping):
            raise ValueError("dependency resolution snapshot must be an object")
        if len(_canonical(snapshot)) > _MAX_REQUEST_BYTES:
            raise ValueError(
                f"dependency resolution snapshot exceeds {_MAX_REQUEST_BYTES} encoded bytes"
            )
        if snapshot.get("schema") != _SCHEMA:
            raise ValueError(f"dependency resolution schema must be {_SCHEMA}")

        producer = snapshot.get("producer")
        if not isinstance(producer, Mapping):
            raise ValueError("dependency resolution producer must be an object")
        producer_packet = dict(producer)
        _identifier(producer_packet.get("kind"), label="producer kind")
        _text(producer_packet.get("schema_version"), label="producer schema_version", required=True)

        scope = snapshot.get("scope")
        if not isinstance(scope, Mapping):
            raise ValueError("dependency resolution scope must be an object")
        scope_packet = dict(scope)
        if not scope_packet:
            raise ValueError("dependency resolution scope must not be empty")
        _canonical(scope_packet)

        raw_roots = snapshot.get("roots", ())
        if not isinstance(raw_roots, Sequence) or isinstance(
            raw_roots, (str, bytes, bytearray)
        ):
            raise ValueError("roots must be a sequence")
        roots = [_identifier(value, label="root") for value in raw_roots]
        if len(roots) > _MAX_ROOTS:
            raise ValueError(f"roots exceeds {_MAX_ROOTS} entries")
        if len(set(roots)) != len(roots):
            raise ValueError("duplicate dependency resolution root")

        nodes = self._dependency_resolution_nodes(snapshot.get("nodes", ()))
        node_ids = {str(row["node_id"]) for row in nodes}
        for root in roots:
            if root not in node_ids:
                raise ValueError(f"dangling dependency resolution root: {root}")
        edges = self._dependency_resolution_edges(snapshot.get("edges", ()), node_ids)

        repository_inputs = self._dependency_repository_inputs(
            snapshot.get("repository_inputs", ())
        )
        completeness = str(snapshot.get("completeness") or "unknown").strip()
        if completeness not in {"complete", "incomplete", "unknown"}:
            raise ValueError(
                "dependency resolution completeness must be complete, incomplete, or unknown"
            )
        truncation = str(snapshot.get("truncation") or "unknown").strip()
        if truncation not in {"complete", "truncated", "unknown"}:
            raise ValueError(
                "dependency resolution truncation must be complete, truncated, or unknown"
            )
        if completeness == "complete" and truncation != "complete":
            raise ValueError(
                "dependency resolution completeness=complete requires truncation=complete"
            )
        definition = {
            "producer": producer_packet,
            "scope": scope_packet,
            "roots": sorted(roots),
        }
        graph = {
            "nodes": sorted(nodes, key=lambda row: str(row["node_id"])),
            "edges": sorted(
                edges,
                key=lambda row: (
                    str(row["source"]),
                    str(row["target"]),
                    str(row["kind"]),
                    str(row["marker"]),
                ),
            ),
        }
        definition_identity = _identity(
            "hashmarks.dependency-resolution-definition.v1", definition
        )
        resolution_identity = _identity(
            "hashmarks.dependency-resolution-observation.v1",
            {"definition_identity": definition_identity, "graph": graph},
        )
        return {
            "schema": _SCHEMA,
            "authority": "qualified-external-observation",
            "producer_authority": "caller-claimed",
            "definition_identity": definition_identity,
            "resolution_identity": resolution_identity,
            "producer": producer_packet,
            "scope": scope_packet,
            "roots": sorted(roots),
            **graph,
            "repository_inputs": repository_inputs,
            "completeness": completeness,
            "truncation": truncation,
            "negative_evidence": (
                "admissible-within-declared-scope"
                if completeness == "complete" and truncation == "complete"
                else "not-admissible"
            ),
        }

    @staticmethod
    def _dependency_resolution_nodes(value: object) -> list[dict[str, object]]:
        rows = _objects(value, label="nodes", limit=_MAX_NODES)
        result: list[dict[str, object]] = []
        seen: set[str] = set()
        for raw in rows:
            node_id = _identifier(raw.get("node_id"), label="node_id")
            if node_id in seen:
                raise ValueError(f"duplicate dependency resolution node_id: {node_id}")
            seen.add(node_id)
            name = _text(raw.get("name"), label="distribution name", required=True)
            result.append(
                {
                    "node_id": node_id,
                    "name": name,
                    "version": _text(raw.get("version"), label="version"),
                    "source": _text(raw.get("source"), label="source"),
                    "marker": _text(raw.get("marker"), label="marker"),
                }
            )
        return result

    @staticmethod
    def _dependency_resolution_edges(
        value: object,
        node_ids: set[str],
    ) -> list[dict[str, object]]:
        rows = _objects(value, label="edges", limit=_MAX_EDGES)
        result: list[dict[str, object]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for raw in rows:
            source = _identifier(raw.get("source"), label="edge source")
            target = _identifier(raw.get("target"), label="edge target")
            if source not in node_ids or target not in node_ids:
                raise ValueError(f"dangling dependency resolution edge: {source}->{target}")
            packet = {
                "source": source,
                "target": target,
                "kind": _text(raw.get("kind"), label="edge kind", required=True),
                "marker": _text(raw.get("marker"), label="edge marker"),
            }
            key = (source, target, str(packet["kind"]), str(packet["marker"]))
            if key in seen:
                raise ValueError(f"duplicate dependency resolution edge: {source}->{target}")
            seen.add(key)
            result.append(packet)
        return result

    def _dependency_repository_inputs(self, value: object) -> list[dict[str, object]]:
        rows = _objects(value, label="repository_inputs", limit=_MAX_INPUTS)
        result: list[dict[str, object]] = []
        seen: set[str] = set()
        for raw in rows:
            path = _identifier(raw.get("path"), label="repository input path")
            if path in seen:
                raise ValueError(f"duplicate repository input path: {path}")
            seen.add(path)
            claimed = raw.get("member_revision")
            if claimed is not None and not _SHA256.fullmatch(str(claimed)):
                raise ValueError(
                    "repository input member_revision must use sha256:<64 lowercase hex characters>"
                )
            member, _raw = self._repository_member_observation(path)
            observed = member.get("member_revision")
            if claimed is None or observed is None:
                equivalence = "unknown"
            elif str(claimed) == str(observed):
                equivalence = "proven"
            else:
                equivalence = "mismatch"
            result.append(
                {
                    "path": path,
                    "claimed_member_revision": claimed,
                    "observed_member_revision": observed,
                    "source_equivalence": equivalence,
                    "repository_state": member.get("state"),
                }
            )
        return sorted(result, key=lambda row: str(row["path"]))

    @staticmethod
    def dependency_resolution_delta(
        before: Mapping[str, object],
        after: Mapping[str, object],
    ) -> dict[str, object]:
        if before.get("schema") != _SCHEMA or after.get("schema") != _SCHEMA:
            raise ValueError("dependency resolution delta requires qualified v1 observations")
        before_definition = before.get("definition_identity")
        after_definition = after.get("definition_identity")
        if not _SHA256.fullmatch(str(before_definition or "")) or not _SHA256.fullmatch(
            str(after_definition or "")
        ):
            raise ValueError("dependency resolution definition identity is malformed")
        if before_definition != after_definition:
            return {
                "schema": "hashmarks.dependency-resolution-delta.v1",
                "comparability": "not-comparable",
                "reason": "definition-changed",
                "before_definition_identity": before_definition,
                "after_definition_identity": after_definition,
            }
        before_nodes = {
            str(row["node_id"]): row
            for row in before.get("nodes", ())
            if isinstance(row, Mapping) and row.get("node_id")
        }
        after_nodes = {
            str(row["node_id"]): row
            for row in after.get("nodes", ())
            if isinstance(row, Mapping) and row.get("node_id")
        }
        changed = sorted(
            node_id
            for node_id in before_nodes.keys() & after_nodes.keys()
            if before_nodes[node_id] != after_nodes[node_id]
        )
        return {
            "schema": "hashmarks.dependency-resolution-delta.v1",
            "comparability": "comparable",
            "before_resolution_identity": before.get("resolution_identity"),
            "after_resolution_identity": after.get("resolution_identity"),
            "nodes_added": sorted(after_nodes.keys() - before_nodes.keys()),
            "nodes_removed": sorted(before_nodes.keys() - after_nodes.keys()),
            "nodes_changed": changed,
        }
