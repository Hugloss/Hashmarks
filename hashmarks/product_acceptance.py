from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from .portable_scalar import require_portable_nonnegative_integer
from .semantic_equivalence import verify_cold_warm_semantic_equivalence
from .verification_selection import validate_verification_selection_envelope

_SCALE_CLASSES = (
    ("tiny", 1_000, 10_000_000),
    ("small", 10_000, 100_000_000),
    ("medium", 100_000, 1_000_000_000),
    ("large", None, None),
)


def _scale_class(files: int, source_bytes: int) -> str:
    for name, max_files, max_bytes in _SCALE_CLASSES[:-1]:
        if files <= int(max_files) and source_bytes <= int(max_bytes):
            return name
    return "large"


def scale_class_contract(*, files: int, source_bytes: int) -> dict[str, object]:
    """Classify repository scale using explicit file-count and source-byte bounds."""
    files = require_portable_nonnegative_integer(files, field="files")
    source_bytes = require_portable_nonnegative_integer(
        source_bytes, field="source_bytes"
    )
    return {
        "schema": "hashmarks.repository-scale-class.v1",
        "class": _scale_class(files, source_bytes),
        "observed": {"files": files, "source_bytes": source_bytes},
        "classes": [
            {"name": name, "max_files": max_files, "max_source_bytes": max_bytes}
            for name, max_files, max_bytes in _SCALE_CLASSES
        ],
        "boundary": "repository-intelligence-only",
    }


def _identity_check(packet: Mapping[str, object]) -> bool:
    identity = packet.get("identity")
    return (
        isinstance(identity, Mapping)
        and bool(identity.get("repository_identity"))
        and bool(identity.get("decision_generation"))
    )


def _ownership_check(action: Mapping[str, object]) -> bool:
    authority = action.get("ownership_authority")
    if not isinstance(authority, Mapping):
        return False
    return (
        authority.get("status") == "resolved"
        or authority.get("resolved_owner") is None
    )


def _verification_check(packet: Mapping[str, object]) -> bool:
    membership = packet.get("verification_membership")
    return isinstance(membership, Mapping) and bool(
        membership.get("membership_identity")
    )


def _envelope_check(packet: Mapping[str, object]) -> bool:
    envelope = packet.get("verification_selection_envelope")
    if not isinstance(envelope, Mapping):
        return False
    validation = validate_verification_selection_envelope(envelope)
    return bool(validation.get("valid"))


def _downstream_check(packet: Mapping[str, object]) -> bool:
    downstream = packet.get("downstream_verification_contract")
    return (
        isinstance(downstream, Mapping)
        and downstream.get("authority") == "repository-intelligence-only"
        and downstream.get("execution_layout") == "external"
        and isinstance(downstream.get("producer_implementation_identity"), str)
        and isinstance(downstream.get("contract_identity"), str)
    )


def _symbolic_nomination_check(packet: Mapping[str, object]) -> bool:
    nomination = packet.get("symbolic_nomination")
    return (
        isinstance(nomination, Mapping)
        and nomination.get("authority") == "nomination-only"
        and nomination.get("ranking_effect") == "none"
        and nomination.get("execution_effect") == "none"
    )


def _packet_checks(
    packet: Mapping[str, object],
    action: Mapping[str, object],
) -> dict[str, bool]:
    return {
        "identity_present": _identity_check(packet),
        "ownership_fail_closed": _ownership_check(action),
        "verification_membership_present": _verification_check(packet),
        "selection_envelope_valid": _envelope_check(packet),
        "downstream_boundary_external": _downstream_check(packet),
        "symbolic_nomination_non_authoritative": _symbolic_nomination_check(packet),
    }


def _stable_query_checks(
    first: Mapping[str, object],
    second: Mapping[str, object],
) -> bool:
    keys = ("identity", "verification_membership")
    return all(first.get(key) == second.get(key) for key in keys)


def executable_acceptance_suite(
    workspace: str | Path,
    *,
    task: str,
    limit: int = 20,
) -> dict[str, object]:
    """Run the bounded Hashmarks product acceptance contract for one task."""
    if limit < 1:
        raise ValueError("limit must be >= 1")
    if not task.strip():
        raise ValueError("task must be nonblank")

    from .codemap import CodeMap

    root = Path(workspace)
    with CodeMap(root) as codemap:
        sync = codemap.sync()
        action = codemap.task_action_map(task, limit=limit)
        first = codemap.task_decision_packet(task, limit=limit)
        second = codemap.task_decision_packet(task, limit=limit)

    checks = _packet_checks(first, action)
    checks["deterministic_repeated_query"] = _stable_query_checks(first, second)
    semantic = verify_cold_warm_semantic_equivalence(
        root, query="task_decision_packet", task=task, limit=limit
    )
    checks["cold_warm_semantic_equivalence"] = bool(semantic["equivalent"])
    scale = scale_class_contract(
        files=int(sync.discovered),
        source_bytes=int(sync.economics.get("source_bytes") or 0),
    )
    return {
        "schema": "hashmarks.executable-acceptance-suite.v1",
        "task": task,
        "checks": checks,
        "passed": all(checks.values()),
        "scale": scale,
        "semantic_equivalence": semantic,
        "boundary": "repository-intelligence-only",
    }


def observability_capabilities() -> dict[str, object]:
    """Advertise exact experiment/QA surfaces without claiming unavailable metrics."""
    values = {
        "stable_verification_membership": True,
        "provenance_bound_selection_envelope": True,
        "ownership_decision_trace": True,
        "fail_closed_ambiguity": True,
        "verification_evidence_levels": True,
        "cold_warm_semantic_equivalence": True,
        "cache_invalidation_adversaries": True,
        "shared_python_ast_audit": True,
        "qualified_import_identity": True,
        "downstream_consumption_contract": True,
        "batch_layout_independence": True,
        "deterministic_repeated_query": True,
        "repository_economics_receipt": True,
        "ownership_graph_economics_receipt": True,
        "related_query_reuse_receipt": True,
        "bounded_top_n_profile": True,
        "symbolic_identity_nomination": True,
        "repository_scale_class": True,
        "executable_acceptance_suite": True,
        "producer_implementation_identity": True,
        "same_version_implementation_drift_detection": True,
        "qualification_classification_identity": True,
        "qualification_coverage_validation": True,
        "qualification_classification_economics": True,
        "native_qualification_handoff": True,
        "consumer_conformance_kit": True,
        "qualified_cross_repository_identity": True,
        "residual_repository_economics": True,
        "graph_nodes_traversed_exact": False,
        "sort_operations_exact": False,
        "set_constructions_exact": False,
        "string_normalizations_exact": False,
    }
    return {
        "schema": "hashmarks.observability-capabilities.v1",
        "values": values,
        "boundary": "repository-intelligence-only",
    }
