from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from hashmarks.operation_contract import operation_schema

from .decision_session import decision_scoped
from .model import EvidenceVisibility, SearchHit
from .query_primitives import _WORD_RE, _query_terms
from .query_router import QueryRoute, route_query
from .repository_domains import RepositoryDomain, classify_repository_path

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from .engine import CodeMap


@dataclass(frozen=True)
class _FindContext:
    query: str
    route: QueryRoute
    terms: tuple[str, ...]
    raw_query: str
    raw_words: tuple[str, ...]
    limit: int
    bound_reasons: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class _FindEvidence:
    hits: tuple[SearchHit, ...]
    bound_reasons: tuple[str, ...]


@dataclass
class _FindSelectionState:
    selected: list[SearchHit]
    selected_ids: set[tuple[str, str | None, int | None]]
    seen_paths: set[str]


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)


def _find_freshness_state(stale: bool | None) -> str:
    if stale is True:
        return "stale"
    if stale is False:
        return "current"
    return "unknown"


def _find_claim_scope(intent: str) -> str:
    return {
        "identifier": "indexed-visible-symbol-surface",
        "path": "admitted-visible-repository-path-index",
    }.get(intent, "bounded-retrieval-only")


def _find_exact_targets(
    query: str,
    intent: str,
    hits: tuple[SearchHit, ...],
) -> set[tuple[object, ...]]:
    if intent == "identifier":
        return {
            (hit.path, hit.qualname or hit.name, hit.start_line)
            for hit in hits
            if query in {hit.name, hit.qualname}
        }
    if intent == "path":
        normalized = query[2:] if query.startswith("./") else query
        return {
            (hit.path,)
            for hit in hits
            if hit.path == normalized
            or ("/" not in normalized and hit.path.rsplit("/", 1)[-1] == normalized)
        }
    return set()


def _find_claim_fields(
    query: str,
    intent: str,
    hits: tuple[SearchHit, ...],
    bound_reasons: tuple[str, ...],
    *,
    freshness: str,
) -> dict[str, object]:
    omissions = sorted(set(bound_reasons))
    exact_query = intent in {"identifier", "path"}
    exact_targets = _find_exact_targets(query, intent, hits)
    search_complete = exact_query and not omissions
    claims_admissible = search_complete and freshness == "current"

    reasons: list[str] = []
    if not exact_query:
        reasons.append("query-intent-not-exact")
    if omissions:
        reasons.append("bounded-search-omission")
    if freshness != "current":
        reasons.append(f"repository-freshness-{freshness}")

    negative_evidence = "not-applicable"
    if exact_query and not exact_targets:
        negative_evidence = (
            "admissible-within-declared-scope"
            if claims_admissible
            else "not-admissible"
        )
    elif not exact_query and not hits:
        negative_evidence = "not-admissible"

    uniqueness_evidence = "not-applicable"
    if len(exact_targets) == 1:
        uniqueness_evidence = (
            "admissible-within-declared-scope"
            if claims_admissible
            else "not-admissible"
        )

    return {
        "scope": _find_claim_scope(intent),
        "completeness": "complete" if search_complete else "incomplete",
        "observed_exact_match_count": len(exact_targets),
        "negative_evidence": negative_evidence,
        "uniqueness_evidence": uniqueness_evidence,
        "omissions": omissions,
        "admissibility_reasons": reasons,
    }


