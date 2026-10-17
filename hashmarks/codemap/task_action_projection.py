from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from hashmarks.operation_contract import operation_response, operation_schema

from ..ownership_decision import bounded_presentation_contract
from .decision_session import ReadScopeOwner, decision_scoped, diagnostic_producer
from .task_action_types import (
    _TaskActionAmbiguityPayloadState,
    _TaskActionFinalState,
    _TaskActionMapContext,
    _TaskActionProjectionChoices,
    _TaskActionSelectionState,
)
from .task_evidence_contract import read_task_candidate
from .verification_defaults import VERIFICATION_RELEVANCE_DEFAULTS
from .verification_relevance_model import (
    VerificationRequest,
    verification_without_edit_owner,
)

if TYPE_CHECKING:
    from .repository_tasks import RepositoryTasks
    from .task_evidence_types import ActionDiscrimination, TaskActionMap


@dataclass(frozen=True, slots=True)
class TaskActionOptions:
    """Default selection bounds for public task-action projections."""

    limit: int = 20
    per_role: int = 3


TASK_ACTION_DEFAULT_OPTIONS = TaskActionOptions()


class TaskActionProjectionMixin(ReadScopeOwner):
    @operation_response("task_action_map")
    @diagnostic_producer
    def action_map(
        self,
        task: str,
        *,
        limit: int = TASK_ACTION_DEFAULT_OPTIONS.limit,
        per_role: int = TASK_ACTION_DEFAULT_OPTIONS.per_role,
    ) -> TaskActionMap:
        """Reconcile task evidence before its generation-bound observation."""
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        self.prepare(task, limit)
        return self._observe_task_action_map(task, limit=limit, per_role=per_role)

    @decision_scoped
    def _observe_task_action_map(
        self,
        task: str,
        *,
        limit: int = TASK_ACTION_DEFAULT_OPTIONS.limit,
        per_role: int = TASK_ACTION_DEFAULT_OPTIONS.per_role,
    ) -> TaskActionMap:
        """Translate canonical task evidence into worker actions without reranking it.

        ``find_task`` remains retrieval authority.  This projection classifies only
        already-retrieved paths into edit, verify, contract, inspect, and related
        roles, preserving canonical rank/provenance on every row.
        """
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        self.ownership._validate_task_action_limits(limit, per_role)
        action_key, cached = self._task_action_cache_lookup(task, limit, per_role)
        if cached is not None:
            return cached
        context = self.ownership.observe_candidates(
            self._task_observation(task, limit), limit
        )
        selection = self.ownership.nominate(task, context, limit, per_role)
        choices = self._task_action_projection_choices(task, context, selection, limit)
        final = self.ownership.qualify(
            task, context, selection, choices, (limit, per_role)
        )
        result = self._task_action_projection_result(
            task, context, selection, final, (limit, per_role)
        )
        self._task_action_record_result(task, limit, action_key, result)
        return result

    def _task_action_cache_lookup(
        self, task: str, limit: int, per_role: int
    ) -> tuple[tuple[int, str, int, int] | None, TaskActionMap | None]:
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        if self.reads.depth <= 0:
            return None, None
        if self._task_action_reuse.scope is not self.reads.scope:
            self._task_action_reuse.entries.clear()
            self._task_action_reuse.scope = self.reads.scope
        generation = int(self.reads.generation or self.store.generation())
        action_key = (generation, task, int(limit), int(per_role))
        cached = self._task_action_reuse.entries.get(action_key)
        if cached is not None:
            self.reads.count("task_action_hit")
            return action_key, deepcopy(cached)
        self.reads.count("task_action_miss")
        return action_key, None

    def _task_action_projection_choices(
        self,
        task: str,
        context: _TaskActionMapContext,
        selection: _TaskActionSelectionState,
        limit: int,
    ) -> _TaskActionProjectionChoices:
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        edit = self.ownership._task_action_promoted_edit(context, selection)
        contract = self.ownership._task_action_local_contract(selection, edit)
        structural_starts = selection.structural_starts
        structural_conflict = bool(
            len(cast("Sequence[str]", structural_starts.get("observed_owners") or []))
            > 1
            or any(
                row.get("status") in {"graph-incomplete", "stale", "unresolved"}
                for row in cast(
                    "Sequence[Mapping[str, object]]",
                    structural_starts.get("candidates") or [],
                )
            )
        )
        if self.ownership._task_action_verification_edit_is_admitted(
            selection
        ) and not (
            structural_conflict
            and structural_starts.get("status") == "observed"
            and selection.owner_basis
            not in {
                "literal-path",
                "qualified-symbol",
                "unique-exact-symbol",
                "exact-symbol",
                "exact-import-owner",
            }
        ):
            verification_relevance = self.verification.for_owner(
                VerificationRequest(
                    context.observation.scope,
                    context.observation.query,
                    "nominated",
                    edit,
                    selection.verify,
                    tuple(context.rows),
                ),
                limit=VERIFICATION_RELEVANCE_DEFAULTS.candidate_limit,
            )
        else:
            current_verify_path = (
                str(selection.verify.get("path") or "")
                if isinstance(selection.verify, Mapping)
                else ""
            )
            verification_relevance = verification_without_edit_owner(
                current_verify_path
            )
        verify = self.ownership._task_action_finalize_verification_selection(
            verification_relevance.get("selected"), context.rows, limit
        )
        return _TaskActionProjectionChoices(
            edit=edit,
            verify=verify if verify is not None else selection.verify,
            contract=contract,
            verification_relevance=verification_relevance,
        )

    @staticmethod
    def _task_action_discrimination_payload(
        final: _TaskActionFinalState,
        authority: Mapping[str, object],
    ) -> ActionDiscrimination:
        """Classify unresolved action evidence once for downstream projections."""
        reason = "resolved"
        if final.edit is None:
            reason = "no-supported-owner-candidate"
        elif final.ambiguous:
            reason = "competing-action-roles"
        elif not bool(authority.get("owner_resolved")):
            reason = "ownership-unresolved"
        elif final.verify is None:
            reason = "missing-verification-evidence"
        return {
            "needed": reason != "resolved",
            "reason": reason,
        }

    def _task_action_projection_result(
        self,
        task: str,
        context: _TaskActionMapContext,
        selection: _TaskActionSelectionState,
        final: _TaskActionFinalState,
        bounds: tuple[int, int],
    ) -> TaskActionMap:
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        limit, per_role = bounds
        ownership = self.ownership._task_action_ownership_payload_fields(
            final.edit,
            final.competing,
            final.structural_owner,
            final.ambiguous,
            final.ambiguity_reason,
            selection.owner_basis,
        )
        authority = ownership["ownership_authority"]
        action_edit = ownership.get("action_edit")
        action_discrimination = self._task_action_discrimination_payload(
            final, authority
        )
        proof_identity = str(authority.get("authority_proof_identity") or "")
        presentation = bounded_presentation_contract(
            proof_identity,
            total_candidates=len(final.competing),
            returned_candidates=min(len(final.competing), per_role),
            limit=limit,
            per_role=per_role,
            compact=False,
        )
        search_complete = selection.exact_identifier_search_complete
        return {
            "schema": operation_schema("task_action_map"),
            "task": task,
            "edit": None if final.edit is None else read_task_candidate(final.edit),
            "action_edit": action_edit,
            "action_discrimination": action_discrimination,
            "verify": None
            if final.verify is None
            else read_task_candidate(final.verify),
            "contract": None
            if final.contract is None
            else read_task_candidate(final.contract),
            "inspect": [read_task_candidate(row) for row in selection.inspect_rows],
            "related": [read_task_candidate(row) for row in selection.related_rows],
            "ownership_resolution": final.structural_owner,
            "structural_starts": selection.structural_starts,
            "owner_basis": selection.owner_basis,
            **ownership,
            "exact_identifier_search": {
                "evaluation": "evaluated"
                if search_complete is not None
                else "not-evaluated",
                "completeness": (
                    "complete"
                    if search_complete is True
                    else "incomplete"
                    if search_complete is False
                    else "unknown"
                ),
                "truncation": (
                    "complete"
                    if search_complete is True
                    else "truncated"
                    if search_complete is False
                    else "unknown"
                ),
                "negative_evidence_admissible": search_complete is True,
                "uniqueness_admissible": search_complete is True,
                "bound_reasons": list(selection.exact_identifier_search_bound_reasons),
            },
            "verification_relevance": final.verification_relevance,
            "ambiguity": self.ownership._task_action_ambiguity_payload(
                _TaskActionAmbiguityPayloadState(
                    ambiguous=final.ambiguous,
                    reason=final.ambiguity_reason,
                    candidates=cast(
                        "Sequence[dict[str, object]]",
                        final.ambiguity_state["candidates"],
                    ),
                    alternatives=final.competing[:per_role],
                    structural_owners=cast(
                        "Mapping[str, object]",
                        final.ambiguity_state["structural_owners"],
                    ),
                    verification_origins=cast(
                        "Sequence[dict[str, object]]",
                        final.ambiguity_state["verification_origins"],
                    ),
                    multi_structural_owner_ambiguity=bool(
                        final.ambiguity_state["multi_structural_owner_ambiguity"]
                    ),
                )
            ),
            "canonical": [
                read_task_candidate(dict(row)) for row in context.canonical_rows
            ],
            "bounds": self.ownership._task_action_bounds_payload(limit, per_role),
            "authority_non_interference": {
                "presentation_bounded": True,
                **presentation,
                "presentation_limit": limit,
                "per_role": per_role,
            },
            "ranking_effect": "none",
            "discovery_effect": self.ownership._task_action_discovery_effect(
                final.verification_relevance
            ),
        }

    def _task_action_record_result(
        self,
        task: str,
        limit: int,
        action_key: tuple[int, str, int, int] | None,
        result: TaskActionMap,
    ) -> None:
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        authority_paths = {
            str(row.get("path"))
            for row in (
                result.get("edit"),
                result.get("verify"),
                result.get("ownership_resolution"),
            )
            if isinstance(row, Mapping) and row.get("path")
        }
        starts = result.get("structural_starts")
        if isinstance(starts, Mapping):
            authority_paths.update(
                str(row.get("start_path"))
                for row in cast(
                    "Sequence[Mapping[str, object]]", starts.get("candidates") or []
                )
                if isinstance(row, Mapping) and row.get("start_path")
            )
            authority_paths.update(
                str(path)
                for path in cast("Sequence[str]", starts.get("observed_owners") or [])
                if path
            )
        self.remember_paths(task, authority_paths, limit=limit)
        if action_key is not None:
            self._task_action_reuse.entries[action_key] = deepcopy(result)
