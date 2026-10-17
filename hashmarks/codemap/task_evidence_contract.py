"""Structural readers for current ownership/task evidence at JSON boundaries.

Readers preserve every field and verify structure only. Operation versions remain
registry-owned; repository qualification remains producer-owned.
"""

from __future__ import annotations

from typing import Protocol, cast

from hashmarks.operation_contract import validate_operation_response
from hashmarks.ownership_decision import (
    OwnershipAuthority,
    OwnershipCandidateIdentity,
    OwnershipDecisionTrace,
    OwnershipEvidenceState,
    OwnershipTraceCandidate,
)

from .ownership_relation_types import (
    OwnershipCandidate,
    OwnershipNode,
    OwnershipPathHop,
    OwnershipRelationBounds,
    OwnershipRelationEdge,
    OwnershipRelationGraph,
    OwnershipTraceStructuralEvidence,
    StructuralOwnerResolution,
    StructuralStartObservation,
    StructuralStarts,
)
from .task_evidence_types import (
    ActionDiscrimination,
    DiscriminationRead,
    ExactIdentifierSearch,
    InitialExpansion,
    InitialOmissionCount,
    InitialOmissions,
    InitialProjectionInfo,
    InitialTaskEvidenceProjection,
    ReplacementProvenance,
    SourceReadPending,
    TaskActionBounds,
    TaskActionMap,
    TaskAmbiguity,
    TaskCandidate,
    TaskEvidencePacket,
    TaskEvidenceProvenance,
    TaskFreshness,
    TaskOwnership,
    TaskPathChange,
    TaskPostChangeDelta,
    TaskPostChangeReplacement,
    TaskRelatedEvidence,
    TaskRetrieval,
    TaskRetrievalBounds,
    TaskSourceBudget,
    TaskSourceConfig,
    TaskSourceEvidence,
    TaskSourceEvidenceBase,
    TaskVerification,
    VerificationRelevance,
)


class _RequiredFieldContract(Protocol):
    @property
    def __required_keys__(self) -> frozenset[str]: ...


def _record(
    value: object, path: str, contract: _RequiredFieldContract | None = None
) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise RuntimeError(f"invalid {path}: expected an object with string keys")
    if contract is not None:
        required = contract.__required_keys__
        missing = required.difference(value)
        if missing:
            raise RuntimeError(f"invalid {path}.{min(missing)}: missing required field")
    return cast("dict[str, object]", value)


def _field(value: dict[str, object], key: str, kind: type, path: str) -> object:
    item = value.get(key)
    if (
        key not in value
        or not isinstance(item, kind)
        or (kind is int and type(item) is bool)
    ):
        raise RuntimeError(f"invalid {path}.{key}: expected {kind.__name__}")
    return item


def _fields(
    value: dict[str, object],
    path: str,
    kind: type,
    required: tuple[str, ...],
    optional: tuple[str, ...] = (),
) -> None:
    for key in required:
        _field(value, key, kind, path)
    for key in optional:
        if key in value:
            _field(value, key, kind, path)


def _nullable(value: dict[str, object], key: str, kind: type, path: str) -> None:
    if key not in value:
        raise RuntimeError(f"invalid {path}.{key}: missing nullable field")
    if value[key] is not None:
        _field(value, key, kind, path)


def _strings(value: object, path: str) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise RuntimeError(f"invalid {path}: expected a list of strings")


def _records(
    value: object, path: str, contract: _RequiredFieldContract | None = None
) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise RuntimeError(f"invalid {path}: expected a list of objects")
    return [
        _record(item, f"{path}[{index}]", contract) for index, item in enumerate(value)
    ]


def _hops(value: object, path: str) -> None:
    for hop in _records(value, path, OwnershipPathHop):
        _fields(hop, path, str, ("from", "to", "relation"))


