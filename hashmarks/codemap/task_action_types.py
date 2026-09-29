from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from .model import SearchHit
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


@dataclass
class _TaskActionMapContext:
    hits: Sequence[SearchHit]
    rows: list[dict[str, object]]
    failed: set[str]
    cues: _TaskActionCues
    cue_words: set[str]
    strong_config_cues: set[str]
    strong_contract_cues: set[str]
    strong_authority_cues: set[str]
    projection_state: _TaskActionProjectionState


@dataclass
class _TaskActionInitialSurfaceState:
    edit: dict[str, object] | None
    verify: dict[str, object] | None
    contract: dict[str, object] | None
    explicit_surface_ambiguity: bool
    explicit_edit_surface_selected: bool
    verification_anchor_tokens: Sequence[str]
    literal_reference_owner: dict[str, object] | None
    localized_config_edit: bool
    explicit_config_surface_request: bool


@dataclass
class _TaskActionOwnerResolutionState:
    edit: dict[str, object] | None
    basis: str | None
    structural_owner: dict[str, object] | None
    structural_owner_origin: Mapping[str, object] | None
    archive_live_owner_ambiguity: bool
    exact_identifier_paths: tuple[str, ...]


@dataclass(frozen=True)
class _TaskActionOwnerResolutionRequest:
    task: str
    context: _TaskActionMapContext
    surface: _TaskActionInitialSurfaceState
    discrimination: _TaskActionDiscriminationState
    limit: int


@dataclass
class _TaskActionOwnerCandidateState:
    edit: dict[str, object] | None
    basis: str | None
    structural_owner: dict[str, object] | None
    archive_live_owner_ambiguity: bool
    exact_identifier_edits: list[dict[str, object]]
    exact_identifier_paths: tuple[str, ...]
    literal_task_path: str


@dataclass
class _TaskActionSelectionState:
    edit: dict[str, object] | None
    verify: dict[str, object] | None
    contract: dict[str, object] | None
    discrimination: _TaskActionDiscriminationState
    explicit_surface_ambiguity: bool
    explicit_edit_surface_selected: bool
    verification_anchor_tokens: Sequence[str]
    localized_config_edit: bool
    explicit_config_surface_request: bool
    owner_basis: str | None
    structural_owner: dict[str, object] | None
    structural_owner_origin: Mapping[str, object] | None
    archive_live_owner_ambiguity: bool
    exact_identifier_paths: tuple[str, ...]
    inspect_rows: list[dict[str, object]]
    related_rows: list[dict[str, object]]


@dataclass
class _TaskActionProjectionChoices:
    edit: dict[str, object] | None
    verify: dict[str, object] | None
    contract: dict[str, object] | None
    verification_relevance: Mapping[str, object]


@dataclass
class _TaskActionFinalState:
    edit: dict[str, object] | None
    verify: dict[str, object] | None
    contract: dict[str, object] | None
    structural_owner: dict[str, object] | None
    verification_relevance: Mapping[str, object]
    ambiguity_state: Mapping[str, object]
    competing: list[dict[str, object]]
    ambiguous: bool
    ambiguity_reason: str
