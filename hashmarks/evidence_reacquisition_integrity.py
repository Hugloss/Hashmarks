"""Portable evidence binding descriptor checks, not a session or replay engine.

A descriptor digest protects accidental or undisclosed transformation, not
authenticity. Only the native CodeMap binding delta can validate producer
packets and qualify current repository evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from .freshness import FRESHNESS_STATES
from .generation_domain import require_generation
from .operation_contract import operation_schema

SCHEMA = "hashmarks.evidence-binding-reacquisition.v1"
_SHA = re.compile(r"^sha256:[0-9a-f]{64}$")


def descriptor_identity(value: Mapping[str, Any]) -> str:
    """Identity of the transport description, not proof of producer signature."""
    try:
        raw = json.dumps(
            value, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (ValueError, TypeError) as exc:
        raise ValueError("reacquisition descriptor must be portable JSON") from exc
    return "sha256:" + hashlib.sha256(SCHEMA.encode() + b"\0" + raw).hexdigest()


def _qualified_requery(value: object) -> None:
    from .evidence_context import (
        _reacquisition_dependencies,
        _reacquisition_relationships,
        _reacquisition_scopes,
    )

    if not isinstance(value, Mapping) or set(value) != {
        "binding_id", "evidence", "dependency_paths",
        "include_relationships", "relationship_limit_per_path",
    }:
        raise ValueError("malformed reacquisition requery contract")
    binding_id = value["binding_id"]
    if not isinstance(binding_id, str) or not binding_id.strip():
        raise ValueError("reacquisition binding id must not be blank")
    scopes = _reacquisition_scopes(value["evidence"])
    dependencies = _reacquisition_dependencies(
        [{"path": p} for p in value["dependency_paths"]]
    ) if isinstance(value["dependency_paths"], list) else None
    if dependencies != value["dependency_paths"] or scopes != value["evidence"]:
        raise ValueError("reacquisition selectors must be canonical")
    rel = {
        "state": "observed" if value["include_relationships"] is True
        else "not-requested" if value["include_relationships"] is False
        else "invalid",
        "bounds": {"limit_per_path": value["relationship_limit_per_path"]},
    }
    _reacquisition_relationships(rel)


def validate_reacquisition_descriptor(value: Mapping[str, Any]) -> dict[str, Any]:
    """Fail closed on altered scope/provenance and noncanonical selectors."""
    if not isinstance(value, Mapping) or set(value) != {
        "schema", "source_packet_identity", "binding_definition_identity",
        "binding_observation_identity", "repository", "requery", "authority",
        "current_freshness_proven", "execution_effect", "descriptor_identity",
    } or value.get("schema") != SCHEMA:
        raise ValueError("unsupported reacquisition descriptor schema/fields")
    for key in (
        "source_packet_identity", "binding_definition_identity",
        "binding_observation_identity", "descriptor_identity",
    ):
        if not isinstance(value.get(key), str) or not _SHA.fullmatch(value[key]):
            raise ValueError("reacquisition descriptor has invalid identities")
    if (
        value.get("authority") != "consumer-reacquisition-description-only"
        or value.get("current_freshness_proven") is not False
        or value.get("execution_effect") != "none"
    ):
        raise ValueError("reacquisition descriptor must not grant current authority")
    repository = value.get("repository")
    if not isinstance(repository, Mapping):
        raise ValueError("reacquisition repository context is required")
    require_generation(repository.get("codemap_generation"), field="codemap_generation")
    if repository.get("freshness") not in FRESHNESS_STATES:
        raise ValueError("invalid reacquisition source freshness")
    _qualified_requery(value["requery"])
    semantic = {k: v for k, v in value.items() if k != "descriptor_identity"}
    if descriptor_identity(semantic) != value["descriptor_identity"]:
        raise ValueError("reacquisition descriptor identity mismatch")
    return dict(value)


def compare_reacquisition_observation(
    descriptor: Mapping[str, Any], reobserved: Mapping[str, Any]
) -> dict[str, Any]:
    """Compare *supplied claims* only; this is not CodeMap's binding delta.

    The native packet must be separately validated/reobtained through its
    authoritative producer. Stable scope identity is never proof of freshness.
    """
    old = validate_reacquisition_descriptor(descriptor)
    if not isinstance(reobserved, Mapping) or reobserved.get("schema") != operation_schema(
        "repository_evidence", "observation"
    ):
        raise ValueError("reobservation must be a native evidence binding packet")
    if (
        reobserved.get("authority") != "repository-intelligence-only"
        or reobserved.get("execution_effect") != "none"
    ):
        raise ValueError("invalid reobservation authority")
    rows = reobserved.get("bindings")
    if not isinstance(rows, list):
        raise ValueError("reobserved bindings must be a list")
    candidates = [
        row for row in rows
        if isinstance(row, Mapping)
        and row.get("binding_id") == old["requery"]["binding_id"]
    ]
    if len(candidates) != 1:
        raise ValueError("reobservation requires exactly one matching binding")
    candidate = candidates[0]
    repository = reobserved.get("repository")
    if not isinstance(repository, Mapping):
        raise ValueError("missing reobserved repository")
    same_repository = (
        repository.get("repository_identity")
        == old["repository"].get("repository_identity")
    )
    same_definition = (
        candidate.get("binding_definition_identity")
        == old["binding_definition_identity"]
    )
    same_observation = (
        candidate.get("binding_observation_identity")
        == old["binding_observation_identity"]
    )
    return {
        "schema": "hashmarks.evidence-binding-reacquisition-comparison.v1",
        "descriptor_identity": old["descriptor_identity"],
        "repository_correspondence": (
            "matching-claim" if same_repository else "different-or-unknown"
        ),
        "definition_correspondence": (
            "matching-claim" if same_definition else "different-or-unknown"
        ),
        "observation_correspondence": (
            "matching-claim" if same_observation else "different-or-unknown"
        ),
        "reobserved_freshness": repository.get("freshness", "unknown"),
        "authority": "supplied-packet-claim-comparison-only",
        "current_freshness_proven": False,
        "negative_evidence_admissible": False,
        "execution_effect": "none",
    }
