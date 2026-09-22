from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import TYPE_CHECKING, cast

from .decision_session import decision_scoped, diagnostic_producer
from .model import EvidenceVisibility
from .repository_domains import RepositoryDomain
from .task_action_owner_resolution import TaskActionOwnerResolutionMixin
from .task_action_types import (
    _TaskActionAmbiguityPayloadState,
    _TaskActionFinalState,
    _TaskActionInitialSurfaceState,
    _TaskActionMapContext,
    _TaskActionProjectionChoices,
    _TaskActionSelectionState,
)

if TYPE_CHECKING:
    from .engine import CodeMap


class TaskActionProjectionMixin(TaskActionOwnerResolutionMixin):
    @decision_scoped
    @diagnostic_producer
    def task_action_map(
        self,
        task: str,
        *,
        limit: int = 20,
        per_role: int = 3,
    ) -> dict[str, object]:
        """Translate canonical task evidence into worker actions without reranking it.

        ``find_task`` remains retrieval authority.  This projection classifies only
        already-retrieved paths into edit, verify, contract, inspect, and related
        roles, preserving canonical rank/provenance on every row.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._validate_task_action_limits(limit, per_role)
        action_key, cached = self._task_action_cache_lookup(task, limit, per_role)
        if cached is not None:
            return cached
        context = self._task_action_map_context(task, limit)
        selection = self._task_action_surface_owner_state(
            task, context, limit, per_role
        )
        choices = self._task_action_projection_choices(task, context, selection, limit)
        final = self._task_action_final_state(
            task, context, selection, choices, (limit, per_role)
        )
        result = self._task_action_projection_result(
            task, context, selection, final, (limit, per_role)
        )
        self._task_action_record_result(task, limit, action_key, result)
        return result

    def _task_action_cache_lookup(
        self, task: str, limit: int, per_role: int
    ) -> tuple[tuple[int, str, int, int] | None, dict[str, object] | None]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if self._decision_session_depth <= 0:
            return None, None
        generation = int(self._decision_session_generation or self.store.generation())
        action_key = (generation, task, int(limit), int(per_role))
        cached = self._decision_task_action_cache.get(action_key)
        if cached is not None:
            self._decision_session_stats["task_action_hit"] += 1
            return action_key, deepcopy(cached)
        self._decision_session_stats["task_action_miss"] += 1
        return action_key, None

    def _task_action_map_context(self, task: str, limit: int) -> _TaskActionMapContext:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        failed: set[str] = set()
        hits = [
            hit
            for hit in self.find_task(task, limit=limit)
            if hit.evidence_visibility is not EvidenceVisibility.DENY
        ]
        cues = self._task_action_cues(task)
        strong_config_cues = self._strong_config_cues()
        rows = [
            self._task_action_row(hit, rank, failed, cues, strong_config_cues)
            for rank, hit in enumerate(hits, 1)
        ]
        self._session_preload_symbols([str(row.get("path") or "") for row in rows])
        return _TaskActionMapContext(
            hits=hits,
            rows=rows,
            failed=failed,
            cues=cues,
            cue_words=set(cues.words),
            strong_config_cues=strong_config_cues,
            strong_contract_cues=self._strong_contract_cues(),
            strong_authority_cues=self._strong_authority_cues(),
            projection_state=self._task_action_projection_state(task, rows, limit),
        )

    def _task_action_surface_owner_state(
        self,
        task: str,
        context: _TaskActionMapContext,
        limit: int,
        per_role: int,
    ) -> _TaskActionSelectionState:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        surface = self._task_action_initial_surface_selection(task, context, limit)
        discrimination = self._task_action_discrimination_state(task, context.rows)
        owner = self._task_action_resolve_owner(
            task=task,
            hits=context.hits,
            rows=context.rows,
            failed=context.failed,
            edit=surface.edit,
            verify=surface.verify,
            discrimination=discrimination,
            verification_anchor_tokens=surface.verification_anchor_tokens,
            literal_reference_owner=cast(
                "dict[str, object] | None", surface.literal_reference_owner
            ),
            localized_config_edit=surface.localized_config_edit,
            explicit_config_surface_request=bool(
                surface.explicit_config_surface_request
            ),
            explicit_edit_surface_selected=bool(surface.explicit_edit_surface_selected),
            limit=limit,
        )
        return _TaskActionSelectionState(
            edit=owner.edit,
            verify=surface.verify,
            contract=surface.contract,
            discrimination=discrimination,
            explicit_surface_ambiguity=surface.explicit_surface_ambiguity,
            explicit_edit_surface_selected=bool(surface.explicit_edit_surface_selected),
            verification_anchor_tokens=cast(
                "Sequence[str]", surface.verification_anchor_tokens
            ),
            localized_config_edit=surface.localized_config_edit,
            explicit_config_surface_request=bool(
                surface.explicit_config_surface_request
            ),
            owner_basis=owner.basis,
            structural_owner=owner.structural_owner,
            structural_owner_origin=owner.structural_owner_origin,
            archive_live_owner_ambiguity=owner.archive_live_owner_ambiguity,
            exact_identifier_paths=owner.exact_identifier_paths,
            inspect_rows=[row for row in context.rows if "inspect" in row["roles"]][
                :per_role
            ],
            related_rows=[row for row in context.rows if "related" in row["roles"]][
                :per_role
            ],
        )

    def _task_action_promoted_edit(
        self,
        context: _TaskActionMapContext,
        selection: _TaskActionSelectionState,
    ) -> dict[str, object] | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
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
            self = cast("CodeMap", self)
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

    def _task_action_projection_choices(
        self,
        task: str,
        context: _TaskActionMapContext,
        selection: _TaskActionSelectionState,
        limit: int,
    ) -> _TaskActionProjectionChoices:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        edit = self._task_action_promoted_edit(context, selection)
        contract = self._task_action_local_contract(selection, edit)
        verification_relevance = self._verification_relevance(
            task,
            edit=edit,
            current_verify=selection.verify,
            rows=context.rows,
            limit=8,
        )
        verify = self._task_action_finalize_verification_selection(
            verification_relevance.get("selected"), context.rows, limit
        )
        return _TaskActionProjectionChoices(
            edit=edit,
            verify=verify if verify is not None else selection.verify,
            contract=contract,
            verification_relevance=verification_relevance,
        )

    def _task_action_final_state(
        self,
        task: str,
        context: _TaskActionMapContext,
        selection: _TaskActionSelectionState,
        choices: _TaskActionProjectionChoices,
        bounds: tuple[int, int],
    ) -> _TaskActionFinalState:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
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
                and not self._indexed_path_current(edit_path)
            ):
                edit = None
                structural_owner = None
                ambiguous = True
                ambiguity_reason = "stale-edit-evidence"
                verification_relevance = self._verification_without_edit_owner(
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

    def _task_action_projection_result(
        self,
        task: str,
        context: _TaskActionMapContext,
        selection: _TaskActionSelectionState,
        final: _TaskActionFinalState,
        bounds: tuple[int, int],
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        limit, per_role = bounds
        return {
            "schema": "hashmarks.task-action-map.v1",
            "task": task,
            "edit": final.edit,
            "verify": final.verify,
            "contract": final.contract,
            "inspect": selection.inspect_rows,
            "related": selection.related_rows,
            "ownership_resolution": final.structural_owner,
            "owner_basis": selection.owner_basis,
            **self._task_action_ownership_payload_fields(
                final.edit,
                final.competing[:per_role],
                final.structural_owner,
                final.ambiguous,
                final.ambiguity_reason,
            ),
            "verification_relevance": final.verification_relevance,
            "ambiguity": self._task_action_ambiguity_payload(
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
            "canonical": [hit.as_dict() for hit in context.hits],
            "bounds": self._task_action_bounds_payload(limit, per_role),
            "ranking_effect": "none",
            "discovery_effect": self._task_action_discovery_effect(
                final.verification_relevance
            ),
        }

    def _task_action_record_result(
        self,
        task: str,
        limit: int,
        action_key: tuple[int, str, int, int] | None,
        result: dict[str, object],
    ) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        authority_paths = {
            str(row.get("path"))
            for row in (
                result.get("edit"),
                result.get("verify"),
                result.get("ownership_resolution"),
            )
            if isinstance(row, Mapping) and row.get("path")
        }
        generation = self.store.generation()
        self._task_authority_paths_cache[(generation, task, int(limit))] = tuple(
            sorted(authority_paths)
        )
        recent_key = (task, int(limit))
        previous_authority_paths = self._task_recent_authority_paths.get(recent_key, ())
        self._task_recent_authority_paths[recent_key] = tuple(
            sorted({*previous_authority_paths, *authority_paths})
        )
        if len(self._task_recent_authority_paths) > 256:
            self._task_recent_authority_paths.clear()
        if action_key is not None:
            self._decision_task_action_cache[action_key] = deepcopy(result)

    @staticmethod
    def _task_action_first_role(
        rows: Sequence[dict[str, object]],
        role: str,
    ) -> dict[str, object] | None:
        return next((row for row in rows if role in row["roles"]), None)

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
                            [*test_surface.get("roles", []), "edit", "verify"]
                        )
                    ),
                }
                edit = test_surface
                verify = test_surface
                explicit_edit_surface_selected = True
            elif test_surface_ambiguous:
                explicit_surface_ambiguity = True

        explicit_build_tuning = bool(
            context.cue_words.intersection({"pytest", "test", "tests"})
            and context.cue_words.intersection({"batch", "batches", "shard", "shards"})
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
                            [*build_surface.get("roles", []), "edit", "related"]
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
        dict[str, object] | None,
        bool,
    ]:
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

        literal_reference_owner: dict[str, object] | None = None
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
            self = cast("CodeMap", self)

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
        ambiguity_flags: tuple[bool, bool, bool],
    ) -> tuple[bool, bool, bool]:
        (
            archive_live_owner_ambiguity,
            multi_structural_owner_ambiguity,
            verification_identity_ambiguity,
        ) = ambiguity_flags
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
                verification_identity_ambiguity,
            )
        )
        explicit_identifier_surface = bool(
            selection.explicit_edit_surface_selected
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
                ambiguity_flags,
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
        if selection.structural_owner is None or selection.localized_config_edit:
            return {}, []
        return self._task_action_local_structural_owner_evidence(
            task,
            context.rows,
            context.failed,
            selection.discrimination,
            limit,
            selection.structural_owner_origin,
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
            self = cast("CodeMap", self)
        limit, per_role = bounds
        (
            task_local_structural_owners,
            task_local_verification_origins,
        ) = self._task_action_local_owner_ambiguity_evidence(
            task, context, selection, limit
        )
        multi_structural_owner_ambiguity = len(task_local_structural_owners) > 1

        competing = self._task_action_competing_rows(choices.edit, context.rows)
        verification_identity_ambiguity = bool(
            choices.verification_relevance.get("qualified_identity_ambiguous")
        )
        ambiguity_flags = (
            selection.archive_live_owner_ambiguity,
            multi_structural_owner_ambiguity,
            verification_identity_ambiguity,
        )
        (
            exact_identifier_ambiguity,
            multi_identifier_edit_ambiguity,
            decisive_qualified_verification,
        ) = self._task_action_identifier_ambiguity(
            context,
            selection,
            choices,
            ambiguity_flags,
        )
        weak_contract_anchor_ambiguity = self._task_action_weak_contract_ambiguity(
            context,
            selection,
            choices,
            decisive_qualified_verification,
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
                selection.archive_live_owner_ambiguity,
                multi_structural_owner_ambiguity,
                verification_identity_ambiguity,
            ),
        )
        reason = self._task_action_ambiguity_reason(
            choices.edit,
            (
                (
                    "ambiguous-explicit-task-surface",
                    selection.explicit_surface_ambiguity,
                ),
                ("weak-task-anchor", weak_contract_anchor_ambiguity),
                (
                    "multiple-live-owners-behind-archive-hit",
                    selection.archive_live_owner_ambiguity,
                ),
                (
                    "multiple-task-local-structural-owners",
                    multi_structural_owner_ambiguity,
                ),
                (
                    "unresolved-qualified-import-identity",
                    verification_identity_ambiguity,
                ),
                ("multiple-exact-identifier-edit-owners", exact_identifier_ambiguity),
                ("multiple-identifier-edit-owners", multi_identifier_edit_ambiguity),
            ),
            ambiguous,
        )
        return {
            "ambiguous": ambiguous,
            "reason": reason,
            "candidates": self._task_action_ambiguity_candidates(
                choices.edit, competing, per_role
            ),
            "competing": competing,
            "structural_owners": task_local_structural_owners,
            "verification_origins": task_local_verification_origins,
            "multi_structural_owner_ambiguity": multi_structural_owner_ambiguity,
        }