def _locator(value: object, path: str) -> None:
    row = _record(value, path, TaskCandidate)
    _field(row, "path", str, path)
    # Indexed candidate metadata is owned by the index. Validate nullable identity
    # fields without treating missing display metadata as missing evidence.
    for key in (
        "name",
        "qualname",
        "signature",
        "verification_test_symbol",
        "test_symbol",
        "start_line",
        "end_line",
        "canonical_rank",
    ):
        if key in row:
            _nullable(
                row,
                key,
                int if key.endswith("line") or key == "canonical_rank" else str,
                path,
            )
    if "roles" in row:
        _strings(row["roles"], f"{path}.roles")
    _fields(row, path, str, (), ("evidence_visibility", "selection_reason"))
    _fields(row, path, int, (), ("namespace_overlap",))
    for key in ("reference_symbols", "task_anchor_terms", "indirect_reference_symbols"):
        if key in row:
            _strings(row[key], f"{path}.{key}")
    _fields(
        row,
        path,
        str,
        (),
        (
            "plausibility",
            "discriminator",
            "reference_strength",
            "reference_backed_source_path",
        ),
    )
    _fields(
        row,
        path,
        bool,
        (),
        (
            "direct_reference",
            "indirect_reference",
            "reference_backed_source_projection",
            "exact_identifier_projection",
            "qualified_identifier_index_projection",
            "locality_projection",
        ),
    )


def read_task_candidate(value: object) -> TaskCandidate:
    """Bind stable identity fields at the untyped index/JSON boundary.

    Preserve index-owned extensions and make no ownership admission decision.
    """
    row = _record(value, "task_candidate", TaskCandidate)
    _locator(row, "task_candidate")
    return cast("TaskCandidate", row)


def _nullable_locator(value: dict[str, object], key: str, path: str) -> None:
    _nullable(value, key, dict, path)
    if value[key] is not None:
        _locator(value[key], f"{path}.{key}")


def _ambiguity(value: object, path: str) -> None:
    row = _record(value, path, TaskAmbiguity)
    _fields(row, path, str, ("schema", "reason"))
    _fields(row, path, bool, ("ambiguous", "secret_knowledge_used"))
    _nullable(row, "discrimination_question", str, path)
    for key in ("candidates", "alternatives", "task_local_verification_origins"):
        for locator in _records(row.get(key), f"{path}.{key}"):
            _locator(locator, f"{path}.{key}")
    _strings(
        row.get("task_local_structural_owners"), f"{path}.task_local_structural_owners"
    )


def _plan(value: object, path: str) -> None:
    row = _record(value, path)
    _field(row, "schema", str, path)
    _field(row, "available", bool, path)
    if row["available"]:
        _fields(
            row,
            path,
            str,
            ("path", "runner", "working_directory", "confidence", "evidence"),
            ("scope",),
        )
        _strings(row.get("argv"), f"{path}.argv")
        if "test_symbol" in row:
            _nullable(row, "test_symbol", str, path)
    else:
        _fields(row, path, str, ("reason",), ("path",))


def _relevance(value: object, path: str) -> None:
    row = _record(value, path, VerificationRelevance)
    _fields(
        row,
        path,
        str,
        ("schema", "selection_reason", "authority"),
        ("completeness", "truncation"),
    )
    _fields(
        row,
        path,
        bool,
        ("selection_changed", "secret_knowledge_used"),
        (
            "negative_evidence_admissible",
            "qualified_identity_ambiguous",
            "verifier_identity_ambiguous",
        ),
    )
    _fields(
        row,
        path,
        int,
        (),
        ("candidate_count", "unresolved_reference_identity_omitted_paths"),
    )
    _nullable_locator(row, "selected", path)
    for locator in _records(row.get("candidates"), f"{path}.candidates"):
        _locator(locator, f"{path}.candidates")
    for key in (
        "search_bound_reasons",
        "unresolved_import_identity_paths",
        "unresolved_reference_identity_paths",
    ):
        if key in row:
            _strings(row[key], f"{path}.{key}")
    _relevance_extensions(row, path)


def _relevance_extensions(row: dict[str, object], path: str) -> None:
    if "current_canonical_verify" in row:
        _nullable(row, "current_canonical_verify", str, path)
    if "bounds" in row:
        bounds = _record(row["bounds"], f"{path}.bounds")
        _fields(bounds, f"{path}.bounds", int, tuple(bounds))
    for key in ("task_matches", "candidate_disclosure"):
        if key in row:
            _record(row[key], f"{path}.{key}")


def _source(value: object, path: str, *, initial: bool = False) -> None:
    row = _record(
        value, path, TaskSourceEvidenceBase if initial else TaskSourceEvidence
    )
    _fields(row, path, str, ("representation",), ("role", "path"))
    if not initial:
        _field(row, "content", str, path)
    _nullable(row, "symbol", str, path)
    _field(row, "estimated_tokens", int, path)
    _source_details(row, path)


