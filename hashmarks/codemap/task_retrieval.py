from __future__ import annotations

import heapq
import math
from contextlib import nullcontext
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, cast

from .decision_session import decision_scoped
from .model import EvidenceVisibility, SearchHit
from .query_primitives import (
    _TASK_EVIDENCE_FAMILIES,
    _TASK_GOVERNANCE_CUES,
    _TASK_STOPWORDS,
    _WORD_RE,
    _query_terms,
)
from .query_router import QueryRoute, route_query
from .repository_domains import RepositoryDomain, classify_repository_path

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from .engine import CodeMap


@dataclass
class _TaskFindFusion:
    path_scores: dict[str, float]
    best_hit: dict[str, SearchHit]
    selected: list[str]


@dataclass(frozen=True, slots=True)
class _ScoreSurface:
    path: str
    name: str
    qualname: str
    signature: str


_FINAL_IDENTITY_WEIGHTS = (120.0, 100.0, 70.0, 55.0, 45.0)
_FINAL_TOKEN_WEIGHTS = (30.0, 20.0, 12.0, 15.0, 8.0)
_PRESCORE_IDENTITY_WEIGHTS = (120.0, 100.0, 70.0, 55.0, 45.0)
_PRESCORE_TOKEN_WEIGHTS = (24.0, 16.0, 10.0, 12.0, 5.0)


def _nonempty_str(value: object) -> str | None:
    text = str(value or "")
    return text or None


def _positive_int(value: object) -> int | None:
    number = int(value or 0)
    return number or None


def _evidence_visibility(value: object) -> EvidenceVisibility:
    try:
        return EvidenceVisibility(str(value or EvidenceVisibility.SOURCE.value))
    except ValueError:
        return EvidenceVisibility.SOURCE


def _path_is_within(candidate: str, parent: str) -> bool:
    try:
        Path(candidate).relative_to(Path(parent))
    except ValueError:
        return False
    return True


_TASK_SCOPE_EXPANSIONS: tuple[tuple[frozenset[str], tuple[str, ...]], ...] = (
    (frozenset({"frontend"}), ("frontend", "readme", "agents")),
    (frozenset({"backend", "fastapi", "api"}), ("backend", "readme", "agents")),
    (
        frozenset({"plan", "plans", "goon", "goons"}),
        ("plan", "goon", "agents", "readme"),
    ),
    (
        frozenset({"make", "certify", "certification", "setup", "bootstrap"}),
        ("make", "certification", "docs", "contract"),
    ),
    (
        frozenset({"generated", "openapi"}),
        ("generated", "contract", "agents", "readme"),
    ),
    (
        frozenset({"schedule", "scheduler"}),
        ("schedule", "scheduler", "ownership", "backend", "agents"),
    ),
)


