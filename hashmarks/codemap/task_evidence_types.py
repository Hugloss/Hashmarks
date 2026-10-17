"""Current task-evidence response shapes, shared by producers and consumers.

These declarations describe existing evidence; they neither validate repository
authority nor replace the schema versions owned by the operation registry.
Producer-specific leaf evidence remains a mapping or object until its owner
provides a more precise contract. Runtime responses remain ordinary dictionaries.
"""

from collections.abc import Mapping, Sequence
from typing import Literal, NotRequired, TypeAlias, TypedDict

from hashmarks.ownership_decision import OwnershipAuthority, OwnershipDecisionTrace

from .ownership_relation_types import StructuralOwnerResolution, StructuralStarts


class TaskCandidate(TypedDict):
    """Stable indexed candidate identity; index-owned metadata may extend it."""

    path: str
    name: NotRequired[str | None]
    qualname: NotRequired[str | None]
    signature: NotRequired[str | None]
    canonical_rank: NotRequired[int | None]
    roles: NotRequired[list[str]]
    start_line: NotRequired[int | None]
    end_line: NotRequired[int | None]
    evidence_visibility: NotRequired[str]
    verification_test_symbol: NotRequired[str | None]
    selection_reason: NotRequired[str]
    reference_symbols: NotRequired[list[str]]
    namespace_overlap: NotRequired[int]
    task_anchor_terms: NotRequired[list[str]]
    test_symbol: NotRequired[str | None]
    plausibility: NotRequired[str]
    discriminator: NotRequired[str]
    reference_strength: NotRequired[str]
    reference_backed_source_path: NotRequired[str]
    direct_reference: NotRequired[bool]
    indirect_reference: NotRequired[bool]
    indirect_reference_symbols: NotRequired[list[str]]
    reference_backed_source_projection: NotRequired[bool]
    exact_identifier_projection: NotRequired[bool]
    qualified_identifier_index_projection: NotRequired[bool]
    locality_projection: NotRequired[bool]


class ActionDiscrimination(TypedDict):
    needed: bool
    reason: str


class ExactIdentifierSearch(TypedDict):
    evaluation: str
    completeness: str
    truncation: str
    negative_evidence_admissible: bool
    uniqueness_admissible: bool
    bound_reasons: list[str]


class TaskAmbiguity(TypedDict):
    schema: str
    ambiguous: bool
    reason: str
    candidates: list[TaskCandidate]
    alternatives: list[TaskCandidate]
    task_local_structural_owners: list[str]
    task_local_verification_origins: list[TaskCandidate]
    discrimination_question: str | None
    secret_knowledge_used: bool


class TaskSourceBudget(TypedDict):
    requested_tokens: int
    estimated_tokens: int
    complete: bool


class VerificationPlanHeaders(TypedDict):
    schema: str


class AvailableVerificationPlan(VerificationPlanHeaders):
    available: Literal[True]
    path: str
    runner: str
    argv: list[str]
    working_directory: str
    confidence: str
    evidence: str
    scope: NotRequired[str]
    test_symbol: NotRequired[str | None]


class UnavailableVerificationPlan(VerificationPlanHeaders):
    available: Literal[False]
    reason: str
    path: NotRequired[str]


TaskVerificationPlan: TypeAlias = (
    AvailableVerificationPlan | UnavailableVerificationPlan
)


class TaskSourceConfig(TypedDict):
    format: str
    kind: str
    name: str
    locator: str


class TaskSourceRange(TypedDict):
    role: str
    path: str
    symbol: str | None
    lines: list[int]


class TaskSourceEvidenceBase(TypedDict):
    representation: str
    symbol: str | None
    estimated_tokens: int
    role: NotRequired[str]
    path: NotRequired[str]
    lines: NotRequired[list[int]]
    config: NotRequired[TaskSourceConfig]


class TaskSourceEvidence(TaskSourceEvidenceBase):
    content: str


class SourceReadFields(TypedDict, total=False):
    role: str
    path: str
    symbol: str | None
    lines: list[int]
    estimated_tokens: int
    candidate_count: int
    config: TaskSourceConfig


class SourceReadPendingDraft(SourceReadFields):
    """Source-range assembly also returns an empty record when the read succeeds."""

    reason: NotRequired[str]


class SourceReadPending(SourceReadFields):
    reason: str


