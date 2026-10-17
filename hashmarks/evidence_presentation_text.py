"""Read-only text encoding of an already selected evidence projection."""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
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
    lines = _endpoint_comparison_lines(result) + _dependency_lines(result)
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


def _dependency_lines(result: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    for group in result["groups"]:
        for row in group["findings"]:
            if row["kind"] == "change_axes":
                context = row["source_context"]
                lines.extend(
                    [
                        "Dependency comparison: "
                        + str(context.get("comparability", "unknown")),
                        "Causation: " + str(context.get("causation", "not-inferred")),
                        "~ change axes: " + _encode(row["details"]),
                    ]
                )
            elif row["kind"] == "component_selection_transitions":
                lines.append(
                    "Displayed producer selection transition: "
                    + _encode(row["details"])
                )
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


def _initial_endpoint_binding_refs(
    endpoint: dict[str, Any], pointer: str
) -> dict[str, str]:
    """Factor only byte-equivalent binding values; references name native facts."""
    binding = endpoint.get("source_binding")
    resolution = endpoint.get("resolution")
    refs: dict[str, str] = {}
    if not isinstance(binding, Mapping) or not isinstance(resolution, dict):
        return refs
    owners = [(pointer + "/resolution", resolution)]
    owners.extend(
        (pointer + f"/resolution/candidates/{index}", candidate)
        for index, candidate in enumerate(resolution.get("candidates", []))
        if isinstance(candidate, dict)
    )
    for location, owner in owners:
        if "source_binding" in owner and _encode(owner["source_binding"]) == _encode(
            binding
        ):
            owner.pop("source_binding")
            refs[location + "/source_binding"] = pointer + "/source_binding"
    return refs


def initial_semantic_relationship_details(
    value: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    """A lossless view: only JSON-identical duplicates become native value refs."""
    details = deepcopy(dict(value))
    refs: dict[str, str] = {}
    _initial_evidence_value_refs(value, details, refs)
    bindings = {
        _encode(endpoint["source_binding"]): f"/claims/{index}/{side}/source_binding"
        for index, claim in enumerate(value.get("claims", []))
        if isinstance(claim, Mapping)
        for side in ("source", "target")
        if isinstance(endpoint := claim.get(side), Mapping)
        and isinstance(endpoint.get("source_binding"), Mapping)
    }
    _initial_qualification_binding_refs(details, bindings, refs)
    for index, claim in enumerate(details.get("claims", [])):
        if not isinstance(claim, dict):
            continue
        for side in ("source", "target"):
            endpoint = claim.get(side)
            if isinstance(endpoint, dict):
                refs.update(
                    _initial_endpoint_binding_refs(endpoint, f"/claims/{index}/{side}")
                )
    return details, refs


def _initial_evidence_value_refs(
    value: Mapping[str, Any], details: dict[str, Any], refs: dict[str, str]
) -> None:
    evidence = details.get("evidence")
    if isinstance(evidence, dict):
        if all(
            key in value and _encode(item) == _encode(value[key])
            for key, item in evidence.items()
        ):
            details.pop("evidence")
            refs["/evidence"] = "/evidence"
        else:
            for key in list(evidence):
                if key in value and _encode(evidence[key]) == _encode(value[key]):
                    evidence.pop(key)
                    escaped = key.replace("~", "~0").replace("/", "~1")
                    refs["/evidence/" + escaped] = "/" + escaped


def _initial_qualification_binding_refs(
    details: dict[str, Any], bindings: dict[str, str], refs: dict[str, str]
) -> None:
    for index, qualification in enumerate(details.get("qualifications", [])):
        if not isinstance(qualification, dict):
            continue
        for ordinal, binding in enumerate(qualification.get("source_bindings", [])):
            canonical = bindings.get(_encode(binding))
            if canonical is not None:
                qualification["source_bindings"][ordinal] = {"value_ref": canonical}
                refs[f"/qualifications/{index}/source_bindings/{ordinal}"] = canonical


def initial_semantic_relationship_text(packet: Mapping[str, object]) -> list[str]:
    """Retain the complete supplied-claim record beside its qualified subject."""
    relationships = packet.get("semantic_relationships")
    if not isinstance(relationships, Mapping):
        return []
    details, refs = initial_semantic_relationship_details(relationships)
    return [
        f"Semantic subject: {_encode(relationships.get('subject'))}",
        f"Producer relationships: {_encode({'record': details, 'value_refs': refs, 'value_ref_base': '/semantic_relationships'})} (@ /semantic_relationships; value refs use decoded native data).",
    ]


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
