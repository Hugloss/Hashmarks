"""Conserved per-file diagnostic deltas and explicit repository-edge annotations."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from hashmarks.operation_contract import operation_schema
from hashmarks.paths import normalize_relative_path

from .diagnostic_provenance import _revision_scope, member_collection_states
from .evidence_correlation import EvidenceCorrelationMixin
from .evidence_verification import VerificationMixin
from .repository_evidence_binding_delta import RepositoryEvidenceBindingDeltaMixin


class _RetainedRelationshipEvidence(
    EvidenceCorrelationMixin, RepositoryEvidenceBindingDeltaMixin
):
    """Reuse native binding integrity validation without observing repository state."""

    _packet_digest = staticmethod(VerificationMixin._packet_digest)


def _canonical_path(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return normalize_relative_path(value, allow_root=False)
    except ValueError:
        return None


def _path_index(rows: Mapping[str, Mapping[str, object]]) -> dict[str | None, set[str]]:
    result: dict[str | None, set[str]] = defaultdict(set)
    for identity, row in rows.items():
        result[_canonical_path(row.get("path"))].add(identity)
    return result


def _relationship_packet(value: Mapping[str, object]) -> Mapping[str, Any]:
    _RetainedRelationshipEvidence._validate_previous_correlation_size(value)
    if value.get("schema") != operation_schema("correlate_evidence"):
        raise ValueError("relationship_evidence must be a canonical correlation packet")
    expected = "sha256:" + VerificationMixin._packet_digest(
        operation_schema("correlate_evidence"),
        {
            key: item
            for key, item in value.items()
            if key not in ("correlation_identity", "delta_from_previous")
        },
    )
    if value.get("correlation_identity") != expected:
        raise ValueError("relationship_evidence correlation identity mismatch")
    packet = value.get("repository_evidence")
    if not isinstance(packet, Mapping):
        raise ValueError("relationship_evidence repository evidence is missing")
    validator = _RetainedRelationshipEvidence()
    validator._validate_binding_delta_input(packet, name="relationship_evidence")
    validator._validate_correlation_projections(value, label="relationship_evidence")
    return packet


def _qualified_targets(value: Mapping[str, Any]) -> dict[str, dict[str, object]]:
    candidates: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    for bundle_index, bundle in enumerate(value["bundles"]):
        for anchor_index, anchor in enumerate(bundle["anchors"]):
            resolution, claims = anchor["resolution"], anchor["claims"]
            path = resolution.get("repository_path")
            if (
                resolution.get("state") != "resolved-unique"
                or resolution.get("candidate_completeness") != "complete"
                or not isinstance(path, str)
            ):
                continue
            labels: set[str] = set()
            module, symbol = claims.get("module"), claims.get("symbol")
            if isinstance(module, str):
                labels.add(module + "." + symbol if isinstance(symbol, str) else module)
            resolved_symbol = resolution.get("symbol")
            if isinstance(resolved_symbol, Mapping) and isinstance(
                resolved_symbol.get("qualname"), str
            ):
                labels.add(path + "::" + resolved_symbol["qualname"])
            for label in labels:
                candidates[label][path] = {
                    "path": path,
                    "source_ref": f"/relationship_evidence/bundles/{bundle_index}/anchors/{anchor_index}",
                    "resolution": deepcopy(resolution),
                }
    return {
        label: next(iter(paths.values()))
        for label, paths in candidates.items()
        if len(paths) == 1
    }


def _relationship_context_reason(
    packet: Mapping[str, Any], after: Mapping[str, object]
) -> str | None:
    repo = packet.get("repository")
    if not isinstance(repo, Mapping):
        return "repository-binding-missing"
    if repo.get("repository_identity") != after.get("repository_identity"):
        return "repository-binding-mismatch"
    if repo.get("codemap_generation") != after.get("codemap_generation"):
        return "repository-generation-mismatch"
    return (
        None if repo.get("freshness") == "current" else "repository-freshness-unproven"
    )


def diagnostic_relationship_annotations(
    value: Mapping[str, object] | None,
    after: Mapping[str, object],
    changed_paths: set[str],
) -> tuple[dict[str, list[dict[str, object]]], str]:
    if value is None:
        return {}, "relationship-evidence-not-supplied"
    packet = _relationship_packet(value)
    reason = _relationship_context_reason(packet, after)
    if reason:
        return {}, reason
    annotations: dict[str, list[dict[str, object]]] = defaultdict(list)
    targets = _qualified_targets(value)
    for index, binding in enumerate(packet["bindings"]):
        relationships = binding.get("relationships")
        if (
            not isinstance(relationships, Mapping)
            or relationships.get("state") != "observed"
        ):
            continue
        for edge_index, edge in enumerate(relationships.get("relationships", [])):
            _annotate_edge(
                annotations,
                edge,
                changed_paths,
                targets,
                {
                    "source_ref": f"/relationship_evidence/repository_evidence/bindings/{index}/relationships/relationships/{edge_index}",
                    "completeness": relationships.get("completeness"),
                    "bounds": deepcopy(relationships.get("bounds")),
                },
            )
    return dict(annotations), "no-qualified-explicit-edge-observed"


def _annotate_edge(
    annotations: dict[str, list[dict[str, object]]],
    edge: object,
    changed_paths: set[str],
    targets: dict[str, dict[str, object]],
    context: dict[str, object],
) -> None:
    if not isinstance(edge, Mapping):
        raise ValueError("relationship_evidence contains malformed edges")
    if edge.get("confidence") == "static-name":
        return
    source = _canonical_path(edge.get("path"))
    target_name = edge.get("target")
    resolved = targets.get(target_name) if isinstance(target_name, str) else None
    target = resolved["path"] if resolved else None
    if source is None or not isinstance(target, str) or source == target:
        return
    if source in changed_paths:
        annotations.setdefault(target, []).append(
            {
                **context,
                "edge": deepcopy(dict(edge)),
                "changed_path": source,
                "target_resolution": resolved,
            }
        )
    if target in changed_paths:
        annotations.setdefault(source, []).append(
            {
                **context,
                "edge": deepcopy(dict(edge)),
                "changed_path": target,
                "target_resolution": resolved,
            }
        )


def _revision_change(
    before: Mapping[str, object], after: Mapping[str, object], path: str | None
) -> dict[str, object]:
    prior = before.get("source_revisions")
    later = after.get("source_revisions")
    old = prior.get(path) if isinstance(prior, Mapping) else None
    new = later.get(path) if isinstance(later, Mapping) else None
    return {
        "before": old,
        "after": new,
        "state": "unknown"
        if old is None or new is None
        else "unchanged"
        if old == new
        else "changed",
        "authority": "producer-claimed",
    }


def _path_provenance(packet: Mapping[str, object], path: str | None) -> object:
    claims = packet.get("source_provenance")
    return deepcopy(claims.get(path)) if isinstance(claims, Mapping) else None


def _path_delta(
    path: str | None,
    old: set[str],
    new: set[str],
    endpoints: tuple[Mapping[str, object], Mapping[str, object]],
    collections: tuple[dict[str, str], dict[str, str]],
) -> dict[str, object]:
    before, after = endpoints
    return {
        "path": path,
        "before_identities": sorted(old),
        "after_identities": sorted(new),
        "added_identities": sorted(new - old),
        "removed_identities": sorted(old - new),
        "unchanged_identities": sorted(old & new),
        "collection_before": collections[0].get(path or "", "unknown"),
        "collection_after": collections[1].get(path or "", "unknown"),
        "scope_before": path in collections[0],
        "scope_after": path in collections[1],
        "source_revisions": _revision_change(before, after, path),
        "source_provenance": {
            "before": _path_provenance(before, path),
            "after": _path_provenance(after, path),
            "authority": "producer-claimed",
        },
        "claim_authority": "producer-claimed",
        "causation": "not-inferred",
    }


def diagnostic_path_deltas(
    before: Mapping[str, object],
    after: Mapping[str, object],
    indexed: tuple[
        Mapping[str, Mapping[str, object]], Mapping[str, Mapping[str, object]]
    ],
    *,
    changed_paths: Sequence[str],
    change_set_complete: bool,
    relationship_evidence: Mapping[str, object] | None,
) -> list[dict[str, object]]:
    if type(change_set_complete) is not bool:
        raise ValueError("change_set_complete must be a boolean")
    changed = _revision_scope(changed_paths)
    before_by_path, after_by_path = _path_index(indexed[0]), _path_index(indexed[1])
    paths = set(before_by_path) | set(after_by_path) | changed
    paths.update(_revision_scope(before.get("scope_paths", ())))
    paths.update(_revision_scope(after.get("scope_paths", ())))
    relationships, reason = diagnostic_relationship_annotations(
        relationship_evidence, after, changed
    )
    rows = []
    collections = (member_collection_states(before), member_collection_states(after))
    for path in sorted(paths, key=lambda item: (item is None, item or "")):
        row = _path_delta(
            path,
            before_by_path.get(path, set()),
            after_by_path.get(path, set()),
            (before, after),
            collections,
        )
        row["edit_relation"] = (
            "reported-changed"
            if path in changed
            else "caller-claimed-unchanged"
            if change_set_complete and path is not None
            else "unknown"
        )
        row["relationship"] = {
            "state": "observed-related" if relationships.get(path or "") else "unknown",
            "reason": "explicit-indexed-edge"
            if relationships.get(path or "")
            else reason,
            "evidence": relationships.get(path or "", []),
            "authority": "caller-supplied-repository-evidence",
        }
        rows.append(row)
    return rows
