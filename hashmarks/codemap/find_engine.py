from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from .model import EvidenceVisibility, SearchHit
from .query_primitives import _WORD_RE, _query_terms
from .query_router import QueryRoute, route_query
from .repository_domains import RepositoryDomain, classify_repository_path

@dataclass(frozen=True)
class _FindContext:
    query: str
    route: QueryRoute
    terms: tuple[str, ...]
    raw_query: str
    raw_words: tuple[str, ...]
    limit: int

@dataclass
class _FindSelectionState:
    selected: list[SearchHit]
    selected_ids: set[tuple[str, str | None, int | None]]
    seen_paths: set[str]

def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)

def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)


class FindEngineMixin:
    def query_route(self, query: str) -> QueryRoute:
        """Return the deterministic retrieval route without executing search."""
        return route_query(query)


    def find(self, query: str, *, limit: int = 20) -> tuple[SearchHit, ...]:
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
        result, _shared = self._find_flight.run(key, lambda: self._find_impl(query, limit=limit))
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
        for row in self._session_exact_symbol_candidates(ctx.terms, limit=max(100, ctx.limit * 8)):
            key = (str(row.get("path", "")), str(row.get("qualname", "")), "symbol")
            candidates[key] = row


    def _find_add_lexical_candidates(
        self, ctx: _FindContext, candidates: dict[tuple[str, str, str], dict]
    ) -> list[dict[str, object]]:
        lexical_files = self._session_lexical_file_candidates(
            ctx.terms[:16], limit=max(80, ctx.limit * 6)
        )
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
        return self._find_lexical_symbol_candidates(ctx, candidates, lexical_files, match_by_path)


    def _find_lexical_symbol_candidates(
        self,
        ctx: _FindContext,
        candidates: dict[tuple[str, str, str], dict],
        lexical_files: Sequence[dict],
        match_by_path: Mapping[str, int],
    ) -> list[dict[str, object]]:
        candidate_paths = [str(row["path"]) for row in lexical_files]
        bridge_rows: list[dict[str, object]] = []
        bridge_count: dict[str, int] = {}
        for raw_row in self._session_symbols_for_paths(candidate_paths, limit=max(1000, ctx.limit * 150)):
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
            if existing is None or float(existing.get("_relation_boost", 0.0) or 0.0) < float(row["_relation_boost"]):
                candidates[key] = row
        return bridge_rows


    @staticmethod
    def _find_symbol_matches_terms(row: Mapping[str, object], terms: Sequence[str]) -> bool:
        if not terms:
            return True
        haystack = " ".join((
            str(row.get("name") or ""),
            str(row.get("qualname") or ""),
            str(row.get("signature") or ""),
        )).lower()
        return any(term in haystack for term in terms)


    def _find_add_path_candidates(
        self, ctx: _FindContext, candidates: dict[tuple[str, str, str], dict]
    ) -> None:
        if ctx.route.path_lookup:
            for row in self.store.path_candidates(ctx.terms[:8], limit=max(50, ctx.limit * 4)):
                key = (str(row.get("path", "")), "", "file")
                candidates.setdefault(key, row)
        if len(ctx.raw_words) == 1 and not candidates:
            for row in self.store.search_candidates(ctx.query, limit=max(50, ctx.limit * 5)):
                key = (
                    str(row.get("path", "")),
                    str(row.get("qualname", "")),
                    str(row.get("row_type", "")),
                )
                candidates[key] = row


    def _find_native_rows(self, ctx: _FindContext) -> list[dict]:
        rows: list[dict] = []
        for term in (ctx.query, *ctx.raw_words):
            if term.strip():
                rows.extend(self._fresh_native_definitions(term, limit=max(30, ctx.limit * 3)))
        return list({
            (str(row.get("path") or ""), str(row.get("display_name") or ""), int(row.get("line") or 0)): row
            for row in rows
        }.values())


    @staticmethod
    def _find_native_candidate(row: Mapping[str, object], mapped: Mapping[str, object]) -> dict:
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
        seed_rows = self._find_symbol_seed_rows(candidates, bridge_rows)
        seed_rows.sort(key=lambda row: -self._score(
            ctx.query, row, tokens=ctx.terms, raw_query=ctx.raw_query
        ))
        seed_limit = 12 if ctx.route.intent.value == "relationship" else 8
        return self._find_named_seed_names(seed_rows, seed_limit)


    @staticmethod
    def _find_caller_paths(
        refs_by_seed: Mapping[str, Sequence[Mapping[str, object]]]
    ) -> set[str]:
        return {
            str(ref.get("path") or "")
            for refs in refs_by_seed.values() for ref in refs
            if str(ref.get("path") or "")
        }


    def _find_add_caller_candidates(
        self,
        ctx: _FindContext,
        candidates: dict[tuple[str, str, str], dict],
        bridge_rows: Sequence[dict[str, object]],
    ) -> None:
        if not ctx.route.caller_expansion:
            return
        seed_names = self._find_caller_seed_names(ctx, candidates, bridge_rows)
        refs_by_seed = self._session_refs_many(seed_names, limit_per_target=30)
        caller_files = self._session_file_rows(self._find_caller_paths(refs_by_seed))
        for seed_name in seed_names:
            self._find_merge_caller_seed(candidates, refs_by_seed.get(seed_name, ()), caller_files)


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
            if existing is None or float(existing.get("_relation_boost", 0.0) or 0.0) < relation_boost:
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
    def _find_seed_keys(seeds: Sequence[dict], seed_limit: int) -> list[tuple[str, str]]:
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
        seeds = self._find_exact_semantic_seeds(candidates, set(ctx.terms))
        seeds.sort(key=lambda row: -self._score(
            ctx.query, row, tokens=ctx.terms, raw_query=ctx.raw_query
        ))
        seed_limit = 12 if ctx.route.intent.value in {"relationship", "structural"} else 8
        return self._find_seed_keys(seeds, seed_limit)


    def _find_add_semantic_candidates(
        self, ctx: _FindContext, candidates: dict[tuple[str, str, str], dict]
    ) -> set[tuple[str, str]]:
        type_kinds = {"return-type", "parameter-type", "inherits", "attribute-type"}
        seed_keys = self._find_semantic_seed_keys(ctx, candidates)
        targets = self._find_semantic_targets(seed_keys, type_kinds)
        return self._find_merge_semantic_targets(candidates, targets)


    def _find_semantic_targets(
        self, seed_keys: Sequence[tuple[str, str]], type_kinds: set[str]
    ) -> set[str]:
        targets: set[str] = set()
        edges_by_seed = self._session_edges_from_many(seed_keys, limit_per_seed=24)
        for seed_key in seed_keys:
            for edge in edges_by_seed.get(seed_key, ()):
                if str(edge.get("kind") or "") not in type_kinds:
                    continue
                target = str(edge.get("target") or "")
                if target:
                    targets.add(target.rsplit(".", 1)[-1])
        return targets


    def _find_merge_semantic_targets(
        self, candidates: dict[tuple[str, str, str], dict], targets: set[str]
    ) -> set[tuple[str, str]]:
        protected: set[tuple[str, str]] = set()
        if not targets:
            return protected
        for related in self._session_exact_symbol_candidates(sorted(targets), limit=max(24, len(targets) * 8)):
            value = {"row_type": "symbol", **related, "_relation_boost": 42.0}
            key = (str(related.get("path", "")), str(related.get("qualname", "")), "symbol")
            existing = candidates.get(key)
            protected.add((str(related.get("path", "")), str(related.get("qualname", ""))))
            if existing is None or float(existing.get("_relation_boost", 0.0) or 0.0) < 42.0:
                candidates[key] = value
        return protected


    def _find_search_hit(
        self, ctx: _FindContext, row: Mapping[str, object], recent: set[str]
    ) -> SearchHit | None:
        score = self._score(
            ctx.query, row, ranks=None, recent=recent, tokens=ctx.terms, raw_query=ctx.raw_query
        )
        if score <= 0:
            return None
        visibility = EvidenceVisibility(str(row.get("evidence_visibility", "source")))
        if visibility is EvidenceVisibility.DENY:
            return None
        return SearchHit(
            path=str(row["path"]), score=score,
            kind=str(row.get("kind") or row.get("row_type") or "file"),
            name=_optional_str(row.get("name")), qualname=_optional_str(row.get("qualname")),
            signature=_optional_str(row.get("signature")),
            start_line=_optional_int(row.get("start_line")), end_line=_optional_int(row.get("end_line")),
            evidence_visibility=visibility,
        )


    def _find_rank_candidates(
        self, ctx: _FindContext, candidates: Mapping[tuple[str, str, str], dict]
    ) -> list[SearchHit]:
        domain_rows = self._apply_repository_domain_hints(tuple(candidates.values()), ctx.route)
        rerank_rows = self._bounded_rerank_rows(ctx.query, domain_rows, limit=ctx.limit, tokens=ctx.terms)
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
            RepositoryDomain.ARCHITECTURE, RepositoryDomain.OWNERSHIP, RepositoryDomain.BUILD,
            RepositoryDomain.PLAN, RepositoryDomain.CONFIG, RepositoryDomain.SCRIPT,
            RepositoryDomain.CONTRACT, RepositoryDomain.DOC,
        }
        return tuple(domain for domain in route.preferred_domains if domain in domains)


    @staticmethod
    def _find_control_hits(
        route: QueryRoute, ranked: Sequence[SearchHit], limit: int
    ) -> list[SearchHit]:
        wanted = FindEngineMixin._find_control_domains(route)
        hits: list[SearchHit] = []
        covered: set[RepositoryDomain] = set()
        for hit in ranked:
            matches = [
                domain for domain in wanted
                if domain in set(classify_repository_path(hit.path)) and domain not in covered
            ]
            if not matches or hit.score < 24.0:
                continue
            hits.append(hit)
            covered.update(matches)
            if len(hits) >= min(4, max(1, limit // 5)):
                break
        return hits


    @staticmethod
    def _find_add_selected(state: _FindSelectionState, hits: Iterable[SearchHit]) -> None:
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
        self, ctx: _FindContext, ranked: Sequence[SearchHit],
        protected: set[tuple[str, str]], state: _FindSelectionState
    ) -> None:
        self._find_add_selected(state, self._find_control_hits(ctx.route, ranked, ctx.limit))
        self._find_add_selected(state, self._find_protected_hits(ranked, protected))
        best_file = self._find_best_file(ranked)
        if best_file is not None:
            state.selected.append(best_file)
            state.selected_ids.add((best_file.path, best_file.qualname, best_file.start_line))
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
        self, ctx: _FindContext, ranked: Sequence[SearchHit], protected: set[tuple[str, str]]
    ) -> tuple[SearchHit, ...]:
        if len(ranked) <= ctx.limit:
            return tuple(ranked)
        state = _FindSelectionState([], set(), set())
        self._find_reserve_hits(ctx, ranked, protected, state)
        quota = min(10, max(1, ctx.limit // 2))
        self._find_fill_diverse(ranked, quota, state)
        self._find_fill_ranked(ranked, ctx.limit, state)
        state.selected.sort(key=lambda hit: (-hit.score, hit.path, hit.start_line or 0))
        return tuple(state.selected[:ctx.limit])


    def _find_impl(self, query: str, *, limit: int = 20) -> tuple[SearchHit, ...]:
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
        return self._find_select_diverse(ctx, ranked, protected)
