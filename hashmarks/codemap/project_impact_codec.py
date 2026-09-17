from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

COMPACT_PROJECT_IMPACT_SCHEMA = "hashmarks.project-impact.compact.v1"


@dataclass(frozen=True)
class _ImpactDictionary:
    projects: list[str]
    kinds: list[str]
    producers: list[str]
    confidences: list[str]

    @property
    def project_index(self) -> dict[str, int]:
        return {value: index for index, value in enumerate(self.projects)}

    @property
    def kind_index(self) -> dict[str, int]:
        return {value: index for index, value in enumerate(self.kinds)}

    @property
    def producer_index(self) -> dict[str, int]:
        return {value: index for index, value in enumerate(self.producers)}

    @property
    def confidence_index(self) -> dict[str, int]:
        return {value: index for index, value in enumerate(self.confidences)}


def _mapping_rows(fragment: Mapping[str, object], key: str) -> list[dict[str, object]]:
    return [dict(row) for row in fragment.get(key, []) if isinstance(row, dict)]


def _impact_dictionary(roots: list[str], affected: list[dict[str, object]], edges: list[dict[str, object]]) -> _ImpactDictionary:
    projects = sorted({*roots, *(str(row.get("project") or "") for row in affected), *(str(row.get("from") or "") for row in edges), *(str(row.get("to") or "") for row in edges)} - {""})
    return _ImpactDictionary(
        projects=projects,
        kinds=sorted({str(row.get("kind") or "declared") for row in edges}),
        producers=sorted({str(row.get("producer") or "") for row in edges}),
        confidences=sorted({str(row.get("confidence") or "") for row in edges if row.get("confidence")}),
    )


def _edge_by_source(edges: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for edge in edges:
        source = str(edge.get("from") or "")
        if source:
            result.setdefault(source, edge)
    return result


def _compact_row(affected: dict[str, object], edge: dict[str, object] | None, dictionary: _ImpactDictionary) -> list[int] | None:
    project = str(affected.get("project") or "")
    if not project:
        return None
    depth = int(affected.get("depth") or 0)
    project_index = dictionary.project_index
    if edge is None:
        return [project_index[project], depth, -1, -1, -1]
    row = [
        project_index[project], depth, project_index.get(str(edge.get("to") or ""), -1),
        dictionary.kind_index[str(edge.get("kind") or "declared")],
        dictionary.producer_index[str(edge.get("producer") or "")],
    ]
    if dictionary.confidences:
        row.append(dictionary.confidence_index.get(str(edge.get("confidence") or ""), -1))
    return row


def compact_project_impact(fragment: Mapping[str, object]) -> dict[str, object]:
    roots = [str(value) for value in fragment.get("roots", []) if value]
    affected = _mapping_rows(fragment, "affected")
    edges = _mapping_rows(fragment, "edges")
    dictionary = _impact_dictionary(roots, affected, edges)
    edge_map = _edge_by_source(edges)
    rows = [row for item in affected if (row := _compact_row(item, edge_map.get(str(item.get("project") or "")), dictionary))]
    project_index = dictionary.project_index
    result: dict[str, object] = {
        "schema": COMPACT_PROJECT_IMPACT_SCHEMA, "projects": dictionary.projects,
        "kinds": dictionary.kinds, "producers": dictionary.producers,
        "roots": [project_index[value] for value in roots if value in project_index], "rows": rows,
        "reported_affected": int(fragment.get("reported_affected") or len(affected)),
        "total_affected": int(fragment.get("total_affected") or len(affected)), "complete": bool(fragment.get("complete")),
    }
    if dictionary.confidences:
        result["confidences"] = dictionary.confidences
    return result


def _lookup(values: list[str], index: int) -> str:
    return values[index] if 0 <= index < len(values) else ""


def _expanded_row(raw: object, dictionary: _ImpactDictionary) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    if not isinstance(raw, (list, tuple)) or len(raw) < 5:
        return None, None
    project_i, depth, target_i, kind_i, producer_i = (int(raw[index]) for index in range(5))
    project = _lookup(dictionary.projects, project_i)
    if not project:
        return None, None
    affected = {"project": project, "depth": depth}
    target = _lookup(dictionary.projects, target_i)
    if not target:
        return affected, None
    edge: dict[str, object] = {
        "from": project, "to": target, "kind": _lookup(dictionary.kinds, kind_i) or "declared",
        "producer": _lookup(dictionary.producers, producer_i),
    }
    if len(raw) >= 6:
        confidence = _lookup(dictionary.confidences, int(raw[5]))
        if confidence:
            edge["confidence"] = confidence
    return affected, edge


def expand_project_impact(fragment: Mapping[str, object]) -> dict[str, object]:
    if fragment.get("schema") != COMPACT_PROJECT_IMPACT_SCHEMA:
        return dict(fragment)
    dictionary = _ImpactDictionary(
        [str(value) for value in fragment.get("projects", [])],
        [str(value) for value in fragment.get("kinds", [])],
        [str(value) for value in fragment.get("producers", [])],
        [str(value) for value in fragment.get("confidences", [])],
    )
    affected: list[dict[str, object]] = []
    edges: list[dict[str, object]] = []
    for raw in fragment.get("rows", []):
        affected_row, edge = _expanded_row(raw, dictionary)
        if affected_row is not None:
            affected.append(affected_row)
        if edge is not None:
            edges.append(edge)
    roots = [_lookup(dictionary.projects, int(index)) for index in fragment.get("roots", [])]
    return {
        "roots": [value for value in roots if value], "affected": affected, "edges": edges,
        "reported_affected": int(fragment.get("reported_affected") or len(affected)),
        "total_affected": int(fragment.get("total_affected") or len(affected)), "complete": bool(fragment.get("complete")),
    }
