from __future__ import annotations

from typing import Any, TypedDict

Finding = dict[str, Any]
OwnershipNode = dict[str, Any]
OwnershipEdge = dict[str, Any]


class ImportOwnershipSummary(TypedDict):
    files_considered: int
    findings: int
    warnings: int
    advisories: int


class ImportOwnershipResult(TypedDict):
    schema: str
    generation: int
    identity_generation: int | None
    stale: bool | None
    summary: ImportOwnershipSummary
    findings: list[Finding]


class CacheOwnershipSummary(TypedDict):
    files_considered: int
    owners: int
    import_identity_risks: int
    invalidation_not_proven: int


class CacheOwnershipResult(TypedDict):
    schema: str
    generation: int
    identity_generation: int | None
    stale: bool | None
    summary: CacheOwnershipSummary
    owners: list[Finding]


class ConcurrencyRiskSummary(TypedDict):
    files_considered: int
    sequences: int
    unguarded: int


class ConcurrencyRiskResult(TypedDict):
    schema: str
    generation: int
    identity_generation: int | None
    stale: bool | None
    summary: ConcurrencyRiskSummary
    findings: list[Finding]
    boundary: str


class CacheInvalidationSummary(TypedDict):
    files_considered: int
    cache_owners: int
    invalidators: int
    invalidation_edges: int
    owners_without_resolved_invalidator: int


class CacheInvalidationResult(TypedDict):
    schema: str
    generation: int
    identity_generation: int | None
    stale: bool | None
    summary: CacheInvalidationSummary
    nodes: list[OwnershipNode]
    edges: list[OwnershipEdge]
    unresolved_cache_owners: list[str]
    boundary: str