def _source_details(row: dict[str, object], path: str) -> None:
    if "lines" in row:
        lines = row["lines"]
        if not isinstance(lines, list) or any(type(line) is not int for line in lines):
            raise RuntimeError(f"invalid {path}.lines: expected integer lines")
    if "config" in row:
        config = _record(row["config"], f"{path}.config", TaskSourceConfig)
        _fields(config, f"{path}.config", str, ("format", "kind", "name", "locator"))


def _next_read(value: object, path: str) -> None:
    row = _record(value, path, SourceReadPending)
    _fields(
        row,
        path,
        str,
        ("reason",),
        (
            "role",
            "path",
            "ambiguity_reason",
            "selection_basis",
            "authority",
            "discriminator",
            "availability_reason",
        ),
    )
    _fields(
        row,
        path,
        int,
        (),
        ("estimated_tokens", "candidate_count", "rank", "start_line", "end_line"),
    )
    if "symbol" in row:
        _nullable(row, "symbol", str, path)
    _source_details(row, path)
    if "selection_basis" in row:
        _record(row, path, DiscriminationRead)
        _retrieval_locator(row, path)
        _fields(row, path, str, ("ambiguity_reason", "selection_basis", "authority"))


def _ownership(value: object, path: str, *, initial: bool = False) -> None:
    row = _record(value, path, TaskOwnership)
    _fields(row, path, str, ("status", "authority_proof_identity", "authority"))
    _field(row, "proof_scope_complete", bool, path)
    _nullable(row, "proof_scope", str, path)
    _nullable(row, "basis", str, path)
    _nullable(row, "candidate_basis", str, path)
    for key in ("owner", "candidate"):
        _nullable_locator(row, key, path)
    _ambiguity(row.get("ambiguity"), f"{path}.ambiguity")
    _ownership_disclosure(row, path, initial=initial)


def _ownership_disclosure(
    row: dict[str, object], path: str, *, initial: bool = False
) -> None:
    for key in ("source_evidence", "next_read", "source_budget"):
        _nullable(row, key, dict, path)
    if row["source_evidence"] is not None:
        _source(row["source_evidence"], f"{path}.source_evidence", initial=initial)
    if row["next_read"] is not None:
        _next_read(row["next_read"], f"{path}.next_read")
    if row["source_budget"] is not None:
        budget = _record(
            row["source_budget"], f"{path}.source_budget", TaskSourceBudget
        )
        _fields(
            budget,
            f"{path}.source_budget",
            int,
            ("requested_tokens", "estimated_tokens"),
        )
        _field(budget, "complete", bool, f"{path}.source_budget")


def _verification(value: object, path: str) -> None:
    row = _record(value, path, TaskVerification)
    _field(row, "authority", str, path)
    _nullable_locator(row, "selected", path)
    _plan(row.get("plan"), f"{path}.plan")
    _relevance(row.get("relevance"), f"{path}.relevance")


def _provenance(value: object, path: str) -> None:
    row = _record(value, path, TaskEvidenceProvenance)
    _fields(
        row,
        path,
        str,
        ("why", "freshness", "context_identity"),
        ("freshness_proof", "revision", "freshness_reason"),
    )
    _fields(
        row,
        path,
        int,
        (),
        ("generation", "identity_generation", "selection_generation"),
    )


def _retrieval_locator(value: object, path: str) -> None:
    row = _record(value, path)
    _fields(row, path, str, ("path",), ("symbol", "evidence_visibility", "supplement"))
    _fields(row, path, int, (), ("rank", "start_line", "end_line"))
    if "roles" in row:
        _strings(row["roles"], f"{path}.roles")
    for key in (
        "enclosing_declarations",
        "class_declarations",
        "same_name_declarations",
        "direct_call_declarations",
    ):
        if key in row:
            _record(row[key], f"{path}.{key}")


