"""Presentation of supplied changed-set verification and nomination evidence.

The shared projection builder owns bounds, references and omission accounting.
These views preserve producer claims and reuse canonical nested presenters;
they do not resolve relationships, choose tests or infer execution commands.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .evidence_presentation import _Projection


def _records(packet: Mapping[str, object], key: str) -> list[Mapping[str, object]]:
    value = packet.get(key)
    if not isinstance(value, list) or any(
        not isinstance(row, Mapping) for row in value
    ):
        raise ValueError(f"malformed changed-set verification {key}")
    return value


def project_changed_set(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    """Render the producer's classifications and qualified logical targets."""
    p.field(packet, "changed_paths", "source", ref, ctx, shape="values")
    for index, change in enumerate(_records(packet, "changes")):
        change_ref = (*ref, "changes", index)
        change_context = {**ctx, "changed_path": change.get("path")}
        p.record_context(change_ref, change_context)
        p.field(
            change,
            "classification",
            "verification",
            change_ref,
            change_context,
            shape="record",
        )
        p.field(
            change,
            "context",
            "repository_structure",
            change_ref,
            change_context,
            shape="record",
        )
        p.field(change, "relationships", "relationship", change_ref, change_context)
        p.field(
            change,
            "consumer_scope",
            "qualification",
            change_ref,
            change_context,
            shape="record",
        )
        p.field(
            change,
            "support_scope",
            "repository_structure",
            change_ref,
            change_context,
            shape="record",
        )
        p.nested(change, "source", change_ref, change_context)
        p.nested(change, "explanation", change_ref, change_context)
        p.account(change, change_ref, change_context)
    p.record_context((*ref, "changes"), ctx)
    for index, target in enumerate(_records(packet, "targets")):
        target_ref = (*ref, "targets", index)
        p.field(target, "member", "verification", target_ref, ctx, shape="record")
        p.field(
            target, "context", "repository_structure", target_ref, ctx, shape="record"
        )
        p.nested(target, "nomination", target_ref, ctx)
        p.account(target, target_ref, ctx)
    p.record_context((*ref, "targets"), ctx)
    p.field(packet, "membership", "verification", ref, ctx, shape="record")
    p.nested(packet, "collection", ref, ctx)
    p.nested(packet, "correlation", ref, ctx)
    p.add(
        "qualification",
        "negative_evidence_admissible",
        packet["negative_evidence_admissible"],
        (*ref, "negative_evidence_admissible"),
        ctx,
    )


def project_nomination(
    p: _Projection,
    packet: Mapping[str, object],
    ref: tuple[object, ...],
    ctx: Mapping[str, object],
) -> None:
    """Expose the existing nomination facts without executable projection."""
    p.field(packet, "verification_target", "verification", ref, ctx, shape="record")
    p.field(packet, "supporting_source_members", "source", ref, ctx)
    for key in (
        "available",
        "path",
        "runner_evidence",
        "source_evidence",
        "confidence",
        "source_member_revision",
    ):
        if key in packet:
            p.add("verification", key, packet[key], (*ref, key), ctx)
