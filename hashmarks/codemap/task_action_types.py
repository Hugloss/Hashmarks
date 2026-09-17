from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .repository_domains import RepositoryDomain

@dataclass(frozen=True)
class _TaskActionCues:
    words: frozenset[str]
    explicit_test_edit: bool
    explicit_policy_surface: bool
    explicit_architecture_contract: bool

@dataclass(frozen=True)
class _TaskActionSurface:
    domains: tuple[RepositoryDomain, ...]
    benchmark_external: bool
    is_test: bool
    is_contract: bool
    is_config: bool
    is_source: bool

@dataclass
class _TaskActionProjectionState:
    terms: list[str]
    document_frequency: dict[str, int]
    candidates: list[dict[str, object]]
    file_rows: dict[str, object]
    text_cache: dict[str, str | None]
    rows: list[dict[str, object]]
    limit: int

@dataclass
class _TaskActionDiscriminationState:
    task_terms: list[str]
    row_text: dict[int, str]
    term_rows: dict[str, int]

@dataclass
class _TaskActionAmbiguityPayloadState:
    ambiguous: bool
    reason: str
    candidates: Sequence[dict[str, object]]
    alternatives: Sequence[dict[str, object]]
    structural_owners: Mapping[str, object]
    verification_origins: Sequence[dict[str, object]]
    multi_structural_owner_ambiguity: bool

@dataclass
class _TaskActionConfigState:
    task_terms: list[str]
    row_text: dict[int, str]
    term_rows: dict[str, int]