def _retrieval(value: object, path: str) -> None:
    row = _record(value, path, TaskRetrieval)
    _fields(row, path, str, ("ordering", "presentation"))
    _fields(row, path, bool, ("ownership_authority",), ("supplemental_authority",))
    _fields(row, path, int, (), ("canonical_omitted_results", "supplemental_results"))
    bounds = _record(row.get("bounds"), f"{path}.bounds", TaskRetrievalBounds)
    _fields(bounds, f"{path}.bounds", int, ("limit", "per_role"))
    _fields(
        bounds,
        f"{path}.bounds",
        str,
        ("canonical_completeness", "canonical_truncation"),
    )
    _strings(bounds.get("bound_reasons"), f"{path}.bounds.bound_reasons")
    for locator in _records(row.get("results"), f"{path}.results"):
        _retrieval_locator(locator, f"{path}.results")
    if "exact_identifier_supplements" in row:
        _record(
            row["exact_identifier_supplements"], f"{path}.exact_identifier_supplements"
        )


def _packet_roles(row: dict[str, object], path: str) -> None:
    _ownership(row.get("ownership"), f"{path}.ownership")
    _verification(row.get("verification"), f"{path}.verification")
    related = _record(row.get("related"), f"{path}.related", TaskRelatedEvidence)
    _nullable_locator(related, "contract", f"{path}.related")
    for key in ("inspect", "candidates"):
        for locator in _records(related.get(key), f"{path}.related.{key}"):
            _locator(locator, f"{path}.related.{key}")
    if "resource_lifecycle" in related:
        from .filesystem_lifecycle_contract import validate_lifecycle_observation

        validate_lifecycle_observation(
            _record(related["resource_lifecycle"], f"{path}.related.resource_lifecycle")
        )
    explicit = _record(row.get("explicit_target"), f"{path}.explicit_target")
    _field(explicit, "status", str, f"{path}.explicit_target")
    for key in ("basis", "path", "symbol"):
        _nullable(explicit, key, str, f"{path}.explicit_target")


def read_task_evidence(value: object) -> TaskEvidencePacket:
    """Read a complete current packet without deriving authority from its shape."""
    path = "task_evidence"
    row = _record(validate_operation_response(path, value), path, TaskEvidencePacket)
    _fields(
        row,
        path,
        str,
        ("schema", "task", "consumer_action", "evidence_packet_identity"),
    )
    _record(row.get("evidence_receipt"), f"{path}.evidence_receipt")
    _retrieval(row.get("retrieval"), f"{path}.retrieval")
    _packet_roles(row, path)
    _provenance(row.get("provenance"), f"{path}.provenance")
    freshness = _record(row.get("freshness"), f"{path}.freshness", TaskFreshness)
    _field(freshness, "state", str, f"{path}.freshness")
    _nullable(freshness, "reason", str, f"{path}.freshness")
    _packet_extensions(row, path)
    return cast("TaskEvidencePacket", row)


def _packet_extensions(row: dict[str, object], path: str) -> None:
    for key in ("semantic_relationships", "supplied_observation_accounting"):
        if key in row:
            _record(row[key], f"{path}.{key}")


def _structural_resolution(value: object, path: str) -> None:
    row = _record(value, path, StructuralOwnerResolution)
    _fields(
        row,
        path,
        str,
        ("selected",),
        (
            "path",
            "via",
            "source_path",
            "selection_reason",
            "authority_reason",
            "effect",
            "consumer_action",
            "relation_graph_schema",
            "relation_graph_completeness",
            "relation_graph_truncation",
        ),
    )
    _fields(row, path, bool, ("secret_knowledge_used",), ("authority_admissible",))
    _fields(row, path, int, (), ("depth", "cycle_count", "revisit_count"))
    if "owner_path" in row:
        _hops(row["owner_path"], f"{path}.owner_path")
    for key in ("corroboration", "relation_graph_search_bound_reasons"):
        if key in row:
            _strings(row[key], f"{path}.{key}")


def _structural_starts(value: object, path: str) -> None:
    row = _record(value, path, StructuralStarts)
    _fields(row, path, str, ("scope", "status", "retrieval_completeness"))
    _fields(row, path, bool, ("limit_reached", "observation_complete"))
    _field(row, "candidate_count", int, path)
    _strings(row.get("observed_owners"), f"{path}.observed_owners")
    for start in _records(
        row.get("candidates"), f"{path}.candidates", StructuralStartObservation
    ):
        _fields(
            start, path, str, ("start_path", "origin", "graph_completeness", "status")
        )
        _nullable(start, "canonical_rank", int, path)
        _nullable(start, "observed_owner", str, path)
        for key in ("roles", "anchor_terms", "graph_bound_reasons"):
            _strings(start.get(key), f"{path}.candidates.{key}")
        _hops(start.get("owner_path"), f"{path}.candidates.owner_path")