class TaskRetrievalMixin:
    _TASK_CACHE_PREFLIGHT_METHODS = frozenset(
        {
            "task_action_map",
            "task_decision_brief",
            "task_decision_packet",
        }
    )

    def _decision_preflight(self, method_name, args, kwargs):
        """Reconcile known stale task evidence before authority is sampled."""
        if method_name not in self._TASK_CACHE_PREFLIGHT_METHODS or not args:
            return
        task = args[0]
        if not isinstance(task, str):
            return
        raw_limit = kwargs.get("limit", 20)
        if type(raw_limit) is not int or raw_limit < 1:
            return
        self._reconcile_cached_task_paths(task, raw_limit, probe_on_miss=True)

    def _remember_task_resurrection_paths(
        self,
        recent_key: tuple[str, int],
        recent_paths: tuple[str, ...],
        stale_paths: tuple[str, ...],
    ) -> tuple[str, ...]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if not stale_paths:
            return recent_paths
        remembered = tuple(sorted({*recent_paths, *stale_paths}))
        self._task_recent_authority_paths[recent_key] = remembered
        if len(self._task_recent_authority_paths) > 256:
            # Preserve only the task proving stale authority so the pressure
            # event cannot erase the resurrection fence it just established.
            self._task_recent_authority_paths.clear()
            self._task_recent_authority_paths[recent_key] = remembered
        return remembered

    def _reconcile_active_task_stale_paths(self, stale_paths: tuple[str, ...]) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if not stale_paths:
            return
        # Missing authority may have moved to an unknown path, which requires
        # repository discovery. Byte changes and file->symlink transitions are
        # exact-path changes and stay path-scoped.
        if any(not (self.workspace / path).exists() for path in stale_paths):
            self.sync()
        else:
            self.sync(stale_paths)

    def _task_resurrection_paths(
        self, recent_paths: tuple[str, ...]
    ) -> tuple[str, ...]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        return tuple(
            sorted(
                path
                for path in recent_paths
                if self._path_admitted_for_analysis(path)
                and (self.workspace / path).is_file()
                and not (self.workspace / path).is_symlink()
                and not self._indexed_path_current(path)
            )
        )

    def _reconcile_task_resurrection_paths(
        self, recent_paths: tuple[str, ...]
    ) -> tuple[str, ...]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        restored = self._task_resurrection_paths(recent_paths)
        if restored:
            self.sync(restored)
        return restored

    def _reconcile_cached_task_paths(
        self, task: str, limit: int, *, probe_on_miss: bool = False
    ) -> tuple[str, ...]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if self._decision_session_depth > 0:
            return ()
        generation = self.store.generation()
        key = (generation, task, int(limit))
        cached = self._task_result_cache.get(key)
        authority_paths = self._task_authority_paths_cache.get(key, ())
        recent_key = (task, int(limit))
        recent_authority_paths = self._task_recent_authority_paths.get(recent_key, ())
        if cached is None and not authority_paths and not recent_authority_paths:
            if not probe_on_miss:
                return ()
            # Cache/history pressure must not make an old task permanently weaker
            # than cold truth. Authority-producing decisions may probe canonical
            # retrieval before their decision session opens; this remains read-only
            # evidence selection. Task evidence deliberately does not use this path:
            # it owns an independent closing freshness fence and must preserve the
            # selected stale evidence rather than silently reselect it.
            cached = self._find_task_impl(task, limit=limit, ensure_ready=False)

        active_paths = {*(hit.path for hit in (cached or ())), *authority_paths}
        active_stale = tuple(
            sorted(
                path for path in active_paths if not self._indexed_path_current(path)
            )
        )
        # The preflight may be the first decision for this task after an
        # unsignaled disappearance. Preserve only stale task-local paths before
        # reconciliation retires their rows; they remain non-authoritative.
        recent_authority_paths = self._remember_task_resurrection_paths(
            recent_key, recent_authority_paths, active_stale
        )
        self._reconcile_active_task_stale_paths(active_stale)

        # Missing/symlink tombstones do no work. Exact regular-file return pays
        # one admitted path-scoped sync, closing delete/recreate and symlink ABA
        # without a watcher or repository-wide polling.
        restored = self._reconcile_task_resurrection_paths(recent_authority_paths)
        return tuple(sorted({*active_stale, *restored}))

    @staticmethod
    def _repository_domain_boost(
        path: str, route: QueryRoute
    ) -> tuple[float, tuple[str, ...]]:
        """Return bounded intent-scoped control-surface preference.

        Domains are derived retrieval hints, never visibility or authority.  No
        boost is applied when the query did not explicitly imply a repository
        domain, which keeps ordinary symbol/test retrieval behavior unchanged.
        """
        if not route.preferred_domains:
            return 0.0, ()
        path_domains = classify_repository_path(path)
        matches = tuple(
            domain for domain in route.preferred_domains if domain in path_domains
        )
        if not matches:
            return 0.0, ()
        weights = {
            domain: max(16.0, 42.0 - index * 7.0)
            for index, domain in enumerate(route.preferred_domains)
        }
        boost = max(weights[domain] for domain in matches)
        control = {
            RepositoryDomain.ARCHITECTURE,
            RepositoryDomain.OWNERSHIP,
            RepositoryDomain.BUILD,
            RepositoryDomain.PLAN,
            RepositoryDomain.CONFIG,
            RepositoryDomain.SCRIPT,
            RepositoryDomain.CONTRACT,
            RepositoryDomain.DOC,
        }
        if any(domain in control for domain in matches):
            boost += 12.0
        return min(60.0, boost), tuple(domain.value for domain in matches)

    def _apply_repository_domain_hints(
        self, rows: tuple[dict, ...], route: QueryRoute
    ) -> tuple[dict, ...]:
        if not route.preferred_domains:
            return rows
        enriched: list[dict] = []
        path_hints: dict[str, tuple[float, tuple[str, ...]]] = {}
        for row in rows:
            path = str(row.get("path", ""))
            hint = path_hints.get(path)
            if hint is None:
                hint = self._repository_domain_boost(path, route)
                path_hints[path] = hint
            boost, matches = hint
            if boost <= 0:
                enriched.append(row)
                continue
            value = dict(row)
            value["_relation_boost"] = (
                float(value.get("_relation_boost", 0.0) or 0.0) + boost
            )
            value["_repository_domains"] = matches
            enriched.append(value)
        return tuple(enriched)

    @staticmethod
    def _score_surface(row: dict) -> _ScoreSurface:
        return _ScoreSurface(
            path=str(row.get("path", "")).lower(),
            name=str(row.get("name", "")).lower(),
            qualname=str(row.get("qualname", "")).lower(),
            signature=str(row.get("signature", "")).lower(),
        )

    @staticmethod
    def _identity_score(
        raw_query: str,
        surface: _ScoreSurface,
        weights: tuple[float, float, float, float, float],
    ) -> float:
        if not raw_query:
            return 0.0
        exact_qual, exact_name, qual_contains, path_contains, signature_contains = (
            weights
        )
        return sum(
            (
                exact_qual if raw_query == surface.qualname else 0.0,
                exact_name if raw_query == surface.name else 0.0,
                qual_contains if raw_query in surface.qualname else 0.0,
                path_contains if raw_query in surface.path else 0.0,
                signature_contains if raw_query in surface.signature else 0.0,
            )
        )

    @staticmethod
    def _token_score(
        tokens: Sequence[str],
        surface: _ScoreSurface,
        weights: tuple[float, float, float, float, float],
    ) -> float:
        exact_name, name_contains, path_contains, qual_contains, signature_contains = (
            weights
        )
        return sum(
            (
                exact_name
                if token == surface.name
                else name_contains
                if token in surface.name
                else 0.0
            )
            + (path_contains if token in surface.path else 0.0)
            + (qual_contains if token in surface.qualname else 0.0)
            + (signature_contains if token in surface.signature else 0.0)
            for token in tokens
        )

    def _score(
        self,
        query: str,
        row: dict,
        *,
        ranks: dict[str, float] | None = None,
        recent: set[str] | None = None,
        tokens: list[str] | None = None,
        raw_query: str | None = None,
    ) -> float:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        raw = query.strip().lower() if raw_query is None else raw_query
        tokens = _query_terms(query) if tokens is None else tokens
        surface = self._score_surface(row)
        score = self._identity_score(raw, surface, _FINAL_IDENTITY_WEIGHTS)
        score += self._token_score(tokens, surface, _FINAL_TOKEN_WEIGHTS)
        if ranks is not None:
            score += 18.0 * float(ranks.get(str(row.get("path", "")), 0.0))
        if recent and str(row.get("path", "")) in recent:
            score += 24.0
        if self._is_test_path(str(row.get("path", ""))):
            score += (
                12.0
                if any(token in {"test", "tests", "spec"} for token in tokens)
                else -16.0
            )
        score += float(row.get("_relation_boost", 0.0) or 0.0)
        return score

    def _candidate_prescore(
        self,
        query: str,
        row: dict,
        *,
        tokens: tuple[str, ...],
        raw_query: str,
    ) -> float:
        """Cheap stage-one score used only to bound the rerank working set.

        This deliberately excludes freshness lookups and any future expensive
        reranker/provider.  It preserves exact name/path/qualname matches and
        relation boosts so the bounded stage cannot become a random truncation.
        """
        surface = self._score_surface(row)
        return (
            float(row.get("_relation_boost", 0.0) or 0.0)
            + self._identity_score(raw_query, surface, _PRESCORE_IDENTITY_WEIGHTS)
            + self._token_score(tokens, surface, _PRESCORE_TOKEN_WEIGHTS)
        )

    @staticmethod
    def _best_rerank_candidate_by_path(
        scored: Sequence[tuple[tuple[float, str, str, int], dict]],
    ) -> dict[str, tuple[tuple[float, str, str, int], dict]]:
        best_by_path: dict[str, tuple[tuple[float, str, str, int], dict]] = {}
        for item in scored:
            path = str(item[1].get("path", ""))
            current = best_by_path.get(path)
            if current is None or item[0] < current[0]:
                best_by_path[path] = item
        return best_by_path

    def _bounded_rerank_rows(
        self,
        query: str,
        rows: tuple[dict, ...],
        *,
        limit: int,
        tokens: tuple[str, ...],
    ) -> tuple[dict, ...]:
        """Keep the full candidate set for small queries; bound huge reranks.

        The cap is intentionally generous and path-diverse.  This makes the
        stage behavior a scaling optimization while retained recall gates stay
        authoritative.  Future model/semantic rerankers may plug into stage two
        without ever seeing the entire repository candidate surface.
        """
        rerank_limit = max(256, limit * 16)
        if len(rows) <= rerank_limit:
            return rows
        raw = query.strip().lower()
        # Score every candidate once, then use bounded top-N selection rather
        # than sorting the entire broad pool. The original ordering is stable
        # on ties, so retain the input index as the final deterministic key.
        scored: list[tuple[tuple[float, str, str, int], dict]] = []
        for index, row in enumerate(rows):
            key = (
                -self._candidate_prescore(query, row, tokens=tokens, raw_query=raw),
                str(row.get("path", "")),
                str(row.get("qualname", "")),
                index,
            )
            scored.append((key, row))
        # Reserve one strong candidate per path before filling by pre-score so
        # a symbol-dense file cannot consume the entire rerank working set.
        path_quota = min(64, max(16, rerank_limit // 4))
        selected: list[dict] = []
        selected_ids: set[int] = set()
        best_by_path = self._best_rerank_candidate_by_path(scored)
        for _key, row in heapq.nsmallest(
            path_quota, best_by_path.values(), key=lambda item: item[0]
        ):
            selected.append(row)
            selected_ids.add(id(row))

        # At most path_quota rows can be removed from the global top list by the
        # diversity reservation, so rerank_limit+path_quota is sufficient to
        # reproduce the old full-sort fill exactly.
        global_top = heapq.nsmallest(
            min(len(scored), rerank_limit + path_quota),
            scored,
            key=lambda item: item[0],
        )
        for _key, row in global_top:
            if id(row) in selected_ids:
                continue
            selected.append(row)
            if len(selected) >= rerank_limit:
                break
        return tuple(selected)

    @staticmethod
    def _task_query_term_score(
        term: str,
        total: int,
        frequencies: Mapping[str, int],
        original: Mapping[str, str],
    ) -> tuple[float, int, str]:
        df = frequencies.get(term, total)
        rarity = math.log((max(1, total) + 1) / (df + 1)) + 1.0
        raw = original.get(term, term)
        bonus = 0.0
        if any(ch.isupper() for ch in raw[1:]) or raw.isupper():
            bonus += 2.5
        if any(ch in raw for ch in "_-/"):
            bonus += 1.5
        if term in {
            "api",
            "goon",
            "plan",
            "fleet",
            "uv",
            "scout",
            "codemap",
            "hashmarks",
            "executor",
            "certification",
            "workspace",
            "runtime",
            "contract",
            "identity",
            "schedule",
            "repository",
        }:
            bonus += 1.0
        return rarity + bonus, len(term), term

    def _formulate_task_query_base(self, task: str, *, max_terms: int = 10) -> str:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        raw_tokens = _WORD_RE.findall(task)
        words: list[str] = []
        original: dict[str, str] = {}
        for raw in raw_tokens:
            low = raw.lower().strip("_-")
            if len(low) < 2 or low in _TASK_STOPWORDS:
                continue
            if low not in words:
                words.append(low)
                original[low] = raw
        total, frequencies = self._session_lexical_document_frequencies(words)

        ranked = sorted(
            (term for term in words if term in frequencies),
            key=lambda term: self._task_query_term_score(
                term, total, frequencies, original
            ),
            reverse=True,
        )
        selected = ranked[:max_terms]
        return " ".join(selected) if selected else " ".join(words[:max_terms])

    @staticmethod
    def _bounded_query_terms(
        base: str, additions: Sequence[str], *, limit: int
    ) -> list[str]:
        values = base.split()
        for value in additions:
            if value not in values:
                values.append(value)
            if len(values) >= limit:
                break
        return values

    def task_query_views(self, task: str) -> dict[str, str]:
        """Return deterministic candidate-visible retrieval views for one task."""
        base = self._formulate_task_query_base(task)
        raw_tokens = _WORD_RE.findall(task)
        visible_words = {value.lower() for value in raw_tokens}
        additions: list[str] = []
        if visible_words & _TASK_GOVERNANCE_CUES:
            additions.extend(
                (
                    "ownership",
                    "authority",
                    "architecture",
                    "contract",
                    "agents",
                    "readme",
                )
            )
        for cues, values in _TASK_SCOPE_EXPANSIONS:
            if visible_words & cues:
                additions.extend(values)
        expanded = self._bounded_query_terms(base, additions, limit=16)
        evidence_additions: list[str] = []
        for cues, values in _TASK_EVIDENCE_FAMILIES:
            if visible_words & cues:
                evidence_additions.extend(values)
        evidence = self._bounded_query_terms(base, evidence_additions, limit=18)
        return {
            "schema": "hashmarks.task-query-views.v2",
            "base": base,
            "governance": " ".join(expanded),
            "evidence": " ".join(evidence),
        }

    def formulate_task_query(self, task: str, *, max_terms: int = 16) -> str:
        """Derive a bounded repository query from a full task description.

        This public convenience returns the governance-aware view.  ``find_task``
        fuses it with the base rare-term view so the new control-surface search can
        add evidence without replacing v0.10.18's established retrieval behavior.
        """
        if max_terms < 1:
            raise ValueError("max_terms must be >= 1")
        view = self.task_query_views(task)["governance"]
        return " ".join(view.split()[:max_terms])

    @staticmethod
    def _rare_symbol_by_path(
        token: str, symbols: Sequence[dict[str, object]]
    ) -> dict[str, dict[str, object]]:
        selected: dict[str, dict[str, object]] = {}
        for row in symbols:
            text = " ".join(
                str(row.get(key) or "").lower() for key in ("path", "name", "qualname")
            )
            if token in text:
                selected.setdefault(str(row.get("path") or ""), row)
        return selected

    @staticmethod
    def _rare_task_anchor_hit(
        path: str,
        row: Mapping[str, object],
        symbol: Mapping[str, object] | None,
    ) -> SearchHit:
        visibility_raw = str(
            row.get("evidence_visibility") or EvidenceVisibility.SOURCE.value
        )
        try:
            visibility = EvidenceVisibility(visibility_raw)
        except ValueError:
            visibility = EvidenceVisibility.SOURCE
        return SearchHit(
            path=path,
            score=1000.0 if symbol is not None else 900.0,
            kind=str(symbol.get("kind") or "symbol") if symbol is not None else "file",
            name=_nonempty_str(symbol.get("name")) if symbol is not None else None,
            qualname=_nonempty_str(symbol.get("qualname"))
            if symbol is not None
            else None,
            signature=_nonempty_str(symbol.get("signature"))
            if symbol is not None
            else None,
            start_line=_positive_int(symbol.get("start_line"))
            if symbol is not None
            else None,
            end_line=_positive_int(symbol.get("end_line"))
            if symbol is not None
            else None,
            evidence_visibility=visibility,
        )

    def _rare_task_anchor_hits(
        self, token: str, *, limit: int
    ) -> tuple[SearchHit, ...]:
        """Return exact indexed evidence for one rare task-local identifier.

        The projection combines exact lexical-token membership with bounded path
        matches, then enriches only those paths with already-indexed symbols.
        Static ownership traversal remains a later action-map concern.  No file
        contents are scanned and no alternate ranking authority is introduced.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        normalized = token.lower()
        file_rows = self._session_lexical_file_candidates(
            [normalized], limit=max(8, min(32, limit * 2))
        )
        path_rows = self.store.path_candidates(
            [normalized], limit=max(8, min(32, limit * 2))
        )
        by_path: dict[str, dict[str, object]] = {}
        for row in [*file_rows, *path_rows]:
            path = str(row.get("path") or "")
            if path:
                by_path.setdefault(path, dict(row))
        if not by_path:
            return ()
        symbols = self.store.symbols_for_paths(
            list(by_path), limit=max(64, min(512, len(by_path) * 16))
        )
        symbol_by_path = self._rare_symbol_by_path(normalized, symbols)

        def locality_order(path: str) -> tuple[int, int, str]:
            domains = set(classify_repository_path(path))
            is_test = RepositoryDomain.TEST in domains
            parts = {part.lower() for part in Path(path).parts}
            archive_like = bool(parts.intersection({"archive", "legacy", "deprecated"}))
            # Verification first gives structural traversal a task-local root;
            # active source stays ahead of obvious archival/legacy decoys.
            return (
                0 if is_test else 2 if archive_like else 1,
                len(Path(path).parts),
                path,
            )

        output: list[SearchHit] = []
        for path in sorted(by_path, key=locality_order):
            row = by_path[path]
            symbol = symbol_by_path.get(path)
            output.append(self._rare_task_anchor_hit(path, row, symbol))
            if len(output) >= limit:
                break
        return tuple(output)

    def _task_local_island_terms(self, task: str) -> tuple[str, ...]:
        """Return bounded rare lexical terms eligible for locality evidence."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if len(_WORD_RE.findall(task)) < 2:
            return ()
        locality_generic = {
            "accepted",
            "actually",
            "active",
            "behavior",
            "change",
            "drives",
            "implementation",
            "owner",
            "request",
            "response",
            "that",
            "update",
            "verification",
            "verify",
        }
        terms = [
            term
            for term in dict.fromkeys(_query_terms(task))
            if len(term) >= 4
            and term not in _TASK_STOPWORDS
            and term not in locality_generic
            and not term.isdigit()
        ]
        if len(terms) < 2:
            return ()
        total_docs, frequencies = self._session_lexical_document_frequencies(terms)
        max_documents = max(12, min(64, int(max(total_docs, 1) * 0.25)))
        rare_terms = [
            term for term in terms if 0 < int(frequencies.get(term, 0)) <= max_documents
        ]
        rare_terms.sort(
            key=lambda term: (int(frequencies.get(term, 0)), -len(term), term)
        )
        return tuple(rare_terms[:6])

    def _task_local_island_rows(
        self, selected_terms: tuple[str, ...], *, limit: int
    ) -> tuple[list[dict[str, object]], dict[str, set[RepositoryDomain]]] | None:
        """Validate one bounded lexical island and retain its path domains."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if len(selected_terms) < 2:
            return None
        rows = self._session_lexical_file_candidates(
            list(selected_terms), limit=max(32, min(96, limit * 4))
        )
        island = [row for row in rows if int(row.get("matches") or 0) >= 2]
        if not island or len(island) > 16:
            return None
        domains_by_path = {
            str(row.get("path") or ""): set(
                classify_repository_path(str(row.get("path") or ""))
            )
            for row in island
        }
        test_rows = [
            row
            for row in island
            if RepositoryDomain.TEST in domains_by_path[str(row.get("path") or "")]
        ]
        if len(test_rows) != 1:
            return None
        action_domains = {
            RepositoryDomain.SOURCE,
            RepositoryDomain.SCRIPT,
            RepositoryDomain.CONFIG,
            RepositoryDomain.BUILD,
            RepositoryDomain.CONTRACT,
        }
        if not any(
            RepositoryDomain.TEST not in domains_by_path[str(row.get("path") or "")]
            and bool(
                domains_by_path[str(row.get("path") or "")].intersection(action_domains)
            )
            for row in island
        ):
            return None
        return island, domains_by_path

    def _task_local_island_symbols(
        self, island: list[dict[str, object]], selected_terms: tuple[str, ...]
    ) -> dict[str, dict[str, object]]:
        """Bind task-local island paths to already-indexed matching symbols."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        paths = [str(row.get("path") or "") for row in island if row.get("path")]
        symbols = self.store.symbols_for_paths(
            paths, limit=max(64, min(512, len(paths) * 16))
        )
        symbol_by_path: dict[str, dict[str, object]] = {}
        selected_set = set(selected_terms)
        for row in symbols:
            text_terms = set(
                _query_terms(
                    " ".join(
                        str(row.get(key) or "")
                        for key in ("name", "qualname", "signature")
                    )
                )
            )
            if len(selected_set.intersection(text_terms)) >= 2:
                symbol_by_path.setdefault(str(row.get("path") or ""), row)
        return symbol_by_path

    def _task_local_lexical_island_hits(
        self, task: str, *, limit: int
    ) -> tuple[SearchHit, ...]:
        """Return a bounded multi-term task-local evidence island when one is unique.

        This is a repository-evidence projection only. It uses the existing lexical
        index and activates only for a small island with one test surface and at
        least one actionable source surface; otherwise normal RRF stays authoritative.
        """
        selected_terms = self._task_local_island_terms(task)
        island_state = self._task_local_island_rows(selected_terms, limit=limit)
        if island_state is None:
            return ()
        island, domains_by_path = island_state
        symbol_by_path = self._task_local_island_symbols(island, selected_terms)

        def locality_order(row: dict[str, object]) -> tuple[int, int, int, str]:
            path = str(row.get("path") or "")
            domains = domains_by_path[path]
            parts = {part.lower() for part in Path(path).parts}
            archive_like = bool(
                parts.intersection({"archive", "legacy", "deprecated", "vendor"})
            )
            is_test = RepositoryDomain.TEST in domains
            return (
                0 if is_test else 2 if archive_like else 1,
                -int(row.get("matches") or 0),
                len(Path(path).parts),
                path,
            )

        output: list[SearchHit] = []
        for index, row in enumerate(sorted(island, key=locality_order)):
            path = str(row.get("path") or "")
            symbol = symbol_by_path.get(path)
            visibility_raw = str(
                row.get("evidence_visibility") or EvidenceVisibility.SOURCE.value
            )
            try:
                visibility = EvidenceVisibility(visibility_raw)
            except ValueError:
                visibility = EvidenceVisibility.SOURCE
            output.append(
                SearchHit(
                    path=path,
                    score=980.0 - index,
                    kind=str(symbol.get("kind") or "symbol")
                    if symbol is not None
                    else "file",
                    name=(str(symbol.get("name") or "") or None)
                    if symbol is not None
                    else None,
                    qualname=(str(symbol.get("qualname") or "") or None)
                    if symbol is not None
                    else None,
                    signature=(str(symbol.get("signature") or "") or None)
                    if symbol is not None
                    else None,
                    start_line=(int(symbol.get("start_line") or 0) or None)
                    if symbol is not None
                    else None,
                    end_line=(int(symbol.get("end_line") or 0) or None)
                    if symbol is not None
                    else None,
                    evidence_visibility=visibility,
                )
            )
            if len(output) >= limit:
                break
        return tuple(output)

    def _task_find_cache_key(
        self, task: str, limit: int, *, ensure_ready: bool = True
    ) -> tuple[tuple[int, str, int], tuple[SearchHit, ...] | None]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if ensure_ready:
            self._ensure_map_ready()
        generation = self.store.generation()
        key = (generation, task, int(limit))
        cached = self._task_result_cache.get(key)
        if self._decision_session_depth > 0:
            stat = "task_result_hit" if cached is not None else "task_result_miss"
            self._decision_session_stats[stat] += 1
        return key, cached

    def _task_find_trim_cache(self, generation: int) -> None:
        if (
            len(self._task_result_cache) < 256
            and len(self._task_authority_paths_cache) < 256
        ):
            return
        self._task_result_cache = {
            key: value
            for key, value in self._task_result_cache.items()
            if key[0] == generation
        }
        self._task_authority_paths_cache = {
            key: value
            for key, value in self._task_authority_paths_cache.items()
            if key[0] == generation
        }
        if len(self._task_result_cache) >= 256:
            self._task_result_cache.clear()
        if len(self._task_authority_paths_cache) >= 256:
            self._task_authority_paths_cache.clear()

    @staticmethod
    def _task_is_identifier_token(token: str) -> bool:
        if len(token) < 3:
            return False
        if "_" not in token and not any(ch.isupper() for ch in token[1:]):
            return False
        return not token.isupper() or any(ch.isdigit() for ch in token)

    @classmethod
    def _task_raw_identifier_tokens(cls, task: str) -> list[str]:
        return [
            token
            for token in _WORD_RE.findall(task)
            if cls._task_is_identifier_token(token)
        ]

    @staticmethod
    def _task_cue_words(task: str) -> set[str]:
        return {value.lower() for value in _WORD_RE.findall(task)}

    @staticmethod
    def _task_broad_authority_cues() -> set[str]:
        return {
            "config",
            "configuration",
            "settings",
            "makefile",
            "pyproject",
            "toml",
            "yaml",
            "yml",
            "sql",
            "schema",
            "policy",
            "invariant",
            "authority",
            "agents",
        }

    @staticmethod
    def _task_fast_identifier_tokens(raw_tokens: Sequence[str]) -> list[str]:
        return [
            token
            for token in raw_tokens
            if any(ch.isdigit() for ch in token) or "_" in token
        ]

    def _task_rare_identifier(
        self, raw_tokens: Sequence[str], cue_words: set[str]
    ) -> str | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        fast_tokens = self._task_fast_identifier_tokens(raw_tokens)
        if not fast_tokens:
            return None
        if cue_words.intersection(self._task_broad_authority_cues()):
            return None
        _total_docs, frequencies = self._session_lexical_document_frequencies(
            [token.lower() for token in fast_tokens[:4]]
        )
        for token in fast_tokens:
            frequency = int(frequencies.get(token.lower(), 0))
            if 0 < frequency <= 8:
                return token
        return None

    def _task_rare_identifier_result(
        self, token: str, limit: int
    ) -> tuple[SearchHit, ...] | None:
        fast_hits = self._rare_task_anchor_hits(
            token, limit=max(20, min(40, limit * 2))
        )
        unique_paths = list(dict.fromkeys(hit.path for hit in fast_hits))
        domains = {
            domain for path in unique_paths for domain in classify_repository_path(path)
        }
        has_test = RepositoryDomain.TEST in domains
        action_domains = {
            RepositoryDomain.SOURCE,
            RepositoryDomain.SCRIPT,
            RepositoryDomain.CONFIG,
            RepositoryDomain.BUILD,
            RepositoryDomain.CONTRACT,
        }
        if has_test and domains.intersection(action_domains) and len(unique_paths) >= 2:
            return tuple(fast_hits[:limit])
        return None

    def _task_local_island_result(
        self, task: str, limit: int, cue_words: set[str]
    ) -> tuple[SearchHit, ...] | None:
        if cue_words.intersection(self._task_broad_authority_cues()):
            return None
        hits = self._task_local_lexical_island_hits(task, limit=limit)
        return hits or None

    @staticmethod
    def _task_sequence_specs(
        views: Mapping[str, str], limit: int
    ) -> list[tuple[str, float, int]]:
        fetch = max(40, min(80, limit * 4))
        evidence_fetch = max(24, min(40, limit * 2))
        specs = [(views["base"], 1.2, fetch), (views["governance"], 1.0, fetch)]
        if views["evidence"] not in {views["base"], views["governance"]}:
            specs.append((views["evidence"], 0.8, evidence_fetch))
        seen: set[str] = set()
        unique: list[tuple[str, float, int]] = []
        for view, weight, view_fetch in specs:
            if view in seen:
                continue
            seen.add(view)
            unique.append((view, weight, view_fetch))
        return unique

    def _task_find_sequences(
        self, task: str, limit: int
    ) -> tuple[dict[str, str], tuple[tuple[tuple[SearchHit, ...], float], ...]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        views = self.task_query_views(task)
        specs = self._task_sequence_specs(views, limit)
        rows: list[tuple[tuple[SearchHit, ...], float]] = []
        session_scope = (
            nullcontext(self)
            if self._decision_session_depth > 0
            else self.decision_session()
        )
        with session_scope:
            for view, weight, view_fetch in specs:
                rows.append((self.find(view, limit=view_fetch), weight))
        return views, tuple(rows)

    @staticmethod
    def _task_fuse_sequences(
        sequences: Sequence[tuple[Sequence[SearchHit], float]],
    ) -> tuple[dict[str, float], dict[str, SearchHit], list[str]]:
        path_scores: dict[str, float] = {}
        best_hit: dict[str, SearchHit] = {}
        for sequence, weight in sequences:
            seen: set[str] = set()
            path_rank = 0
            for hit in sequence:
                if hit.path in seen:
                    continue
                seen.add(hit.path)
                path_rank += 1
                path_scores[hit.path] = path_scores.get(hit.path, 0.0) + weight / (
                    60.0 + path_rank
                )
                current = best_hit.get(hit.path)
                if current is None or hit.score > current.score:
                    best_hit[hit.path] = hit
        ranked_paths = sorted(path_scores, key=lambda path: (-path_scores[path], path))
        return path_scores, best_hit, ranked_paths

    @staticmethod
    def _task_anchor_hit(anchor: Mapping[str, object]) -> SearchHit | None:
        anchor_path = str(anchor.get("path") or "")
        if not anchor_path:
            return None
        return SearchHit(
            path=anchor_path,
            score=1000.0,
            kind=str(anchor.get("kind") or "symbol"),
            name=_nonempty_str(anchor.get("name")),
            qualname=_nonempty_str(anchor.get("qualname")),
            signature=_nonempty_str(anchor.get("signature")),
            start_line=_positive_int(anchor.get("start_line")),
            end_line=_positive_int(anchor.get("end_line")),
            evidence_visibility=_evidence_visibility(anchor.get("evidence_visibility")),
        )

    def _task_preserve_exact_anchor(
        self, raw_tokens: Sequence[str], fusion: _TaskFindFusion
    ) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        rows = self._session_exact_symbol_candidates(raw_tokens, limit=64)
        token_order = {token.lower(): index for index, token in enumerate(raw_tokens)}
        rows.sort(
            key=lambda row: (
                token_order.get(
                    str(row.get("name") or row.get("qualname") or "").lower(),
                    len(token_order),
                ),
                str(row.get("path") or ""),
                int(row.get("start_line") or 0),
            )
        )
        if not rows:
            return
        anchor_hit = self._task_anchor_hit(rows[0])
        if anchor_hit is None:
            return
        fusion.best_hit[anchor_hit.path] = anchor_hit
        fusion.path_scores[anchor_hit.path] = max(
            fusion.path_scores.get(anchor_hit.path, 0.0), 2.0 / 61.0
        )
        fusion.selected.append(anchor_hit.path)

    def _task_component_hits(self, token: str) -> list[SearchHit]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        token_lower = token.lower()
        hits: list[SearchHit] = []
        for hit in self.find(token, limit=10):
            haystack = " ".join(
                value.lower()
                for value in (hit.path, hit.name or "", hit.qualname or "")
            )
            if token_lower in haystack:
                hits.append(hit)
        return hits

    @staticmethod
    def _task_preserve_component_hits(
        hits: Sequence[SearchHit], fusion: _TaskFindFusion, *, limit: int = 2
    ) -> None:
        for preserved, hit in enumerate(hits[:limit]):
            current = fusion.best_hit.get(hit.path)
            fusion.best_hit[hit.path] = (
                hit if current is None or hit.score > current.score else current
            )
            fusion.path_scores[hit.path] = max(
                fusion.path_scores.get(hit.path, 0.0), 1.8 / (61.0 + preserved)
            )
            if hit.path not in fusion.selected:
                fusion.selected.append(hit.path)

    def _task_preserve_components(
        self, raw_tokens: Sequence[str], fusion: _TaskFindFusion
    ) -> None:
        for token in raw_tokens[:3]:
            hits = self._task_component_hits(token)
            if not hits or len(hits) > 8:
                continue
            self._task_preserve_component_hits(hits, fusion)

    @staticmethod
    def _task_is_omitted_alnum_candidate(token: str, visible_terms: set[str]) -> bool:
        lowered = token.lower()
        return (
            token == lowered
            and len(lowered) >= 3
            and lowered not in visible_terms
            and any(ch.isalpha() for ch in lowered)
            and any(ch.isdigit() for ch in lowered)
        )

    @classmethod
    def _task_omitted_alnum_tokens(
        cls, task: str, views: Mapping[str, str]
    ) -> tuple[str, ...]:
        visible_terms = {
            term.lower()
            for key in ("base", "governance", "evidence")
            for term in views[key].split()
        }
        tokens = (
            token
            for token in _WORD_RE.findall(task)
            if cls._task_is_omitted_alnum_candidate(token, visible_terms)
        )
        return tuple(dict.fromkeys(tokens))[:32]

    @staticmethod
    def _task_hits_for_token(
        token: str, hits: Sequence[SearchHit]
    ) -> tuple[SearchHit, ...]:
        lowered = token.lower()
        return tuple(
            hit
            for hit in hits
            if lowered
            in " ".join(
                value.lower()
                for value in (hit.path, hit.name or "", hit.qualname or "")
            )
        )

    def _task_preserve_omitted_alnum_components(
        self,
        task: str,
        views: Mapping[str, str],
        cue_words: set[str],
        fusion: _TaskFindFusion,
    ) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        tokens = self._task_omitted_alnum_tokens(task, views)
        if not tokens:
            return
        preserve_limit = (
            3
            if cue_words.intersection({"config", "configuration", "policy", "settings"})
            else 2
        )
        proven = 0
        for offset in range(0, len(tokens), 8):
            chunk = tokens[offset : offset + 8]
            hits = self.find(" ".join(chunk), limit=40)
            for token in chunk:
                local_hits = self._task_hits_for_token(token, hits)
                if not local_hits or len(local_hits) > 8:
                    continue
                self._task_preserve_component_hits(
                    local_hits, fusion, limit=preserve_limit
                )
                proven += 1
                if proven >= 2:
                    return

    @staticmethod
    def _task_fill_ranked_paths(
        sequences: Sequence[tuple[Sequence[SearchHit], float]],
        ranked_paths: Sequence[str],
        limit: int,
        fusion: _TaskFindFusion,
    ) -> None:
        base_hits = sequences[0][0]
        if base_hits and base_hits[0].path not in fusion.selected:
            fusion.selected.append(base_hits[0].path)
        for path in ranked_paths:
            if path not in fusion.selected:
                fusion.selected.append(path)
            if len(fusion.selected) >= limit:
                break

    @staticmethod
    def _task_has_authority_surface(selected: Sequence[str]) -> bool:
        return any(
            Path(candidate).name in {"README.md", "AGENTS.md"} for candidate in selected
        )

    @staticmethod
    def _task_selected_within(selected: Sequence[str], parent: Path) -> bool:
        parent_path = parent.as_posix()
        return any(
            _path_is_within(candidate, parent_path) for candidate in selected[:10]
        )

    @staticmethod
    def _task_scoped_authority(
        governance_hits: Sequence[SearchHit], selected: Sequence[str]
    ) -> str | None:
        seen: set[str] = set()
        for hit in governance_hits:
            if hit.path in seen:
                continue
            seen.add(hit.path)
            if len(seen) > 15:
                break
            if hit.path in selected:
                continue
            authority = Path(hit.path)
            if authority.name != "AGENTS.md" or authority.parent == Path("."):
                continue
            if TaskRetrievalMixin._task_selected_within(selected, authority.parent):
                return hit.path
        return None

    def _task_preserve_scoped_authority(
        self,
        views: Mapping[str, str],
        sequences: Sequence[tuple[Sequence[SearchHit], float]],
        limit: int,
        fusion: _TaskFindFusion,
    ) -> None:
        route = route_query(views["base"])
        eligible = (
            len(sequences) >= 2
            and limit >= 2
            and not self._task_has_authority_surface(fusion.selected)
            and route.intent.value == "hybrid"
        )
        if not eligible:
            return
        scoped = self._task_scoped_authority(sequences[1][0], fusion.selected)
        if scoped is not None:
            fusion.selected[:] = fusion.selected[: limit - 1] + [scoped]

    @staticmethod
    def _task_scoped_readme_candidates(
        governance_hits: Sequence[SearchHit], selected: Sequence[str]
    ) -> list[tuple[int, int, int, str]]:
        rows: list[tuple[int, int, int, str]] = []
        seen: set[str] = set()
        rank = 0
        for hit in governance_hits:
            if hit.path in seen:
                continue
            seen.add(hit.path)
            rank += 1
            if rank > 20:
                break
            candidate = TaskRetrievalMixin._task_scoped_readme_candidate(
                hit, selected, rank
            )
            if candidate is not None:
                rows.append(candidate)
        return rows

    @staticmethod
    def _task_scoped_readme_candidate(
        hit: SearchHit, selected: Sequence[str], rank: int
    ) -> tuple[int, int, int, str] | None:
        if hit.path in selected:
            return None
        readme = Path(hit.path)
        parent = readme.parent
        if readme.name != "README.md" or len(parent.parts) < 3:
            return None
        local_evidence = sum(
            1
            for candidate in selected[:10]
            if Path(candidate).name not in {"README.md", "AGENTS.md"}
            and _path_is_within(candidate, parent.as_posix())
        )
        if local_evidence < 2:
            return None
        return (len(parent.parts), local_evidence, -rank, hit.path)

    def _task_preserve_scoped_readme(
        self,
        views: Mapping[str, str],
        sequences: Sequence[tuple[Sequence[SearchHit], float]],
        limit: int,
        fusion: _TaskFindFusion,
    ) -> None:
        route = route_query(views["base"])
        if len(sequences) < 2 or limit < 2 or route.intent.value != "conceptual":
            return
        rows = self._task_scoped_readme_candidates(sequences[1][0], fusion.selected)
        if rows:
            rows.sort(reverse=True)
            fusion.selected[:] = fusion.selected[: limit - 1] + [rows[0][3]]

    def _task_current_hits(self, hits: tuple[SearchHit, ...]) -> tuple[SearchHit, ...]:
        """Fail closed when retrieval evidence no longer matches workspace bytes."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        return tuple(hit for hit in hits if self._indexed_path_current(hit.path))

    def _find_task_impl(
        self, task: str, *, limit: int = 20, ensure_ready: bool = True
    ) -> tuple[SearchHit, ...]:
        """Internal retrieval implementation without opening a decision session."""
        if limit < 1:
            raise ValueError("limit must be >= 1")
        cache_key, cached = self._task_find_cache_key(
            task, limit, ensure_ready=ensure_ready
        )
        if cached is not None:
            return self._task_current_hits(cached)
        self._task_find_trim_cache(cache_key[0])
        raw_tokens = self._task_raw_identifier_tokens(task)
        cue_words = self._task_cue_words(task)
        rare_token = self._task_rare_identifier(raw_tokens, cue_words)
        if rare_token is not None:
            result = self._task_rare_identifier_result(rare_token, max(20, limit))
            if result is not None:
                bounded = result[:limit]
                self._task_result_cache[cache_key] = bounded
                return bounded
        island = self._task_local_island_result(task, max(20, limit), cue_words)
        if island is not None:
            bounded = island[:limit]
            self._task_result_cache[cache_key] = bounded
            return bounded
        views, sequences = self._task_find_sequences(task, max(20, limit))
        path_scores, best_hit, ranked_paths = self._task_fuse_sequences(sequences)
        fusion = _TaskFindFusion(path_scores, best_hit, [])
        self._task_preserve_exact_anchor(raw_tokens, fusion)
        self._task_preserve_components(raw_tokens, fusion)
        self._task_preserve_omitted_alnum_components(task, views, cue_words, fusion)
        self._task_fill_ranked_paths(sequences, ranked_paths, max(20, limit), fusion)
        self._task_preserve_scoped_authority(views, sequences, max(20, limit), fusion)
        self._task_preserve_scoped_readme(views, sequences, max(20, limit), fusion)
        result = tuple(
            replace(fusion.best_hit[path], score=fusion.path_scores[path] * 1000.0)
            for path in fusion.selected[:limit]
        )
        self._task_result_cache[cache_key] = result
        return result

    @decision_scoped
    def find_task(self, task: str, *, limit: int = 20) -> tuple[SearchHit, ...]:
        """Retrieve a full task description through bounded path-level RRF."""
        return self._find_task_impl(task, limit=limit)