class FindEngineMixin:
    def query_route(self, query: str) -> QueryRoute:
        """Return the deterministic retrieval route without executing search."""
        return route_query(query)

    @decision_scoped
    def find(self, query: str, *, limit: int = 20) -> tuple[SearchHit, ...]:
        return self._find_evidence(query, limit=limit).hits

    @decision_scoped
    def find_packet(self, query: str, *, limit: int = 20) -> dict[str, object]:
        """Return the canonical repository find observation for every transport."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        evidence = self._find_evidence(query, limit=limit)
        route = self.query_route(query)
        generation, identity_generation, stale = self._generation_status()
        freshness = _find_freshness_state(stale)
        claims = _find_claim_fields(
            query,
            route.intent.value,
            evidence.hits,
            evidence.bound_reasons,
            freshness=freshness,
        )
        return {
            "schema": operation_schema("find"),
            "query": query,
            "query_intent": route.intent.value,
            "results": [hit.as_dict() for hit in evidence.hits],
            "truncated": "find-result-limit" in evidence.bound_reasons,
            "generation": generation,
            "identity_generation": identity_generation,
            "freshness": freshness,
            **claims,
        }

    def _find_evidence(self, query: str, *, limit: int) -> _FindEvidence:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._ensure_map_ready()
        if not query.strip():
            raise ValueError("query must not be empty")
        key = (
            "find.v1",
            self.store.meta("workspace_fingerprint", "") or "",
            self.store.generation(),
            self.policy.fingerprint(),
            query,
            int(limit),
        )
        result, _shared = self._find_flight.run(
            key, lambda: self._find_compose(query, limit=limit)
        )
        return result

    def _find_context(self, query: str, limit: int) -> _FindContext:
        terms = tuple(_query_terms(query))
        return _FindContext(
            query=query,
            route=route_query(query),
            terms=terms,
            raw_query=query.strip().lower(),
            raw_words=tuple(_WORD_RE.findall(query)),
            limit=limit,
        )

    def _find_add_exact_candidates(
        self, ctx: _FindContext, candidates: dict[tuple[str, str, str], dict]
    ) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        bound = max(100, ctx.limit * 8)
        rows = self._session_exact_symbol_candidates(ctx.terms, limit=bound)
        if len(rows) >= bound:
            ctx.bound_reasons.add("find-exact-symbol-limit")
        for row in rows:
            key = (str(row.get("path", "")), str(row.get("qualname", "")), "symbol")
            candidates[key] = row

    def _find_add_lexical_candidates(
        self, ctx: _FindContext, candidates: dict[tuple[str, str, str], dict]
    ) -> list[dict[str, object]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        bound = max(80, ctx.limit * 6)
        if len(ctx.terms) > 16:
            ctx.bound_reasons.add("find-lexical-term-limit")
        lexical_files = self._session_lexical_file_candidates(
            ctx.terms[:16], limit=bound
        )
        if len(lexical_files) >= bound:
            ctx.bound_reasons.add("find-lexical-file-limit")
        term_count = max(1, len(ctx.terms))
        match_by_path: dict[str, int] = {}
        for row in lexical_files:
            path = str(row["path"])
            matches = int(row.get("matches", 0) or 0)
            match_by_path[path] = matches
            coverage = min(1.0, float(matches) / float(term_count))
            candidates[(path, "", "file")] = {
                "row_type": "file",
                **row,
                "_relation_boost": min(72.0, float(matches) * 6.0 + coverage * 30.0),
            }
        return self._find_lexical_symbol_candidates(
            ctx, candidates, lexical_files, match_by_path
        )

    def _find_lexical_symbol_candidates(
        self,
        ctx: _FindContext,
        candidates: dict[tuple[str, str, str], dict],
        lexical_files: Sequence[dict],
        match_by_path: Mapping[str, int],
    ) -> list[dict[str, object]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        candidate_paths = [str(row["path"]) for row in lexical_files]
        bridge_rows: list[dict[str, object]] = []
        bridge_count: dict[str, int] = {}
        bound = max(1000, ctx.limit * 150)
        symbol_rows = self._session_symbols_for_paths(candidate_paths, limit=bound)
        if len(symbol_rows) >= bound:
            ctx.bound_reasons.add("find-lexical-symbol-limit")
        for raw_row in symbol_rows:
            path = str(raw_row.get("path", ""))
            matches = match_by_path.get(path, 0)
            row = dict(raw_row)
            row["_relation_boost"] = min(18.0, float(matches) * 2.0)
            if bridge_count.get(path, 0) < 4:
                bridge_rows.append(row)
                bridge_count[path] = bridge_count.get(path, 0) + 1
            if not self._find_symbol_matches_terms(row, ctx.terms):
                continue
            key = (path, str(row.get("qualname", "")), "symbol")
            existing = candidates.get(key)
            if existing is None or float(
                existing.get("_relation_boost", 0.0) or 0.0
            ) < float(row["_relation_boost"]):
                candidates[key] = row
        return bridge_rows

    @staticmethod
    def _find_symbol_matches_terms(
        row: Mapping[str, object], terms: Sequence[str]
    ) -> bool:
        if not terms:
            return True
        haystack = " ".join(
            (
                str(row.get("name") or ""),
                str(row.get("qualname") or ""),
                str(row.get("signature") or ""),
            )
        ).lower()
        return any(term in haystack for term in terms)

    def _find_add_path_candidates(  # noqa: C901
        self, ctx: _FindContext, candidates: dict[tuple[str, str, str], dict]
    ) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if ctx.route.path_lookup:
            bound = max(50, ctx.limit * 4)
            if len(ctx.terms) > 8:
                ctx.bound_reasons.add("find-path-term-limit")
            rows = self.store.path_candidates(ctx.terms[:8], limit=bound)
            if len(rows) >= bound:
                ctx.bound_reasons.add("find-path-candidate-limit")
            for row in rows:
                key = (str(row.get("path", "")), "", "file")
                candidates.setdefault(key, row)
        if len(ctx.raw_words) == 1 and not candidates:
            bound = max(50, ctx.limit * 5)
            rows = self.store.search_candidates(ctx.query, limit=bound)
            if len(rows) >= bound:
                ctx.bound_reasons.add("find-search-candidate-limit")
            for row in rows:
                key = (
                    str(row.get("path", "")),
                    str(row.get("qualname", "")),
                    str(row.get("row_type", "")),
                )
                candidates[key] = row

    def _find_native_rows(self, ctx: _FindContext) -> list[dict]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        rows: list[dict] = []
        for term in (ctx.query, *ctx.raw_words):
            if term.strip():
                bound = max(30, ctx.limit * 3)
                selected = self._fresh_native_definitions(term, limit=bound)
                if len(selected) >= bound:
                    ctx.bound_reasons.add("find-native-definition-limit")
                rows.extend(selected)
        return list(
            {
                (
                    str(row.get("path") or ""),
                    str(row.get("display_name") or ""),
                    int(row.get("line") or 0),
                ): row
                for row in rows
            }.values()
        )

    @staticmethod
    def _find_native_candidate(
        row: Mapping[str, object], mapped: Mapping[str, object]
    ) -> dict:
        return {
            "row_type": "native-definition",
            "path": row["path"],
            "name": row["display_name"],
            "qualname": row["display_name"],
            "kind": "native-definition",
            "signature": row["display_name"],
            "start_line": row["line"],
            "end_line": row["end_line"],
            "evidence_visibility": mapped["evidence_visibility"],
            "_relation_boost": 24.0,
        }

    def _find_add_native_candidates(
        self, ctx: _FindContext, candidates: dict[tuple[str, str, str], dict]
    ) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if not ctx.route.native_definitions:
            return
        native_rows = self._find_native_rows(ctx)
        file_rows = self._session_file_rows(str(row["path"]) for row in native_rows)
        for row in native_rows:
            mapped = file_rows.get(str(row["path"]))
            if mapped is None:
                continue
            display = str(row["display_name"])
            candidates[(str(row["path"]), display, "native-definition")] = (
                self._find_native_candidate(row, mapped)
            )

    @staticmethod
    def _find_symbol_seed_rows(
        candidates: Mapping[tuple[str, str, str], dict],
        bridge_rows: Sequence[dict[str, object]],
    ) -> list[dict]:
        seed_by_identity: dict[tuple[str, str], dict] = {}
        for row in candidates.values():
            if row.get("row_type") == "symbol":
                key = (str(row.get("path") or ""), str(row.get("qualname") or ""))
                seed_by_identity[key] = row
        for row in bridge_rows:
            key = (str(row.get("path") or ""), str(row.get("qualname") or ""))
            seed_by_identity.setdefault(key, dict(row))
        return list(seed_by_identity.values())

    @staticmethod
    def _find_named_seed_names(seed_rows: Sequence[dict], seed_limit: int) -> list[str]:
        names: list[str] = []
        for seed in seed_rows[:seed_limit]:
            name = str(seed.get("name") or "")
            if name:
                names.append(name)
        return names

    def _find_caller_seed_names(
        self,
        ctx: _FindContext,
        candidates: Mapping[tuple[str, str, str], dict],
        bridge_rows: Sequence[dict[str, object]],
    ) -> list[str]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        seed_rows = self._find_symbol_seed_rows(candidates, bridge_rows)
        seed_rows.sort(
            key=lambda row: (
                -self._score(ctx.query, row, tokens=ctx.terms, raw_query=ctx.raw_query)
            )
        )
        seed_limit = 12 if ctx.route.intent.value == "relationship" else 8
        if len(seed_rows) >= seed_limit:
            ctx.bound_reasons.add("find-caller-seed-limit")
        return self._find_named_seed_names(seed_rows, seed_limit)

    @staticmethod
    def _find_caller_paths(
        refs_by_seed: Mapping[str, Sequence[Mapping[str, object]]],
    ) -> set[str]:
        return {
            str(ref.get("path") or "")
            for refs in refs_by_seed.values()
            for ref in refs
            if str(ref.get("path") or "")
        }

    def _find_add_caller_candidates(
        self,
        ctx: _FindContext,
        candidates: dict[tuple[str, str, str], dict],
        bridge_rows: Sequence[dict[str, object]],
    ) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if not ctx.route.caller_expansion:
            return
        seed_names = self._find_caller_seed_names(ctx, candidates, bridge_rows)
        refs_by_seed = self._session_refs_many(seed_names, limit_per_target=30)
        if any(len(rows) >= 30 for rows in refs_by_seed.values()):
            ctx.bound_reasons.add("find-caller-reference-limit")
        caller_files = self._session_file_rows(self._find_caller_paths(refs_by_seed))
        for seed_name in seed_names:
            self._find_merge_caller_seed(
                candidates, refs_by_seed.get(seed_name, ()), caller_files
            )

    @staticmethod
    def _find_merge_caller_seed(
        candidates: dict[tuple[str, str, str], dict],
        refs: Sequence[Mapping[str, object]],
        caller_files: Mapping[str, Mapping[str, object]],
    ) -> None:
        for ref in refs:
            path = str(ref.get("path") or "")
            file_row = caller_files.get(path)
            if file_row is None:
                continue
            key = (path, "", "file")
            existing = candidates.get(key)
            relation_boost = 30.0 if ref.get("kind") == "call" else 18.0
            value = {"row_type": "file", **file_row, "_relation_boost": relation_boost}
            if (
                existing is None
                or float(existing.get("_relation_boost", 0.0) or 0.0) < relation_boost
            ):
                candidates[key] = value

    @staticmethod
    def _find_exact_semantic_seeds(
        candidates: Mapping[tuple[str, str, str], dict], term_set: set[str]
    ) -> list[dict]:
        seeds: list[dict] = []
        for row in candidates.values():
            if row.get("row_type") != "symbol":
                continue
            if str(row.get("name") or "").lower() in term_set:
                seeds.append(row)
        return seeds

    @staticmethod
    def _find_seed_keys(
        seeds: Sequence[dict], seed_limit: int
    ) -> list[tuple[str, str]]:
        keys: list[tuple[str, str]] = []
        for seed in seeds[:seed_limit]:
            path = str(seed.get("path") or "")
            qualname = str(seed.get("qualname") or "")
            if path and qualname:
                keys.append((path, qualname))
        return keys

    def _find_semantic_seed_keys(
        self, ctx: _FindContext, candidates: Mapping[tuple[str, str, str], dict]
    ) -> list[tuple[str, str]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        seeds = self._find_exact_semantic_seeds(candidates, set(ctx.terms))
        seeds.sort(
            key=lambda row: (
                -self._score(ctx.query, row, tokens=ctx.terms, raw_query=ctx.raw_query)
            )
        )
        seed_limit = (
            12 if ctx.route.intent.value in {"relationship", "structural"} else 8
        )
        if len(seeds) >= seed_limit:
            ctx.bound_reasons.add("find-semantic-seed-limit")
        return self._find_seed_keys(seeds, seed_limit)

    def _find_add_semantic_candidates(
        self, ctx: _FindContext, candidates: dict[tuple[str, str, str], dict]
    ) -> set[tuple[str, str]]:
        type_kinds = {"return-type", "parameter-type", "inherits", "attribute-type"}
        seed_keys = self._find_semantic_seed_keys(ctx, candidates)
        targets = self._find_semantic_targets(seed_keys, type_kinds, ctx.bound_reasons)
        return self._find_merge_semantic_targets(candidates, targets, ctx.bound_reasons)

    def _find_semantic_targets(
        self,
        seed_keys: Sequence[tuple[str, str]],
        type_kinds: set[str],
        bound_reasons: set[str],
    ) -> set[str]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        targets: set[str] = set()
        edges_by_seed = self._session_edges_from_many(seed_keys, limit_per_seed=24)
        if any(len(rows) >= 24 for rows in edges_by_seed.values()):
            bound_reasons.add("find-semantic-edge-limit")
        for seed_key in seed_keys:
            for edge in edges_by_seed.get(seed_key, ()):
                if str(edge.get("kind") or "") not in type_kinds:
                    continue
                target = str(edge.get("target") or "")
                if target:
                    targets.add(target.rsplit(".", 1)[-1])
        return targets

    def _find_merge_semantic_targets(
        self,
        candidates: dict[tuple[str, str, str], dict],
        targets: set[str],
        bound_reasons: set[str],
    ) -> set[tuple[str, str]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        protected: set[tuple[str, str]] = set()
        if not targets:
            return protected
        bound = max(24, len(targets) * 8)
        related_rows = self._session_exact_symbol_candidates(
            sorted(targets), limit=bound
        )
        if len(related_rows) >= bound:
            bound_reasons.add("find-semantic-target-limit")
        for related in related_rows:
            value = {"row_type": "symbol", **related, "_relation_boost": 42.0}
            key = (
                str(related.get("path", "")),
                str(related.get("qualname", "")),
                "symbol",
            )
            existing = candidates.get(key)
            protected.add(
                (str(related.get("path", "")), str(related.get("qualname", "")))
            )
            if (
                existing is None
                or float(existing.get("_relation_boost", 0.0) or 0.0) < 42.0
            ):
                candidates[key] = value
        return protected

    def _find_search_hit(
        self, ctx: _FindContext, row: Mapping[str, object], recent: set[str]
    ) -> SearchHit | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        score = self._score(
            ctx.query,
            row,
            ranks=None,
            recent=recent,
            tokens=ctx.terms,
            raw_query=ctx.raw_query,
        )
        if score <= 0:
            return None
        visibility = EvidenceVisibility(str(row.get("evidence_visibility", "source")))
        if visibility is EvidenceVisibility.DENY:
            return None
        return SearchHit(
            path=str(row["path"]),
            score=score,
            kind=str(row.get("kind") or row.get("row_type") or "file"),
            name=_optional_str(row.get("name")),
            qualname=_optional_str(row.get("qualname")),
            signature=_optional_str(row.get("signature")),
            start_line=_optional_int(row.get("start_line")),
            end_line=_optional_int(row.get("end_line")),
            evidence_visibility=visibility,
        )

    def _find_rank_candidates(
        self, ctx: _FindContext, candidates: Mapping[tuple[str, str, str], dict]
    ) -> list[SearchHit]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        domain_rows = self._apply_repository_domain_hints(
            tuple(candidates.values()), ctx.route
        )
        rerank_rows = self._bounded_rerank_rows(
            ctx.query, domain_rows, limit=ctx.limit, tokens=ctx.terms
        )
        if len(rerank_rows) < len(domain_rows):
            ctx.bound_reasons.add("find-rerank-limit")
        recent = self._recent_changed_paths()
        ranked: list[SearchHit] = []
        for row in rerank_rows:
            hit = self._find_search_hit(ctx, row, recent)
            if hit is not None:
                ranked.append(hit)
        ranked.sort(key=lambda hit: (-hit.score, hit.path, hit.start_line or 0))
        return ranked

    @staticmethod
    def _find_control_domains(route: QueryRoute) -> tuple[RepositoryDomain, ...]:
        domains = {
            RepositoryDomain.ARCHITECTURE,
            RepositoryDomain.OWNERSHIP,
            RepositoryDomain.BUILD,
            RepositoryDomain.PLAN,
            RepositoryDomain.CONFIG,
            RepositoryDomain.SCRIPT,
            RepositoryDomain.CONTRACT,
            RepositoryDomain.DOC,
        }
        return tuple(domain for domain in route.preferred_domains if domain in domains)

    @staticmethod
    def _find_control_matches(
        hit: SearchHit,
        wanted: Sequence[RepositoryDomain],
        covered: set[RepositoryDomain],
    ) -> tuple[RepositoryDomain, ...]:
        if hit.score < 24.0:
            return ()
        domains = set(classify_repository_path(hit.path))
        return tuple(
            domain for domain in wanted if domain in domains and domain not in covered
        )

    @staticmethod
    def _find_control_hits(
        route: QueryRoute, ranked: Sequence[SearchHit], limit: int
    ) -> list[SearchHit]:
        wanted = FindEngineMixin._find_control_domains(route)
        hits: list[SearchHit] = []
        covered: set[RepositoryDomain] = set()
        quota = min(4, max(1, limit // 5))
        for hit in ranked:
            matches = FindEngineMixin._find_control_matches(hit, wanted, covered)
            if not matches:
                continue
            hits.append(hit)
            covered.update(matches)
            if len(hits) >= quota:
                break
        return hits

    @staticmethod
    def _find_add_selected(
        state: _FindSelectionState, hits: Iterable[SearchHit]
    ) -> None:
        for hit in hits:
            identity = (hit.path, hit.qualname, hit.start_line)
            if identity in state.selected_ids:
                continue
            state.selected.append(hit)
            state.selected_ids.add(identity)
            state.seen_paths.add(hit.path)

    @staticmethod
    def _find_protected_hits(
        ranked: Sequence[SearchHit], protected: set[tuple[str, str]]
    ) -> list[SearchHit]:
        hits: list[SearchHit] = []
        for hit in ranked:
            if (hit.path, hit.qualname or "") in protected:
                hits.append(hit)
                if len(hits) >= 2:
                    break
        return hits

    @staticmethod
    def _find_best_file(ranked: Sequence[SearchHit]) -> SearchHit | None:
        first_path = ranked[0].path
        for hit in ranked:
            if hit.kind == "file" and hit.score >= 30.0 and hit.path != first_path:
                return hit
        return None

    def _find_reserve_hits(
        self,
        ctx: _FindContext,
        ranked: Sequence[SearchHit],
        protected: set[tuple[str, str]],
        state: _FindSelectionState,
    ) -> None:
        self._find_add_selected(
            state, self._find_control_hits(ctx.route, ranked, ctx.limit)
        )
        self._find_add_selected(state, self._find_protected_hits(ranked, protected))
        best_file = self._find_best_file(ranked)
        if best_file is not None:
            state.selected.append(best_file)
            state.selected_ids.add(
                (best_file.path, best_file.qualname, best_file.start_line)
            )
            state.seen_paths.add(best_file.path)

    def _find_fill_diverse(
        self, ranked: Sequence[SearchHit], quota: int, state: _FindSelectionState
    ) -> None:
        for hit in ranked:
            if hit.path in state.seen_paths:
                continue
            self._find_add_selected(state, (hit,))
            if len(state.selected) >= quota:
                break

    @staticmethod
    def _find_fill_ranked(
        ranked: Sequence[SearchHit], limit: int, state: _FindSelectionState
    ) -> None:
        for hit in ranked:
            identity = (hit.path, hit.qualname, hit.start_line)
            if identity in state.selected_ids:
                continue
            state.selected.append(hit)
            state.selected_ids.add(identity)
            if len(state.selected) >= limit:
                break

    def _find_select_diverse(
        self,
        ctx: _FindContext,
        ranked: Sequence[SearchHit],
        protected: set[tuple[str, str]],
    ) -> tuple[SearchHit, ...]:
        if len(ranked) <= ctx.limit:
            return tuple(ranked)
        state = _FindSelectionState([], set(), set())
        self._find_reserve_hits(ctx, ranked, protected, state)
        quota = min(10, max(1, ctx.limit // 2))
        self._find_fill_diverse(ranked, quota, state)
        self._find_fill_ranked(ranked, ctx.limit, state)
        state.selected.sort(key=lambda hit: (-hit.score, hit.path, hit.start_line or 0))
        return tuple(state.selected[: ctx.limit])

    def _find_compose(self, query: str, *, limit: int = 20) -> _FindEvidence:
        if not query.strip():
            raise ValueError("query must not be empty")
        ctx = self._find_context(query, limit)
        candidates: dict[tuple[str, str, str], dict] = {}
        self._find_add_exact_candidates(ctx, candidates)
        bridge_rows = self._find_add_lexical_candidates(ctx, candidates)
        self._find_add_path_candidates(ctx, candidates)
        self._find_add_native_candidates(ctx, candidates)
        self._find_add_caller_candidates(ctx, candidates, bridge_rows)
        protected = self._find_add_semantic_candidates(ctx, candidates)
        ranked = self._find_rank_candidates(ctx, candidates)
        hits = self._find_select_diverse(ctx, ranked, protected)
        if len(ranked) > limit:
            ctx.bound_reasons.add("find-result-limit")
        return _FindEvidence(hits, tuple(sorted(ctx.bound_reasons)))