def _authority(value: object, path: str) -> None:
    row = _record(value, path, OwnershipAuthority)
    _fields(
        row,
        path,
        str,
        (
            "schema",
            "status",
            "reason",
            "authority",
            "consumer_action",
            "authority_proof_identity",
        ),
    )
    _fields(
        row, path, bool, ("owner_resolved", "proof_complete", "proof_scope_complete")
    )
    for key in ("resolved_owner", "candidate_owner", "proof_scope"):
        _nullable(row, key, str, path)
    _ownership_evidence_state(row.get("evidence_state"), f"{path}.evidence_state")


def _trace(value: object, path: str) -> None:
    row = _record(value, path, OwnershipDecisionTrace)
    _fields(row, path, str, ("schema", "status", "confidence"))
    _field(row, "proof_scope_complete", bool, path)
    for key in ("authority_basis", "proof_scope"):
        _nullable(row, key, str, path)
    _trace_candidates(row, path)
    structural = _record(row.get("structural_evidence"), f"{path}.structural_evidence")
    for key in ("selected", "via", "owner_path"):
        if key not in structural:
            raise RuntimeError(
                f"invalid {path}.structural_evidence.{key}: missing field"
            )
    ambiguity = _record(row.get("ambiguity"), f"{path}.ambiguity")
    _field(ambiguity, "ambiguous", bool, f"{path}.ambiguity")
    _field(ambiguity, "reason", str, f"{path}.ambiguity")
    _ownership_evidence_state(row.get("evidence_state"), f"{path}.evidence_state")


def _ownership_evidence_state(value: object, path: str) -> None:
    flags = _record(value, path, OwnershipEvidenceState)
    _fields(flags, path, bool, tuple(OwnershipEvidenceState.__required_keys__))


def _trace_candidates(row: dict[str, object], path: str) -> None:
    _nullable(row, "selected", dict, path)
    selected = (
        []
        if row["selected"] is None
        else [_record(row["selected"], f"{path}.selected", OwnershipCandidateIdentity)]
    )
    candidates = _records(
        row.get("candidates"), f"{path}.candidates", OwnershipTraceCandidate
    )
    for candidate in selected + candidates:
        _field(candidate, "path", str, path)
        for key in ("name", "qualname"):
            if key not in candidate:
                raise RuntimeError(f"invalid {path}.candidates.{key}: missing field")
        _field(candidate, "canonical_rank", int, path)
        _strings(candidate.get("roles"), f"{path}.candidates.roles")
    for candidate in candidates:
        _field(candidate, "disposition", str, path)
        _nullable(candidate, "rejection_reason", str, path)


def read_task_action_map(value: object) -> TaskActionMap:
    path = "task_action_map"
    row = _record(validate_operation_response(path, value), path, TaskActionMap)
    _fields(row, path, str, ("schema", "task", "ranking_effect", "discovery_effect"))
    for key in ("edit", "verify", "contract", "admitted_edit", "action_edit"):
        _nullable_locator(row, key, path)
    for key in ("inspect", "related", "canonical"):
        for locator in _records(row.get(key), f"{path}.{key}"):
            _locator(locator, f"{path}.{key}")
    _nullable(row, "ownership_resolution", dict, path)
    if row["ownership_resolution"] is not None:
        _structural_resolution(
            row["ownership_resolution"], f"{path}.ownership_resolution"
        )
    _structural_starts(row.get("structural_starts"), f"{path}.structural_starts")
    _action_qualification(row, path)
    return cast("TaskActionMap", row)


def _action_qualification(row: dict[str, object], path: str) -> None:
    for key in ("candidate_path", "owner_basis"):
        _nullable(row, key, str, path)
    _ambiguity(row.get("ambiguity"), f"{path}.ambiguity")
    _relevance(row.get("verification_relevance"), f"{path}.verification_relevance")
    _authority(row.get("ownership_authority"), f"{path}.ownership_authority")
    _trace(row.get("ownership_decision_trace"), f"{path}.ownership_decision_trace")
    bounds = _record(row.get("bounds"), f"{path}.bounds", TaskActionBounds)
    _fields(bounds, f"{path}.bounds", int, ("limit", "per_role"))
    _action_search(row, path)


