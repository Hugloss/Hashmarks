"""Bounded retrieval supplements; selection and ownership stay with their owners."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

from .model import EvidenceVisibility, SearchHit

if TYPE_CHECKING:
    from .engine import CodeMap
    from .task_evidence_types import TaskEvidenceDraft


class TaskEvidenceRetrievalMixin:
    @staticmethod
    def _task_evidence_requested_locator_key(
        row: Mapping[str, object],
    ) -> tuple[str, str]:
        return (
            str(row.get("path") or ""),
            str(row.get("symbol") or row.get("qualname") or row.get("name") or ""),
        )

    @staticmethod
    def _task_evidence_retrieval_query(task: str) -> str:
        """Exclude a separate output-format sentence from retrieval vocabulary."""
        directive = re.search(
            r"[.!?]\s+(?:return|output|respond with)\s+exactly\s+"
            r"(?:(?:one|an?|the)\s+)?"
            r"(?:JSON|YAML|XML|Markdown)\b",
            task,
            flags=re.IGNORECASE,
        )
        return task[: directive.start()].strip() if directive else task

    def _task_evidence_natural_candidate_paths(
        self,
        task: str,
        existing: Sequence[Mapping[str, object]],
        terms: Sequence[str],
        bound_reasons: set[str],
    ) -> list[str]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        paths = list(
            dict.fromkeys(
                str(row.get("path"))
                for row in existing
                if isinstance(row.get("path"), str) and row.get("path")
            )
        )[:16]
        salient = self._task_salient_natural_terms(
            task,
            limit=6,
            bound_reasons=bound_reasons,
        )
        rare_paths: list[str] = []
        for term in salient:
            hits = self._task_component_hits(
                term,
                bound_reasons,
                include_signature=True,
            )
            if not hits or len(hits) > 8:
                continue
            for hit in hits[:2]:
                if (
                    self.policy.decide(hit.path).evidence_visibility
                    is EvidenceVisibility.DENY
                ):
                    continue
                if hit.path not in rare_paths:
                    rare_paths.append(hit.path)
            if len(rare_paths) >= 4:
                break
        paths.extend(path for path in rare_paths[:4] if path not in paths)
        lexical = self._session_lexical_file_candidates(terms, limit=64)
        code_paths = [
            str(row["path"])
            for row in lexical
            if row.get("path") and row.get("language") not in {"text", "markdown"}
        ][:12]
        paths.extend(path for path in code_paths if path not in paths)
        return paths

    @staticmethod
    def _task_evidence_identifier_parts(name: str) -> tuple[str, ...]:
        parts: list[str] = []
        for piece in name.replace("-", "_").split("_"):
            parts.extend(
                part.lower()
                for part in re.findall(
                    r"[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|\d+", piece
                )
                if len(part) >= 2
            )
        return tuple(parts)

    @staticmethod
    def _task_evidence_phrase_relevance(
        parts: Sequence[str], query_tokens: Sequence[tuple[str, ...]]
    ) -> float:
        def matches(part: str, variant: str) -> bool:
            return variant == part or (len(part) >= 5 and variant.startswith(part))

        phrase_length = 0
        phrase_position = 0
        for start in range(len(parts)):
            for position in range(len(query_tokens)):
                length = 0
                while (
                    start + length < len(parts)
                    and position + length < len(query_tokens)
                    and any(
                        matches(parts[start + length], variant)
                        for variant in query_tokens[position + length]
                    )
                ):
                    length += 1
                if length > phrase_length or (
                    length == phrase_length and position > phrase_position
                ):
                    phrase_length, phrase_position = length, position
        return 2 * phrase_length + (
            12 * phrase_position / len(query_tokens) if phrase_length >= 2 else 0
        )

    @classmethod
    def _task_evidence_symbol_relevance(
        cls,
        name: str,
        query_tokens: Sequence[tuple[str, ...]],
        frequencies: Mapping[str, int],
        total: int,
    ) -> float:
        parts = cls._task_evidence_identifier_parts(name)
        if not parts:
            return 0.0

        def matches(part: str, variant: str) -> bool:
            return variant == part or (len(part) >= 5 and variant.startswith(part))

        weighted = 0.0
        matched_parts = 0
        for part in parts:
            options = [
                (variant, position)
                for position, variants in enumerate(query_tokens)
                for variant in variants
                if matches(part, variant)
            ]
            if not options:
                continue
            variant, position = max(options, key=lambda row: row[1])
            matched_parts += 1
            weighted += math.log((total + 1) / (frequencies.get(variant, 0) + 1)) * (
                1 + 0.5 * position / len(query_tokens)
            )
        if not matched_parts:
            return 0.0
        return (
            weighted
            + cls._task_evidence_phrase_relevance(parts, query_tokens)
            + 2 * matched_parts / len(parts)
        )

    def _task_evidence_scored_symbols(
        self,
        path: str,
        query_tokens: Sequence[tuple[str, ...]],
        frequencies: Mapping[str, int],
        total: int,
    ) -> list[tuple[float, Mapping[str, object]]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        scored: list[tuple[float, str, Mapping[str, object]]] = []
        for symbol in self._session_symbols_for_path(path):
            score = self._task_evidence_symbol_relevance(
                str(symbol.get("name") or ""), query_tokens, frequencies, total
            )
            if score > 0:
                scored.append(
                    (
                        score,
                        str(symbol.get("qualname") or symbol.get("name") or ""),
                        symbol,
                    )
                )
        scored.sort(key=lambda row: (-row[0], row[1]))
        return [(row[0], row[2]) for row in scored[:8]]

    @staticmethod
    def _task_evidence_supplement_row(
        path: str,
        symbol: Mapping[str, object],
        *,
        score: float,
        visibility: EvidenceVisibility,
    ) -> dict[str, object]:
        def optional_text(key: str) -> str | None:
            value = symbol.get(key)
            return None if value is None else str(value)

        def optional_line(key: str) -> int | None:
            value = symbol.get(key)
            return value if isinstance(value, int) and value > 0 else None

        row = SearchHit(
            path=path,
            score=float(score),
            kind=str(symbol.get("kind") or "symbol"),
            name=optional_text("name"),
            qualname=optional_text("qualname"),
            signature=optional_text("signature"),
            start_line=optional_line("start_line"),
            end_line=optional_line("end_line"),
            evidence_visibility=visibility,
        ).as_dict()
        # SearchHit's public wire shape uses `lines`; retrieval locators consume
        # explicit endpoints. Retain both when adapting an indexed declaration.
        row["start_line"] = optional_line("start_line")
        row["end_line"] = optional_line("end_line")
        row["retrieval_supplement"] = "bounded-natural-language"
        row["score_basis"] = "natural-identifier-phrase-relevance"
        return row

    def _task_evidence_natural_retrieval_supplements(
        self,
        task: str,
        existing: Sequence[Mapping[str, object]],
        *,
        limit: int,
    ) -> list[dict[str, object]]:
        """Add bounded retrieval-only evidence without changing action authority."""
        self = cast("CodeMap", self)
        if limit < 10:
            return []
        existing_keys = {
            (
                str(row.get("path") or ""),
                str(row.get("symbol") or row.get("qualname") or row.get("name") or ""),
            )
            for row in existing
        }
        query = self._task_evidence_retrieval_query(task)
        terms, _truncated = self._task_natural_term_candidates(query)
        if not terms:
            return []
        term_set = set(terms)
        query_tokens = tuple(
            tuple(
                variant
                for variant in self._task_natural_term_variants(word)
                if variant in term_set
            )
            for word in re.findall(r"[A-Za-z]+", query.lower())
        )
        total, frequencies = self._session_lexical_document_frequencies(terms)
        scoped = self._task_evidence_scoped_method_supplement(
            task, query_tokens, frequencies, total, existing_keys
        )
        bound_reasons: set[str] = set()
        paths = self._task_evidence_natural_candidate_paths(
            query, existing, terms, bound_reasons
        )
        eligible: list[tuple[str, EvidenceVisibility]] = []
        for path in paths:
            visibility = self._task_evidence_visibility(path)
            if (
                visibility is None
                or visibility is EvidenceVisibility.DENY
                or self.policy.decide(path).evidence_visibility
                is EvidenceVisibility.DENY
                or not self._indexed_path_current(path)
            ):
                continue
            eligible.append((path, visibility))
        self._session_preload_symbols([path for path, _ in eligible])
        scored_rows: list[tuple[float, int, str, dict[str, object]]] = []
        for path_rank, (path, visibility) in enumerate(eligible):
            for score, symbol in self._task_evidence_scored_symbols(
                path, query_tokens, frequencies, total
            ):
                key = (
                    path,
                    str(symbol.get("qualname") or symbol.get("name") or ""),
                )
                if key in existing_keys:
                    continue
                existing_keys.add(key)
                scored_rows.append(
                    (
                        score,
                        path_rank,
                        str(symbol.get("qualname") or symbol.get("name") or ""),
                        self._task_evidence_supplement_row(
                            path, symbol, score=score, visibility=visibility
                        ),
                    )
                )
        scored_rows.sort(key=lambda row: (-row[0], row[1], row[2]))
        return ([scoped] if scoped is not None else []) + [
            row[3] for row in scored_rows[: 2 - int(scoped is not None)]
        ]

    def _task_evidence_attach_retrieval_supplements(
        self,
        result: TaskEvidenceDraft,
        task: str,
        *,
        limit: int,
    ) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        retrieval = result.get("retrieval")
        if not isinstance(retrieval, dict):
            return
        current = retrieval.get("results")
        if not isinstance(current, list):
            return
        rows = [row for row in current if isinstance(row, Mapping)]
        # A structural file/class owner is not a reason to hide an explicitly
        # named declaration. Reuse exact identity resolution for locators only;
        # these rows never change the independently selected edit/test owner.
        explicit = result["explicit_target"]
        literal_path = explicit["path"] if explicit["basis"] == "literal-path" else None
        exact, exact_complete, exact_terms = self._task_evidence_requested_identifiers(
            task, literal_path, canonical_rank=len(current) + 1
        )
        requested_keys = {
            self._task_evidence_requested_locator_key(row) for row in exact
        }
        if not requested_keys and literal_path:
            requested_keys.update(
                self._task_evidence_requested_locator_key(row)
                for row in rows
                if row.get("path") == literal_path
            )
        # Qualifying an explicit locator changes disclosure order only. Preserve
        # all matching identities when the request has multiple declarations;
        # neither ordering nor the return bound establishes a unique owner.
        current = sorted(
            current,
            key=lambda row: (
                self._task_evidence_requested_locator_key(row) not in requested_keys
            ),
        )
        existing_keys = {
            (str(row.get("path") or ""), str(row.get("symbol") or "")) for row in rows
        }
        exact = [
            row
            for row in exact
            if (
                str(row.get("path") or ""),
                str(row.get("qualname") or row.get("name") or ""),
            )
            not in existing_keys
        ]
        exact_bound = min(2, limit)
        supplements = [
            {
                **row,
                "retrieval_supplement": row.get(
                    "retrieval_supplement", "exact-qualified-identifier"
                ),
            }
            for row in exact[:exact_bound]
        ]
        natural = self._task_evidence_natural_retrieval_supplements(
            task,
            [*current, *supplements],
            limit=limit,
        )
        supplements.extend(natural[: 2 - len(supplements)])
        if exact_terms or literal_path:
            retrieval["exact_identifier_supplements"] = {
                "observed": len(exact),
                "returned": min(len(exact), exact_bound),
                "search_complete": exact_complete,
                "omitted": max(0, len(exact) - exact_bound),
                "ownership_authority": False,
            }
        if supplements:
            keep = max(0, limit - len(supplements))
            retrieval["results"] = [
                *current[:keep],
                *[self._task_evidence_retrieval_locator(row) for row in supplements],
            ]
            retrieval["canonical_omitted_results"] = max(0, len(current) - keep)
            retrieval["supplemental_results"] = len(supplements)
            retrieval["supplemental_authority"] = False
            retrieval["ordering"] = (
                "canonical-then-bounded-supplements"
                if any(
                    row.get("retrieval_supplement") == "exact-qualified-identifier"
                    for row in supplements
                )
                else "canonical-then-bounded-natural-language"
            )
        if requested_keys:
            retrieval["results"] = sorted(
                retrieval["results"],
                key=lambda row: (
                    self._task_evidence_requested_locator_key(row) not in requested_keys
                ),
            )
            retrieval["ordering"] = "requested-identifiers-then-retrieval-relevance"
        self._task_evidence_attach_class_declarations(result)
        self._task_evidence_attach_enclosing_functions(result)
        self._task_evidence_attach_candidate_verifiers(result, task)

    def _task_evidence_requested_identifiers(
        self,
        task: str,
        literal_path: str | None,
        *,
        canonical_rank: int,
    ) -> tuple[list[dict[str, object]], bool, tuple[str, ...]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        terms = tuple(
            term
            for term in self._task_action_exact_identifier_terms(task)
            if "." in term
        )
        exact, complete = self._task_action_qualified_identifier_index_evidence(
            terms, set(), canonical_rank=canonical_rank
        )
        if literal_path is None:
            return exact, complete, terms
        exact = [row for row in exact if row.get("path") == literal_path]
        known = {self._task_evidence_requested_locator_key(row) for row in exact}
        exact.extend(
            row
            for row in self._task_evidence_literal_identifier_supplements(
                task, literal_path
            )
            if self._task_evidence_requested_locator_key(row) not in known
        )
        return exact, complete, terms

    def _task_evidence_literal_identifier_supplements(
        self, task: str, path: str
    ) -> list[dict[str, object]]:
        """Disclose literal name matches within the caller's file, never owners."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if not self._task_evidence_declaration_visible(
            path
        ) or not self._indexed_path_current(path):
            return []
        # Retain common identifiers and private-member syntax for disclosure.
        # The action owner keeps its stricter rules for ownership admission.
        terms = {
            term.lower()
            for term in re.findall(
                r"[A-Za-z_$][\w$]*(?:\.#?[A-Za-z_$][\w$]*)*",
                task.replace(path, " "),
            )
        }
        symbols = [
            symbol
            for symbol in self._session_symbols_for_path(path)
            if terms.intersection(
                str(symbol.get(key) or "").lower() for key in ("name", "qualname")
            )
        ]
        symbols.sort(
            key=lambda symbol: (
                str(symbol.get("qualname") or "").lower() not in terms,
                line if isinstance(line := symbol.get("start_line"), int) else 0,
                str(symbol.get("qualname") or ""),
            )
        )
        visibility = self._task_evidence_visibility(path)
        assert visibility is not None
        return [
            {
                **self._task_evidence_supplement_row(
                    path, symbol, score=0, visibility=visibility
                ),
                "retrieval_supplement": "literal-identifier-in-requested-file",
                "score_basis": "literal-identifier-in-requested-file",
            }
            for symbol in symbols
        ]
