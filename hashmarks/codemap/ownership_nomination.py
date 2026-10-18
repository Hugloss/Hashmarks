from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

from .model import EvidenceVisibility
from .repository_domains import RepositoryDomain
from .task_action_types import (
    TaskObservation,
    _TaskActionFinalState,
    _TaskActionInitialSurfaceState,
    _TaskActionMapContext,
    _TaskActionOwnerResolutionRequest,
    _TaskActionProjectionChoices,
    _TaskActionSelectionState,
)
from .verification_relevance_model import verification_without_edit_owner

if TYPE_CHECKING:
    from .ownership_graph import RepositoryOwnership
    from .ownership_relation_types import StructuralOwnerResolution


class OwnershipNominationMixin:
    """Nominate repository candidates and finish proof from supplied qualifiers."""

    def observe_candidates(
        self, observation: TaskObservation, limit: int
    ) -> _TaskActionMapContext:
        if TYPE_CHECKING:
            self = cast("RepositoryOwnership", self)
        if self.reads.scope is not observation.scope:
            raise RuntimeError(
                "candidate observation belongs to a different read scope"
            )
        task = observation.query.text
        failed: set[str] = set()
        hits = [
            hit
            for hit in observation.retrieval.hits
            if hit.evidence_visibility is not EvidenceVisibility.DENY
        ]
        cues = self._task_action_cues(task)
        strong_config_cues = self._strong_config_cues()
        rows = [
            self._task_action_row(hit, rank, failed, cues, strong_config_cues)
            for rank, hit in enumerate(hits, 1)
        ]
        self.reads.preload_symbols([str(row.get("path") or "") for row in rows])
        return _TaskActionMapContext(
            observation=observation,
            hits=hits,
            rows=rows,
            canonical_rows=tuple(rows),
            failed=failed,
            cues=cues,
            cue_words=set(cues.words),
            strong_config_cues=strong_config_cues,
            strong_contract_cues=self._strong_contract_cues(),
            strong_authority_cues=self._strong_authority_cues(),
            projection_state=self._task_action_projection_state(task, rows, limit),
        )

    def nominate(
        self,
        task: str,
        context: _TaskActionMapContext,
        limit: int,
        per_role: int,
    ) -> _TaskActionSelectionState:
        if TYPE_CHECKING:
            self = cast("RepositoryOwnership", self)
        if self.reads.scope is not context.observation.scope:
            raise RuntimeError("owner nomination belongs to a different read scope")
        surface = self._task_action_initial_surface_selection(task, context, limit)
        discrimination = self._task_action_discrimination_state(task, context.rows)
        owner = self._task_action_resolve_owner(
            _TaskActionOwnerResolutionRequest(
                task=task,
                context=context,
                surface=surface,
                discrimination=discrimination,
                limit=limit,
            )
        )
        return _TaskActionSelectionState(
            edit=owner.edit,
            verify=surface.verify,
            contract=surface.contract,
            discrimination=discrimination,
            explicit_surface_ambiguity=surface.explicit_surface_ambiguity,
            explicit_edit_surface_selected=bool(surface.explicit_edit_surface_selected),
            verification_anchor_tokens=surface.verification_anchor_tokens,
            localized_config_edit=surface.localized_config_edit,
            explicit_config_surface_request=bool(
                surface.explicit_config_surface_request
            ),
            owner_basis=owner.basis,
            structural_owner=owner.structural_owner,
            exact_identifier_paths=owner.exact_identifier_paths,
            exact_identifier_search_complete=owner.exact_identifier_search_complete,
            exact_identifier_search_bound_reasons=(
                owner.exact_identifier_search_bound_reasons
            ),
            structural_starts=owner.structural_starts,
            inspect_rows=[
                row
                for row in context.rows
                if "inspect" in cast("Sequence[str]", row["roles"])
            ][:per_role],
            related_rows=[
                row
                for row in context.rows
                if "related" in cast("Sequence[str]", row["roles"])
            ][:per_role],
        )

    def _task_action_promoted_edit(
        self,
        context: _TaskActionMapContext,
        selection: _TaskActionSelectionState,
    ) -> dict[str, object] | None:
        if TYPE_CHECKING:
            self = cast("RepositoryOwnership", self)
        edit = selection.edit
        current_edit_has_identifier_anchor = (
            self._task_action_current_edit_has_identifier_anchor(
                edit,
                selection.discrimination,
                selection.verification_anchor_tokens,
            )
        )
        promote_contract_surface = self._task_action_should_promote_contract_surface(
            current_edit_has_identifier_anchor,
            context.cues.explicit_policy_surface,
            context.cues.explicit_architecture_contract,
            context.cue_words,
            context.strong_config_cues,
            context.strong_contract_cues | context.strong_authority_cues,
        )
        if (
            selection.structural_owner is None
            and selection.owner_basis
            not in {
                "literal-path",
                "qualified-symbol",
                "unique-exact-symbol",
                "exact-symbol",
                "exact-import-owner",
            }
            and not selection.localized_config_edit
            and not selection.explicit_edit_surface_selected
            and promote_contract_surface
        ):
            contract_edit = self._task_action_contract_edit_candidate(
                context.rows, context.failed
            )
            if contract_edit is not None:
                edit = contract_edit
        return edit

    def _task_action_local_contract(
        self,
        selection: _TaskActionSelectionState,
        edit: dict[str, object] | None,
    ) -> dict[str, object] | None:
        if TYPE_CHECKING:
            self = cast("RepositoryOwnership", self)
        contract = selection.contract
        if (
            selection.verification_anchor_tokens
            and isinstance(contract, dict)
            and not self._task_action_contract_is_local(
                contract, edit, selection.verify
            )
        ):
            return None
        return contract

    @staticmethod
    def _task_action_verification_edit_is_admitted(
        selection: _TaskActionSelectionState,
    ) -> bool:
        return not (
            len(selection.exact_identifier_paths) > 1
            and selection.owner_basis is None
            and selection.structural_owner is None
        )

    def qualify(
        self,
        task: str,
        context: _TaskActionMapContext,
        selection: _TaskActionSelectionState,
        choices: _TaskActionProjectionChoices,
        bounds: tuple[int, int],
    ) -> _TaskActionFinalState:
        if TYPE_CHECKING:
            self = cast("RepositoryOwnership", self)
        if self.reads.scope is not context.observation.scope:
            raise RuntimeError("owner proof belongs to a different read scope")
        limit, per_role = bounds
        ambiguity = self._task_action_projection_ambiguity_state(
            task,
            context,
            selection,
            choices,
            (limit, per_role),
        )
        competing = cast("list[dict[str, object]]", ambiguity["competing"])
        ambiguous = bool(ambiguity["ambiguous"])
        ambiguity_reason = str(ambiguity["reason"])
        edit = choices.edit
        structural_owner = selection.structural_owner
        verification_relevance = choices.verification_relevance
        if isinstance(edit, Mapping):
            edit_path = edit.get("path")
            if (
                isinstance(edit_path, str)
                and edit_path
                and not self.index.is_current(edit_path)
            ):
                edit = None
                structural_owner = None
                ambiguous = True
                ambiguity_reason = "stale-edit-evidence"
                verification_relevance = verification_without_edit_owner(
                    str(choices.verify.get("path") or "")
                    if isinstance(choices.verify, Mapping)
                    else ""
                )
        return _TaskActionFinalState(
            edit=edit,
            verify=choices.verify,
            contract=choices.contract,
            structural_owner=structural_owner,
            verification_relevance=verification_relevance,
            ambiguity_state=ambiguity,
            competing=competing,
            ambiguous=ambiguous,
            ambiguity_reason=ambiguity_reason,
        )

    @staticmethod
    def _task_action_first_role(
        rows: Sequence[dict[str, object]],
        role: str,
    ) -> dict[str, object] | None:
        return next(
            (row for row in rows if role in cast("Sequence[str]", row["roles"])), None
        )

    def _task_action_explicit_surface_selection(
        self,
        context: _TaskActionMapContext,
        edit: dict[str, object] | None,
        verify: dict[str, object] | None,
    ) -> tuple[
        dict[str, object] | None,
        dict[str, object] | None,
        bool,
        bool,
    ]:
        if TYPE_CHECKING:
            self = cast("RepositoryOwnership", self)
        explicit_surface_ambiguity = False
        explicit_edit_surface_selected = False
        if context.cues.explicit_test_edit:
            test_surface, test_surface_ambiguous = self._projected_task_surface(
                RepositoryDomain.TEST, context.projection_state
            )
            if test_surface is not None and not test_surface_ambiguous:
                test_surface = {
                    **test_surface,
                    "explicit_target_basis": "explicit-test-edit",
                    "roles": list(
                        dict.fromkeys(
                            [
                                *cast("Sequence[str]", test_surface.get("roles", [])),
                                "edit",
                                "verify",
                            ]
                        )
                    ),
                }
                edit = test_surface
                verify = test_surface
                explicit_edit_surface_selected = True
            elif test_surface_ambiguous:
                explicit_surface_ambiguity = True

        explicit_build_tuning = bool(
            context.cue_words.intersection({"batch", "batches", "shard", "shards"})
            and context.cue_words.intersection(
                {"size", "workers", "timeout", "timeouts"}
            )
        )
        if explicit_build_tuning:
            build_surface, build_surface_ambiguous = self._projected_task_surface(
                RepositoryDomain.BUILD, context.projection_state
            )
            if build_surface is not None and not build_surface_ambiguous:
                edit = {
                    **build_surface,
                    "roles": list(
                        dict.fromkeys(
                            [
                                *cast("Sequence[str]", build_surface.get("roles", [])),
                                "edit",
                                "related",
                            ]
                        )
                    ),
                }
                explicit_edit_surface_selected = True
            elif build_surface_ambiguous:
                explicit_surface_ambiguity = True
        return (
            edit,
            verify,
            explicit_surface_ambiguity,
            explicit_edit_surface_selected,
        )

    def _task_action_verification_surface(
        self,
        task: str,
        context: _TaskActionMapContext,
        edit: dict[str, object] | None,
        verify: dict[str, object] | None,
        explicit_edit_surface_selected: bool,
        limit: int,
    ) -> tuple[
        dict[str, object] | None,
        dict[str, object] | None,
        Sequence[str],
        StructuralOwnerResolution | None,
        bool,
    ]:
        if TYPE_CHECKING:
            self = cast("RepositoryOwnership", self)
        verification_anchor_tokens = self._task_identifier_anchor_tokens(task)
        if verification_anchor_tokens:
            local_verify = self._task_identifier_verification_row(
                context.rows, verification_anchor_tokens
            )
            if local_verify is not None:
                verify = local_verify
                if (
                    context.cues.explicit_test_edit
                    and not explicit_edit_surface_selected
                ):
                    edit = {
                        **local_verify,
                        "explicit_target_basis": "explicit-test-edit",
                    }
                    explicit_edit_surface_selected = True

        literal_reference_owner: StructuralOwnerResolution | None = None
        if (
            "sql" in context.cue_words
            and isinstance(verify, dict)
            and verify.get("path")
        ):
            sql_edit, literal_reference_owner = self._literal_sql_reference_projection(
                verify, context.rows, limit
            )
            if sql_edit is not None:
                edit = sql_edit
        return (
            edit,
            verify,
            verification_anchor_tokens,
            literal_reference_owner,
            explicit_edit_surface_selected,
        )

    def _task_action_config_surface(
        self,
        task: str,
        context: _TaskActionMapContext,
        edit: dict[str, object] | None,
        verify: dict[str, object] | None,
        explicit_edit_surface_selected: bool,
        limit: int,
    ) -> tuple[dict[str, object] | None, bool, bool]:
        if TYPE_CHECKING:
            self = cast("RepositoryOwnership", self)
        explicit_config_surface_request = bool(
            context.cue_words.intersection(context.strong_config_cues)
            or context.cues.explicit_policy_surface
        )
        if (
            not context.cue_words.intersection(
                context.strong_config_cues | {"policy", "schema", "invariant"}
            )
            or explicit_edit_surface_selected
        ):
            return edit, False, explicit_config_surface_request

        config_state = self._task_action_config_state(task, context.rows)
        anchor = self._task_action_config_anchor(context.rows, config_state)
        config_candidates = self._task_action_initial_config_candidates(
            context.rows, context.failed
        )
        source_anchor = self._verification_locality_source_anchor(
            task, verify, context.rows, limit
        )
        if source_anchor is None:
            source_anchor = self._task_action_fallback_config_source_anchor(
                context.rows, config_state
            )
        if source_anchor is not None:
            self._admit_config_locality_siblings(
                source_anchor,
                context.rows,
                config_candidates,
                context.failed,
                limit,
            )
        if anchor is None or not config_candidates:
            return edit, False, explicit_config_surface_request
        # Local siblings use the original term-frequency population. Their
        # admission supplies row text without reweighting the selected anchor.
        config_state.row_text.update(
            (id(row), self._task_action_discrimination_text(row))
            for row in config_candidates
            if id(row) not in config_state.row_text
        )
        local_config = self._local_config_for_anchor(
            anchor, config_candidates, config_state
        )
        if local_config is None:
            return edit, False, explicit_config_surface_request
        return local_config, True, explicit_config_surface_request

    def _task_action_initial_surface_selection(
        self,
        task: str,
        context: _TaskActionMapContext,
        limit: int,
    ) -> _TaskActionInitialSurfaceState:
        """Select explicit and task-local surfaces before ownership resolution."""
        if TYPE_CHECKING:
            self = cast("RepositoryOwnership", self)

        edit = self._task_action_first_role(context.rows, "edit")
        verify = self._task_action_first_role(context.rows, "verify")
        contract = self._task_action_first_role(context.rows, "contract")
        (
            edit,
            verify,
            explicit_surface_ambiguity,
            explicit_edit_surface_selected,
        ) = self._task_action_explicit_surface_selection(context, edit, verify)
        (
            edit,
            verify,
            verification_anchor_tokens,
            literal_reference_owner,
            explicit_edit_surface_selected,
        ) = self._task_action_verification_surface(
            task,
            context,
            edit,
            verify,
            explicit_edit_surface_selected,
            limit,
        )
        (
            edit,
            localized_config_edit,
            explicit_config_surface_request,
        ) = self._task_action_config_surface(
            task,
            context,
            edit,
            verify,
            explicit_edit_surface_selected,
            limit,
        )
        return _TaskActionInitialSurfaceState(
            edit=edit,
            verify=verify,
            contract=contract,
            explicit_surface_ambiguity=explicit_surface_ambiguity,
            explicit_edit_surface_selected=explicit_edit_surface_selected,
            verification_anchor_tokens=verification_anchor_tokens,
            literal_reference_owner=literal_reference_owner,
            localized_config_edit=localized_config_edit,
            explicit_config_surface_request=explicit_config_surface_request,
        )

    def _task_action_identifier_ambiguity(
        self,
        context: _TaskActionMapContext,
        selection: _TaskActionSelectionState,
        choices: _TaskActionProjectionChoices,
    ) -> tuple[bool, bool, bool]:
        if TYPE_CHECKING:
            self = cast("RepositoryOwnership", self)
        identifier_edit_candidates = self._task_action_identifier_edit_candidates(
            context.rows,
            context.failed,
            selection.discrimination,
            selection.verification_anchor_tokens,
        )
        identifier_edit_paths = {
            str(row.get("path") or "") for row in identifier_edit_candidates
        }
        exact_identifier_path_set = {
            str(path) for path in selection.exact_identifier_paths if path
        }
        exact_identifier_ambiguity = len(exact_identifier_path_set) > 1
        explicit_field_contract = self._task_action_explicit_field_contract(
            choices.edit,
            selection.verification_anchor_tokens,
            context.cue_words,
        )
        decisive_qualified_verification = (
            self._task_action_decisive_qualified_verification(
                choices.verification_relevance,
                bool(
                    choices.verification_relevance.get("qualified_identity_ambiguous")
                ),
            )
        )
        explicit_identifier_surface = bool(
            selection.explicit_edit_surface_selected
            or selection.localized_config_edit
            or selection.explicit_config_surface_request
            or context.cues.explicit_architecture_contract
            or explicit_field_contract
            or selection.owner_basis
            in {
                "literal-path",
                "qualified-symbol",
                "unique-exact-symbol",
                "exact-symbol",
                "exact-import-owner",
            }
        )
        multi_identifier_edit_ambiguity = (
            self._task_action_multi_identifier_edit_ambiguity(
                identifier_edit_paths,
                selection.structural_owner,
                decisive_qualified_verification,
                explicit_identifier_surface,
            )
        )
        return (
            exact_identifier_ambiguity,
            multi_identifier_edit_ambiguity,
            decisive_qualified_verification,
        )

    def _task_action_weak_contract_ambiguity(
        self,
        context: _TaskActionMapContext,
        selection: _TaskActionSelectionState,
        choices: _TaskActionProjectionChoices,
        decisive_qualified_verification: bool,
    ) -> bool:
        if TYPE_CHECKING:
            self = cast("RepositoryOwnership", self)
        repository_rare_anchor = self._task_action_repository_rare_anchor(
            context.projection_state,
            selection.discrimination.task_terms,
        )
        explicit_surface_selected = bool(
            selection.explicit_edit_surface_selected
            or selection.localized_config_edit
            or context.cues.explicit_architecture_contract
            or context.cues.explicit_policy_surface
        )
        return self._task_action_weak_contract_anchor_ambiguity(
            choices.edit,
            selection.verification_anchor_tokens,
            selection.structural_owner,
            explicit_surface_selected,
            repository_rare_anchor,
            decisive_qualified_verification,
        )

    def _task_action_local_owner_ambiguity_evidence(
        self,
        task: str,
        context: _TaskActionMapContext,
        selection: _TaskActionSelectionState,
        limit: int,
    ) -> tuple[dict[str, dict[str, object]], list[dict[str, object]]]:
        del task, context, limit
        starts = selection.structural_starts
        if starts.get("status") != "observed" or selection.localized_config_edit:
            return {}, []
        owners: dict[str, dict[str, object]] = {
            str(path): {"path": str(path)}
            for path in cast("Sequence[str]", starts.get("observed_owners") or [])
        }
        origins: list[dict[str, object]] = [
            {
                "path": str(row["start_path"]),
                "owner_path": str(row["observed_owner"]),
                "canonical_rank": int(
                    cast("int | str", row.get("canonical_rank") or 0)
                ),
            }
            for row in cast(
                "Sequence[Mapping[str, object]]", starts.get("candidates") or []
            )
            if "verify" in cast("Sequence[str]", row.get("roles", []))
            and row.get("observed_owner")
        ]
        return owners, origins

    @staticmethod
    def _task_action_exact_identifier_search_incomplete(
        selection: _TaskActionSelectionState,
    ) -> bool:
        return bool(
            selection.exact_identifier_search_complete is False
            and selection.owner_basis != "literal-path"
        )

    @staticmethod
    def _task_action_structural_search_incomplete(
        selection: _TaskActionSelectionState,
    ) -> bool:
        starts = selection.structural_starts
        return bool(
            starts.get("status") == "observed"
            and not starts.get("observation_complete")
        )

    def _task_action_projection_ambiguity_state(
        self,
        task: str,
        context: _TaskActionMapContext,
        selection: _TaskActionSelectionState,
        choices: _TaskActionProjectionChoices,
        bounds: tuple[int, int],
    ) -> dict[str, object]:
        """Resolve ambiguity from already-selected task-action evidence.

        This stage performs discrimination only. It does not discover paths,
        rerank canonical task evidence, or acquire a new ownership authority.
        """
        if TYPE_CHECKING:
            self = cast("RepositoryOwnership", self)
        limit, per_role = bounds
        (
            task_local_structural_owners,
            task_local_verification_origins,
        ) = self._task_action_local_owner_ambiguity_evidence(
            task, context, selection, limit
        )
        multi_structural_owner_ambiguity = len(task_local_structural_owners) > 1
        competing = self._task_action_competing_rows(choices.edit, context.rows)
        # Unqualified production callers cannot veto an independently observed
        # owner. Keep the aggregate check below when verification discriminates
        # owners: unresolved callers still prevent proof of verifier uniqueness.
        verifier_identity_ambiguity = bool(
            choices.verification_relevance.get(
                "verifier_identity_ambiguous",
                choices.verification_relevance.get("qualified_identity_ambiguous"),
            )
        )
        (
            exact_identifier_ambiguity,
            multi_identifier_edit_ambiguity,
            decisive_qualified_verification,
        ) = self._task_action_identifier_ambiguity(
            context,
            selection,
            choices,
        )
        weak_contract_anchor_ambiguity = self._task_action_weak_contract_ambiguity(
            context,
            selection,
            choices,
            decisive_qualified_verification,
        )
        exact_search_incomplete = self._task_action_exact_identifier_search_incomplete(
            selection
        )
        structural_search_incomplete = self._task_action_structural_search_incomplete(
            selection
        )
        ambiguous = self._task_action_global_ambiguity(
            choices.edit,
            competing,
            selection.structural_owner,
            selection.localized_config_edit,
            bool(
                selection.owner_basis
                in {
                    "literal-path",
                    "qualified-symbol",
                    "unique-exact-symbol",
                    "exact-symbol",
                    "exact-import-owner",
                }
            ),
            (
                selection.explicit_surface_ambiguity,
                exact_identifier_ambiguity,
                multi_identifier_edit_ambiguity,
                weak_contract_anchor_ambiguity,
                exact_search_incomplete,
                multi_structural_owner_ambiguity,
                structural_search_incomplete,
                verifier_identity_ambiguity,
            ),
        )
        return {
            "ambiguous": ambiguous,
            "reason": self._task_action_ambiguity_reason(
                choices.edit,
                (
                    (
                        "ambiguous-explicit-task-surface",
                        selection.explicit_surface_ambiguity,
                    ),
                    ("weak-task-anchor", weak_contract_anchor_ambiguity),
                    (
                        "exact-identifier-search-bounded",
                        exact_search_incomplete,
                    ),
                    (
                        "multiple-task-local-structural-owners",
                        multi_structural_owner_ambiguity,
                    ),
                    (
                        "unresolved-qualified-import-identity",
                        verifier_identity_ambiguity,
                    ),
                    (
                        "multiple-exact-identifier-edit-owners",
                        exact_identifier_ambiguity,
                    ),
                    (
                        "multiple-identifier-edit-owners",
                        multi_identifier_edit_ambiguity,
                    ),
                    (
                        "structural-start-observation-incomplete",
                        structural_search_incomplete,
                    ),
                ),
                ambiguous,
            ),
            "candidates": self._task_action_ambiguity_candidates(
                choices.edit, competing, per_role
            ),
            "competing": competing,
            "structural_owners": task_local_structural_owners,
            "verification_origins": task_local_verification_origins,
            "multi_structural_owner_ambiguity": multi_structural_owner_ambiguity,
            "structural_search_incomplete": structural_search_incomplete,
            "exact_identifier_search_incomplete": exact_search_incomplete,
        }
