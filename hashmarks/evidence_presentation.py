"""Pure, bounded presentation of producer-owned repository evidence.

Records retain native details and JSON-pointer references. Presentation never
re-observes the repository or decides freshness, absence, ownership or action.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Literal, TypedDict, Unpack, cast, get_args

from hashmarks.evidence_presentation_text import evidence_projection_text
from hashmarks.operation_contract import (
    operation_default_mode,
    operation_schema,
    validate_operation_response,
)

FAMILIES = (
    "source",
    "relationship",
    "dependency",
    "diagnostic",
    "verification",
    "correspondence",
    "qualification",
    "repository_structure",
    "retrieval_evidence",
    "ownership_evidence",
    "evidence_measurement",
)
PresentationFormat = Literal["none", "structured", "compact", "text"]
FORMATS = get_args(PresentationFormat)
_MAX_PRESENTED_ROWS = 48
_CONTEXT_KEYS = frozenset(
    {
        "repository",
        "repository_binding",
        "source",
        "observer",
        "producer",
        "producer_context",
        "provenance",
        "generation",
        "identity_generation",
        "generation_before",
        "generation_after",
        "outcome_before",
        "outcome_after",
        "collection_before",
        "collection_after",
        "repository_before",
        "repository_after",
        "from",
        "to",
        "stale",
        "freshness",
        "scope",
        "observation_scope",
        "availability",
        "state",
        "status",
        "reason",
        "collection",
        "outcome",
        "completeness",
        "truncation",
        "truncated",
        "query_intent",
        "omissions",
        "admissibility_reasons",
        "uniqueness_evidence",
        "observed_exact_match_count",
        "before_repository_binding",
        "after_repository_binding",
        "before_adapter_semantics",
        "after_adapter_semantics",
        "change",
        "semantic_invalidation",
        "previous_index_binding",
        "coverage",
        "source_coverage",
        "negative_evidence",
        "bounds",
        "limits",
        "claims",
        "causation",
        "precision",
        "comparability",
        "comparable",
        "incomparability_reasons",
        "measurement",
        "storage",
        "definition_options",
        "changed_evidence",
        "proof_scope",
        "proof_scope_complete",
        "candidate_search",
        "observed_match_count",
        "exact_match_count",
        "member_count",
        "literal",
        "literal_query",
        "ownership_status",
        "consumer_owner",
        "winner",
    }
)


def validate_presentation(value: object) -> str:
    if not isinstance(value, str) or value not in FORMATS:
        raise ValueError(f"presentation must be one of: {', '.join(FORMATS)}")
    return value


def _pointer(parts: tuple[object, ...]) -> str:
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def _context(packet: Mapping[str, object]) -> dict[str, object]:
    return deepcopy(
        {
            key: value
            for key, value in packet.items()
            if key in _CONTEXT_KEYS or "authority" in key or key.endswith("identity")
        }
    )


def presentation_source_identities(packet: Mapping[str, object]) -> dict[str, object]:
    return deepcopy(
        {
            key: value
            for key, value in packet.items()
            if key.endswith("identity")
            or key
            in {
                "from",
                "to",
                "repository",
                "repository_binding",
                "observer",
                "producer",
                "source",
            }
        }
    )


def _collection_rows(
    value: object, shape: str, ref: tuple[object, ...]
) -> list[tuple[object, object]]:
    if shape == "keyed":
        if not isinstance(value, Mapping):
            raise ValueError(f"malformed evidence mapping at {_pointer(ref)}")
        rows = sorted(value.items())
    else:
        if not isinstance(value, (list, tuple)):
            raise ValueError(f"malformed evidence records at {_pointer(ref)}")
        rows = list(enumerate(value))
    if shape in {"keyed", "records"}:
        for suffix, row in rows:
            if not isinstance(row, Mapping):
                raise ValueError(
                    f"malformed evidence record at {_pointer((*ref, suffix))}"
                )
    return cast("list[tuple[object, object]]", rows)


class _FieldOptions(TypedDict, total=False):
    assertion: str
    kind: str | None
    shape: str


class _Projection:
    def __init__(self, row_limit: int) -> None:
        self.row_limit = row_limit
        self.counts: dict[str, int] = dict.fromkeys(FAMILIES, 0)
        self.grouped: dict[str, list[dict[str, object]]] = {key: [] for key in FAMILIES}
        self.unprojected: list[dict[str, object]] = []
        self.contexts: list[dict[str, object]] = []
        self.used: set[str] = set()

    def add(
        self,
        family: str,
        kind: str,
        value: object,
        ref: tuple[object, ...],
        context: Mapping[str, object],
        *,
        assertion: str = "observed_fact",
    ) -> dict[str, object]:
        self.counts[family] += 1
        self.used.add(_pointer(ref))
        qualification = _context(value) if isinstance(value, Mapping) else {}
        if qualification:
            self.contexts.append(
                {"source_ref": _pointer(ref), "details": qualification}
            )
        if len(self.grouped[family]) >= self.row_limit:
            return {}
        row_context = deepcopy(dict(context))
        row: dict[str, object] = {
            "kind": kind,
            "assertion": assertion,
            "basis": "native-producer-record",
            "details": deepcopy(value),
            "source_refs": [_pointer(ref)],
            "source_context": row_context,
        }
        if isinstance(value, Mapping):
            if qualification:
                row_context["record_qualification"] = deepcopy(qualification)
            for key in (
                "path",
                "member",
                "name",
                "qualname",
                "from",
                "to",
                "reason",
                "state",
                "component_id",
                "node_id",
                "binding_id",
                "evidence_identity",
                "target",
                "source",
                "version",
                "line",
                "diagnostic_id",
                "symbol",
            ):
                if key in value:
                    row[key] = deepcopy(value[key])
        if isinstance(value, bool):
            row["projection_changed"] = value
        self.grouped[family].append(row)
        return row

    def field(
        self,
        packet: Mapping[str, object],
        key: str,
        family: str,
        ref: tuple[object, ...],
        context: Mapping[str, object],
        **options: Unpack[_FieldOptions],
    ) -> None:
        assertion = options.get("assertion", "observed_fact")
        kind = options.get("kind") or key
        shape = options.get("shape", "records")
        if key not in packet:
            return
        value = packet[key]
        field_ref = (*ref, key)
        self.used.add(_pointer(field_ref))
        if value is None:
            if shape == "records":
                raise ValueError(f"malformed evidence records at {_pointer(field_ref)}")
            return
        if shape == "record":
            if not isinstance(value, Mapping):
                raise ValueError(f"malformed evidence record at {_pointer(field_ref)}")
            self.add(
                family, kind or key, value, field_ref, context, assertion=assertion
            )
            return
        for suffix, row in _collection_rows(value, shape, field_ref):
            entry = self.add(
                family, kind, row, (*field_ref, suffix), context, assertion=assertion
            )
            if shape == "keyed":
                entry["key"] = suffix

    def nested(
        self,
        packet: Mapping[str, object],
        key: str,
        ref: tuple[object, ...],
        context: Mapping[str, object],
    ) -> None:
        if key not in packet or packet[key] is None:
            return
        value = packet[key]
        if not isinstance(value, Mapping):
            raise ValueError(f"malformed nested evidence at {_pointer((*ref, key))}")
        if self.project(value, (*ref, key), context):
            self.used.add(_pointer((*ref, key)))

    def account(
        self,
        packet: Mapping[str, object],
        ref: tuple[object, ...],
        context: Mapping[str, object],
    ) -> None:
        for key, value in sorted(packet.items()):
            pointer = _pointer((*ref, key))
            if key == "schema" or key in context or pointer in self.used:
                continue
            entry: dict[str, object] = {
                "source_ref": pointer,
                "reason": "not-projected",
            }
            if isinstance(value, (list, tuple, Mapping)):
                entry["native_item_count"] = len(value)
            self.unprojected.append(entry)

    def project(
        self,
        packet: Mapping[str, object],
        ref: tuple[object, ...] = (),
        inherited: Mapping[str, object] | None = None,
    ) -> bool:
        context = {**(inherited or {}), **_context(packet)}
        schema = packet.get("schema")
        projector = _projectors().get(str(schema))
        self.contexts.append(
            {
                "source_ref": _pointer(ref),
                "source_schema": schema,
                "details": deepcopy(context),
            }
        )
        if projector is None:
            self.unprojected.append(
                {
                    "source_ref": _pointer(ref),
                    "reason": "unsupported-schema",
                    "source_schema": schema,
                }
            )
            return False
        _require_fields(packet, str(schema))
        projector(self, packet, ref, context)
        self.account(packet, ref, context)
        return True


def _fields(
    projection: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    context: Mapping[str, object],
    specs: tuple[tuple[str, str, str], ...],
    *,
    assertion: str = "observed_fact",
) -> None:
    for key, family, shape in specs:
        projection.field(
            packet, key, family, ref, context, assertion=assertion, shape=shape
        )


def _snapshot(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    _snapshot_members(p, packet, ref, ctx)
    _fields(
        p,
        packet,
        ref,
        ctx,
        (
            ("ownership", "ownership_evidence", "record"),
            ("verification", "verification", "record"),
        ),
    )
    affected = packet.get("affected", {})
    if not isinstance(affected, Mapping):
        raise ValueError("malformed affected surfaces")
    p.used.add(_pointer((*ref, "affected")))
    for role in sorted(affected):
        p.field(
            affected,
            role,
            "relationship",
            (*ref, "affected"),
            ctx,
            kind="related_surface:" + role,
        )
    if "freshness" in packet:
        p.add(
            "qualification",
            "freshness_observed",
            packet["freshness"],
            (*ref, "freshness"),
            ctx,
        )


def _snapshot_members(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    paths = packet.get("paths", {})
    if not isinstance(paths, Mapping):
        raise ValueError("malformed snapshot paths")
    p.used.add(_pointer((*ref, "paths")))
    for path, row in sorted(paths.items()):
        if not isinstance(row, Mapping):
            raise ValueError("malformed snapshot member")
        path_ref = (*ref, "paths", path)
        for field, kind in (
            ("revision", "member_revision_observed"),
            ("member_state", "member_state_observed"),
        ):
            if field in row:
                entry = p.add("source", kind, row[field], (*path_ref, field), ctx)
                entry["path"] = path
        p.field(row, "symbols", "source", path_ref, ctx)
        p.field(row, "dependencies", "relationship", path_ref, ctx)
        p.account(row, path_ref, {})


def _delta(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    semantic = packet.get("semantic", {})
    if not isinstance(semantic, Mapping):
        raise ValueError("malformed delta semantic records")
    semantic_ref = (*ref, "semantic")
    p.used.add(_pointer(semantic_ref))
    for key, family, kind in (
        ("symbols_added", "source", "symbol_added"),
        ("symbols_removed", "source", "symbol_removed"),
        ("dependencies_added", "relationship", "dependency_edge_added"),
        ("dependencies_removed", "relationship", "dependency_edge_removed"),
    ):
        p.field(
            semantic,
            key,
            family,
            semantic_ref,
            ctx,
            assertion="observed_change",
            kind=kind,
        )
    p.field(
        semantic,
        "possible_symbol_moves",
        "correspondence",
        semantic_ref,
        ctx,
        assertion="candidate_correspondence",
        kind="possible_symbol_move",
    )
    for key, family in (
        ("ownership_changed", "ownership_evidence"),
        ("impact_changed", "relationship"),
        ("verification_changed", "verification"),
        ("freshness_changed", "qualification"),
        ("project_provenance_changed", "qualification"),
    ):
        if semantic.get(key) is True:
            p.add(
                family,
                key,
                True,
                (*semantic_ref, key),
                ctx,
                assertion="observed_change",
            )
    for key, kind in (
        ("completeness", "completeness_changed"),
        ("observer", "observer_capability_changed"),
    ):
        value = packet.get(key)
        if isinstance(value, Mapping) and value.get("changed") is True:
            p.add(
                "qualification",
                kind,
                value,
                (*ref, key),
                ctx,
                assertion="observed_change",
            )
    _delta_fields(p, packet, ref, ctx)
    p.account(semantic, semantic_ref, {})


def _delta_fields(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    changes = packet.get("changes", [])
    if not isinstance(changes, list):
        raise ValueError("malformed delta changes")
    p.used.add(_pointer((*ref, "changes")))
    for index, row in enumerate(changes):
        if not isinstance(row, Mapping) or not isinstance(row.get("path"), list):
            raise ValueError("malformed delta change path")
        parts = row["path"]
        family, kind = "qualification", "projection_field_changed"
        if len(parts) >= 2 and parts[0] == "paths":
            family = "source"
            kind = (
                "member_revision_changed"
                if len(parts) >= 3 and parts[2] == "revision"
                else "snapshot_member_changed"
            )
        entry = p.add(
            family,
            kind,
            row,
            (*ref, "changes", index),
            ctx,
            assertion="observed_change",
        )
        if family == "source":
            entry["path"] = parts[1]


def _profile(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    evidence = packet.get("evidence")
    if not isinstance(evidence, Mapping):
        raise ValueError("malformed profile evidence")
    evidence_ref = (*ref, "evidence")
    p.used.add(_pointer(evidence_ref))
    if packet.get("profile") == "audit":
        p.nested(evidence, "snapshot", evidence_ref, ctx)
    else:
        context = {**ctx, **_context(evidence)}
        p.contexts.append({"source_ref": _pointer(evidence_ref), "details": context})
        _snapshot(p, evidence, evidence_ref, context)
        p.account(evidence, evidence_ref, context)


def _diagnostic(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    value = packet.get("diagnostics")
    if not isinstance(value, Mapping):
        raise ValueError("malformed diagnostic delta")
    field_ref = (*ref, "diagnostics")
    p.used.add(_pointer(field_ref))
    for key, kind in (
        ("added", "diagnostic_added"),
        ("removed", "diagnostic_missing_after"),
    ):
        p.field(
            value,
            key,
            "diagnostic",
            field_ref,
            ctx,
            assertion="producer_claim",
            kind=kind,
        )
    locality = value.get("path_locality")
    if isinstance(locality, Mapping) and locality.get("rows"):
        p.field(
            value,
            "path_locality",
            "diagnostic",
            field_ref,
            ctx,
            assertion="producer_claim",
            kind="diagnostic_path_locality",
            shape="record",
        )
    p.field(
        value,
        "possible_relocations",
        "correspondence",
        field_ref,
        ctx,
        assertion="candidate_correspondence",
        kind="possible_diagnostic_relocation",
    )
    p.field(
        value,
        "path_deltas",
        "qualification",
        field_ref,
        ctx,
        assertion="producer_claim",
        kind="diagnostic_path_delta",
    )
    for field in (
        "source_revisions",
        "source_provenance",
        "collection_by_path",
        "change_set",
        "scope_paths",
    ):
        p.field(
            packet,
            field,
            "qualification",
            ref,
            ctx,
            shape="record",
            assertion="producer_claim",
            kind=f"diagnostic_{field}",
        )
    p.account(value, field_ref, {})


def _diagnostic_observation_projection(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    p.field(
        packet,
        "diagnostics",
        "diagnostic",
        ref,
        ctx,
        assertion="producer_claim",
        kind="diagnostic_observed",
    )
    for field in ("source_revisions", "source_provenance", "collection_by_path"):
        p.field(
            packet,
            field,
            "qualification",
            ref,
            ctx,
            shape="record",
            assertion="producer_claim",
            kind=f"diagnostic_{field}",
        )


def _diagnostic_revision_projection(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    p.field(
        packet,
        "rows",
        "source",
        ref,
        ctx,
        assertion="producer_claim",
        kind="diagnostic_source_revision_correspondence",
    )
    p.field(
        packet,
        "source_provenance",
        "qualification",
        ref,
        ctx,
        shape="record",
        assertion="producer_claim",
        kind="diagnostic_source_provenance",
    )


def _source(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    _fields(
        p,
        packet,
        ref,
        ctx,
        (
            ("occurrences", "source", "records"),
            ("literal_observations", "qualification", "records"),
            ("line_anchors", "source", "records"),
            ("member", "source", "record"),
            ("member_observations", "source", "records"),
            ("source_shape", "evidence_measurement", "record"),
        ),
    )


def _locality(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    p.field(
        packet,
        "native_semantic_relationships",
        "relationship",
        ref,
        ctx,
        shape="record",
        assertion="producer_claim",
    )
    supplied = packet.get("supplied_relationship_observation")
    if isinstance(supplied, Mapping):
        p.project(supplied, (*ref, "supplied_relationship_observation"), ctx)
    _fields(
        p,
        packet,
        ref,
        ctx,
        (
            ("nodes", "repository_structure", "records"),
            ("edges", "relationship", "records"),
            ("unresolved_calls", "relationship", "records"),
            ("external_or_unindexed_calls", "relationship", "records"),
            ("verification_paths", "verification", "values"),
            ("dimensions", "evidence_measurement", "record"),
        ),
    )


def _direct_relationships(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    p.field(packet, "coverage", "qualification", ref, ctx, shape="record")
    p.field(
        packet,
        "producer_correspondence",
        "correspondence",
        ref,
        ctx,
        shape="record",
        assertion="producer_claim",
    )
    observations = packet.get("observations", [])
    if not isinstance(observations, list):
        return
    for index, observation in enumerate(observations):
        observation_ref = (*ref, "observations", index)
        observation_context = {
            **ctx,
            "relationship_observation": {
                key: deepcopy(value)
                for key, value in observation.items()
                if key not in ("claims", "source_bindings")
            },
        }
        p.contexts.append(
            {"source_ref": _pointer(observation_ref), "details": observation_context}
        )
        for field, family, kind in (
            ("claims", "relationship", "direct_semantic_relationship"),
            ("source_bindings", "source", "relationship_source_binding"),
        ):
            p.field(
                observation,
                field,
                family,
                observation_ref,
                observation_context,
                shape="records",
                assertion="producer_claim",
                kind=kind,
            )
        p.add(
            "qualification",
            "relationship_observation_qualification",
            observation["collection_state"],
            (*observation_ref, "collection_state"),
            observation_context,
            assertion="producer_claim",
        )


def _direct_relationship_delta(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    ctx = {**ctx, "semantic_subject": packet["target"]}
    p.field(
        packet,
        "producer_deltas",
        "relationship",
        ref,
        ctx,
        shape="records",
        assertion="observed_change",
        kind="semantic_relationship_delta",
    )
    p.add(
        "qualification",
        "semantic_relationships_comparable",
        packet["comparable"],
        (*ref, "comparable"),
        ctx,
    )
    p.field(
        packet, "incomparability_reasons", "qualification", ref, ctx, shape="values"
    )
    p.field(packet, "observation_changes", "qualification", ref, ctx, shape="record")
    for endpoint in ("before", "after"):
        value = packet.get(endpoint)
        if isinstance(value, Mapping):
            p.project(value, (*ref, endpoint), ctx)


def _bindings(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    _fields(
        p,
        packet,
        ref,
        ctx,
        (
            ("bindings", "source", "records"),
            ("relationships", "relationship", "records"),
            ("binding_impacts", "source", "records"),
            ("change_set", "source", "record"),
            ("classification", "source", "record"),
        ),
    )


def _dependency(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    _fields(
        p,
        packet,
        ref,
        ctx,
        (
            ("change_axes", "dependency", "record"),
            ("component_selection_transitions", "dependency", "records"),
        ),
        assertion="producer_claim",
    )
    p.nested(packet, "observation", ref, ctx)
    _fields(
        p,
        packet,
        ref,
        ctx,
        (
            ("components", "dependency", "records"),
            ("selections", "dependency", "records"),
            ("inventory", "dependency", "records"),
            ("relationships", "dependency", "records"),
            ("module_ownership", "dependency", "records"),
            ("evidence_sources", "dependency", "records"),
            ("repository_inputs", "source", "records"),
            ("root_evidence", "dependency", "records"),
            ("queries", "dependency", "record"),
            ("explanations", "dependency", "records"),
        ),
        assertion="producer_claim",
    )
    for subject in (
        "components",
        "selections",
        "inventory",
        "relationships",
        "module_ownership",
    ):
        for change in ("added", "removed", "changed"):
            key = subject + "_" + change
            p.field(
                packet,
                key,
                "dependency",
                ref,
                ctx,
                assertion="producer_claim",
                shape="values",
            )
    _fields(
        p,
        packet,
        ref,
        ctx,
        (
            ("semantic_result", "dependency", "record"),
            ("derivation", "dependency", "record"),
        ),
        assertion="producer_claim",
    )


def _correlation(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    bundles = packet.get("bundles", [])
    if not isinstance(bundles, list):
        raise ValueError("malformed correlation bundles")
    p.used.add(_pointer((*ref, "bundles")))
    for index, bundle in enumerate(bundles):
        if not isinstance(bundle, Mapping):
            raise ValueError("malformed correlation bundle")
        bundle_ref = (*ref, "bundles", index)
        bundle_context = {
            **ctx,
            "bundle": deepcopy(
                {key: value for key, value in bundle.items() if key != "anchors"}
            ),
        }
        p.contexts.append(
            {"source_ref": _pointer(bundle_ref), "details": bundle_context}
        )
        p.field(
            bundle,
            "anchors",
            "correspondence",
            bundle_ref,
            bundle_context,
            assertion="producer_claim",
        )
    p.nested(packet, "repository_evidence", ref, ctx)
    p.nested(packet, "delta_from_previous", ref, ctx)
    p.nested(packet, "delta", ref, ctx)
    # Delta's domain-owned comparison is retained as a claim, without causality.
    if "repository_evidence_delta" in packet:
        p.field(packet, "repository_evidence_delta", "source", ref, ctx, shape="record")


def _binding_delta(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    bindings = packet.get("bindings")
    if not isinstance(bindings, Mapping):
        raise ValueError("malformed binding delta")
    binding_ref = (*ref, "bindings")
    p.used.add(_pointer(binding_ref))
    for kind in ("added", "removed", "preserved", "changed"):
        p.field(
            bindings,
            kind,
            "source",
            binding_ref,
            ctx,
            shape="values",
            assertion="observed_change" if kind != "preserved" else "observed_fact",
        )


def _declarations(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    _fields(
        p,
        packet,
        ref,
        ctx,
        (
            ("groups", "correspondence", "records"),
            ("explanations", "correspondence", "records"),
            ("group", "correspondence", "record"),
            ("delta_from_previous", "correspondence", "record"),
            ("semantic_result", "correspondence", "record"),
            ("derivation", "correspondence", "record"),
        ),
        assertion="producer_claim",
    )
    p.nested(packet, "repository_evidence", ref, ctx)


def _context_packet(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    _fields(
        p,
        packet,
        ref,
        ctx,
        (
            ("areas", "repository_structure", "records"),
            ("projects", "repository_structure", "records"),
            ("project_edges", "relationship", "records"),
            ("frequent_dependency_targets", "relationship", "records"),
            ("stats", "evidence_measurement", "record"),
        ),
    )


def _find(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    p.field(packet, "results", "retrieval_evidence", ref, ctx)


def _task_owner_display_qualified(
    ownership: Mapping[str, object],
    owner_path: object,
    freshness: object,
) -> bool:
    """Respect existing producer-owned proof/freshness, without redeciding owner."""
    return (
        ownership.get("status") == "resolved"
        and ownership.get("proof_scope_complete") is True
        and ownership.get("authority") == "repository-ownership-only"
        and isinstance(owner_path, str)
        and bool(owner_path)
        and isinstance(freshness, Mapping)
        and freshness.get("state") == "current"
    )


def _task_ownership(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    """Project owner claims without promoting incomplete or stale evidence."""
    ownership = packet.get("ownership")
    if not isinstance(ownership, Mapping):
        return
    owner = ownership.get("owner")
    owner_path = owner.get("path") if isinstance(owner, Mapping) else None
    freshness = packet.get("freshness")
    freshness_state = (
        freshness.get("state") if isinstance(freshness, Mapping) else "unknown"
    )
    qualified = _task_owner_display_qualified(ownership, owner_path, freshness)
    ownership_context = {
        **ctx,
        "task_ownership": {
            "status": ownership.get("status"),
            "authority": ownership.get("authority"),
            "authority_proof_identity": ownership.get("authority_proof_identity"),
            "proof_scope_complete": ownership.get("proof_scope_complete"),
            "owner_path": owner_path,
            "freshness_state": freshness_state,
            "display_qualification": (
                "producer-claimed-qualified" if qualified else "unqualified"
            ),
        },
    }
    for key, family, kind, assertion in (
        (
            "owner",
            "ownership_evidence",
            "qualified_owner" if qualified else "unqualified_owner",
            "observed_fact" if qualified else "producer_claim",
        ),
        ("candidate", "ownership_evidence", "owner_candidate", "producer_claim"),
        (
            "source_evidence",
            "source",
            "owner_source_evidence" if qualified else "unqualified_owner_source",
            "observed_fact" if qualified else "producer_claim",
        ),
        ("next_read", "ownership_evidence", "discrimination_read", "producer_claim"),
    ):
        if isinstance(ownership.get(key), Mapping):
            p.field(
                ownership,
                key,
                family,
                (*ref, "ownership"),
                ownership_context,
                kind=kind,
                shape="record",
                assertion=assertion,
            )


def _task_verification(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    """Show producer-owned verification choices without executing them."""
    verification = packet.get("verification")
    if isinstance(verification, Mapping):
        verification_context = {
            **ctx,
            "verification_authority": verification.get("authority"),
        }
        for key, kind in (
            ("selected", "selected_verifier"),
            ("plan", "verification_plan"),
        ):
            if isinstance(verification.get(key), Mapping):
                p.field(
                    verification,
                    key,
                    "verification",
                    (*ref, "verification"),
                    verification_context,
                    kind=kind,
                    shape="record",
                    assertion="producer_claim",
                )


def _task(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    retrieval = packet.get("retrieval")
    if retrieval is not None:
        if not isinstance(retrieval, Mapping):
            raise ValueError("malformed task retrieval")
        retrieval_ref = (*ref, "retrieval")
        retrieval_context = {
            **ctx,
            "retrieval": {
                key: deepcopy(value)
                for key, value in retrieval.items()
                if key != "results"
            },
        }
        p.contexts.append(
            {"source_ref": _pointer(retrieval_ref), "details": retrieval_context}
        )
        p.field(
            retrieval, "results", "retrieval_evidence", retrieval_ref, retrieval_context
        )
        p.used.add(_pointer(retrieval_ref))
    # Preserve native ownership and verification records, but surface their
    _task_ownership(p, packet, ref, ctx)
    _task_verification(p, packet, ref, ctx)
    p.field(
        packet,
        "semantic_relationships",
        "relationship",
        ref,
        ctx,
        kind="scip_semantic_discovery",
        shape="record",
        assertion="producer_claim",
    )
    _fields(
        p,
        packet,
        ref,
        ctx,
        (
            ("ownership", "ownership_evidence", "record"),
            ("supplied_observation_accounting", "qualification", "record"),
            ("verification", "verification", "record"),
            ("explicit_target", "ownership_evidence", "record"),
            ("evidence_receipt", "qualification", "record"),
            ("related", "relationship", "record"),
        ),
    )


def _impact(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    p.field(
        packet,
        "semantic_relationships",
        "relationship",
        ref,
        ctx,
        kind="task_semantic_evidence_delta",
        shape="record",
        assertion="producer_claim",
    )
    _fields(
        p,
        packet,
        ref,
        ctx,
        (
            ("changed", "source", "records"),
            ("path_changes", "source", "records"),
            ("invalidated", "source", "values"),
            ("reused", "source", "values"),
            ("replacement", "source", "record"),
            ("replacements", "source", "record"),
            ("project_impact", "relationship", "record"),
        ),
    )
    surfaces = packet.get("surfaces", {})
    if not isinstance(surfaces, Mapping):
        raise ValueError("malformed impact surfaces")
    p.used.add(_pointer((*ref, "surfaces")))
    for key in sorted(surfaces):
        p.field(
            surfaces,
            key,
            "verification" if key == "tests" else "relationship",
            (*ref, "surfaces"),
            ctx,
        )


def _brief(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    p.field(packet, "changed", "source", ref, ctx)
    _snapshot(p, packet, ref, ctx)


def _freshness(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    p.field(packet, "entries", "qualification", ref, ctx)
    p.field(packet, "prior", "qualification", ref, ctx, shape="values")


def _verification(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    p.add("verification", "verification_selection_explanation", dict(packet), ref, ctx)
    p.used.update(_pointer((*ref, key)) for key in packet)


def _cross_repository(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    _fields(
        p,
        packet,
        ref,
        ctx,
        (
            ("dependents", "repository_structure", "values"),
            ("relationships", "relationship", "records"),
            ("affected_ownership_surface", "ownership_evidence", "record"),
            ("verification", "verification", "record"),
            ("unresolved", "qualification", "values"),
        ),
    )


def _economics(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    _fields(
        p,
        packet,
        ref,
        ctx,
        (
            ("profile_economics", "evidence_measurement", "keyed"),
            ("evidence_counts", "evidence_measurement", "record"),
            ("delta_economics", "evidence_measurement", "record"),
        ),
    )


def _findings(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    p.field(packet, "findings", "diagnostic", ref, ctx, assertion="producer_claim")


def _structural_comparison(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    """Keep structural incomparability separate from observed endpoint changes."""
    if packet.get("comparable") is not True:
        p.add(
            "qualification",
            "structural_endpoints_incomparable",
            packet.get("incomparability_reasons"),
            (*ref, "incomparability_reasons"),
            ctx,
        )
        return
    for key, family in (
        ("introduced_symbol_ids", "source"),
        ("removed_symbol_ids", "source"),
        ("verification_paths_added", "verification"),
        ("verification_paths_removed", "verification"),
    ):
        p.field(
            packet,
            key,
            family,
            ref,
            ctx,
            assertion="observed_change",
            shape="values",
        )
    if "dimension_delta" in packet:
        p.add(
            "evidence_measurement",
            "dimension_delta",
            packet["dimension_delta"],
            (*ref, "dimension_delta"),
            ctx,
            assertion="observed_change",
        )
    if "native_relationships_comparable" in packet:
        p.add(
            "qualification",
            "scip_relationship_delta_comparable",
            packet["native_relationships_comparable"],
            (*ref, "native_relationships_comparable"),
            ctx,
        )
        p.field(
            packet,
            "native_relationships_incomparability_reasons",
            "qualification",
            ref,
            ctx,
            kind="scip_relationship_delta_incomparability_reason",
            shape="values",
        )
        for key, kind in (
            ("native_relationships_added", "scip_relationship_claim_added"),
            ("native_relationships_removed", "scip_relationship_claim_removed"),
        ):
            p.field(
                packet,
                key,
                "relationship",
                ref,
                ctx,
                kind=kind,
                assertion="observed_change",
                shape="values",
            )


def _projectors() -> dict[str, Any]:
    # Producer constants are loaded after CodeMap initialization to avoid cycles.
    from hashmarks.codemap.change_intelligence import CHANGE_INTELLIGENCE_SCHEMA
    from hashmarks.codemap.cross_repository_evidence import CROSS_REPOSITORY_SCHEMA
    from hashmarks.codemap.dependency_resolution_contract import SCHEMA_V3
    from hashmarks.codemap.evidence_correlation_replay import (
        _DELTA_SCHEMA as CORRELATION_DELTA_SCHEMA,
    )
    from hashmarks.codemap.evidence_profiles import EVIDENCE_PROFILE_SCHEMA
    from hashmarks.codemap.freshness_map import FRESHNESS_MAP_SCHEMA
    from hashmarks.codemap.intelligence_economics import INTELLIGENCE_ECONOMICS_SCHEMA
    from hashmarks.codemap.repository_delta import (
        DIAGNOSTIC_DELTA_SCHEMA,
        REPOSITORY_DELTA_SCHEMA,
        REPOSITORY_SNAPSHOT_SCHEMA,
    )
    from hashmarks.codemap.repository_evidence_binding_delta import (
        REPOSITORY_BINDING_DELTA_SCHEMA,
    )
    from hashmarks.codemap.verification_explanation import (
        VERIFICATION_EXPLANATION_SCHEMA,
    )

    return {
        REPOSITORY_SNAPSHOT_SCHEMA: _snapshot,
        REPOSITORY_DELTA_SCHEMA: _delta,
        DIAGNOSTIC_DELTA_SCHEMA: _diagnostic,
        "hashmarks.external-diagnostic-observation.v1": _diagnostic_observation_projection,
        "hashmarks.diagnostic-source-revision-evidence.v1": _diagnostic_revision_projection,
        EVIDENCE_PROFILE_SCHEMA: _profile,
        CHANGE_INTELLIGENCE_SCHEMA: _brief,
        FRESHNESS_MAP_SCHEMA: _freshness,
        VERIFICATION_EXPLANATION_SCHEMA: _verification,
        CROSS_REPOSITORY_SCHEMA: _cross_repository,
        INTELLIGENCE_ECONOMICS_SCHEMA: _economics,
        SCHEMA_V3: _dependency,
        CORRELATION_DELTA_SCHEMA: _correlation,
        REPOSITORY_BINDING_DELTA_SCHEMA: _binding_delta,
        operation_schema("structural_locality_delta"): _structural_comparison,
        operation_schema("structural_locality", "relationships"): _direct_relationships,
        operation_schema(
            "evidence_comparison", "relationships"
        ): _direct_relationship_delta,
        operation_schema("repository_context"): _context_packet,
        operation_schema("find"): _find,
        operation_schema("task_evidence"): _task,
        operation_schema("change_impact"): _impact,
        operation_schema("post_change"): _impact,
        operation_schema("structural_locality"): _locality,
        operation_schema("repository_findings"): _findings,
        operation_schema("source_observation", "member"): _source,
        operation_schema("source_observation", "scope"): _source,
        operation_schema("source_observation", "literals"): _source,
        operation_schema("repository_evidence", "observation"): _bindings,
        operation_schema("repository_evidence", "coverage"): _bindings,
        operation_schema("dependency_codemap", "observation"): _dependency,
        operation_schema("dependency_codemap", "explain"): _dependency,
        operation_schema("dependency_codemap", "compare"): _dependency,
        operation_schema("correlate_evidence"): _correlation,
        operation_schema("repository_declarations", "observation"): _declarations,
        operation_schema("repository_declarations", "explain"): _declarations,
    }


def _require_fields(packet: Mapping[str, object], schema: str) -> None:
    required = {
        operation_schema("find"): ("results",),
        operation_schema("repository_context"): ("areas",),
        operation_schema("task_evidence"): ("retrieval", "ownership", "verification"),
        operation_schema("source_observation", "member"): ("member", "occurrences"),
        operation_schema("source_observation", "scope"): (
            "member_observations",
            "occurrences",
        ),
        operation_schema("source_observation", "literals"): (
            "member_observations",
            "literal_observations",
            "occurrences",
        ),
        operation_schema("structural_locality"): ("nodes", "edges"),
        operation_schema("repository_findings"): ("findings",),
        operation_schema("repository_evidence", "observation"): ("bindings",),
        operation_schema("repository_evidence", "coverage"): (
            "classification",
            "change_set",
        ),
        operation_schema("dependency_codemap", "observation"): ("observation",),
        operation_schema("dependency_codemap", "explain"): (
            "semantic_result",
            "derivation",
        ),
        operation_schema("dependency_codemap", "compare"): ("comparability",),
        operation_schema("repository_declarations", "observation"): ("groups",),
        operation_schema("repository_declarations", "explain"): (
            "semantic_result",
            "derivation",
        ),
        operation_schema("correlate_evidence"): ("bundles",),
        operation_schema("change_impact"): ("changed", "surfaces"),
        operation_schema("post_change"): ("path_changes",),
    }.get(schema, ())
    missing = [key for key in required if key not in packet or packet[key] is None]
    if missing:
        raise ValueError(
            f"malformed evidence packet; missing required fields: {missing}"
        )


def presentation_source_identity(packet: Mapping[str, object]) -> object:
    """Return only an aggregate identity explicitly provided by this producer."""
    return deepcopy(
        next(
            (
                packet[key]
                for key in (
                    "delta_identity",
                    "snapshot_identity",
                    "profile_identity",
                    "evidence_identity",
                    "observation_identity",
                    "bindings_identity",
                    "coverage_identity",
                    "correlation_identity",
                    "packet_identity",
                    "evidence_packet_identity",
                    "brief_identity",
                    "explanation_identity",
                    "freshness_map_identity",
                    "receipt_identity",
                    "source_observation_identity",
                    "scope_identity",
                )
                if packet.get(key) is not None
            ),
            None,
        )
    )


def present_repository_evidence(
    packet: Mapping[str, object], *, format: str = "compact"
) -> dict[str, object]:
    """Render an already observed packet; bounds apply only to displayed records."""
    if validate_presentation(format) == "none":
        raise ValueError("presentation must be one of: structured, compact, text")
    limit = _MAX_PRESENTED_ROWS if format == "structured" else 5
    projection = _Projection(limit)
    supported = projection.project(packet)
    groups = [
        {
            "family": family,
            "count_observed_in_packet": projection.counts[family],
            "findings": rows,
            "omitted_from_presentation": projection.counts[family] - len(rows),
        }
        for family, rows in projection.grouped.items()
        if rows
    ]
    identity = presentation_source_identity(packet)
    result: dict[str, object] = {
        "schema": operation_schema("evidence_presentation", "projection"),
        "source_schema": packet.get("schema"),
        "source_evidence_identity": deepcopy(identity),
        "source_identities": presentation_source_identities(packet),
        "source_context": projection.contexts,
        "identity_limitation": None
        if identity is not None
        else "producer-has-no-aggregate-evidence-identity",
        "format": format,
        "supported": supported,
        "coverage": "projection-only" if supported else "unsupported",
        "groups": groups,
        "unprojected_sections": projection.unprojected,
        "authority": "descriptive-only",
        "execution_effect": "none",
    }
    if format == "text":
        result["text"] = evidence_projection_text(result)
    return result


def presentation_response(
    operation: str,
    result: dict[str, object],
    *,
    format: str = "none",
    result_mode: str | None = None,
) -> dict[str, object]:
    """Keep the validated native response alongside an optional projection."""
    validate_presentation(format)
    validate_operation_response(operation, result, mode=result_mode)
    if format == "none":
        return result
    if operation == "repository_intelligence_query":
        from hashmarks.codemap.repository_intelligence_query import (
            repository_query_response,
        )

        producer = result.get("result")
        if not isinstance(producer, Mapping):
            raise ValueError("malformed query producer result")
        return repository_query_response(
            str(result["surface"]), producer, presentation=format
        )
    return {
        "schema": operation_schema("evidence_presentation", "envelope"),
        "operation": operation,
        "result_mode": result_mode or operation_default_mode(operation),
        "result": result,
        "presentation": present_repository_evidence(result, format=format),
        "authority": "descriptive-only",
        "execution_effect": "none",
    }
