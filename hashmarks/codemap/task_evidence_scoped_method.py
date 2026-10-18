"""Non-authoritative method retrieval within one explicit class scope."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from itertools import zip_longest
from pathlib import Path
from typing import TYPE_CHECKING, cast

from .model import EvidenceVisibility
from .task_evidence_contract import read_task_candidate

if TYPE_CHECKING:
    from .evidence_verification import _VerificationRelevanceState
    from .repository_tasks import RepositoryTasks
    from .task_evidence_types import RetrievalLocator, TaskEvidenceDraft


class TaskEvidenceScopedMethodMixin:
    def _task_evidence_direct_call_declarations(
        self, path: str, locator: Mapping[str, object]
    ) -> dict[str, object] | None:
        """Project qualified direct calls using the structural-locality resolver."""
        codemap = cast("RepositoryTasks", self)
        symbol = str(locator.get("symbol") or "")
        selected = codemap.store.symbol_at(path, symbol)
        if selected is None or (
            selected.get("start_line"),
            selected.get("end_line"),
        ) != (locator.get("start_line"), locator.get("end_line")):
            return None
        calls = [
            edge
            for edge in codemap.store.edges_from(path, symbol)
            if edge.get("kind") == "call" and edge.get("source") == symbol
        ]
        targets: dict[str, dict[str, object]] = {}
        resolved_calls = 0
        for edge in calls[:64]:
            target, _, _, complete = codemap.structure._resolve_call_target(edge)
            if not complete or target is None or target.get("path") != path:
                continue
            if target.get("kind") not in {"function", "method"}:
                continue
            resolved_calls += 1
            name = str(target["qualname"])
            targets.setdefault(
                name,
                {
                    "path": path,
                    "symbol": name,
                    "start_line": target["start_line"],
                    "end_line": target["end_line"],
                    "call_line": edge["line"],
                },
            )
        member = codemap.reads.file_row(path)
        if not targets or member is None or not codemap.index.is_current(path):
            return None
        declarations = list(targets.values())
        return {
            "authority": "indexed-qualified-local-call-declarations-only",
            "scope": "same-file-direct-call-target-declarations",
            "ownership_authority": False,
            "runtime_members": "not-established",
            "negative_evidence_admissible": False,
            "source_revision": member["file_digest"],
            "index_generation": codemap.store.generation(),
            "observed_calls": len(calls),
            "examined_calls": min(len(calls), 64),
            "unexamined_calls": max(0, len(calls) - 64),
            "unresolved_or_other_scope_calls": min(len(calls), 64) - resolved_calls,
            "observed": len(declarations),
            "returned": min(len(declarations), 4),
            "omitted": max(0, len(declarations) - 4),
            "bound": 4,
            "declarations": declarations[:4],
        }

    def _task_evidence_attach_direct_call_declarations(
        self, packet: TaskEvidenceDraft
    ) -> None:
        codemap = cast("RepositoryTasks", self)
        for row in packet["retrieval"]["results"][:3]:
            path = row["path"]
            if (
                row.get("supplement") != "bounded-lexical-source-position"
                or not codemap.index.is_current(path)
                or codemap._task_evidence_visibility(path)
                is not EvidenceVisibility.SOURCE
                or codemap.files.decide(path).evidence_visibility
                is not EvidenceVisibility.SOURCE
            ):
                continue
            context = codemap._task_evidence_direct_call_declarations(path, row)
            if context is not None and codemap.index.is_current(path):
                row["direct_call_declarations"] = context

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
            self = cast("RepositoryTasks", self)
        indexed: dict[str, list[dict]] = {}
        for row in self.reads.symbols_for_path(path):
            indexed.setdefault(str(row.get("qualname") or ""), []).append(row)
        selected = indexed.get(symbol, [])
        member = self.reads.file_row(path)
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
            self = cast("RepositoryTasks", self)
        return (
            self._task_evidence_visibility(path)
            in {EvidenceVisibility.SOURCE, EvidenceVisibility.OUTLINE}
            and self.files.decide(path).evidence_visibility
            is not EvidenceVisibility.DENY
        )

    def _task_evidence_attach_enclosing_functions(
        self, packet: TaskEvidenceDraft
    ) -> None:
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        retrieval = packet.get("retrieval")
        if not isinstance(retrieval, dict):
            return
        for row in retrieval.get("results", [])[:3]:
            path, symbol = row.get("path"), row.get("symbol")
            if not path or not symbol or not self.index.is_current(path):
                continue
            if not self._task_evidence_declaration_visible(path):
                continue
            context = self._task_evidence_enclosing_functions(path, symbol)
            if context is not None and self.index.is_current(path):
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
            self = cast("RepositoryTasks", self)
        qualname = str(parent["qualname"])
        members = sorted(
            (
                row
                for row in self.reads.symbols_for_path(path)
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
        member = self.reads.file_row(path)
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
            self = cast("RepositoryTasks", self)
        symbols = self.reads.symbols_for_path(path)
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

    def _task_evidence_same_named_declarations(
        self, path: str, locator: Mapping[str, object]
    ) -> dict[str, object] | None:
        """Expose lexical name alternatives, without dispatch/inheritance claims."""
        codemap = cast("RepositoryTasks", self)
        symbols = codemap.reads.symbols_for_path(path)
        selected = [
            row
            for row in symbols
            if (row.get("qualname"), row.get("start_line"), row.get("end_line"))
            == (
                locator.get("symbol"),
                locator.get("start_line"),
                locator.get("end_line"),
            )
        ]
        if len(selected) != 1 or selected[0].get("kind") not in {"method", "function"}:
            return None
        alternatives = sorted(
            (
                row
                for row in symbols
                if row is not selected[0]
                and row.get("name") == selected[0].get("name")
                and row.get("kind") in {"method", "function"}
            ),
            key=lambda row: str(row.get("qualname") or ""),
        )
        member = codemap.reads.file_row(path)
        if not alternatives or member is None:
            return None
        return {
            "authority": "indexed-lexical-declarations-only",
            "scope": "same-file-same-name-declarations",
            "ownership_authority": False,
            "runtime_members": "not-established",
            "negative_evidence_admissible": False,
            "source_revision": member["file_digest"],
            "index_generation": codemap.store.generation(),
            "observed": len(alternatives),
            "returned": min(len(alternatives), 4),
            "omitted": max(0, len(alternatives) - 4),
            "bound": 4,
            "declarations": [
                {
                    "path": path,
                    "symbol": row["qualname"],
                    "start_line": row["start_line"],
                    "end_line": row["end_line"],
                }
                for row in alternatives[:4]
            ],
        }

    def _task_evidence_attach_same_named_declarations(
        self, path: str, row: RetrievalLocator
    ) -> None:
        codemap = cast("RepositoryTasks", self)
        alternatives = codemap._task_evidence_same_named_declarations(path, row)
        if alternatives is not None and codemap.index.is_current(path):
            row["same_name_declarations"] = alternatives

    def _task_evidence_attach_class_declarations(
        self, packet: TaskEvidenceDraft
    ) -> None:
        """Disclose bounded class scopes for the first three source locators."""
        codemap = cast("RepositoryTasks", self)
        retrieval = packet.get("retrieval")
        if not isinstance(retrieval, dict):
            return
        observed = set()
        for row in retrieval.get("results", [])[:3]:
            path, symbol = row.get("path"), row.get("symbol")
            if not path or not symbol or not codemap.index.is_current(path):
                continue
            if "verify" in row.get("roles", []) and "edit" not in row.get("roles", []):
                continue
            if not codemap._task_evidence_declaration_visible(path):
                continue
            codemap._task_evidence_attach_same_named_declarations(path, row)
            declaration = codemap._task_evidence_retrieved_class_scope(path, row)
            if declaration is None or (path, declaration["qualname"]) in observed:
                continue
            observed.add((path, declaration["qualname"]))
            context = codemap._task_evidence_class_declarations(
                path, declaration, selected_symbol=str(symbol)
            )
            if codemap.index.is_current(path):
                row["class_declarations"] = context

    def _task_evidence_verification_subject(
        self, row: Mapping[str, object]
    ) -> Mapping[str, object] | None:
        codemap = cast("RepositoryTasks", self)
        path = str(row.get("path") or "")
        if not path or not codemap.index.is_current(path):
            return None
        if not codemap._task_evidence_declaration_visible(path):
            return None
        if all(row.get(key) is None for key in ("symbol", "start_line", "end_line")):
            return {
                "kind": "file",
                "qualname": None,
                "start_line": None,
                "end_line": None,
            }
        matches = [
            symbol
            for symbol in codemap.reads.symbols_for_path(path)
            if symbol.get("qualname") == row.get("symbol")
            and (symbol.get("start_line"), symbol.get("end_line"))
            == (row.get("start_line"), row.get("end_line"))
        ]
        return matches[0] if len(matches) == 1 else None

    def _task_evidence_candidate_verifiers(
        self, task: str, row: Mapping[str, object]
    ) -> list[dict[str, object]]:
        """Disclose source references without proving behavior ownership."""
        from .query_primitives import _query_terms
        from .repository_domains import RepositoryDomain, classify_repository_path
        from .verification_defaults import VERIFICATION_RELEVANCE_DEFAULTS

        codemap = cast("RepositoryTasks", self)
        path = str(row.get("path") or "")
        if RepositoryDomain.TEST in classify_repository_path(path):
            return []
        subject = codemap._task_evidence_verification_subject(row)
        member = codemap.reads.file_row(path)
        if subject is None or member is None:
            return []
        state = codemap.verification._verification_state(
            codemap._task_query(task), path, "", ()
        )
        state.task_terms = {
            variant
            for term in state.task_terms
            for variant in codemap.search._task_natural_term_variants(
                term, include_derivations=True
            )
        }
        subject_terms = sorted(
            state.task_terms.intersection(
                _query_terms(str(subject["qualname"] or Path(path).stem))
            )
        )
        lexical = (
            codemap.reads.lexical_file_candidates(
                subject_terms,
                limit=65,
                paths=codemap.verification._verification_test_paths(state),
            )
            if subject_terms
            else []
        )
        if len(lexical) > 64:
            state.search_bound_reasons.add("source-identifier-lexical-file-limit")
        term_counts = {
            str(match["path"]): cast("int", match["matches"])
            for match in lexical[:64]
            if codemap.verification._verification_ref_visible(match)
            and RepositoryDomain.TEST in classify_repository_path(str(match["path"]))
        }
        state.candidate_paths.update(term_counts)
        filename_candidates = codemap._task_evidence_filename_test_candidates(
            state, subject_terms
        )
        state.candidate_paths.update(filename_candidates)
        codemap._task_evidence_collect_source_references(state, subject)
        test_modules = codemap._task_evidence_test_module_references(state)
        state.source_ref_paths.update(test_modules)
        codemap.verification._verification_collect_indirect_references(state)
        candidates = codemap.verification._verification_candidates(state)
        candidates.extend(codemap.verification._verification_lexical_candidates(state))
        for candidate in candidates:
            candidate["subject_term_matches"] = term_counts.get(
                str(candidate["path"]), 0
            )
            candidate.update(filename_candidates.get(str(candidate["path"]), {}))
        candidates.sort(
            key=lambda candidate: codemap._task_evidence_candidate_verifier_score(
                candidate, source_symbol=str(row.get("symbol") or ""), source_path=path
            ),
            reverse=True,
        )
        basis = {
            "path": path,
            "scope": "indexed-source-declaration"
            if subject["qualname"]
            else "indexed-source-file",
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
            test_member = codemap.reads.file_row(str(candidate["path"]))
            if (
                test_member is None
                or not codemap.index.is_current(str(candidate["path"]))
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
                            **filename_candidates.get(str(candidate["path"]), {}),
                            "reference_strength": candidate.get("reference_strength"),
                            "direct_reference": candidate.get("direct_reference"),
                            "indirect_reference": candidate.get("indirect_reference"),
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
            if codemap.index.is_current(path)
            and all(codemap.index.is_current(name) for name in test_modules)
            else []
        )

    def _task_evidence_collect_source_references(
        self,
        state: _VerificationRelevanceState,
        subject: Mapping[str, object],
    ) -> None:
        """Keep file-symbol bounds distinct from exact declaration selection."""
        codemap = cast("RepositoryTasks", self)
        if subject["qualname"]:
            symbols = [str(subject["qualname"])]
        else:
            symbols, complete = codemap.verification._verification_edit_symbols(
                state.edit_path, None
            )
            if not complete:
                state.search_bound_reasons.add("edit-file-symbol-limit")
        codemap.verification._verification_collect_direct_references(state, symbols)

    def _task_evidence_test_module_references(
        self, state: _VerificationRelevanceState
    ) -> dict[str, str]:
        """Bound test-owned source observations for candidate disclosure only."""
        from .repository_domains import RepositoryDomain, classify_repository_path

        codemap = cast("RepositoryTasks", self)
        paths = sorted(
            path
            for path in state.refs_by_path
            if RepositoryDomain.SOURCE in classify_repository_path(path)
        )
        if len(paths) > 16:
            state.search_bound_reasons.add("source-candidate-test-module-limit")
        result = {}
        for path in paths[:16]:
            member = codemap.reads.file_row(path)
            if member is not None and codemap.index.is_current(path):
                result[path] = str(member["file_digest"])
            else:
                state.search_bound_reasons.add("source-candidate-test-module-stale")
        return result

    def _task_evidence_candidate_verifier_score(
        self,
        row: Mapping[str, object],
        *,
        source_symbol: str = "",
        source_path: str = "",
    ) -> tuple:
        """Projection ordering only; lexical locality never grants selection proof."""
        from .query_primitives import _query_terms

        codemap = cast("RepositoryTasks", self)
        score = codemap.verification._verification_candidate_score(row)
        declaration_matches = self._task_evidence_test_declaration_matches(
            row, fallback=score[2]
        )
        # Tasks can paraphrase a declaration's spelling. Coherent multiword
        # overlap with that observed declaration remains weak lexical evidence.
        source_overlap = (
            self._task_evidence_test_declaration_matches(
                {
                    **row,
                    "task_anchor_terms": list(_query_terms(source_symbol)),
                },
                fallback=0,
            )
            if source_symbol
            else 0
        )
        return (
            score[0],
            score[1],
            source_overlap if source_overlap >= 2 else 0,
            int(row.get("source_filename_prefix_match") is True),
            self._task_evidence_problem_filename_matches(
                row, source_symbol=source_symbol, source_path=source_path
            ),
            self._task_evidence_test_directory_matches(row),
            cast("int", row.get("subject_term_matches", 0)),
            declaration_matches,
            int(bool(row.get("test_symbol")) and declaration_matches > 0),
            *score[3:],
        )

    @staticmethod
    def _task_evidence_problem_filename_matches(
        row: Mapping[str, object], *, source_symbol: str, source_path: str
    ) -> int:
        """Keep a task's concern visible beside incidental source-name matches.

        Exact references and namespace locality retain their earlier precedence.
        A filename match remains lexical disclosure, with no selection authority.
        """
        from .query_primitives import _TASK_STOPWORDS, _query_terms

        anchors = row.get("task_anchor_terms")
        if not source_path or not isinstance(anchors, list):
            return 0
        identity_terms = set(_query_terms(source_path + " " + source_symbol))
        problem_terms = (
            {term for term in anchors if isinstance(term, str)}
            - identity_terms
            - _TASK_STOPWORDS
            - {"source", "inspect"}
        )
        filename = Path(str(row.get("path") or "")).stem
        return len(problem_terms.intersection(_query_terms(filename)))

    def _task_evidence_test_declaration_matches(
        self, row: Mapping[str, object], *, fallback: int
    ) -> int:
        """Rank a coherent declaration match without changing module-wide facts."""
        from .query_primitives import _query_terms

        codemap = cast("RepositoryTasks", self)
        anchors = row.get("task_anchor_terms")
        if not isinstance(anchors, list):
            return fallback
        terms = {term for term in anchors if isinstance(term, str)}
        # Candidate construction has already loaded the complete symbol rows
        # into this decision's generation-bound session. Reuse that observation.
        symbols = codemap.reads.symbols_for_path(str(row["path"]))
        return max(
            (
                len(
                    terms.intersection(
                        _query_terms(str(symbol.get("qualname") or symbol["name"]))
                    )
                )
                for symbol in symbols
                if str(symbol.get("name") or "").startswith("test_")
                and symbol.get("kind") in {"function", "method"}
            ),
            default=fallback,
        )

    @staticmethod
    def _task_evidence_test_directory_matches(row: Mapping[str, object]) -> int:
        """Use existing task/path facts for disclosure, never test selection."""
        from .query_primitives import _query_terms

        anchors = row.get("task_anchor_terms")
        if not isinstance(anchors, list):
            return 0
        directory = str(Path(str(row.get("path") or "")).parent).replace("/", " ")
        terms = set(_query_terms(directory))
        return sum(isinstance(term, str) and term in terms for term in anchors)

    def _task_evidence_filename_test_candidates(
        self,
        state: _VerificationRelevanceState,
        subject_terms: Sequence[str],
    ) -> dict[str, dict[str, object]]:
        """Observe indexed test filename similarity without import/use authority."""
        codemap = cast("RepositoryTasks", self)
        if not subject_terms:
            return {}
        prefix = (
            Path(state.edit_path).name.split(".", 1)[0].removeprefix("test_").casefold()
        )
        paths = [
            path
            for path in codemap.verification._verification_test_paths(state)
            if Path(path).name.split(".", 1)[0].removeprefix("test_").casefold()
            == prefix
        ]
        codemap.reads.file_rows(paths)
        paths = [
            path for path in paths if codemap._task_evidence_declaration_visible(path)
        ]
        if len(paths) > 64:
            state.search_bound_reasons.add("source-filename-test-candidate-limit")
        if not paths:
            return {}
        matches = codemap.reads.lexical_file_candidates(
            subject_terms, limit=65, paths=paths[:64]
        )
        return {
            str(row["path"]): {
                "source_filename_prefix_match": True,
                "subject_term_matches": row["matches"],
            }
            for row in matches
            if codemap.index.is_current(str(row["path"]))
        }

    def _task_evidence_attach_candidate_verifiers(
        self, packet: TaskEvidenceDraft, task: str
    ) -> None:
        """Disclose source-bound test candidates without altering edit/verify selection."""
        from .repository_domains import RepositoryDomain, classify_repository_path
        from .verification_defaults import VERIFICATION_RELEVANCE_DEFAULTS

        codemap = cast("RepositoryTasks", self)
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
        source_rows = codemap._task_evidence_verification_subject_rows(source_rows)
        candidate_groups = [
            codemap._task_evidence_candidate_verifiers(task, row) for row in source_rows
        ]
        by_path = {
            str(row["path"]): dict(row) for row in relevance.get("candidates", [])
        }
        for candidate in (
            candidate for group in candidate_groups for candidate in group
        ):
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
                # The existing row is qualified against the task's selected
                # owner. Candidate-local references describe their own source
                # basis and cannot replace that relationship or its rank.
                by_path[path] = {**candidate, **previous}
                by_path[path]["source_candidate_basis"] = merged_bases
        # Each namespace/reference score is relative to its observed source.
        # Preserve those source-local orders instead of comparing their scores
        # globally, where one source's broad pool can hide every other source.
        ordered_by_path = {
            str(row["path"]): by_path[str(row["path"])]
            for rows in zip_longest(*candidate_groups)
            for row in rows
            if row is not None
        }
        ordered_by_path.update(
            (path, row) for path, row in by_path.items() if path not in ordered_by_path
        )
        ordered = list(ordered_by_path.values())
        ordered = codemap.verification._verification_disclosure_order(
            ordered,
            task_candidates=[
                by_path[str(row["path"])] for row in relevance.get("candidates", [])
            ],
        )
        limit = VERIFICATION_RELEVANCE_DEFAULTS.candidate_limit
        relevance["candidates"] = [
            read_task_candidate(row)
            for row in codemap.verification._verification_bounded_candidates(
                ordered, relevance.get("selected"), limit
            )
        ]
        relevance["candidate_disclosure"] = {
            "basis": "indexed-source-candidates-and-task-matches",
            "source_locator_bound": 3,
            "subject_bound": 6,
            "observed_subjects": len(source_rows),
            "returned_bound": limit,
            "observed_candidates": len(ordered),
            "returned_candidates": len(relevance["candidates"]),
            "omitted_candidates": max(0, len(ordered) - len(relevance["candidates"])),
            "verification_selection_authority": False,
            "negative_evidence_admissible": False,
        }

    def _task_evidence_verification_subject_rows(
        self, rows: Sequence[Mapping[str, object]]
    ) -> list[Mapping[str, object]]:
        """Retain exact declarations and independently observed parent contexts."""
        codemap = cast("RepositoryTasks", self)
        subjects: dict[tuple[str, str], Mapping[str, object]] = {}
        for row in rows:
            path = str(row.get("path") or "")
            subjects.setdefault((path, str(row.get("symbol") or "")), row)
            parent = codemap._task_evidence_retrieved_class_scope(path, row)
            if parent is not None and parent["qualname"] != row.get("symbol"):
                subjects.setdefault(
                    (path, str(parent["qualname"])),
                    {
                        "path": path,
                        "symbol": parent["qualname"],
                        "start_line": parent["start_line"],
                        "end_line": parent["end_line"],
                    },
                )
        return list(subjects.values())

    def _task_evidence_named_class_scope(
        self, task: str
    ) -> tuple[str, str, EvidenceVisibility] | None:
        """Bind one explicitly named class to current visible repository symbols."""
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        terms = self.ownership._task_action_exact_identifier_terms(task)
        if re.search(r"\bmethod\b", task, flags=re.IGNORECASE) is None or not terms:
            return None
        indexed = self.reads.exact_symbol_candidates(terms, limit=65)
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
            and self.files.decide(path).evidence_visibility
            is not EvidenceVisibility.DENY
            and self.index.is_current(path)
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
            self = cast("RepositoryTasks", self)
        scope = self._task_evidence_named_class_scope(task)
        if scope is None:
            return None
        path, qualname, visibility = scope
        members = [
            row
            for row in self.reads.symbols_for_path(path)
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
            self = cast("RepositoryTasks", self)
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
        if self.files.decide(
            path
        ).evidence_visibility is EvidenceVisibility.DENY or not self.index.is_current(
            path
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
        self = cast("RepositoryTasks", self)
        from .lsp_relationship_adapter import lsp_query_locator
        from .semantic_relationship_source import RelationshipSourceResolver

        resolver = RelationshipSourceResolver(self.source, self.reads, self.store)
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
            self = cast("RepositoryTasks", self)
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

        with self.reads.session(expected_generation=selection_generation):
            current, subject_scope = self._task_evidence_current_scip_symbol(
                owner, supplied_observations
            )
            if current is None:
                return
            observation = semantic_relationship_observation(
                self.structure, current, supplied_observations
            )
            compact = compact_relationships(observation)
            discovery = self.structure._scip_compact_discovery(current)
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
