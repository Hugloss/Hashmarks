"""Shared shapes of the existing bounded repository ownership observation.

These records describe producer evidence, never a global semantic graph.
Indexed node/candidate payloads retain their index-owned extension fields.
"""

from typing import NotRequired, TypedDict

OwnershipPathHop = TypedDict(
    "OwnershipPathHop", {"from": str, "to": str, "relation": str}
)


class OwnershipRelationBounds(TypedDict):
    max_depth: int
    edges_per_path: int
    node_symbols: int
    symbols_per_alias: int
    symbol_candidates: int


class OwnershipNode(TypedDict):
    path: str
    domains: list[str]
    task_locality_terms: list[str]


OwnershipRelationEdge = TypedDict(
    "OwnershipRelationEdge",
    {
        "from": str,
        "to": str,
        "relation": str,
        "depth": int,
        "resolution": str,
        "cycle": bool,
        "revisited": bool,
    },
)


class OwnershipCandidate(TypedDict):
    path: str
    depth: int
    relations: list[str]
    exact_edges: int
    task_locality_terms: list[str]
    corroboration: NotRequired[list[str]]
    corroborated: NotRequired[bool]


class OwnershipRelationGraph(TypedDict):
    schema: str
    task: str
    start_path: str
    max_depth: int
    nodes: list[OwnershipNode]
    edges: list[OwnershipRelationEdge]
    candidates: list[OwnershipCandidate]
    selected: str | None
    selection_reason: str
    completeness: str
    truncation: str
    negative_evidence_admissible: bool
    uniqueness_admissible: bool
    search_bound_reasons: list[str]
    bounds: OwnershipRelationBounds
    owner_path: list[OwnershipPathHop]
    cycle_count: int
    revisit_count: int
    cycle_policy: str
    relation_authority: str
    secret_knowledge_used: bool


class StructuralOwnerCandidate(TypedDict):
    path: str
    depth: int
    via: str
    source_path: str
    owner_path: list[OwnershipPathHop]
    corroboration: list[str]
    cycle_count: int
    revisit_count: int
    relation_graph_schema: str
    relation_graph_completeness: str
    relation_graph_truncation: str
    relation_graph_search_bound_reasons: list[str]


class StructuralOwnerResolution(TypedDict):
    selected: str
    authority_admissible: NotRequired[bool]
    selection_reason: NotRequired[str]
    authority_reason: NotRequired[str]
    effect: NotRequired[str]
    consumer_action: NotRequired[str]
    secret_knowledge_used: bool
    path: NotRequired[str]
    depth: NotRequired[int]
    via: NotRequired[str]
    source_path: NotRequired[str]
    owner_path: NotRequired[list[OwnershipPathHop]]
    corroboration: NotRequired[list[str]]
    cycle_count: NotRequired[int]
    revisit_count: NotRequired[int]
    relation_graph_schema: NotRequired[str]
    relation_graph_completeness: NotRequired[str]
    relation_graph_truncation: NotRequired[str]
    relation_graph_search_bound_reasons: NotRequired[list[str]]


class StructuralStartObservation(TypedDict):
    start_path: str
    roles: list[str]
    canonical_rank: int | None
    anchor_terms: list[str]
    origin: str
    observed_owner: str | None
    owner_path: list[OwnershipPathHop]
    graph_completeness: str
    graph_bound_reasons: list[str]
    status: str


class StructuralStarts(TypedDict):
    scope: str
    status: str
    retrieval_completeness: str
    limit_reached: bool
    candidates: list[StructuralStartObservation]
    candidate_count: int
    observed_owners: list[str]
    observation_complete: bool


class OwnershipTraceStructuralEvidence(TypedDict):
    # Trace inputs may be partial observer projections; preserve missing values.
    selected: object
    via: object
    owner_path: object