class VerificationRelevanceFields(TypedDict):
    schema: str
    selected: TaskCandidate | None
    selection_reason: str
    selection_changed: bool
    authority: str
    secret_knowledge_used: bool
    candidate_count: NotRequired[int]
    completeness: NotRequired[str]
    truncation: NotRequired[str]
    negative_evidence_admissible: NotRequired[bool]
    search_bound_reasons: NotRequired[list[str]]
    current_canonical_verify: NotRequired[str | None]
    qualified_identity_ambiguous: NotRequired[bool]
    verifier_identity_ambiguous: NotRequired[bool]
    unresolved_import_identity_paths: NotRequired[list[str]]
    unresolved_reference_identity_paths: NotRequired[list[str]]
    unresolved_reference_identity_omitted_paths: NotRequired[int]
    bounds: NotRequired[dict[str, int]]
    task_matches: NotRequired[dict[str, object]]
    candidate_disclosure: NotRequired[Mapping[str, object]]


class VerificationRelevance(VerificationRelevanceFields):
    candidates: list[TaskCandidate]


class InitialCollectionEncoding(TypedDict):
    kind: str
    columns: list[str]


class InitialVerificationRelevance(VerificationRelevanceFields):
    candidates: list[TaskCandidate] | list[list[object]]
    candidates_encoding: NotRequired[InitialCollectionEncoding]


class TaskProvenanceDraft(TypedDict):
    why: str
    freshness: str
    freshness_proof: NotRequired[str]
    revision: NotRequired[str]
    freshness_reason: NotRequired[str]
    generation: NotRequired[int]
    identity_generation: NotRequired[int]
    selection_generation: NotRequired[int]


class TaskEvidenceProvenance(TaskProvenanceDraft):
    context_identity: str


class TaskActionOwnershipFields(TypedDict):
    ownership_decision_trace: OwnershipDecisionTrace
    ownership_authority: OwnershipAuthority
    admitted_edit: TaskCandidate | None
    action_edit: TaskCandidate | None
    candidate_path: str | None


class TaskActionBounds(TypedDict):
    limit: int
    per_role: int


class TaskActionMap(TaskActionOwnershipFields):
    schema: str
    task: str
    edit: TaskCandidate | None
    action_discrimination: ActionDiscrimination
    verify: TaskCandidate | None
    contract: TaskCandidate | None
    inspect: list[TaskCandidate]
    related: list[TaskCandidate]
    ownership_resolution: StructuralOwnerResolution | None
    structural_starts: StructuralStarts
    owner_basis: str | None
    exact_identifier_search: ExactIdentifierSearch
    verification_relevance: VerificationRelevance
    ambiguity: TaskAmbiguity
    canonical: list[TaskCandidate]
    bounds: TaskActionBounds
    authority_non_interference: Mapping[str, object]
    ranking_effect: str
    discovery_effect: str


class RetrievalLocator(TypedDict):
    path: str
    rank: NotRequired[int]
    symbol: NotRequired[str]
    roles: NotRequired[list[str]]
    start_line: NotRequired[int]
    end_line: NotRequired[int]
    evidence_visibility: NotRequired[str]
    supplement: NotRequired[str]
    enclosing_declarations: NotRequired[Mapping[str, object]]
    class_declarations: NotRequired[Mapping[str, object]]
    same_name_declarations: NotRequired[Mapping[str, object]]
    direct_call_declarations: NotRequired[Mapping[str, object]]


class TaskRetrievalDraftBounds(TaskActionBounds):
    canonical_completeness: NotRequired[str]
    canonical_truncation: NotRequired[str]
    bound_reasons: NotRequired[list[str]]


class TaskRetrievalBounds(TaskActionBounds):
    canonical_completeness: str
    canonical_truncation: str
    bound_reasons: list[str]


class TaskRetrievalProjection(TypedDict):
    results: list[RetrievalLocator]
    ordering: str
    ownership_authority: bool
    presentation: str
    exact_identifier_supplements: NotRequired[Mapping[str, object]]
    canonical_omitted_results: NotRequired[int]
    supplemental_results: NotRequired[int]
    supplemental_authority: NotRequired[bool]


class TaskRetrievalDraft(TaskRetrievalProjection):
    bounds: TaskRetrievalDraftBounds


class TaskRetrieval(TaskRetrievalProjection):
    bounds: TaskRetrievalBounds


class ExplicitTaskTarget(TypedDict):
    status: str
    basis: str | None
    path: str | None
    symbol: object


class DiscriminationRead(RetrievalLocator):
    reason: str
    ambiguity_reason: str
    selection_basis: str
    authority: str
    discriminator: NotRequired[str]
    availability_reason: NotRequired[str]


class TaskOwnershipFields(TypedDict):
    status: str
    authority_proof_identity: str
    proof_scope: str | None
    proof_scope_complete: bool
    owner: TaskCandidate | None
    candidate: TaskCandidate | None
    basis: str | None
    candidate_basis: str | None
    ambiguity: TaskAmbiguity
    authority: str
    next_read: SourceReadPending | DiscriminationRead | None
    source_budget: TaskSourceBudget | None


class TaskOwnership(TaskOwnershipFields):
    source_evidence: TaskSourceEvidence | None