def _action_search(row: dict[str, object], path: str) -> None:
    discrimination = _record(
        row.get("action_discrimination"),
        f"{path}.action_discrimination",
        ActionDiscrimination,
    )
    _field(discrimination, "needed", bool, f"{path}.action_discrimination")
    _field(discrimination, "reason", str, f"{path}.action_discrimination")
    search = _record(
        row.get("exact_identifier_search"),
        f"{path}.exact_identifier_search",
        ExactIdentifierSearch,
    )
    _fields(
        search,
        f"{path}.exact_identifier_search",
        str,
        ("evaluation", "completeness", "truncation"),
    )
    _fields(
        search,
        f"{path}.exact_identifier_search",
        bool,
        ("negative_evidence_admissible", "uniqueness_admissible"),
    )
    _strings(
        search.get("bound_reasons"), f"{path}.exact_identifier_search.bound_reasons"
    )
    _record(row.get("authority_non_interference"), f"{path}.authority_non_interference")


def read_ownership_relation_graph(value: object) -> OwnershipRelationGraph:
    path = "ownership_relation_graph"
    row = _record(
        validate_operation_response(path, value), path, OwnershipRelationGraph
    )
    _fields(
        row,
        path,
        str,
        (
            "schema",
            "task",
            "start_path",
            "selection_reason",
            "completeness",
            "truncation",
            "cycle_policy",
            "relation_authority",
        ),
    )
    _fields(row, path, int, ("max_depth", "cycle_count", "revisit_count"))
    _fields(
        row,
        path,
        bool,
        (
            "negative_evidence_admissible",
            "uniqueness_admissible",
            "secret_knowledge_used",
        ),
    )
    _nullable(row, "selected", str, path)
    _strings(row.get("search_bound_reasons"), f"{path}.search_bound_reasons")
    _hops(row.get("owner_path"), f"{path}.owner_path")
    bounds = _record(row.get("bounds"), f"{path}.bounds", OwnershipRelationBounds)
    _fields(
        bounds,
        f"{path}.bounds",
        int,
        (
            "max_depth",
            "edges_per_path",
            "node_symbols",
            "symbols_per_alias",
            "symbol_candidates",
        ),
    )
    _graph_records(row, path)
    return cast("OwnershipRelationGraph", row)


def _graph_records(row: dict[str, object], path: str) -> None:
    for node in _records(row.get("nodes"), f"{path}.nodes", OwnershipNode):
        _field(node, "path", str, f"{path}.nodes")
        _strings(node.get("domains"), f"{path}.nodes.domains")
        _strings(node.get("task_locality_terms"), f"{path}.nodes.task_locality_terms")
    for edge in _records(row.get("edges"), f"{path}.edges", OwnershipRelationEdge):
        _fields(edge, f"{path}.edges", str, ("from", "to", "relation", "resolution"))
        _field(edge, "depth", int, f"{path}.edges")
        _fields(edge, f"{path}.edges", bool, ("cycle", "revisited"))
    _graph_candidates(row.get("candidates"), f"{path}.candidates")


def _graph_candidates(value: object, path: str) -> None:
    for candidate in _records(value, path, OwnershipCandidate):
        _field(candidate, "path", str, path)
        _fields(candidate, path, int, ("depth", "exact_edges"))
        for key in ("relations", "task_locality_terms"):
            _strings(candidate.get(key), f"{path}.{key}")
        if "corroboration" in candidate:
            _strings(candidate["corroboration"], f"{path}.corroboration")
        _fields(candidate, path, bool, (), ("corroborated",))


def read_post_change_delta(value: object) -> TaskPostChangeDelta:
    path = "post_change"
    row = _record(validate_operation_response(path, value), path, TaskPostChangeDelta)
    _fields(
        row,
        path,
        str,
        (
            "schema",
            "change",
            "ownership_status",
            "freshness",
            "scope",
            "consumer_owner",
        ),
        ("previous_index_binding",),
    )
    _fields(row, path, int, ("generation_before", "generation_after"))
    for key in ("invalidated", "reused"):
        _strings(row.get(key), f"{path}.{key}")
    for change in _records(
        row.get("path_changes"), f"{path}.path_changes", TaskPathChange
    ):
        _fields(change, f"{path}.path_changes", str, ("path", "state"), ("revision",))
    _delta_replacements(row, path)
    for key in ("semantic_relationships", "semantic_invalidation"):
        if key in row:
            _record(row[key], f"{path}.{key}")
    return cast("TaskPostChangeDelta", row)


