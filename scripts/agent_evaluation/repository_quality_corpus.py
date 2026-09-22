from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

CORPUS_SCHEMA = "hashmarks.repository-quality-corpus.v1"
ALLOWED_LAYERS = {"L1-synthetic", "L2-retained-real-world", "L3-fresh-dogfood"}
ALLOWED_STATES = {"qualification", "shadow", "canary", "historical", "superseded"}


def _identity(payload: object) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    if manifest.get("schema") != CORPUS_SCHEMA:
        raise ValueError("unsupported repository quality corpus schema")
    for field in ("corpus_id", "repository_identity", "reviewer_identity"):
        if not str(manifest.get(field) or "").strip():
            raise ValueError(f"{field} must be non-empty")
    cases = manifest.get("cases")
    if not isinstance(cases, Sequence) or isinstance(cases, (str, bytes)) or not cases:
        raise ValueError("corpus cases must be a non-empty sequence")
    ids: set[str] = set()
    for case in cases:
        if not isinstance(case, Mapping):
            raise ValueError("corpus case must be an object")
        case_id = str(case.get("case_id") or "")
        if not case_id or case_id in ids:
            raise ValueError("corpus case_id must be non-empty and unique")
        ids.add(case_id)
        if case.get("layer") not in ALLOWED_LAYERS:
            raise ValueError(f"unsupported corpus layer for {case_id}")
        if case.get("state") not in ALLOWED_STATES:
            raise ValueError(f"unsupported corpus state for {case_id}")
        for field in ("task", "source_identity", "ground_truth_basis"):
            if not str(case.get(field) or "").strip():
                raise ValueError(f"{case_id} {field} must be non-empty")
        if (
            case["layer"] != "L1-synthetic"
            and not str(case.get("provenance_reference") or "").strip()
        ):
            raise ValueError(
                f"{case_id} real-world evidence requires provenance_reference"
            )


def corpus_manifest_identity(manifest: Mapping[str, Any]) -> str:
    validate_manifest(manifest)
    return _identity(manifest)


def qualification_membership_identity(manifest: Mapping[str, Any]) -> str:
    validate_manifest(manifest)
    members = sorted(
        str(case["case_id"])
        + "|"
        + str(case["source_identity"])
        + "|"
        + str(case["ground_truth_basis"])
        for case in manifest["cases"]
        if case["state"] == "qualification"
    )
    return _identity({"schema": CORPUS_SCHEMA, "qualification_members": members})


def promotion_transition(
    case: Mapping[str, Any],
    *,
    target_state: str,
    reviewer_identity: str,
    evidence_identity: str,
) -> dict[str, Any]:
    if target_state not in ALLOWED_STATES:
        raise ValueError("unsupported promotion target state")
    source_state = str(case.get("state") or "")
    if source_state not in ALLOWED_STATES:
        raise ValueError("unsupported source state")
    if target_state == "qualification" and source_state not in {"shadow", "canary"}:
        raise ValueError("qualification promotion requires shadow or canary source")
    if not reviewer_identity or not evidence_identity:
        raise ValueError("promotion requires reviewer and evidence identity")
    return {
        "case_id": case["case_id"],
        "from": source_state,
        "to": target_state,
        "reviewer_identity": reviewer_identity,
        "evidence_identity": evidence_identity,
        "transition_identity": _identity(
            {
                "case_id": case["case_id"],
                "from": source_state,
                "to": target_state,
                "reviewer_identity": reviewer_identity,
                "evidence_identity": evidence_identity,
            }
        ),
    }



def corpus_layer_health(manifest: Mapping[str, Any]) -> dict[str, Any]:
    validate_manifest(manifest)
    counts = {layer: 0 for layer in sorted(ALLOWED_LAYERS)}
    qualification = {layer: 0 for layer in sorted(ALLOWED_LAYERS)}
    for case in manifest["cases"]:
        layer = str(case["layer"])
        counts[layer] += 1
        if case["state"] == "qualification":
            qualification[layer] += 1
    return {
        "cases": len(manifest["cases"]),
        "layers": counts,
        "qualification_layers": qualification,
        "has_retained_real_world": counts["L2-retained-real-world"] > 0,
        "has_fresh_dogfood": counts["L3-fresh-dogfood"] > 0,
        "fresh_dogfood_qualified": qualification["L3-fresh-dogfood"] > 0,
    }