class InitialTaskOwnership(TaskOwnershipFields):
    source_evidence: TaskSourceEvidenceBase | None


class TaskVerificationFields(TypedDict):
    selected: TaskCandidate | None
    plan: TaskVerificationPlan
    authority: str


class TaskVerification(TaskVerificationFields):
    relevance: VerificationRelevance


class InitialTaskVerification(TaskVerificationFields):
    relevance: InitialVerificationRelevance


class TaskRelatedEvidence(TypedDict):
    contract: TaskCandidate | None
    inspect: list[TaskCandidate]
    candidates: list[TaskCandidate]
    resource_lifecycle: NotRequired[Mapping[str, object]]


class TaskFreshness(TypedDict):
    state: str
    reason: str | None


class TaskEvidenceBase(TypedDict):
    schema: str
    task: str
    evidence_receipt: dict[str, object]
    explicit_target: ExplicitTaskTarget
    ownership: TaskOwnership
    verification: TaskVerification
    related: TaskRelatedEvidence
    consumer_action: str
    semantic_relationships: NotRequired[Mapping[str, object]]
    supplied_observation_accounting: NotRequired[Mapping[str, object]]


class TaskEvidenceDraft(TaskEvidenceBase):
    """Internal assembly state; closing provenance has not necessarily run."""

    retrieval: TaskRetrievalDraft
    provenance: NotRequired[TaskEvidenceProvenance]
    freshness: NotRequired[TaskFreshness]


class TaskEvidencePacket(TaskEvidenceBase):
    retrieval: TaskRetrieval
    provenance: TaskEvidenceProvenance
    freshness: TaskFreshness
    evidence_packet_identity: str


class StringTableEncoding(TypedDict):
    kind: Literal["json-string-table.v1"]
    strings: list[list[int | str]]


class CompressedInitialEncoding(TypedDict):
    kind: Literal["json-string-table.v1+zlib", "json+zlib"]
    decoded_bytes: int


class InitialOmissionCount(TypedDict):
    observed_in_source_packet: int
    returned: int
    omitted: int


class InitialOmissions(TypedDict):
    locator_fields: list[str]
    locator_scopes: list[str]
    sections: list[str]
    collections: dict[str, InitialOmissionCount]


class InitialExpansion(TypedDict):
    operation: str
    result_mode: str
    identity_check: str


class InitialProjectionInfo(TypedDict):
    authority: str
    omissions: InitialOmissions
    expansion: InitialExpansion
    negative_evidence_from_omissions: str


class InitialTaskEvidenceProjection(TypedDict):
    """Semantic initial view, before string-table encoding.

    The codec owns nested column/table representations; they are deliberately
    distinct from the corresponding complete-packet records.
    """

    schema: str
    task: str
    source_evidence_identity: str
    evidence_packet_identity: NotRequired[str]
    evidence_receipt: dict[str, object]
    retrieval: TaskRetrieval
    explicit_target: ExplicitTaskTarget
    ownership: InitialTaskOwnership
    verification: InitialTaskVerification
    consumer_action: str
    provenance: TaskEvidenceProvenance
    freshness: TaskFreshness
    initial_projection: InitialProjectionInfo
    semantic_relationships: NotRequired[Mapping[str, object]]
    supplied_observation_accounting: NotRequired[Mapping[str, object]]


class InitialEnvelopeHeaders(TypedDict):
    schema: str
    source_evidence_identity: str
    evidence_packet_identity: str


class StringTableInitialEnvelope(InitialEnvelopeHeaders):
    encoding: StringTableEncoding
    data: object


class CompressedInitialEnvelope(InitialEnvelopeHeaders):
    encoding: CompressedInitialEncoding
    data: str


InitialTaskEvidenceEnvelope: TypeAlias = (
    StringTableInitialEnvelope | CompressedInitialEnvelope
)
PreviousTaskEvidence: TypeAlias = TaskEvidencePacket | dict[str, object]


class TaskPathChange(TypedDict):
    path: str
    state: str
    revision: NotRequired[str]


class ReplacementProvenance(TypedDict, total=False):
    why: str
    revision: str


class TaskPostChangeReplacement(TypedDict, total=False):
    ownership: TaskOwnership
    verification: TaskVerification
    provenance: ReplacementProvenance


class TaskPostChangeDelta(TypedDict):
    schema: str
    change: str
    ownership_status: str
    path_changes: list[TaskPathChange]
    generation_before: int
    generation_after: int
    invalidated: list[str]
    reused: list[str]
    freshness: str
    scope: str
    consumer_owner: str
    semantic_relationships: NotRequired[Mapping[str, object]]
    previous_index_binding: NotRequired[str]
    semantic_invalidation: NotRequired[Mapping[str, object]]
    replacement: NotRequired[TaskPostChangeReplacement]
