"""Pure views of producer-owned dependency observations and requalification.

The shared projection builder owns bounds, references and omission accounting.
These handlers retain native claims and qualifiers without reobserving source,
resolving packages or deciding whether an absence or consumer join is admissible.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .evidence_presentation import _Projection


def project_dependency(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    """Preserve the established dependency observation, explanation and delta view."""
    for key, shape in (
        ("change_axes", "record"),
        ("component_selection_transitions", "records"),
    ):
        p.field(
            packet, key, "dependency", ref, ctx, assertion="producer_claim", shape=shape
        )
    p.nested(packet, "observation", ref, ctx)
    for key, family, shape in (
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
    ):
        p.field(packet, key, family, ref, ctx, assertion="producer_claim", shape=shape)
    for subject in (
        "components",
        "selections",
        "inventory",
        "relationships",
        "module_ownership",
    ):
        for change in ("added", "removed", "changed"):
            p.field(
                packet,
                subject + "_" + change,
                "dependency",
                ref,
                ctx,
                assertion="producer_claim",
                shape="values",
            )
    for key in ("semantic_result", "derivation"):
        p.field(
            packet,
            key,
            "dependency",
            ref,
            ctx,
            assertion="producer_claim",
            shape="record",
        )


def _record(packet: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = packet.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"malformed dependency projection {key}")
    return value


def _source_scope(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    scope = _record(packet, "source_scope")
    scope_ref = (*ref, "source_scope")
    scope_context = {
        **ctx,
        **{
            key: scope[key]
            for key in ("freshness", "completeness", "negative_evidence")
            if key in scope
        },
    }
    p.record_context(scope_ref, scope_context)
    p.field(scope, "retained_members", "source", scope_ref, scope_context)
    p.field(scope, "correspondence", "qualification", scope_ref, scope_context)
    observations = scope.get("observations")
    if not isinstance(observations, list) or any(
        not isinstance(row, Mapping) for row in observations
    ):
        raise ValueError("malformed dependency projection source observations")
    for index, observation in enumerate(observations):
        p.project(observation, (*scope_ref, "observations", index), scope_context)
    p.record_context((*scope_ref, "observations"), scope_context)
    p.account(scope, scope_ref, scope_context)


def project_dependency_projection(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    """Keep retained claims and current qualifications distinct in every format."""
    p.field(packet, "request", "dependency", ref, ctx, shape="record")
    p.field(packet, "assessment", "qualification", ref, ctx, shape="record")
    p.field(packet, "packages", "dependency", ref, ctx, assertion="producer_claim")
    _source_scope(p, packet, ref, ctx)
    consumers = _record(packet, "consumer_evidence")
    consumer_ref = (*ref, "consumer_evidence")
    consumer_context = {
        **ctx,
        **{
            key: consumers[key]
            for key in ("state", "reason", "selection_scope", "context_scope")
            if key in consumers
        },
    }
    p.record_context(consumer_ref, consumer_context)
    for key in ("state", "reason", "omitted_node_count"):
        if key in consumers:
            p.add(
                "qualification",
                key,
                consumers[key],
                (*consumer_ref, key),
                consumer_context,
            )
    p.field(
        consumers,
        "node_ids",
        "dependency",
        consumer_ref,
        consumer_context,
        shape="values",
    )
    p.nested(consumers, "observation", consumer_ref, consumer_context)
    p.account(consumers, consumer_ref, consumer_context)
    p.nested(packet, "observation", ref, ctx)
    p.field(
        packet,
        "derivation",
        "dependency",
        ref,
        ctx,
        assertion="producer_claim",
        shape="record",
    )


def project_dependency_consumers(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    """Render canonical source-consumer claims and their bounded scope unchanged."""
    ctx = {
        **ctx,
        **{
            key: packet[key]
            for key in ("capability", "consumer_scope", "observed_consumer_count_scope")
            if key in packet
        },
    }
    p.record_context(ref, ctx)
    p.field(packet, "source_scope", "source", ref, ctx, shape="record")
    p.field(packet, "capability", "qualification", ref, ctx, shape="record")
    p.field(packet, "consumer_scope", "qualification", ref, ctx, shape="record")
    p.field(packet, "consumers", "dependency", ref, ctx, assertion="producer_claim")
    p.field(packet, "downstream_relationships", "relationship", ref, ctx)
    p.field(
        packet,
        "dependency_provenance",
        "dependency",
        ref,
        ctx,
        assertion="producer_claim",
        shape="record",
    )
