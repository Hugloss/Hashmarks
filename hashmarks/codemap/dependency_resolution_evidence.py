from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from .dependency_resolution_query import dependency_queries

if TYPE_CHECKING:
    from .engine import CodeMap

_SCHEMA_V2 = "hashmarks.dependency-resolution.v2"
_MAX_CONTEXTS = 64
_MAX_INVENTORY = 16384
_MAX_EVIDENCE_SOURCES = 256
_MAX_NODES = 4096
_MAX_EDGES = 16384
_MAX_ROOTS = 256
_MAX_INPUTS = 256
_MAX_MODULE_OWNERSHIP = 4096
_MAX_ID_CHARS = 512
_MAX_TEXT_CHARS = 4096
_MAX_REQUEST_BYTES = 1_048_576
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_MEMBER_REVISION = re.compile(r"^[0-9a-f]{64}$")


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
    return (
        "sha256:"
        + hashlib.sha256(domain.encode("utf-8") + b"\0" + _canonical(value)).hexdigest()
    )


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
        if snapshot.get("schema") != _SCHEMA_V2:
            raise ValueError(f"dependency resolution schema must be {_SCHEMA_V2}")
        return self._dependency_resolution_evidence_v2(snapshot)

    def _dependency_resolution_evidence_v2(  # noqa: PLR0914, PLR0915
        self,
        snapshot: Mapping[str, object],
    ) -> dict[str, object]:
        """Qualify a multi-context dependency observation without executing its producer."""
        producer_packet, scope_packet, contexts, context_set = (
            self._dependency_header_v2(snapshot)
        )

        evidence_sources = self._dependency_evidence_sources_v2(
            snapshot.get("evidence_sources", ()), context_set
        )
        source_ids = {str(row["source_id"]) for row in evidence_sources}
        components = self._dependency_components_v2(snapshot.get("components", ()))
        component_ids = {str(row["component_id"]) for row in components}
        selections = self._dependency_selections_v2(
            snapshot.get("selections", ()), component_ids, context_set, source_ids
        )
        node_ids = {str(row["node_id"]) for row in selections}
        selected_component_ids = {str(row["component_id"]) for row in selections}
        orphan_components = sorted(component_ids - selected_component_ids)
        if orphan_components:
            raise ValueError(
                f"component has no dependency selection: {orphan_components[0]}"
            )
        inventory = self._dependency_inventory_v2(
            snapshot.get("inventory", ()), node_ids, context_set, source_ids
        )
        relationships = self._dependency_relationships_v2(
            snapshot.get("relationships", ()), node_ids, context_set, source_ids
        )

        raw_roots = snapshot.get("roots", ())
        roots = self._dependency_roots_v2(raw_roots, node_ids, context_set, source_ids)
        repository_inputs = self._dependency_repository_inputs(
            snapshot.get("repository_inputs", ())
        )
        module_ownership = self._dependency_module_ownership_v2(
            snapshot.get("module_ownership", ()),
            node_ids,
            context_set,
            source_ids,
        )
        coverage = self._dependency_coverage_v2(
            snapshot.get("coverage", ()), context_set, evidence_sources
        )
        self._validate_dependency_coverage_facts_v2(
            coverage=coverage,
            roots=roots,
            inventory=inventory,
            relationships=relationships,
        )
        sources_by_id = {
            str(row["source_id"]): row
            for row in evidence_sources
            if row.get("source_id")
        }
        self._validate_dependency_context_membership_v2(
            roots=roots,
            inventory=inventory,
            relationships=relationships,
            selections=selections,
        )
        self._validate_dependency_resolution_source_contexts_v2(
            roots=roots,
            inventory=inventory,
            relationships=relationships,
            sources_by_id=sources_by_id,
        )
        self._validate_dependency_graph_fact_source_authority_v2(
            roots=roots,
            relationships=relationships,
            inventory=inventory,
            sources_by_id=sources_by_id,
        )
        self._validate_dependency_module_source_authority_v2(
            module_ownership=module_ownership,
            selections=selections,
            sources_by_id=sources_by_id,
        )
        self._validate_dependency_selection_source_contexts_v2(
            selections=selections,
            sources_by_id=sources_by_id,
        )

        definition = {
            "producer": producer_packet,
            "scope": scope_packet,
            "contexts": sorted(contexts),
            "roots": [
                {
                    field: value
                    for field, value in row.items()
                    if field != "evidence_sources"
                }
                for row in roots
            ],
        }
        resolution = {
            "components": components,
            "selections": selections,
            "inventory": inventory,
            "relationships": relationships,
        }
        definition_identity = _identity(
            "hashmarks.dependency-resolution-definition.v2", definition
        )
        identity_resolution = {
            key: [
                {
                    field: value
                    for field, value in row.items()
                    if field != "evidence_sources"
                }
                for row in rows
            ]
            for key, rows in resolution.items()
        }
        resolution_identity = _identity(
            "hashmarks.dependency-resolution-graph.v2",
            {"definition_identity": definition_identity, **identity_resolution},
        )

        repository_binding = {
            "repository_identity": self._repository_packet_identity(),
            "codemap_generation": int(self.store.generation()),
        }
        observation_payload = {
            "resolution_identity": resolution_identity,
            "repository_binding": repository_binding,
            "repository_inputs": repository_inputs,
            "root_evidence": [
                {
                    "node_id": row["node_id"],
                    "context": row["context"],
                    "evidence_sources": row["evidence_sources"],
                }
                for row in roots
            ],
            "module_ownership": module_ownership,
            "evidence_sources": evidence_sources,
            "coverage": coverage,
        }
        observation_identity = _identity(
            "hashmarks.dependency-resolution-observation.v2", observation_payload
        )
        negative = self._dependency_negative_evidence_v2(coverage)
        return {
            "schema": _SCHEMA_V2,
            "authority": "qualified-external-observation",
            "producer_authority": "caller-claimed",
            "definition_identity": definition_identity,
            "resolution_identity": resolution_identity,
            "observation_identity": observation_identity,
            **definition,
            **resolution,
            "repository_binding": repository_binding,
            "repository_inputs": repository_inputs,
            "module_ownership": module_ownership,
            "evidence_sources": evidence_sources,
            "coverage": coverage,
            "negative_evidence": negative,
        }

    @staticmethod
    def _dependency_header_v2(
        snapshot: Mapping[str, object],
    ) -> tuple[dict[str, object], dict[str, object], list[str], set[str]]:
        producer = snapshot.get("producer")
        if not isinstance(producer, Mapping):
            raise ValueError("dependency resolution producer must be an object")
        producer_packet = dict(producer)
        _identifier(producer_packet.get("kind"), label="producer kind")
        _text(
            producer_packet.get("schema_version"),
            label="producer schema_version",
            required=True,
        )

        scope = snapshot.get("scope")
        if not isinstance(scope, Mapping) or not scope:
            raise ValueError("dependency resolution scope must be a non-empty object")
        scope_packet = dict(scope)
        _canonical(scope_packet)

        raw_contexts = snapshot.get("contexts", ())
        if not isinstance(raw_contexts, Sequence) or isinstance(
            raw_contexts, (str, bytes, bytearray)
        ):
            raise ValueError("contexts must be a sequence")
        contexts = [_identifier(value, label="context") for value in raw_contexts]
        if not contexts:
            raise ValueError("contexts must not be empty")
        if len(contexts) > _MAX_CONTEXTS:
            raise ValueError(f"contexts exceeds {_MAX_CONTEXTS} entries")
        if len(set(contexts)) != len(contexts):
            raise ValueError("duplicate dependency resolution context")
        return producer_packet, scope_packet, contexts, set(contexts)

    @staticmethod
    def _validate_dependency_context_membership_v2(
        *,
        roots: Sequence[Mapping[str, object]],
        inventory: Sequence[Mapping[str, object]],
        relationships: Sequence[Mapping[str, object]],
        selections: Sequence[Mapping[str, object]],
    ) -> None:
        selection_contexts = {
            str(row["node_id"]): set(row["contexts"]) for row in selections
        }
        for row in roots:
            if row["context"] not in selection_contexts[str(row["node_id"])]:
                raise ValueError(
                    f"root context not selected: {row['node_id']}:{row['context']}"
                )
        for row in inventory:
            if row["context"] not in selection_contexts[str(row["node_id"])]:
                raise ValueError(
                    f"inventory context not selected: {row['node_id']}:{row['context']}"
                )
        for row in relationships:
            context = str(row["context"])
            if (
                context not in selection_contexts[str(row["source"])]
                or context not in selection_contexts[str(row["target"])]
            ):
                raise ValueError(
                    "relationship context not selected by both endpoints: "
                    f"{row['source']}->{row['target']}:{context}"
                )

    @staticmethod
    def _validate_dependency_resolution_source_contexts_v2(
        *,
        roots: Sequence[Mapping[str, object]],
        inventory: Sequence[Mapping[str, object]],
        relationships: Sequence[Mapping[str, object]],
        inventory: Sequence[Mapping[str, object]],
        sources_by_id: Mapping[str, Mapping[str, object]],
    ) -> None:
        for row in roots:
            for ref in row["evidence_sources"]:
                source_context = str(sources_by_id[str(ref)].get("context") or "")
                if source_context and source_context != row["context"]:
                    raise ValueError(
                        "incompatible root evidence source context: "
                        f"{row['node_id']}:{row['context']}"
                    )
        for row in inventory:
            for ref in row["evidence_sources"]:
                source_context = str(sources_by_id[str(ref)].get("context") or "")
                if source_context and source_context != row["context"]:
                    raise ValueError(
                        "incompatible inventory evidence source context: "
                        f"{row['node_id']}:{row['context']}"
                    )
        for row in relationships:
            for ref in row["evidence_sources"]:
                source_context = str(sources_by_id[str(ref)].get("context") or "")
                if source_context and source_context != row["context"]:
                    raise ValueError(
                        "incompatible relationship evidence source context: "
                        f"{row['source']}->{row['target']}:{row['context']}"
                    )

    @staticmethod
    def _validate_dependency_graph_fact_source_authority_v2(
        *,
        roots: Sequence[Mapping[str, object]],
        relationships: Sequence[Mapping[str, object]],
        sources_by_id: Mapping[str, Mapping[str, object]],
    ) -> None:
        for row in roots:
            if not any(
                sources_by_id[str(ref)].get("kind") == "resolution-graph"
                for ref in row["evidence_sources"]
            ):
                raise ValueError("root requires resolution-graph evidence source")
        for row in relationships:
            if not any(
                sources_by_id[str(ref)].get("kind") == "resolution-graph"
                for ref in row["evidence_sources"]
            ):
                raise ValueError(
                    "relationship requires resolution-graph evidence source"
                )

        for row in inventory:
            if not any(
                sources_by_id[str(ref)].get("kind") == "resolved-inventory"
                for ref in row["evidence_sources"]
            ):
                raise ValueError(
                    "inventory requires resolved-inventory evidence source"
                )

    @staticmethod
    def _validate_dependency_module_source_authority_v2(
        *,
        module_ownership: Sequence[Mapping[str, object]],
        selections: Sequence[Mapping[str, object]],
        sources_by_id: Mapping[str, Mapping[str, object]],
    ) -> None:
        selection_contexts = {
            str(row["node_id"]): set(row["contexts"]) for row in selections
        }
        for row in module_ownership:
            for owner in row["owners"]:
                if row["context"] not in selection_contexts[str(owner)]:
                    raise ValueError(
                        "module owner context not selected: "
                        f"{row['module']}:{owner}:{row['context']}"
                    )
            for ref in row["evidence_sources"]:
                source = sources_by_id[str(ref)]
                source_context = str(source.get("context") or "")
                if source_context and source_context != row["context"]:
                    raise ValueError(
                        "incompatible module ownership evidence source context: "
                        f"{row['module']}:{row['context']}"
                    )
                if row["completeness"] == "complete" and (
                    source.get("completeness") != "complete"
                    or source.get("truncation") != "complete"
                ):
                    raise ValueError(
                        "module ownership exceeds evidence source: "
                        f"{row['module']}:{row['context']}"
                    )

    @staticmethod
    def _validate_dependency_selection_source_contexts_v2(
        *,
        selections: Sequence[Mapping[str, object]],
        sources_by_id: Mapping[str, Mapping[str, object]],
    ) -> None:
        for row in selections:
            contexts_for_selection = set(row["contexts"])
            source_contexts = {
                str(sources_by_id[str(ref)].get("context") or "")
                for ref in row["evidence_sources"]
            }
            for source_context in source_contexts:
                if source_context and source_context not in contexts_for_selection:
                    raise ValueError(
                        "incompatible selection evidence source context: "
                        f"{row['node_id']}:{source_context}"
                    )
            if "" not in source_contexts:
                missing_contexts = sorted(contexts_for_selection - source_contexts)
                if missing_contexts:
                    raise ValueError(
                        "selection context lacks evidence source: "
                        f"{row['node_id']}:{missing_contexts[0]}"
                    )

    @staticmethod
    def _dependency_components_v2(value: object) -> list[dict[str, object]]:
        rows = _objects(value, label="components", limit=_MAX_NODES)
        result: list[dict[str, object]] = []
        seen: set[str] = set()
        for raw in rows:
            component_id = _identifier(raw.get("component_id"), label="component_id")
            if component_id in seen:
                raise ValueError(f"duplicate dependency component_id: {component_id}")
            seen.add(component_id)
            result.append(
                {
                    "component_id": component_id,
                    "name": _text(
                        raw.get("name"), label="component name", required=True
                    ),
                    "ecosystem": _text(raw.get("ecosystem"), label="ecosystem"),
                }
            )
        return sorted(result, key=lambda row: str(row["component_id"]))

    @staticmethod
    def _dependency_context_list_v2(
        value: object, *, label: str, allowed: set[str]
    ) -> list[str]:
        if not isinstance(value, Sequence) or isinstance(
            value, (str, bytes, bytearray)
        ):
            raise ValueError(f"{label} must be a sequence")
        contexts = [_identifier(row, label=label) for row in value]
        if not contexts:
            raise ValueError(f"{label} must not be empty")
        if len(set(contexts)) != len(contexts):
            raise ValueError(f"duplicate {label}")
        unknown = sorted(set(contexts) - allowed)
        if unknown:
            raise ValueError(f"unknown {label}: {unknown[0]}")
        return sorted(contexts)

    @staticmethod
    def _dependency_source_refs_v2(
        value: object, *, label: str, allowed: set[str]
    ) -> list[str]:
        if not isinstance(value, Sequence) or isinstance(
            value, (str, bytes, bytearray)
        ):
            raise ValueError(f"{label} must be a sequence")
        refs = [_identifier(row, label=label) for row in value]
        if len(set(refs)) != len(refs):
            raise ValueError(f"duplicate {label}")
        dangling = sorted(set(refs) - allowed)
        if dangling:
            raise ValueError(f"dangling {label}: {dangling[0]}")
        return sorted(refs)

    @classmethod
    def _dependency_evidence_sources_v2(
        cls, value: object, contexts: set[str]
    ) -> list[dict[str, object]]:
        rows = _objects(value, label="evidence_sources", limit=_MAX_EVIDENCE_SOURCES)
        result: list[dict[str, object]] = []
        seen: set[str] = set()
        for raw in rows:
            source_id = _identifier(raw.get("source_id"), label="source_id")
            if source_id in seen:
                raise ValueError(f"duplicate dependency evidence source: {source_id}")
            seen.add(source_id)
            context = _text(raw.get("context"), label="evidence source context")
            if context and context not in contexts:
                raise ValueError(f"unknown evidence source context: {context}")
            completeness = str(raw.get("completeness") or "unknown").strip()
            truncation = str(raw.get("truncation") or "unknown").strip()
            if completeness not in {"complete", "incomplete", "unknown"}:
                raise ValueError(
                    "evidence source completeness must be complete, incomplete, or unknown"
                )
            if truncation not in {"complete", "truncated", "unknown"}:
                raise ValueError(
                    "evidence source truncation must be complete, truncated, or unknown"
                )
            if completeness == "complete" and truncation != "complete":
                raise ValueError(
                    "complete evidence source requires truncation=complete"
                )
            result.append(
                {
                    "source_id": source_id,
                    "kind": _text(
                        raw.get("kind"), label="evidence source kind", required=True
                    ),
                    "context": context,
                    "completeness": completeness,
                    "truncation": truncation,
                    "producer_digest": _text(
                        raw.get("producer_digest"), label="producer digest"
                    ),
                }
            )
        return sorted(result, key=lambda row: str(row["source_id"]))

    @classmethod
    def _dependency_selections_v2(
        cls,
        value: object,
        component_ids: set[str],
        contexts: set[str],
        source_ids: set[str],
    ) -> list[dict[str, object]]:
        rows = _objects(value, label="selections", limit=_MAX_NODES)
        result: list[dict[str, object]] = []
        seen: set[str] = set()
        for raw in rows:
            node_id = _identifier(raw.get("node_id"), label="node_id")
            if node_id in seen:
                raise ValueError(f"duplicate dependency selection node_id: {node_id}")
            seen.add(node_id)
            component_id = _identifier(raw.get("component_id"), label="component_id")
            if component_id not in component_ids:
                raise ValueError(f"dangling dependency component: {component_id}")
            refs = cls._dependency_source_refs_v2(
                raw.get("evidence_sources", ()),
                label="selection evidence source",
                allowed=source_ids,
            )
            if not refs:
                raise ValueError("selection must reference evidence source")
            selection_contexts = cls._dependency_context_list_v2(
                raw.get("contexts", ()),
                label="selection context",
                allowed=contexts,
            )
            result.append(
                {
                    "node_id": node_id,
                    "component_id": component_id,
                    "version": _text(raw.get("version"), label="version"),
                    "source": _text(raw.get("source"), label="source"),
                    "marker": _text(raw.get("marker"), label="marker"),
                    "contexts": selection_contexts,
                    "evidence_sources": refs,
                }
            )
        return sorted(result, key=lambda row: str(row["node_id"]))

    @classmethod
    def _dependency_inventory_v2(
        cls,
        value: object,
        node_ids: set[str],
        contexts: set[str],
        source_ids: set[str],
    ) -> list[dict[str, object]]:
        rows = _objects(value, label="inventory", limit=_MAX_INVENTORY)
        result: list[dict[str, object]] = []
        seen: set[tuple[str, str]] = set()
        for raw in rows:
            node_id = _identifier(raw.get("node_id"), label="inventory node_id")
            context = _identifier(raw.get("context"), label="inventory context")
            if node_id not in node_ids:
                raise ValueError(f"dangling dependency inventory node: {node_id}")
            if context not in contexts:
                raise ValueError(f"unknown inventory context: {context}")
            key = (node_id, context)
            if key in seen:
                raise ValueError(
                    f"duplicate dependency inventory membership: {node_id}:{context}"
                )
            seen.add(key)
            refs = cls._dependency_source_refs_v2(
                raw.get("evidence_sources", ()),
                label="inventory evidence source",
                allowed=source_ids,
            )
            if not refs:
                raise ValueError("inventory must reference evidence source")
            result.append(
                {
                    "node_id": node_id,
                    "context": context,
                    "evidence_sources": refs,
                }
            )
        return sorted(
            result, key=lambda row: (str(row["node_id"]), str(row["context"]))
        )

    @classmethod
    def _dependency_relationships_v2(
        cls,
        value: object,
        node_ids: set[str],
        contexts: set[str],
        source_ids: set[str],
    ) -> list[dict[str, object]]:
        rows = _objects(value, label="relationships", limit=_MAX_EDGES)
        result: list[dict[str, object]] = []
        seen: set[tuple[str, str, str, str, str, str]] = set()
        for raw in rows:
            source = _identifier(raw.get("source"), label="relationship source")
            target = _identifier(raw.get("target"), label="relationship target")
            context = _identifier(raw.get("context"), label="relationship context")
            if source not in node_ids or target not in node_ids:
                raise ValueError(
                    f"dangling dependency relationship: {source}->{target}"
                )
            if context not in contexts:
                raise ValueError(f"unknown relationship context: {context}")
            refs = cls._dependency_source_refs_v2(
                raw.get("evidence_sources", ()),
                label="relationship evidence source",
                allowed=source_ids,
            )
            if not refs:
                raise ValueError("relationship must reference evidence source")
            packet = {
                "source": source,
                "target": target,
                "kind": _text(
                    raw.get("kind"), label="relationship kind", required=True
                ),
                "context": context,
                "effective_scope": _text(
                    raw.get("effective_scope"), label="effective scope"
                ),
                "marker": _text(raw.get("marker"), label="relationship marker"),
                "evidence_sources": refs,
            }
            key = (
                source,
                target,
                str(packet["kind"]),
                context,
                str(packet["effective_scope"]),
                str(packet["marker"]),
            )
            if key in seen:
                raise ValueError(
                    f"duplicate dependency relationship: {source}->{target}:{context}"
                )
            seen.add(key)
            result.append(packet)
        return sorted(
            result,
            key=lambda row: (
                str(row["source"]),
                str(row["target"]),
                str(row["kind"]),
                str(row["context"]),
                str(row["effective_scope"]),
                str(row["marker"]),
            ),
        )

    @classmethod
    def _dependency_roots_v2(
        cls,
        value: object,
        node_ids: set[str],
        contexts: set[str],
        source_ids: set[str],
    ) -> list[dict[str, object]]:
        rows = _objects(value, label="roots", limit=_MAX_ROOTS)
        result: list[dict[str, object]] = []
        seen: set[tuple[str, str]] = set()
        for raw in rows:
            node_id = _identifier(raw.get("node_id"), label="root node_id")
            context = _identifier(raw.get("context"), label="root context")
            if node_id not in node_ids:
                raise ValueError(f"dangling dependency resolution root: {node_id}")
            if context not in contexts:
                raise ValueError(f"unknown root context: {context}")
            key = (node_id, context)
            if key in seen:
                raise ValueError(
                    f"duplicate dependency resolution root: {node_id}:{context}"
                )
            seen.add(key)
            refs = cls._dependency_source_refs_v2(
                raw.get("evidence_sources", ()),
                label="root evidence source",
                allowed=source_ids,
            )
            if not refs:
                raise ValueError("root must reference evidence source")
            result.append(
                {"node_id": node_id, "context": context, "evidence_sources": refs}
            )
        return sorted(
            result, key=lambda row: (str(row["context"]), str(row["node_id"]))
        )

    @classmethod
    def _dependency_module_ownership_v2(
        cls,
        value: object,
        node_ids: set[str],
        contexts: set[str],
        source_ids: set[str],
    ) -> list[dict[str, object]]:
        rows = _objects(value, label="module_ownership", limit=_MAX_MODULE_OWNERSHIP)
        result: list[dict[str, object]] = []
        seen: set[tuple[str, str]] = set()
        for raw in rows:
            module = _text(raw.get("module"), label="module", required=True)
            context = _identifier(raw.get("context"), label="module ownership context")
            if context not in contexts:
                raise ValueError(f"unknown module ownership context: {context}")
            key = (module, context)
            if key in seen:
                raise ValueError(
                    f"duplicate module ownership observation: {module}:{context}"
                )
            seen.add(key)
            raw_owners = raw.get("owners", ())
            if not isinstance(raw_owners, Sequence) or isinstance(
                raw_owners, (str, bytes, bytearray)
            ):
                raise ValueError("module ownership owners must be a sequence")
            owners = [_identifier(owner, label="module owner") for owner in raw_owners]
            if len(set(owners)) != len(owners):
                raise ValueError(f"duplicate owner for module: {module}")
            dangling = sorted(set(owners) - node_ids)
            if dangling:
                raise ValueError(
                    f"dangling module ownership node for {module}: {dangling[0]}"
                )
            completeness = str(raw.get("completeness") or "unknown").strip()
            if completeness not in {"complete", "incomplete", "unknown"}:
                raise ValueError(
                    "module ownership completeness must be complete, incomplete, or unknown"
                )
            refs = cls._dependency_source_refs_v2(
                raw.get("evidence_sources", ()),
                label="module ownership evidence source",
                allowed=source_ids,
            )
            if not refs:
                raise ValueError("module ownership must reference evidence source")
            result.append(
                {
                    "module": module,
                    "context": context,
                    "owners": sorted(owners),
                    "state": (
                        "resolved-unique"
                        if len(owners) == 1
                        else "resolved-ambiguous"
                        if owners
                        else "unresolved"
                    ),
                    "completeness": completeness,
                    "evidence_sources": refs,
                    "authority": "qualified-external-observation",
                }
            )
        return sorted(result, key=lambda row: (str(row["module"]), str(row["context"])))

    @classmethod
    def _dependency_coverage_v2(
        cls,
        value: object,
        contexts: set[str],
        evidence_sources: Sequence[Mapping[str, object]],
    ) -> list[dict[str, object]]:
        rows = _objects(value, label="coverage", limit=_MAX_CONTEXTS * 4)
        result: list[dict[str, object]] = []
        seen: set[tuple[str, str]] = set()
        sources = {
            str(row["source_id"]): row
            for row in evidence_sources
            if row.get("source_id")
        }
        source_ids = set(sources)
        for raw in rows:
            context = _identifier(raw.get("context"), label="coverage context")
            kind = _identifier(raw.get("kind"), label="coverage kind")
            if context not in contexts:
                raise ValueError(f"unknown coverage context: {context}")
            key = (context, kind)
            if key in seen:
                raise ValueError(f"duplicate dependency coverage: {context}:{kind}")
            seen.add(key)
            completeness = str(raw.get("completeness") or "unknown").strip()
            truncation = str(raw.get("truncation") or "unknown").strip()
            if completeness not in {"complete", "incomplete", "unknown"}:
                raise ValueError(
                    "coverage completeness must be complete, incomplete, or unknown"
                )
            if truncation not in {"complete", "truncated", "unknown"}:
                raise ValueError(
                    "coverage truncation must be complete, truncated, or unknown"
                )
            if completeness == "complete" and truncation != "complete":
                raise ValueError("complete coverage requires truncation=complete")
            refs = cls._dependency_source_refs_v2(
                raw.get("evidence_sources", ()),
                label="coverage evidence source",
                allowed=source_ids,
            )
            if not refs:
                raise ValueError("coverage must reference evidence source")
            referenced_sources = [sources[ref] for ref in refs]
            cls._validate_dependency_coverage_source_kind_v2(
                kind=kind,
                sources=referenced_sources,
            )
            for source in referenced_sources:
                source_context = str(source.get("context") or "")
                if source_context and source_context != context:
                    raise ValueError(
                        f"incompatible evidence source context for coverage: {context}:{kind}"
                    )
                if completeness == "complete" and (
                    source.get("completeness") != "complete"
                    or source.get("truncation") != "complete"
                ):
                    raise ValueError(
                        f"coverage exceeds evidence source: {context}:{kind}"
                    )
            result.append(
                {
                    "context": context,
                    "kind": kind,
                    "completeness": completeness,
                    "truncation": truncation,
                    "evidence_sources": refs,
                }
            )
        return sorted(result, key=lambda row: (str(row["context"]), str(row["kind"])))

    @staticmethod
    def _validate_dependency_coverage_source_kind_v2(
        *,
        kind: str,
        sources: Sequence[Mapping[str, object]],
    ) -> None:
        if kind == "resolution-graph" and not any(
            source.get("kind") == "resolution-graph" for source in sources
        ):
            raise ValueError(
                "resolution-graph coverage requires resolution-graph evidence source"
            )
        if kind == "resolved-inventory" and not any(
            source.get("kind") == "resolved-inventory" for source in sources
        ):
            raise ValueError(
                "resolved-inventory coverage requires resolved-inventory evidence source"
            )

    @staticmethod
    def _validate_dependency_coverage_facts_v2(
        *,
        coverage: Sequence[Mapping[str, object]],
        roots: Sequence[Mapping[str, object]],
        inventory: Sequence[Mapping[str, object]],
        relationships: Sequence[Mapping[str, object]],
    ) -> None:
        for row in coverage:
            if row.get("completeness") != "complete":
                continue
            context = str(row["context"])
            kind = str(row["kind"])
            if kind == "resolution-graph":
                has_root = any(str(item["context"]) == context for item in roots)
                if not has_root:
                    raise ValueError(
                        f"complete resolution-graph coverage lacks root: {context}"
                    )

    @staticmethod
    def _dependency_negative_evidence_v2(
        coverage: Sequence[Mapping[str, object]],
    ) -> list[dict[str, object]]:
        return [
            {
                "context": str(row["context"]),
                "kind": str(row["kind"]),
                "state": (
                    "admissible-within-declared-scope"
                    if row.get("completeness") == "complete"
                    and row.get("truncation") == "complete"
                    else "not-admissible"
                ),
            }
            for row in coverage
        ]

    def dependency_import_correspondence(
        self,
        observation: Mapping[str, object],
        *,
        source_path: str,
        import_target: str,
        context: str | None = None,
    ) -> dict[str, object]:
        schema = observation.get("schema")
        if schema != _SCHEMA_V2:
            raise ValueError(
                "dependency import correspondence requires a qualified observation"
            )
        candidates = self._python_import_module_candidates(source_path, import_target)
        rows = [
            row
            for row in observation.get("module_ownership", ())
            if isinstance(row, Mapping)
            and row.get("module")
            and (context is None or str(row.get("context") or "") == context)
        ]
        matches = [
            row for module in candidates for row in rows if row.get("module") == module
        ]
        repository_paths = self._resolve_import_paths(source_path, import_target)
        if not matches:
            return {
                "source_path": source_path,
                "import_target": import_target,
                **({"context": context} if context is not None else {}),
                "repository_paths": repository_paths,
                "distribution_state": "unknown",
                "distribution_nodes": [],
                "causation": "not-inferred",
            }

        owners = sorted(
            {str(owner) for row in matches for owner in row.get("owners", ()) if owner}
        )
        completeness = (
            "complete"
            if all(row.get("completeness") == "complete" for row in matches)
            else "incomplete"
            if any(row.get("completeness") == "incomplete" for row in matches)
            else "unknown"
        )
        contexts = sorted(
            {
                str(row.get("context"))
                for row in matches
                if row.get("context") is not None
            }
        )
        return {
            "source_path": source_path,
            "import_target": import_target,
            **({"context": context} if context is not None else {}),
            "repository_paths": repository_paths,
            "module": str(matches[0]["module"]),
            "distribution_state": (
                "resolved-unique"
                if len(owners) == 1
                else "resolved-ambiguous"
                if owners
                else "unresolved"
            ),
            "distribution_nodes": owners,
            "ownership_completeness": completeness,
            "observed_contexts": contexts,
            "causation": "not-inferred",
        }

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
            if claimed is not None and not _MEMBER_REVISION.fullmatch(str(claimed)):
                raise ValueError(
                    "repository input member_revision must be a lowercase 64-character sha256 hex digest"
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

    def dependency_evidence_correlation(
        self,
        observation: Mapping[str, object],
        request: Mapping[str, object],
    ) -> dict[str, object]:
        """Compose dependency-owner projections with generic evidence correlation.

        Package semantics remain owned here.  The generic correlation owner receives
        only ordinary external anchors and repository locators.
        """
        schema = observation.get("schema")
        if schema != _SCHEMA_V2:
            raise ValueError(
                "dependency evidence correlation requires a qualified observation"
            )
        raw_correlations = request.get("correlations", ())
        correlations = _objects(raw_correlations, label="correlations", limit=256)
        bundles: list[dict[str, object]] = []
        dependency_links: list[dict[str, object]] = []
        ownership = [
            row
            for row in observation.get("module_ownership", ())
            if isinstance(row, Mapping) and row.get("module")
        ]
        for index, raw in enumerate(correlations):
            module = _text(raw.get("module"), label="correlation module", required=True)
            context = _text(raw.get("context"), label="correlation context")
            anchors = raw.get("anchors", ())
            if not isinstance(anchors, Sequence) or isinstance(
                anchors, (str, bytes, bytearray)
            ):
                raise ValueError("correlation anchors must be a sequence")
            matches = [
                row
                for row in ownership
                if row.get("module") == module
                and (not context or str(row.get("context") or "") == context)
            ]
            owners = sorted(
                {
                    str(owner)
                    for row in matches
                    for owner in row.get("owners", ())
                    if owner
                }
            )
            completeness = (
                "complete"
                if matches
                and all(row.get("completeness") == "complete" for row in matches)
                else "incomplete"
                if any(row.get("completeness") == "incomplete" for row in matches)
                else "unknown"
            )
            observed_contexts = sorted(
                {
                    str(row.get("context"))
                    for row in matches
                    if row.get("context") is not None
                }
            )
            dependency_links.append(
                {
                    "module": module,
                    **({"context": context} if context else {}),
                    "distribution_state": (
                        "resolved-unique"
                        if len(owners) == 1
                        else "resolved-ambiguous"
                        if owners
                        else "unknown"
                    ),
                    "distribution_nodes": owners,
                    "ownership_completeness": completeness,
                    "observed_contexts": observed_contexts,
                    "causation": "not-inferred",
                }
            )
            bundles.append(
                {
                    "bundle_id": f"dependency-correlation-{index}",
                    "producer": {
                        "kind": "dependency-correlation-adapter",
                        "resolution_identity": observation.get("resolution_identity"),
                    },
                    "completeness": str(raw.get("completeness") or "unknown"),
                    "scope": {
                        "kind": "dependency-module-correlation",
                        "module": module,
                        **({"context": context} if context else {}),
                    },
                    "truncation": str(raw.get("truncation") or "unknown"),
                    "anchors": list(anchors),
                }
            )
        packet = self.correlate_evidence(
            bundles,
            path_mappings=list(request.get("path_mappings") or ()),
        )
        return {
            "schema": "hashmarks.dependency-evidence-correlation.v1",
            "resolution_identity": observation.get("resolution_identity"),
            "correlation": packet,
            "dependency_links": dependency_links,
            "authority": "repository-intelligence-only",
            "interpretation_authority": "consumer-owned",
            "causation": "not-inferred",
        }

    @staticmethod
    def dependency_resolution_queries(
        observation: Mapping[str, object],
        requests: Sequence[Mapping[str, object]],
    ) -> dict[str, object]:
        if observation.get("schema") != _SCHEMA_V2:
            raise ValueError("dependency queries require qualified v2 observation")
        return dependency_queries(observation, requests)

    @staticmethod
    def _dependency_resolution_delta_v2(  # noqa: C901
        before: Mapping[str, object],
        after: Mapping[str, object],
    ) -> dict[str, object]:
        before_definition = before.get("definition_identity")
        after_definition = after.get("definition_identity")
        if not _SHA256.fullmatch(str(before_definition or "")) or not _SHA256.fullmatch(
            str(after_definition or "")
        ):
            raise ValueError("dependency resolution definition identity is malformed")
        if before_definition != after_definition:
            return {
                "schema": "hashmarks.dependency-resolution-delta.v2",
                "comparability": "not-comparable",
                "reason": "definition-changed",
                "before_definition_identity": before_definition,
                "after_definition_identity": after_definition,
            }

        def keyed(rows: object, field: str) -> dict[str, Mapping[str, object]]:
            return {
                str(row[field]): row
                for row in rows
                if isinstance(row, Mapping) and row.get(field)
            }

        before_components = keyed(before.get("components", ()), "component_id")
        after_components = keyed(after.get("components", ()), "component_id")
        before_selections = keyed(before.get("selections", ()), "node_id")
        after_selections = keyed(after.get("selections", ()), "node_id")

        def changed(
            left: Mapping[str, Mapping[str, object]],
            right: Mapping[str, Mapping[str, object]],
        ) -> list[str]:
            def semantic(row: Mapping[str, object]) -> dict[str, object]:
                return {
                    key: value
                    for key, value in row.items()
                    if key not in {"evidence_sources", "authority"}
                }

            return sorted(
                key
                for key in left.keys() & right.keys()
                if semantic(left[key]) != semantic(right[key])
            )

        def inventory_key(row: Mapping[str, object]) -> tuple[str, str]:
            return (str(row.get("node_id") or ""), str(row.get("context") or ""))

        def relationship_key(
            row: Mapping[str, object],
        ) -> tuple[str, str, str, str, str, str]:
            return (
                str(row.get("source") or ""),
                str(row.get("target") or ""),
                str(row.get("kind") or ""),
                str(row.get("context") or ""),
                str(row.get("effective_scope") or ""),
                str(row.get("marker") or ""),
            )

        before_inventory = {
            inventory_key(row)
            for row in before.get("inventory", ())
            if isinstance(row, Mapping)
        }
        after_inventory = {
            inventory_key(row)
            for row in after.get("inventory", ())
            if isinstance(row, Mapping)
        }
        before_relationships = {
            relationship_key(row)
            for row in before.get("relationships", ())
            if isinstance(row, Mapping)
        }
        after_relationships = {
            relationship_key(row)
            for row in after.get("relationships", ())
            if isinstance(row, Mapping)
        }

        def ownership_key(row: Mapping[str, object]) -> str:
            return f"{row.get('module') or ''}|{row.get('context') or ''}"

        before_ownership = {
            ownership_key(row): row
            for row in before.get("module_ownership", ())
            if isinstance(row, Mapping) and row.get("module")
        }
        after_ownership = {
            ownership_key(row): row
            for row in after.get("module_ownership", ())
            if isinstance(row, Mapping) and row.get("module")
        }
        return {
            "schema": "hashmarks.dependency-resolution-delta.v2",
            "comparability": "comparable",
            "before_resolution_identity": before.get("resolution_identity"),
            "after_resolution_identity": after.get("resolution_identity"),
            "before_observation_identity": before.get("observation_identity"),
            "after_observation_identity": after.get("observation_identity"),
            "components_added": sorted(
                after_components.keys() - before_components.keys()
            ),
            "components_removed": sorted(
                before_components.keys() - after_components.keys()
            ),
            "components_changed": changed(before_components, after_components),
            "selections_added": sorted(
                after_selections.keys() - before_selections.keys()
            ),
            "selections_removed": sorted(
                before_selections.keys() - after_selections.keys()
            ),
            "selections_changed": changed(before_selections, after_selections),
            "inventory_added": [
                list(row) for row in sorted(after_inventory - before_inventory)
            ],
            "inventory_removed": [
                list(row) for row in sorted(before_inventory - after_inventory)
            ],
            "relationships_added": [
                list(row) for row in sorted(after_relationships - before_relationships)
            ],
            "relationships_removed": [
                list(row) for row in sorted(before_relationships - after_relationships)
            ],
            "module_ownership_added": sorted(
                after_ownership.keys() - before_ownership.keys()
            ),
            "module_ownership_removed": sorted(
                before_ownership.keys() - after_ownership.keys()
            ),
            "module_ownership_changed": changed(before_ownership, after_ownership),
            "causation": "not-inferred",
        }

    @staticmethod
    def dependency_resolution_delta(
        before: Mapping[str, object],
        after: Mapping[str, object],
    ) -> dict[str, object]:
        if before.get("schema") != _SCHEMA_V2 or after.get("schema") != _SCHEMA_V2:
            raise ValueError(
                "dependency resolution delta requires matching qualified v2 observations"
            )
        return DependencyResolutionEvidenceMixin._dependency_resolution_delta_v2(
            before, after
        )
