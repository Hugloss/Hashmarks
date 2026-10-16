"""Non-authoritative method retrieval within one explicit class scope."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

from .model import EvidenceVisibility
from .task_evidence_contract import read_task_candidate

if TYPE_CHECKING:
    from .engine import CodeMap
    from .evidence_verification import _VerificationRelevanceState
    from .task_evidence_types import TaskEvidenceDraft


class TaskEvidenceScopedMethodMixin:
    @staticmethod
    def _enclosing_span_stop(
        parent: Mapping[str, object], child: Mapping[str, object]
    ) -> str | None:
        if parent.get("kind") not in {"function", "method"}:
            return "scope-boundary"
        bounds = [
            parent.get("start_line"),
            child.get("start_line"),
            child.get("end_line"),
            parent.get("end_line"),
        ]
        qualified = [
            value
            for value in bounds
            if isinstance(value, int) and not isinstance(value, bool)
        ]
        return (
            None
            if len(qualified) == 4 and qualified == sorted(qualified)
            else "unqualified-parent-span"
        )

    def _task_evidence_enclosing_functions(
        self, path: str, symbol: str
    ) -> dict[str, object] | None:
        """Observe indexed lexical containers without assigning behavior ownership."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        indexed: dict[str, list[dict]] = {}
        for row in self._session_symbols_for_path(path):
            indexed.setdefault(str(row.get("qualname") or ""), []).append(row)
        selected = indexed.get(symbol, [])
        member = self._session_file_row(path)
        if len(selected) != 1 or member is None:
            return None
        child = selected[0]
        declarations = []
        seen = {symbol}
        stop = "scope-boundary"
        while child.get("parent") and len(declarations) < 4:
            parent_name = str(child["parent"])
            parents = indexed.get(parent_name, [])
            if parent_name in seen or len(parents) != 1:
                stop = "unresolved-parent"
                break
            parent = parents[0]
            reason = self._enclosing_span_stop(parent, child)
            if reason is not None:
                stop = reason
                break
            declarations.append(
                {
                    "path": path,
                    "symbol": parent["qualname"],
                    "start_line": parent["start_line"],
                    "end_line": parent["end_line"],
                }
            )
            seen.add(parent_name)
            child = parent
        if not declarations:
            return None
        return {
            "authority": "indexed-lexical-declarations-only",
            "scope": "direct-enclosing-function-declarations",
            "ownership_authority": False,
            "runtime_members": "not-established",
            "negative_evidence_admissible": False,
            "source_revision": member["file_digest"],
            "index_generation": self.store.generation(),
            "bound": 4,
            "truncated": len(declarations) == 4 and bool(child.get("parent")),
            "stop_reason": stop,
            "declarations": declarations,
        }

    def _task_evidence_declaration_visible(self, path: str) -> bool:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        return (
            self._task_evidence_visibility(path)
            in {EvidenceVisibility.SOURCE, EvidenceVisibility.OUTLINE}
            and self.policy.decide(path).evidence_visibility
            is not EvidenceVisibility.DENY
        )

    def _task_evidence_attach_enclosing_functions(
        self, packet: TaskEvidenceDraft
    ) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        retrieval = packet.get("retrieval")
        if not isinstance(retrieval, dict):
            return
        for row in retrieval.get("results", [])[:3]:
            path, symbol = row.get("path"), row.get("symbol")
            if not path or not symbol or not self._indexed_path_current(path):
                continue
            if not self._task_evidence_declaration_visible(path):
                continue
            context = self._task_evidence_enclosing_functions(path, symbol)
            if context is not None and self._indexed_path_current(path):
                row["enclosing_declarations"] = context

    def _task_evidence_class_declarations(
        self,
        path: str,
        parent: Mapping[str, object],
        *,
        selected_symbol: str | None = None,
    ) -> dict[str, object]:
        """Disclose indexed lexical members; inherited/runtime members are unknown."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        qualname = str(parent["qualname"])
        members = sorted(
            (
                row
                for row in self._session_symbols_for_path(path)
                if row.get("parent") == qualname
                and row.get("kind") == "method"
                and isinstance(row.get("start_line"), int)
                and isinstance(row.get("end_line"), int)
                and cast("int", parent["start_line"])
                <= cast("int", row["start_line"])
                <= cast("int", row["end_line"])
                <= cast("int", parent["end_line"])
            ),
            key=lambda row: (
                cast("int", row["start_line"]),
                str(row.get("qualname") or ""),
            ),
        )
        member = self._session_file_row(path)
        assert member is not None
        context: dict[str, object] = {
            "authority": "indexed-lexical-declarations-only",
            "scope": "direct-declared-methods-of-retrieved-class",
            "ownership_authority": False,
            "runtime_members": "not-established",
            "negative_evidence_admissible": False,
            "source_revision": member["file_digest"],
            "index_generation": self.store.generation(),
            "observed": len(members),
            "returned": min(len(members), 16),
            "omitted": max(0, len(members) - 16),
            "bound": 16,
            "declarations": [
                {
                    "path": path,
                    "symbol": row["qualname"],
                    "start_line": row["start_line"],
                    "end_line": row["end_line"],
                }
                for row in members[:16]
            ],
        }
        if selected_symbol is not None and qualname != selected_symbol:
            context["scope"] = "direct-declared-methods-of-indexed-parent-class"
            context["class_scope"] = {
                "path": path,
                "symbol": qualname,
                "start_line": parent["start_line"],
                "end_line": parent["end_line"],
            }
        return context

    def _task_evidence_retrieved_class_scope(
        self, path: str, row: Mapping[str, object]
    ) -> Mapping[str, object] | None:
        """Resolve one indexed lexical class or direct method container."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        symbols = self._session_symbols_for_path(path)
        selected = [
            symbol for symbol in symbols if symbol.get("qualname") == row.get("symbol")
        ]
        if len(selected) != 1 or (
            selected[0].get("start_line"),
            selected[0].get("end_line"),
        ) != (row.get("start_line"), row.get("end_line")):
            return None
        child = selected[0]
        if child.get("kind") == "class":
            return child
        if child.get("kind") != "method":
            return None
        parents = [
            symbol
            for symbol in symbols
            if symbol.get("qualname") == child.get("parent")
        ]
        if len(parents) != 1 or parents[0].get("kind") != "class":
            return None
        parent = parents[0]
        bounds = [
            parent.get("start_line"),
            child.get("start_line"),
            child.get("end_line"),
            parent.get("end_line"),
        ]
        qualified = [
            value
            for value in bounds
            if isinstance(value, int) and not isinstance(value, bool)
        ]
        if len(qualified) != 4 or qualified != sorted(qualified):
            return None
        return parent

    def _task_evidence_attach_class_declarations(
        self, packet: TaskEvidenceDraft
    ) -> None:
        """Disclose bounded class scopes for the first three source locators."""
        codemap = cast("CodeMap", self)
        retrieval = packet.get("retrieval")
        if not isinstance(retrieval, dict):
            return
        observed = set()
        for row in retrieval.get("results", [])[:3]:
            path, symbol = row.get("path"), row.get("symbol")
            if not path or not symbol or not codemap._indexed_path_current(path):
                continue
            if "verify" in row.get("roles", []) and "edit" not in row.get("roles", []):
                continue
            if not codemap._task_evidence_declaration_visible(path):
                continue
            declaration = codemap._task_evidence_retrieved_class_scope(path, row)
            if declaration is None or (path, declaration["qualname"]) in observed:
                continue
            observed.add((path, declaration["qualname"]))
            context = codemap._task_evidence_class_declarations(
                path, declaration, selected_symbol=str(symbol)
            )
            if codemap._indexed_path_current(path):
                row["class_declarations"] = context

    def _task_evidence_verification_subject(
        self, row: Mapping[str, object]
    ) -> Mapping[str, object] | None:
        codemap = cast("CodeMap", self)
        path = str(row.get("path") or "")
        if not path or not codemap._indexed_path_current(path):
            return None
        if not codemap._task_evidence_declaration_visible(path):
            return None
        parent = codemap._task_evidence_retrieved_class_scope(path, row)
        if parent is not None:
            return parent
        matches = [
            symbol
            for symbol in codemap._session_symbols_for_path(path)
            if symbol.get("qualname") == row.get("symbol")
            and (symbol.get("start_line"), symbol.get("end_line"))
            == (row.get("start_line"), row.get("end_line"))
        ]
        return matches[0] if len(matches) == 1 else None

    def _task_evidence_candidate_verifiers(
        self, task: str, row: Mapping[str, object]
    ) -> list[dict[str, object]]:
        """References to an observed declaration do not prove its behavior ownership."""
        from .query_primitives import _query_terms
        from .repository_domains import RepositoryDomain, classify_repository_path
        from .verification_defaults import VERIFICATION_RELEVANCE_DEFAULTS

        codemap = cast("CodeMap", self)
        path = str(row.get("path") or "")
        if RepositoryDomain.TEST in classify_repository_path(path):
            return []
        subject = codemap._task_evidence_verification_subject(row)
        member = codemap._session_file_row(path)
        if subject is None or member is None:
            return []
        state = codemap._verification_state(task, path, "", ())
        subject_terms = sorted(
            state.task_terms.intersection(
                _query_terms(
                    str(subject["qualname"]) + " " + str(row.get("symbol") or "")
                )
            )
        )
        lexical = (
            codemap._session_lexical_file_candidates(subject_terms, limit=65)
            if subject_terms
            else []
        )
        if len(lexical) > 64:
            state.search_bound_reasons.add("source-identifier-lexical-file-limit")
        term_counts = {
            str(match["path"]): cast("int", match["matches"])
            for match in lexical[:64]
            if codemap._verification_ref_visible(match)
            and RepositoryDomain.TEST in classify_repository_path(str(match["path"]))
        }
        state.candidate_paths.update(term_counts)
        names: list[str] = []
        codemap._append_verification_symbol_names(names, subject)
        codemap._verification_collect_direct_references(state, names)
        test_modules = codemap._task_evidence_test_module_references(state)
        state.source_ref_paths.update(test_modules)
        codemap._verification_collect_indirect_references(state)
        candidates = codemap._verification_candidates(state)
        candidates.extend(codemap._verification_lexical_candidates(state))
        for candidate in candidates:
            candidate["subject_term_matches"] = term_counts.get(
                str(candidate["path"]), 0
            )
        candidates.sort(
            key=codemap._task_evidence_candidate_verifier_score, reverse=True
        )
        basis = {
            "path": path,
            "symbol": subject["qualname"],
            "start_line": subject["start_line"],
            "end_line": subject["end_line"],
            "source_revision": member["file_digest"],
            "ownership_authority": False,
            "search_bound_reasons": sorted(state.search_bound_reasons),
            "subject_task_terms": subject_terms,
        }
        result = []
        for candidate in candidates[: VERIFICATION_RELEVANCE_DEFAULTS.candidate_limit]:
            test_member = codemap._session_file_row(str(candidate["path"]))
            if (
                test_member is None
                or not codemap._indexed_path_current(str(candidate["path"]))
                or not codemap._task_evidence_declaration_visible(
                    str(candidate["path"])
                )
            ):
                continue
            test_module_revisions = {
                name: test_modules[name]
                for name in state.indirect_via_paths.get(str(candidate["path"]), ())
                if name in test_modules
            }
            result.append(
                {
                    **candidate,
                    "candidate_origin": "indexed-source-candidate-disclosure",
                    "source_candidate_basis": [
                        {
                            **basis,
                            "reference_strength": candidate.get("reference_strength"),
                            "reference_symbols": candidate.get("reference_symbols", []),
                            "indirect_reference_symbols": candidate.get(
                                "indirect_reference_symbols", []
                            ),
                            "indirect_via_paths": candidate.get(
                                "indirect_via_paths", []
                            ),
                            **(
                                {"test_module_revisions": test_module_revisions}
                                if test_module_revisions
                                else {}
                            ),
                        }
                    ],
                    "test_revision": test_member["file_digest"],
                    "verification_selection_authority": False,
                    "edit_relationship": "unestablished",
                    "negative_evidence_admissible": False,
                }
            )
        return (
            result
            if codemap._indexed_path_current(path)
            and all(codemap._indexed_path_current(name) for name in test_modules)
            else []
        )

    def _task_evidence_test_module_references(
        self, state: _VerificationRelevanceState
    ) -> dict[str, str]:
        """Bound test-owned source observations for candidate disclosure only."""
        from .repository_domains import RepositoryDomain, classify_repository_path

        codemap = cast("CodeMap", self)
        paths = sorted(
            path
            for path in state.refs_by_path
            if RepositoryDomain.SOURCE in classify_repository_path(path)
        )
        if len(paths) > 16:
            state.search_bound_reasons.add("source-candidate-test-module-limit")
        result = {}
        for path in paths[:16]:
            member = codemap._session_file_row(path)
            if member is not None and codemap._indexed_path_current(path):
                result[path] = str(member["file_digest"])
            else:
                state.search_bound_reasons.add("source-candidate-test-module-stale")
        return result

    def _task_evidence_candidate_verifier_score(
        self, row: Mapping[str, object]
    ) -> tuple:
        """Projection ordering only; lexical locality never grants selection proof."""
        codemap = cast("CodeMap", self)
        score = codemap._verification_candidate_score(row)
        return (
            score[0],
            score[1],
            cast("int", row.get("subject_term_matches", 0)),
            *score[2:],
        )

    def _task_evidence_attach_candidate_verifiers(
        self, packet: TaskEvidenceDraft, task: str
    ) -> None:
        """Disclose source-bound test candidates without altering edit/verify selection."""
        from .repository_domains import RepositoryDomain, classify_repository_path
        from .verification_defaults import VERIFICATION_RELEVANCE_DEFAULTS

        codemap = cast("CodeMap", self)
        retrieval = packet["retrieval"]
        verification = packet["verification"]
        if not isinstance(retrieval, dict) or not isinstance(verification, dict):
            return
        relevance = verification.get("relevance")
        if not isinstance(relevance, dict):
            return
        source_rows = [
            row
            for row in retrieval.get("results", [])
            if RepositoryDomain.TEST
            not in classify_repository_path(str(row.get("path") or ""))
        ][:3]
        candidates = [
            candidate
            for row in source_rows
            for candidate in codemap._task_evidence_candidate_verifiers(task, row)
        ]
        by_path = {
            str(row["path"]): dict(row) for row in relevance.get("candidates", [])
        }
        for candidate in candidates:
            path = str(candidate["path"])
            previous = by_path.get(path)
            if previous is None:
                by_path[path] = candidate
            else:
                previous_bases = cast(
                    "list[dict[str, object]]",
                    previous.get("source_candidate_basis", []),
                )
                new_bases = cast(
                    "list[dict[str, object]]", candidate["source_candidate_basis"]
                )
                merged_bases = previous_bases + [
                    basis for basis in new_bases if basis not in previous_bases
                ]
                if (
                    "test_revision" not in previous
                    or codemap._task_evidence_candidate_verifier_score(candidate)
                    > codemap._task_evidence_candidate_verifier_score(previous)
                ):
                    by_path[path] = candidate
                by_path[path]["source_candidate_basis"] = merged_bases
        ordered = sorted(
            by_path.values(),
            key=codemap._task_evidence_candidate_verifier_score,
            reverse=True,
        )
        ordered = codemap._verification_disclosure_order(
            ordered,
            task_candidates=[
                by_path[str(row["path"])] for row in relevance.get("candidates", [])
            ],
        )
        limit = VERIFICATION_RELEVANCE_DEFAULTS.candidate_limit
        relevance["candidates"] = [
            read_task_candidate(row)
            for row in codemap._verification_bounded_candidates(
                ordered, relevance.get("selected"), limit
            )
        ]
        relevance["candidate_disclosure"] = {
            "basis": "indexed-source-candidates-and-task-matches",
            "subject_bound": 3,
            "returned_bound": limit,
            "observed_candidates": len(ordered),
            "returned_candidates": len(relevance["candidates"]),
            "omitted_candidates": max(0, len(ordered) - len(relevance["candidates"])),
            "verification_selection_authority": False,
            "negative_evidence_admissible": False,
        }

    def _task_evidence_named_class_scope(
        self, task: str
    ) -> tuple[str, str, EvidenceVisibility] | None:
        """Bind one explicitly named class to current visible repository symbols."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        terms = self._task_action_exact_identifier_terms(task)
        if re.search(r"\bmethod\b", task, flags=re.IGNORECASE) is None or not terms:
            return None
        indexed = self._session_exact_symbol_candidates(terms, limit=65)
        classes = [
            row
            for row in indexed
            if row.get("kind") == "class"
            and str(row.get("name") or "").lower() in terms
        ]
        if len(indexed) >= 65 or len(classes) != 1:
            return None
        owner = classes[0]
        path = str(owner.get("path") or "")
        qualname = str(owner.get("qualname") or "")
        if not path or not qualname:
            return None
        visibility = self._task_evidence_visibility(path)
        admitted = (
            visibility in {EvidenceVisibility.SOURCE, EvidenceVisibility.OUTLINE}
            and self.policy.decide(path).evidence_visibility
            is not EvidenceVisibility.DENY
            and self._indexed_path_current(path)
        )
        if not admitted:
            return None
        assert visibility is not None
        return path, qualname, visibility

    def _task_evidence_scoped_method_supplement(
        self,
        task: str,
        query_tokens: Sequence[tuple[str, ...]],
        frequencies: Mapping[str, int],
        total: int,
        existing_keys: set[tuple[str, str]],
    ) -> dict[str, object] | None:
        """Expose a lexical member of one named class without owner authority."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        scope = self._task_evidence_named_class_scope(task)
        if scope is None:
            return None
        path, qualname, visibility = scope
        members = [
            row
            for row in self._session_symbols_for_path(path)
            if row.get("kind") == "method" and str(row.get("parent") or "") == qualname
        ]
        scored = sorted(
            (
                (
                    self._task_evidence_symbol_relevance(
                        str(row.get("name") or ""), query_tokens, frequencies, total
                    ),
                    str(row.get("qualname") or ""),
                    row,
                )
                for row in members
            ),
            key=lambda item: (-item[0], item[1]),
        )
        for score, member_name, member in scored:
            if score <= 0:
                break
            key = (path, member_name)
            if key not in existing_keys:
                existing_keys.add(key)
                return self._task_evidence_supplement_row(
                    path, member, score=score, visibility=visibility
                )
        return None

    @staticmethod
    def _task_evidence_scip_owner_claim(
        packet: Mapping[str, object],
    ) -> Mapping[str, object] | None:
        """Use only the complete, admitted owner; never a retrieval candidate."""
        ownership = packet.get("ownership")
        if not isinstance(ownership, Mapping):
            return None
        if (
            ownership.get("status") != "resolved"
            or ownership.get("proof_scope_complete") is not True
            or ownership.get("authority") != "repository-ownership-only"
        ):
            return None
        owner = ownership.get("owner")
        return owner if isinstance(owner, Mapping) else None

    def _task_evidence_current_scip_symbol(
        self,
        owner: Mapping[str, object],
        captures: Sequence[Mapping[str, object]] = (),
    ) -> tuple[Mapping[str, object] | None, str]:
        """Rebind the admitted locator to an exact, visible current symbol."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        path = str(owner.get("path") or "")
        qualname = str(owner.get("qualname") or "")
        scope = "owner" if qualname else "owned-file-query"
        if not path:
            return None, scope
        if self._task_evidence_visibility(path) not in {
            EvidenceVisibility.SOURCE,
            EvidenceVisibility.OUTLINE,
        }:
            return None, scope
        if (
            self.policy.decide(path).evidence_visibility is EvidenceVisibility.DENY
            or not self._indexed_path_current(path)
        ):
            return None, scope
        return (
            self.store.symbol_at(path, qualname)
            if qualname
            else self._task_evidence_owned_file_query(path, captures),
            scope,
        )

    def _task_evidence_owned_file_query(
        self, path: str, captures: Sequence[Mapping[str, object]]
    ) -> Mapping[str, object] | None:
        """Bind one explicit producer query; never infer a symbol owner from a file."""
        self = cast("CodeMap", self)
        from .lsp_relationship_adapter import lsp_query_locator
        from .semantic_relationship_source import RelationshipSourceResolver

        resolver = RelationshipSourceResolver(self)
        subjects: set[str] = set()
        for capture in captures:
            query_path, locator = lsp_query_locator(capture, self.workspace)
            if query_path != path:
                continue
            documents = capture.get("documents")
            snapshot = documents.get(path) if isinstance(documents, Mapping) else None
            if not isinstance(snapshot, Mapping):
                return None
            resolution = resolver.candidates(path, locator, snapshot, query=True)
            if resolution["state"] != "unique-candidate" or resolution["truncated"]:
                return None
            subjects.add(str(resolution["candidates"][0]["symbol_id"]))
        if len(subjects) != 1:
            return None
        return self.store.symbol_at(path, subjects.pop().split("::", 1)[1])

    def _task_evidence_attach_scip_discovery(
        self,
        packet: TaskEvidenceDraft,
        supplied_observations: Sequence[Mapping[str, object]] = (),
        *,
        selection_generation: int | None = None,
    ) -> None:
        """Expose retained SCIP observations without changing task ownership."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if supplied_observations:
            packet["supplied_observation_accounting"] = {
                "received": len(supplied_observations),
                "retained": 0,
                "omitted": len(supplied_observations),
                "capture_identities": [
                    row["capture_identity"] for row in supplied_observations
                ],
                "reason": "task-owner-or-freshness-not-qualified",
            }
        owner = self._task_evidence_scip_owner_claim(packet)
        freshness = packet.get("freshness")
        if owner is None or not isinstance(freshness, Mapping):
            return
        if freshness.get("state") not in {"current", "unknown"}:
            return
        from .semantic_relationship_model import compact_relationships
        from .semantic_relationship_observation import semantic_relationship_observation

        with self.decision_session(expected_generation=selection_generation):
            current, subject_scope = self._task_evidence_current_scip_symbol(
                owner, supplied_observations
            )
            if current is None:
                return
            observation = semantic_relationship_observation(
                self, current, supplied_observations
            )
            compact = compact_relationships(observation)
            discovery = self._scip_compact_discovery(current)
        if supplied_observations:
            retained = sum(
                "method" in row["scope"] for row in observation["observations"]
            )
            packet["supplied_observation_accounting"] = {
                "received": len(supplied_observations),
                "retained": retained,
                "omitted": len(supplied_observations) - retained,
                "capture_identities": [
                    row["capture_identity"] for row in supplied_observations
                ],
                "reason": "observation-bounds"
                if retained < len(supplied_observations)
                else "current-request-projection",
            }
        if (
            discovery is not None
            or supplied_observations
            or compact["observed_relationship_count"]
        ):
            packet["semantic_relationships"] = {
                **(discovery or compact),
                "repository_freshness": freshness["state"],
                "observed_relationship_count_scope": (
                    f"exact-{subject_scope}-scip-definition-outgoing"
                    if discovery is not None
                    else f"explicit-producer-claims-associated-with-{subject_scope}"
                ),
                "associated_observed_relationship_count": compact[
                    "observed_relationship_count"
                ],
                "associated_observed_relationship_count_scope": (
                    f"explicit-producer-claims-associated-with-{subject_scope}"
                ),
                "evidence": compact,
                "evidence_refs": {
                    "ownership": "/ownership",
                    "source": "/ownership/source_evidence",
                    "verification": "/verification",
                },
            }
