"""Bounded read guidance from existing selected-file backend syntax observations.

Only projects already source-bound provider facts. No repository reads, parser,
graph, evidence ranking, runtime inference or agent-side tool execution.
"""

from __future__ import annotations

from collections.abc import Mapping

MAX_BACKEND_NAVIGATION_READS = 8


def _source_read(
    path: str, start: int, end: int, reasons: list[str]
) -> dict[str, object]:
    return {
        "path": path,
        "start_line": start,
        "end_line": end,
        "reasons": reasons,
        "purpose": "inspect-source-syntax",
        "runtime_proof": "not-established",
    }


def _model_read_candidates(
    path: str, group: Mapping[str, object], value: Mapping[str, object]
) -> list[dict[str, object]]:
    scope = group["scope"]
    class_line = scope["class_line"]
    rows = [
        _source_read(
            path,
            max(1, class_line - 24),
            class_line,
            ["inspect-class-base-and-nearby-import-syntax"],
        )
    ]
    for field in value["fields"]:
        reasons: list[str] = []
        if field["annotation"]["state"] != "direct-annotation-syntax":
            reasons.append("annotation-syntax-unresolved")
        if field["default"]["state"] not in {
            "not-supplied",
            "literal-kind-only",
        }:
            reasons.append("initializer-syntax-requires-source-inspection")
        if "direct_environment_initializer" in field:
            reasons.append("environment-initializer-runtime-meaning-unresolved")
        if reasons:
            rows.append(_source_read(path, field["line"], field["end_line"], reasons))
    return rows


def _environment_read_candidates(
    path: str, group: Mapping[str, object], value: Mapping[str, object]
) -> list[dict[str, object]]:
    reasons: list[str] = []
    if value["key"]["state"] != "literal-key-syntax":
        reasons.append("environment-key-expression-unresolved")
    if value["default"]["state"] in {
        "dynamic-or-unsupported",
        "ambiguous-explicit-syntax",
        "over-bound",
    }:
        reasons.append("environment-default-expression-unresolved")
    if value.get("argument_binding") == "unresolved-ambiguous-or-expanded":
        reasons.append("call-argument-binding-unresolved")
    if value["access_role"] in {
        "store-target-syntax",
        "delete-target-syntax",
        "unknown-context",
    }:
        reasons.append("environment-target-effect-unverified")
    if not reasons:
        return []
    evidence = group["declarations"][0]["evidence"][0]
    return [_source_read(path, evidence["start_line"], evidence["end_line"], reasons)]


def backend_evidence_navigation(group: dict[str, object]) -> None:
    """Add source read guidance in-place to one already qualified provider group.

    This is intentionally not a claim about runtime API compatibility or a
    guarantee that further source reads will settle a runtime question.
    """
    kind = group["concept"]["kind"]
    path = group["scope"]["path"]
    value = group["declarations"][0]["value"]
    if kind == "python-model-class-syntax":
        candidates = _model_read_candidates(path, group, value)
    elif kind == "python-env-access-syntax":
        candidates = _environment_read_candidates(path, group, value)
    else:
        return
    retained = candidates[:MAX_BACKEND_NAVIGATION_READS]
    value["evidence_navigation"] = {
        "state": "bounded-source-syntax-read-guidance",
        "authority": "existing-selected-source-declaration",
        "syntactic_evidence": "already-observed",
        "observed_scope": "caller-selected-source-only",
        "source_inspection_recommended": bool(candidates),
        "read_candidates_observed": len(candidates),
        "read_candidates_retained": len(retained),
        "read_candidates_omitted": len(candidates) - len(retained),
        "read_limit": MAX_BACKEND_NAVIGATION_READS,
        "read_requests": retained,
        "runtime_binding": "not-established",
        "runtime_contract": "unknown",
        "cross_artifact_correspondence": "unresolved",
        "negative_evidence_admissible": False,
        "read_may_not_resolve_runtime": True,
    }