def _delta_replacements(row: dict[str, object], path: str) -> None:
    if "replacement" not in row:
        return
    replacement = _record(
        row["replacement"], f"{path}.replacement", TaskPostChangeReplacement
    )
    if "ownership" in replacement:
        _ownership(replacement["ownership"], f"{path}.replacement.ownership")
    if "verification" in replacement:
        _verification(replacement["verification"], f"{path}.replacement.verification")
    if "provenance" in replacement:
        provenance = _record(
            replacement["provenance"], f"{path}.replacement.provenance"
        )
        _fields(
            provenance, f"{path}.replacement.provenance", str, (), ("why", "revision")
        )


def read_initial_projection(value: object) -> InitialTaskEvidenceProjection:
    """Read the semantic initial projection, including its omission accounting."""
    path = "task_evidence.initial"
    row = _record(
        validate_operation_response("task_evidence", value, mode="initial"),
        path,
        InitialTaskEvidenceProjection,
    )
    _fields(
        row,
        path,
        str,
        ("schema", "task", "source_evidence_identity", "consumer_action"),
        ("evidence_packet_identity",),
    )
    _record(row.get("evidence_receipt"), f"{path}.evidence_receipt")
    _retrieval(row.get("retrieval"), f"{path}.retrieval")
    _ownership(row.get("ownership"), f"{path}.ownership", initial=True)
    _initial_verification(row.get("verification"), f"{path}.verification")
    _provenance(row.get("provenance"), f"{path}.provenance")
    freshness = _record(row.get("freshness"), f"{path}.freshness", TaskFreshness)
    _field(freshness, "state", str, f"{path}.freshness")
    _nullable(freshness, "reason", str, f"{path}.freshness")
    _initial_projection_info(
        row.get("initial_projection"), f"{path}.initial_projection"
    )
    _initial_explicit_target(row.get("explicit_target"), f"{path}.explicit_target")
    _packet_extensions(row, path)
    return cast("InitialTaskEvidenceProjection", row)


def _initial_explicit_target(value: object, path: str) -> None:
    row = _record(value, path)
    _field(row, "status", str, path)
    for key in ("basis", "path", "symbol"):
        _nullable(row, key, str, path)


def _initial_verification(value: object, path: str) -> None:
    from .task_evidence_initial import decode_initial_collection

    row = _record(value, path)
    _field(row, "authority", str, path)
    _nullable_locator(row, "selected", path)
    _plan(row.get("plan"), f"{path}.plan")
    relevance = _record(row.get("relevance"), f"{path}.relevance")
    if "candidates_encoding" in relevance:
        candidates = _field(relevance, "candidates", list, f"{path}.relevance")
        assert isinstance(candidates, list)
        encoding = _record(
            relevance["candidates_encoding"], f"{path}.relevance.candidates_encoding"
        )
        try:
            decoded = decode_initial_collection(candidates, encoding)
        except ValueError as exc:
            raise RuntimeError(f"invalid {path}.relevance.candidates: {exc}") from exc
        relevance = {**relevance, "candidates": decoded}
    _relevance(relevance, f"{path}.relevance")


def _initial_projection_info(value: object, path: str) -> None:
    row = _record(value, path, InitialProjectionInfo)
    _fields(row, path, str, ("authority", "negative_evidence_from_omissions"))
    expansion = _record(row.get("expansion"), f"{path}.expansion", InitialExpansion)
    _fields(
        expansion,
        f"{path}.expansion",
        str,
        ("operation", "result_mode", "identity_check"),
    )
    omissions = _record(row.get("omissions"), f"{path}.omissions", InitialOmissions)
    for key in ("locator_fields", "locator_scopes", "sections"):
        _strings(omissions.get(key), f"{path}.omissions.{key}")
    collections = _record(omissions.get("collections"), f"{path}.omissions.collections")
    for key, count in collections.items():
        scope = f"{path}.omissions.collections.{key}"
        _fields(
            _record(count, scope, InitialOmissionCount),
            scope,
            int,
            ("observed_in_source_packet", "returned", "omitted"),
        )
