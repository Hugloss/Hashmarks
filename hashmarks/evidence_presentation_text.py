"""Read-only text encoding of an already selected evidence projection."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


def _encode(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _relationship_delta_lines(value: Mapping[str, Any]) -> list[str]:
    comparable = value["comparable"] is True
    label = "qualified producer claim" if comparable else "delivered producer claim"
    lines = [
        f"Subject: {_encode(value['scope'].get('subject'))}",
        f"Producer: {_encode(value['producer'])}",
        "Comparison: qualified producer claim sets"
        if comparable
        else "Comparison: delivered subsets only (not comparable)",
        "Repository absence is not inferred.",
    ]
    if value["incomparability_reasons"]:
        lines.append("Reasons: " + _encode(value["incomparability_reasons"]))
    changes = value["facts"] if comparable else value["observed_claim_set_changes"]
    for key, marker in (("added", "+"), ("removed", "-")):
        for claim in changes[key]:
            description = {
                "identity": claim["identity"],
                "kind": claim["kind"],
                "source": claim["source"]["key"],
                "target": claim["target"]["key"],
            }
            lines.append(f"{marker} {label}: {_encode(description)}")
    for key in (
        "collection",
        "source_bindings",
        "capability",
        "configuration",
        "capture",
    ):
        axis = value[key]
        if axis["changed"]:
            lines.append(
                f"~ {key}: before={_encode(axis['before'])} after={_encode(axis['after'])}"
            )
    for key in ("locators", "resolution_changes", "claim_evidence_changes"):
        if value[key]:
            lines.append(f"~ {key}: {_encode(value[key])}")
    return lines


def _task_delta_lines(value: Mapping[str, Any]) -> list[str]:
    lines = [
        "Comparison: bounded task evidence observations; claim sets are not compared",
        f"Observation changed: {_encode(value['changed'])}",
        "Repository absence is not inferred.",
    ]
    for endpoint in ("before", "after"):
        observation = value[endpoint]
        if observation is None:
            lines.append(f"{endpoint}: unavailable in task projection (unknown)")
            continue
        summary = {key: item for key, item in observation.items() if key != "evidence"}
        lines.append(f"{endpoint}: {_encode(summary)}")
        lines.append(
            f"{endpoint} qualifications: {_encode(observation.get('evidence', {}))}"
        )
    return lines


def _semantic_summary(result: Mapping[str, Any]) -> list[str]:
    lines = _endpoint_comparison_lines(result)
    for group in result["groups"]:
        for row in group["findings"]:
            value = row["details"]
            if row["kind"] == "semantic_relationship_delta":
                lines.extend(_relationship_delta_lines(value))
            elif row["kind"] == "task_semantic_evidence_delta":
                lines.extend(_task_delta_lines(value))
            elif row["kind"] == "scip_semantic_discovery":
                lines.append(f"Semantic subject: {_encode(value['subject'])}")
                for key in (
                    "observation_state",
                    "observed_relationship_count",
                    "observed_relationship_count_scope",
                    "associated_observed_relationship_count",
                    "associated_observed_relationship_count_scope",
                    "repository_freshness",
                    "completeness",
                    "source_equivalence",
                    "negative_evidence_admissible",
                    "detail_surface",
                    "detail_arguments",
                ):
                    if key in value:
                        lines.append(f"{key}: {_encode(value[key])}")
    return lines


def _endpoint_comparison_lines(result: Mapping[str, Any]) -> list[str]:
    for group in result["groups"]:
        for row in group["findings"]:
            if row["kind"] != "semantic_relationships_comparable":
                continue
            context = row["source_context"]
            return [
                f"Subject: {_encode(context['semantic_subject'])}",
                "Endpoint comparison: comparable"
                if row["details"] is True
                else "Endpoint comparison: not comparable",
                "Reasons: " + _encode(context.get("incomparability_reasons", [])),
                "Repository absence is not inferred.",
            ]
    return []


def evidence_projection_text(result: Mapping[str, Any]) -> str:
    """Lead with semantic changes, then encode every selected record exactly."""
    groups = result["groups"]
    lines = _semantic_summary(result)
    lines.append(
        "Metadata: "
        + _encode(
            {
                key: value
                for key, value in result.items()
                if key not in {"groups", "text"}
            }
        )
    )
    for group in groups:
        lines.append(
            f"{group['family']}: {group['count_observed_in_packet']} observed ({group['omitted_from_presentation']} omitted from presentation)"
        )
        lines.extend("  " + _encode(item) for item in group["findings"])
    if not groups:
        lines.append(
            "No displayed findings in this projection"
            if result["supported"]
            else "Unsupported evidence schema"
        )
    lines.append("Unprojected sections: " + _encode(result["unprojected_sections"]))
    return "\n".join(lines)
