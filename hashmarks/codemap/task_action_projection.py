from __future__ import annotations

from copy import deepcopy

from .decision_session import decision_scoped, diagnostic_producer
from typing import Mapping, Sequence

from .repository_domains import RepositoryDomain
from .task_action_types import _TaskActionAmbiguityPayloadState


class TaskActionProjectionMixin:
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
        self._validate_task_action_limits(limit, per_role)
        action_key = None
        if self._decision_session_depth > 0:
            generation = int(self._decision_session_generation or self.store.generation())
            action_key = (generation, task, int(limit), int(per_role))
            cached = self._decision_task_action_cache.get(action_key)
            if cached is not None:
                self._decision_session_stats["task_action_hit"] += 1
                return deepcopy(cached)
            self._decision_session_stats["task_action_miss"] += 1
        failed: set[str] = set()
        hits = self.find_task(task, limit=limit)
        cues = self._task_action_cues(task)
        cue_words = set(cues.words)
        explicit_test_edit = cues.explicit_test_edit
        explicit_policy_surface = cues.explicit_policy_surface
        explicit_architecture_contract = cues.explicit_architecture_contract
        strong_config_cues = self._strong_config_cues()
        strong_contract_cues = self._strong_contract_cues()
        strong_authority_cues = self._strong_authority_cues()
        rows = [
            self._task_action_row(hit, rank, failed, cues, strong_config_cues)
            for rank, hit in enumerate(hits, 1)
        ]

        self._session_preload_symbols([str(row.get("path") or "") for row in rows])

        projection_state = self._task_action_projection_state(task, rows, limit)

        surface_state = self._task_action_initial_surface_selection(
            task=task,
            rows=rows,
            failed=failed,
            projection_state=projection_state,
            cues=cues,
            cue_words=cue_words,
            strong_config_cues=strong_config_cues,
            limit=limit,
        )
        edit = surface_state["edit"]
        verify = surface_state["verify"]
        contract = surface_state["contract"]
        explicit_surface_ambiguity = bool(surface_state["explicit_surface_ambiguity"])
        explicit_edit_surface_selected = bool(surface_state["explicit_edit_surface_selected"])
        verification_anchor_tokens = surface_state["verification_anchor_tokens"]
        literal_reference_owner = surface_state["literal_reference_owner"]
        localized_config_edit = bool(surface_state["localized_config_edit"])
        explicit_config_surface_request = bool(surface_state["explicit_config_surface_request"])

        # Task-local discrimination helpers are shared by every ownership path,
        # including literal-reference owners that intentionally bypass the normal
        # structural-owner discovery branch. Keep them in common scope so later
        # ambiguity checks cannot depend on which owner mechanism succeeded.
        discrimination = self._task_action_discrimination_state(task, rows)
        owner_state = self._task_action_resolve_structural_owner(
            task=task,
            hits=hits,
            rows=rows,
            failed=failed,
            edit=edit,
            verify=verify,
            discrimination=discrimination,
            verification_anchor_tokens=verification_anchor_tokens,
            literal_reference_owner=literal_reference_owner,
            localized_config_edit=localized_config_edit,
            explicit_config_surface_request=explicit_config_surface_request,
            explicit_edit_surface_selected=explicit_edit_surface_selected,
            limit=limit,
        )
        edit = owner_state["edit"]
        structural_owner = owner_state["structural_owner"]
        structural_owner_origin = owner_state.get("structural_owner_origin")
        archive_live_owner_ambiguity = bool(owner_state["archive_live_owner_ambiguity"])
        exact_identifier_paths = tuple(owner_state.get("exact_identifier_paths") or ())
        exact_identifier_displacement_guard = bool(
            owner_state.get("exact_identifier_displacement_guard")
        )
        exact_identifier_surface_selected = bool(
            owner_state.get("exact_identifier_surface_selected")
        )
        inspect_rows = [row for row in rows if "inspect" in row["roles"]][:per_role]
        related_rows = [row for row in rows if "related" in row["roles"]][:per_role]

        # Explicit route evidence can make configuration or contract the primary
        # action even when an implementation surface ranks earlier.  This never
        # introduces a path that find_task did not retrieve.
        current_edit_has_identifier_anchor = (
            self._task_action_current_edit_has_identifier_anchor(
                edit, discrimination, verification_anchor_tokens
            )
        )
        promote_contract_surface = self._task_action_should_promote_contract_surface(
            current_edit_has_identifier_anchor,
            explicit_policy_surface,
            explicit_architecture_contract,
            cue_words,
            strong_config_cues,
            strong_contract_cues | strong_authority_cues,
        )
        if (
            structural_owner is None
            and not localized_config_edit
            and not explicit_edit_surface_selected
            and promote_contract_surface
        ):
            contract_edit = self._task_action_contract_edit_candidate(rows, failed)
            if contract_edit is not None:
                edit = contract_edit

        # Once a distinctive identifier-shaped task token has localized edit and
        # verification, keep contract evidence only when it shares task locality.
        if (
            verification_anchor_tokens
            and isinstance(contract, dict)
            and not self._task_action_contract_is_local(contract, edit, verify)
        ):
            contract = None

        verification_relevance = self._verification_relevance(
            task,
            edit=edit,
            current_verify=verify,
            rows=rows,
            limit=8,
        )
        selected_verification = verification_relevance.get("selected")
        finalized_verification = self._task_action_finalize_verification_selection(
            selected_verification, rows, limit
        )
        if finalized_verification is not None:
            verify = finalized_verification

        ambiguity_state = self._task_action_projection_ambiguity_state(
            task=task,
            rows=rows,
            failed=failed,
            discrimination=discrimination,
            projection_state=projection_state,
            edit=edit,
            structural_owner=structural_owner,
            structural_owner_origin=structural_owner_origin,
            localized_config_edit=localized_config_edit,
            verification_anchor_tokens=verification_anchor_tokens,
            verification_relevance=verification_relevance,
            cue_words=cue_words,
            explicit_edit_surface_selected=explicit_edit_surface_selected,
            explicit_architecture_contract=explicit_architecture_contract,
            explicit_policy_surface=explicit_policy_surface,
            explicit_surface_ambiguity=explicit_surface_ambiguity,
            archive_live_owner_ambiguity=archive_live_owner_ambiguity,
            exact_identifier_paths=exact_identifier_paths,
            exact_identifier_displacement_guard=exact_identifier_displacement_guard,
            exact_identifier_surface_selected=exact_identifier_surface_selected,
            limit=limit,
            per_role=per_role,
        )
        competing = ambiguity_state["competing"]
        ambiguous = bool(ambiguity_state["ambiguous"])
        ambiguity_reason = ambiguity_state["reason"]
        # Structural projection can rediscover an owner through stale durable edges
        # even after retrieval correctly filtered changed workspace bytes. Never let
        # that stale path regain safe-to-edit authority.
        if isinstance(edit, Mapping):
            edit_path = edit.get("path")
            if isinstance(edit_path, str) and edit_path and not self._indexed_path_current(edit_path):
                edit = None
                structural_owner = None
                ambiguous = True
                ambiguity_reason = "stale-edit-evidence"
                verification_relevance = self._verification_without_edit_owner(
                    str(verify.get("path") or "") if isinstance(verify, Mapping) else ""
                )
        result = {
            "schema": "hashmarks.task-action-map.v1",
            "task": task,
            "edit": edit,
            "verify": verify,
            "contract": contract,
            "inspect": inspect_rows,
            "related": related_rows,
            "ownership_resolution": structural_owner,
            **self._task_action_ownership_payload_fields(
                edit,
                competing[:per_role],
                structural_owner,
                ambiguous,
                ambiguity_reason,
            ),
            "verification_relevance": verification_relevance,
            "ambiguity": self._task_action_ambiguity_payload(
                _TaskActionAmbiguityPayloadState(
                    ambiguous=ambiguous,
                    reason=ambiguity_reason,
                    candidates=ambiguity_state["candidates"],
                    alternatives=competing[:per_role],
                    structural_owners=ambiguity_state["structural_owners"],
                    verification_origins=ambiguity_state["verification_origins"],
                    multi_structural_owner_ambiguity=bool(
                        ambiguity_state["multi_structural_owner_ambiguity"]
                    ),
                )
            ),
            "canonical": [hit.as_dict() for hit in hits],
            "bounds": self._task_action_bounds_payload(limit, per_role),
            "ranking_effect": "none",
            "discovery_effect": self._task_action_discovery_effect(
                verification_relevance
            ),
        }
        authority_paths = {
            str(row.get("path"))
            for row in (edit, verify, structural_owner)
            if isinstance(row, Mapping) and row.get("path")
        }
        self._task_authority_paths_cache[
            (self.store.generation(), task, int(limit))
        ] = tuple(sorted(authority_paths))
        recent_key = (task, int(limit))
        previous_authority_paths = self._task_recent_authority_paths.get(recent_key, ())
        self._task_recent_authority_paths[recent_key] = tuple(sorted({
            *previous_authority_paths,
            *authority_paths,
        }))
        if len(self._task_recent_authority_paths) > 256:
            self._task_recent_authority_paths.clear()
        if action_key is not None:
            self._decision_task_action_cache[action_key] = deepcopy(result)
        return result

    def _task_action_resolve_structural_owner(
        self,
        *,
        task: str,
        hits: Sequence[object],
        rows: list[dict[str, object]],
        failed: set[str],
        edit: dict[str, object] | None,
        verify: dict[str, object] | None,
        discrimination: object,
        verification_anchor_tokens: object,
        literal_reference_owner: dict[str, object] | None,
        localized_config_edit: bool,
        explicit_config_surface_request: bool,
        explicit_edit_surface_selected: bool,
        limit: int,
    ) -> dict[str, object]:
        """Resolve the active implementation owner from existing repository evidence."""
        structural_owner = literal_reference_owner
        edit, archive_live_owner_ambiguity = self._task_action_archive_live_owner_choice(
            edit, rows, failed, discrimination, verification_anchor_tokens
        )
        edit_path = str(edit.get("path") or "") if isinstance(edit, dict) else ""
        task_path_tokens = {
            token.strip("`'\"()[]{}<>,:;").replace("\\", "/")
            for token in task.split()
        }
        literal_task_paths = tuple(dict.fromkeys(
            str(row.get("path") or "")
            for row in rows
            if row.get("path") and str(row.get("path") or "") in task_path_tokens
        ))
        literal_task_path = literal_task_paths[0] if len(literal_task_paths) == 1 else ""
        exact_identifier_edits: list[dict[str, object]] = []
        if (
            structural_owner is None
            and not localized_config_edit
            and not explicit_config_surface_request
            and not explicit_edit_surface_selected
        ):
            exact_identifier_edits = self._task_action_exact_identifier_edit_candidates(
                task, rows, failed
            )
            if literal_task_path:
                exact_identifier_edits = [
                    row for row in exact_identifier_edits
                    if str(row.get("path") or "") == literal_task_path
                ]
            if len(exact_identifier_edits) == 1:
                edit = exact_identifier_edits[0]
        exact_identifier_surface_selected = bool(
            len(exact_identifier_edits) == 1
            and str(exact_identifier_edits[0].get("signature") or "")
            .lstrip()
            .startswith(("def ", "async def "))
        )
        exact_identifier_paths = tuple(sorted({
            str(row.get("path") or "") for row in exact_identifier_edits
            if row.get("path")
        }))
        selected_edit_path = (
            str(edit.get("path") or "") if isinstance(edit, dict) else ""
        )
        literal_edit_path = bool(
            literal_task_path and selected_edit_path == literal_task_path
        )
        exact_identifier_displacement_guard = False
        should_resolve = (
            structural_owner is None
            and not localized_config_edit
            and not explicit_config_surface_request
            and not explicit_edit_surface_selected
            and not literal_edit_path
        )
        if not should_resolve:
            return {
                "edit": edit,
                "structural_owner": structural_owner,
                "structural_owner_origin": None,
                "archive_live_owner_ambiguity": archive_live_owner_ambiguity,
                "exact_identifier_paths": exact_identifier_paths,
                "exact_identifier_displacement_guard": exact_identifier_displacement_guard,
                "exact_identifier_surface_selected": exact_identifier_surface_selected,
            }

        task_specific = self._task_action_specific_entry_candidate(
            task, rows, discrimination
        )
        task_local_island = self._task_action_local_island(task, hits, limit)
        verify_path = (
            str(verify.get("path"))
            if isinstance(verify, dict) and verify.get("path")
            else ""
        )
        owner_start = (
            verify_path
            if task_local_island and verify_path
            else str(task_specific.get("path"))
            if isinstance(task_specific, dict) and task_specific.get("path")
            else None
        )
        go_entry = self._task_action_go_entry(
            verify_path, rows, discrimination, task_local_island
        )
        if go_entry is not None:
            owner_start = str(go_entry["path"])
        if owner_start is None:
            owner_start = verify_path or None
        if owner_start is None and isinstance(edit, dict) and edit.get("path"):
            owner_start = str(edit["path"])
        if not owner_start:
            return {
                "edit": edit,
                "structural_owner": structural_owner,
                "structural_owner_origin": None,
                "archive_live_owner_ambiguity": archive_live_owner_ambiguity,
                "exact_identifier_paths": exact_identifier_paths,
                "exact_identifier_displacement_guard": exact_identifier_displacement_guard,
                "exact_identifier_surface_selected": exact_identifier_surface_selected,
            }

        resolved = self._structural_owner_candidate(owner_start, max_depth=3, task=task)
        if resolved is None or str(resolved.get("path") or "") in failed:
            return {
                "edit": edit,
                "structural_owner": structural_owner,
                "structural_owner_origin": None,
                "archive_live_owner_ambiguity": archive_live_owner_ambiguity,
                "exact_identifier_paths": exact_identifier_paths,
                "exact_identifier_displacement_guard": exact_identifier_displacement_guard,
                "exact_identifier_surface_selected": exact_identifier_surface_selected,
            }
        owner_path = str(resolved["path"])
        if len(exact_identifier_paths) > 1:
            discriminated_exact_path = self._task_action_structural_exact_identifier_owner(
                resolved, exact_identifier_edits
            )
            if discriminated_exact_path is None:
                return {
                    "edit": edit,
                    "structural_owner": structural_owner,
                    "structural_owner_origin": None,
                    "archive_live_owner_ambiguity": archive_live_owner_ambiguity,
                    "exact_identifier_paths": exact_identifier_paths,
                    "exact_identifier_displacement_guard": exact_identifier_displacement_guard,
                    "exact_identifier_surface_selected": exact_identifier_surface_selected,
                }
            exact_identifier_paths = (discriminated_exact_path,)
        exact_identifier_path = (
            exact_identifier_paths[0] if len(exact_identifier_paths) == 1 else None
        )
        exact_identifier_displacement_guard = bool(
            exact_identifier_path and owner_path != exact_identifier_path
        )
        archive_owner = self._task_action_is_archive_path(owner_path)
        live_current_edit = self._task_action_live_current_edit(
            edit, discrimination, verification_anchor_tokens
        )
        if (
            not exact_identifier_displacement_guard
            and not (archive_owner and live_current_edit)
        ):
            edit = self._task_action_projected_owner_row(
                owner_path, resolved, rows, limit
            )
            structural_owner = self._task_action_structural_owner_evidence(
                resolved, owner_path
            )
        return {
            "edit": edit,
            "structural_owner": structural_owner,
            "structural_owner_origin": {
                "path": owner_start,
                "resolved": resolved,
            } if structural_owner is not None else None,
            "archive_live_owner_ambiguity": archive_live_owner_ambiguity,
            "exact_identifier_paths": exact_identifier_paths,
            "exact_identifier_displacement_guard": exact_identifier_displacement_guard,
            "exact_identifier_surface_selected": exact_identifier_surface_selected,
        }


    def _task_action_initial_surface_selection(
        self,
        *,
        task: str,
        rows: list[dict[str, object]],
        failed: set[str],
        projection_state: object,
        cues: object,
        cue_words: set[str],
        strong_config_cues: set[str],
        limit: int,
    ) -> dict[str, object]:
        """Select explicit and task-local surfaces before ownership resolution."""
        def first_for(role: str) -> dict[str, object] | None:
            for row in rows:
                if role in row["roles"]:
                    return row
            return None

        edit = first_for("edit")
        verify = first_for("verify")
        contract = first_for("contract")
        explicit_surface_ambiguity = False
        explicit_edit_surface_selected = False
        if cues.explicit_test_edit:
            test_surface, test_surface_ambiguous = self._projected_task_surface(
                RepositoryDomain.TEST, projection_state
            )
            if test_surface is not None and not test_surface_ambiguous:
                test_surface = {
                    **test_surface,
                    "roles": list(
                        dict.fromkeys([*test_surface.get("roles", []), "edit", "verify"])
                    ),
                }
                edit = test_surface
                verify = test_surface
                explicit_edit_surface_selected = True
            elif test_surface_ambiguous:
                explicit_surface_ambiguity = True

        explicit_build_tuning = bool(
            cue_words.intersection({"pytest", "test", "tests"})
            and cue_words.intersection({"batch", "batches", "shard", "shards"})
            and cue_words.intersection({"size", "workers", "timeout", "timeouts"})
        )
        if explicit_build_tuning:
            build_surface, build_surface_ambiguous = self._projected_task_surface(
                RepositoryDomain.BUILD, projection_state
            )
            if build_surface is not None and not build_surface_ambiguous:
                edit = {
                    **build_surface,
                    "roles": list(
                        dict.fromkeys([*build_surface.get("roles", []), "edit", "related"])
                    ),
                }
                explicit_edit_surface_selected = True
            elif build_surface_ambiguous:
                explicit_surface_ambiguity = True

        verification_anchor_tokens = self._task_identifier_anchor_tokens(task)
        if verification_anchor_tokens:
            local_verify = self._task_identifier_verification_row(
                rows, verification_anchor_tokens
            )
            if local_verify is not None:
                verify = local_verify
                if cues.explicit_test_edit and not explicit_edit_surface_selected:
                    edit = local_verify
                    explicit_edit_surface_selected = True

        literal_reference_owner: dict[str, object] | None = None
        if "sql" in cue_words and isinstance(verify, dict) and verify.get("path"):
            sql_edit, literal_reference_owner = self._literal_sql_reference_projection(
                verify, rows, limit
            )
            if sql_edit is not None:
                edit = sql_edit

        localized_config_edit = False
        explicit_config_surface_request = bool(
            cue_words.intersection(strong_config_cues) or cues.explicit_policy_surface
        )
        if (
            cue_words.intersection(strong_config_cues | {"policy", "schema", "invariant"})
            and not explicit_edit_surface_selected
        ):
            config_state = self._task_action_config_state(task, rows)
            anchor = self._task_action_config_anchor(rows, config_state)
            config_candidates = self._task_action_initial_config_candidates(rows, failed)
            source_anchor = self._verification_locality_source_anchor(
                task, verify, rows, limit
            )
            if source_anchor is None:
                source_anchor = self._task_action_fallback_config_source_anchor(
                    rows, config_state
                )
            if source_anchor is not None:
                self._admit_config_locality_siblings(
                    source_anchor, rows, config_candidates, failed, limit
                )
            if anchor is not None and config_candidates:
                local_config = self._local_config_for_anchor(
                    anchor, config_candidates, config_state
                )
                if local_config is not None:
                    edit = local_config
                    localized_config_edit = True

        return {
            "edit": edit,
            "verify": verify,
            "contract": contract,
            "explicit_surface_ambiguity": explicit_surface_ambiguity,
            "explicit_edit_surface_selected": explicit_edit_surface_selected,
            "verification_anchor_tokens": verification_anchor_tokens,
            "literal_reference_owner": literal_reference_owner,
            "localized_config_edit": localized_config_edit,
            "explicit_config_surface_request": explicit_config_surface_request,
        }


    def _task_action_projection_ambiguity_state(
        self,
        *,
        task: str,
        rows: list[dict[str, object]],
        failed: set[str],
        discrimination: object,
        projection_state: object,
        edit: dict[str, object] | None,
        structural_owner: dict[str, object] | None,
        structural_owner_origin: Mapping[str, object] | None,
        localized_config_edit: bool,
        verification_anchor_tokens: object,
        verification_relevance: Mapping[str, object],
        cue_words: set[str],
        explicit_edit_surface_selected: bool,
        explicit_architecture_contract: bool,
        explicit_policy_surface: bool,
        explicit_surface_ambiguity: bool,
        archive_live_owner_ambiguity: bool,
        exact_identifier_paths: Sequence[str],
        exact_identifier_displacement_guard: bool,
        exact_identifier_surface_selected: bool,
        limit: int,
        per_role: int,
    ) -> dict[str, object]:
        """Resolve ambiguity from already-selected task-action evidence.

        This stage performs discrimination only. It does not discover paths,
        rerank canonical task evidence, or acquire a new ownership authority.
        """
        task_local_structural_owners: dict[str, dict[str, object]] = {}
        task_local_verification_origins: list[dict[str, object]] = []
        if structural_owner is not None and not localized_config_edit:
            (
                task_local_structural_owners,
                task_local_verification_origins,
            ) = self._task_action_local_structural_owner_evidence(
                task, rows, failed, discrimination, limit, structural_owner_origin
            )
        multi_structural_owner_ambiguity = len(task_local_structural_owners) > 1

        competing = self._task_action_competing_rows(edit, rows)
        verification_identity_ambiguity = bool(
            verification_relevance.get("qualified_identity_ambiguous")
        )
        identifier_edit_candidates = self._task_action_identifier_edit_candidates(
            rows, failed, discrimination, verification_anchor_tokens
        )
        identifier_edit_paths = {
            str(row.get("path") or "") for row in identifier_edit_candidates
        }
        exact_identifier_path_set = {str(path) for path in exact_identifier_paths if path}
        exact_identifier_ambiguity = len(exact_identifier_path_set) > 1
        explicit_field_contract = self._task_action_explicit_field_contract(
            edit, verification_anchor_tokens, cue_words
        )
        decisive_qualified_verification = self._task_action_decisive_qualified_verification(
            verification_relevance, verification_identity_ambiguity
        )
        explicit_identifier_surface = bool(
            explicit_edit_surface_selected
            or explicit_architecture_contract
            or explicit_field_contract
            or exact_identifier_displacement_guard
            or exact_identifier_surface_selected
        )
        multi_identifier_edit_ambiguity = self._task_action_multi_identifier_edit_ambiguity(
            identifier_edit_paths,
            structural_owner,
            decisive_qualified_verification,
            explicit_identifier_surface,
            (
                archive_live_owner_ambiguity,
                multi_structural_owner_ambiguity,
                verification_identity_ambiguity,
            ),
        )

        repository_rare_anchor = self._task_action_repository_rare_anchor(
            projection_state, discrimination.task_terms
        )
        explicit_surface_selected = bool(
            explicit_edit_surface_selected
            or localized_config_edit
            or explicit_architecture_contract
            or explicit_policy_surface
        )
        weak_contract_anchor_ambiguity = self._task_action_weak_contract_anchor_ambiguity(
            edit,
            verification_anchor_tokens,
            structural_owner,
            explicit_surface_selected,
            repository_rare_anchor,
            decisive_qualified_verification,
        )
        ambiguous = self._task_action_global_ambiguity(
            edit,
            competing,
            structural_owner,
            localized_config_edit,
            bool(exact_identifier_displacement_guard or exact_identifier_surface_selected),
            (
                explicit_surface_ambiguity,
                exact_identifier_ambiguity,
                multi_identifier_edit_ambiguity,
                weak_contract_anchor_ambiguity,
                archive_live_owner_ambiguity,
                multi_structural_owner_ambiguity,
                verification_identity_ambiguity,
            ),
        )
        reason = self._task_action_ambiguity_reason(
            edit,
            (
                ("ambiguous-explicit-task-surface", explicit_surface_ambiguity),
                ("weak-task-anchor", weak_contract_anchor_ambiguity),
                ("multiple-live-owners-behind-archive-hit", archive_live_owner_ambiguity),
                ("multiple-task-local-structural-owners", multi_structural_owner_ambiguity),
                ("unresolved-qualified-import-identity", verification_identity_ambiguity),
                ("multiple-exact-identifier-edit-owners", exact_identifier_ambiguity),
                ("multiple-identifier-edit-owners", multi_identifier_edit_ambiguity),
            ),
            ambiguous,
        )
        return {
            "ambiguous": ambiguous,
            "reason": reason,
            "candidates": self._task_action_ambiguity_candidates(edit, competing, per_role),
            "competing": competing,
            "structural_owners": task_local_structural_owners,
            "verification_origins": task_local_verification_origins,
            "multi_structural_owner_ambiguity": multi_structural_owner_ambiguity,
        }

