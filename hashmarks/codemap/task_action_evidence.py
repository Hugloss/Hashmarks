from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, cast

from .model import EvidenceVisibility, SearchHit
from .query_primitives import _TASK_STOPWORDS
from .repository_domains import RepositoryDomain, classify_repository_path
from .task_action_types import (
    _TaskActionConfigState,
    _TaskActionCues,
    _TaskActionProjectionState,
    _TaskActionSurface,
)

if TYPE_CHECKING:
    from .engine import CodeMap

_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class TaskActionEvidenceMixin:
    @staticmethod
    def _validate_task_action_limits(limit: int, per_role: int) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if per_role < 1:
            raise ValueError("per_role must be >= 1")
        if per_role > 8:
            raise ValueError("per_role must be <= 8")

    @staticmethod
    def _task_action_cues(task: str) -> _TaskActionCues:
        task_lower = task.lower()
        explicit_test_edit = bool(
            re.search(
                r"\b(?:fix|update|change|modify|add|remove|strengthen|repair|adjust)"
                r"\s+(?:(?:the|a|an)\s+)?(?:[\w.-]+\s+){0,3}(?:test|tests|regression)\b",
                task_lower,
            )
            or re.search(
                r"\b(?:add|write|create)\s+(?:a\s+)?(?:regression\s+)?test\b",
                task_lower,
            )
            or re.search(r"\b(?:add|write|create)\s+(?:a\s+)?regression\b", task_lower)
        )
        return _TaskActionCues(
            words=frozenset(value.lower() for value in _WORD_RE.findall(task)),
            explicit_test_edit=explicit_test_edit,
            explicit_policy_surface=bool(
                re.search(
                    r"\b(?:fix|update|change|modify|add|remove|strengthen|repair)\b.{0,48}"
                    r"\b(?:policy|schema|invariant)\b",
                    task_lower,
                )
            ),
            explicit_architecture_contract=bool(
                re.search(
                    r"\barchitecture\b.{0,32}\b(?:contract|invariant|policy)\b",
                    task_lower,
                )
            ),
        )

    @staticmethod
    def _strong_config_cues() -> set[str]:
        return {
            "config",
            "configuration",
            "makefile",
            "pyproject",
            "package.json",
            "settings",
            "toml",
            "vite",
            "yaml",
            "yml",
        }

    @staticmethod
    def _strong_contract_cues() -> set[str]:
        return {"contract", "schema", "invariant", "policy", "requirement"}

    @staticmethod
    def _strong_authority_cues() -> set[str]:
        return {"agent", "agents", "authority", "owner", "ownership", "govern"}

    @staticmethod
    def _task_action_surface(path: str) -> _TaskActionSurface:
        domains = tuple(classify_repository_path(path))
        domain_set = set(domains)
        lower = path.lower()
        parts = {part.lower() for part in Path(path).parts}
        return _TaskActionSurface(
            domains=domains,
            benchmark_external=(
                lower.startswith("benchmarks/")
                or "/benchmarks/" in f"/{lower}"
                or bool(parts.intersection({"external", "corpus"}))
            ),
            is_test=RepositoryDomain.TEST in domain_set,
            is_contract=bool(
                domain_set & {RepositoryDomain.OWNERSHIP, RepositoryDomain.CONTRACT}
            ),
            is_config=bool(
                domain_set
                & {
                    RepositoryDomain.CONFIG,
                    RepositoryDomain.BUILD,
                    RepositoryDomain.PLAN,
                }
            ),
            is_source=bool(
                domain_set & {RepositoryDomain.SOURCE, RepositoryDomain.SCRIPT}
            ),
        )

    @staticmethod
    def _task_action_test_roles(
        surface: _TaskActionSurface, *, disproven: bool, explicit_test_edit: bool
    ) -> list[str]:
        if not surface.is_test:
            return []
        return (
            ["verify", "edit"] if explicit_test_edit and not disproven else ["verify"]
        )

    @staticmethod
    def _task_action_content_roles(
        surface: _TaskActionSurface,
        *,
        disproven: bool,
        config_requested: bool,
    ) -> list[str]:
        if surface.benchmark_external:
            return ["inspect"]
        roles: list[str] = []
        if surface.is_source and not surface.is_test and not disproven:
            roles.append("edit")
        if surface.is_config and config_requested and not disproven:
            roles.append("edit")
        return roles

    @staticmethod
    def _task_action_roles(
        surface: _TaskActionSurface,
        *,
        disproven: bool,
        cues: _TaskActionCues,
        strong_config_cues: set[str],
    ) -> list[str]:
        roles = ["disproven"] if disproven else []
        roles.extend(
            TaskActionEvidenceMixin._task_action_test_roles(
                surface, disproven=disproven, explicit_test_edit=cues.explicit_test_edit
            )
        )
        if surface.is_contract and not surface.is_test:
            roles.append("contract")
        roles.extend(
            TaskActionEvidenceMixin._task_action_content_roles(
                surface,
                disproven=disproven,
                config_requested=bool(cues.words.intersection(strong_config_cues)),
            )
        )
        if not roles:
            roles.append("inspect")
        if (
            "edit" not in roles
            and not surface.benchmark_external
            and not surface.is_test
        ):
            roles.append("related")
        return roles

    @staticmethod
    def _task_action_row(
        hit: SearchHit,
        rank: int,
        failed: set[str],
        cues: _TaskActionCues,
        strong_config_cues: set[str],
    ) -> dict[str, object]:
        surface = TaskActionEvidenceMixin._task_action_surface(hit.path)
        roles = TaskActionEvidenceMixin._task_action_roles(
            surface,
            disproven=hit.path in failed,
            cues=cues,
            strong_config_cues=strong_config_cues,
        )
        return {
            "path": hit.path,
            "canonical_rank": rank,
            "canonical_score": hit.score,
            "domains": [domain.value for domain in surface.domains],
            "roles": roles,
            "name": hit.name,
            "qualname": hit.qualname,
            "signature": hit.signature,
            "start_line": hit.start_line,
            "end_line": hit.end_line,
            "evidence_visibility": hit.evidence_visibility.value,
        }

    def _task_action_projection_state(
        self, task: str, rows: list[dict[str, object]], limit: int
    ) -> _TaskActionProjectionState:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        terms = [
            value.lower()
            for value in _WORD_RE.findall(task)
            if len(value) >= 4 and value.lower() not in _TASK_STOPWORDS
        ]
        _, document_frequency = self._session_lexical_document_frequencies(terms)
        candidates = self._session_lexical_file_candidates(terms, limit=64)
        file_rows = self._session_file_rows(
            str(candidate.get("path") or "") for candidate in candidates
        )
        return _TaskActionProjectionState(
            terms=terms,
            document_frequency=document_frequency,
            candidates=candidates,
            file_rows=file_rows,
            text_cache={},
            rows=rows,
            limit=limit,
        )

    @staticmethod
    def _task_surface_file_row(
        path: str, domain: RepositoryDomain, state: _TaskActionProjectionState
    ) -> Mapping[str, object] | None:
        path_domains = classify_repository_path(path)
        if not path or domain not in path_domains:
            return None
        if (
            domain is RepositoryDomain.TEST
            and RepositoryDomain.SOURCE not in path_domains
        ):
            return None
        file_row = state.file_rows.get(path)
        if not isinstance(file_row, Mapping):
            return None
        if (
            EvidenceVisibility(str(file_row["evidence_visibility"]))
            is EvidenceVisibility.DENY
        ):
            return None
        return file_row

    def _task_surface_text(
        self, path: str, state: _TaskActionProjectionState
    ) -> str | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if path not in state.text_cache:
            try:
                state.text_cache[path] = (
                    (self.workspace / path)
                    .read_text(encoding="utf-8", errors="replace")
                    .lower()
                )
            except OSError:
                state.text_cache[path] = None
        return state.text_cache[path]

    def _task_surface_candidate(
        self,
        candidate: dict[str, object],
        domain: RepositoryDomain,
        state: _TaskActionProjectionState,
    ) -> tuple[float, int, dict[str, object]] | None:
        path = str(candidate.get("path") or "")
        if self._task_surface_file_row(path, domain, state) is None:
            return None
        text = self._task_surface_text(path, state)
        if text is None:
            return None
        matched = [term for term in state.terms if term in text]
        if len(matched) < 2:
            return None
        rarity = sum(
            1.0 / max(1, int(state.document_frequency.get(term, 1))) for term in matched
        )
        return rarity, len(matched), candidate

    def _task_surface_candidates(
        self, domain: RepositoryDomain, state: _TaskActionProjectionState
    ) -> list[tuple[float, int, dict[str, object]]]:
        candidates = [
            scored
            for candidate in state.candidates
            if (scored := self._task_surface_candidate(candidate, domain, state))
            is not None
        ]
        if domain is RepositoryDomain.TEST:
            candidates.sort(
                key=lambda item: (-item[1], -item[0], str(item[2].get("path") or ""))
            )
        else:
            candidates.sort(
                key=lambda item: (-item[0], -item[1], str(item[2].get("path") or ""))
            )
        return candidates

    @staticmethod
    def _task_surface_is_unique(
        domain: RepositoryDomain,
        candidates: Sequence[tuple[float, int, dict[str, object]]],
    ) -> bool:
        if len(candidates) == 1:
            return True
        best_score, best_matches, _ = candidates[0]
        second_score, second_matches, _ = candidates[1]
        if domain is RepositoryDomain.TEST:
            return best_matches > second_matches
        return best_score >= second_score + 0.25

    def _task_surface_projection_row(
        self,
        domain: RepositoryDomain,
        state: _TaskActionProjectionState,
        scored: tuple[float, int, dict[str, object]],
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        best_score, best_matches, best = scored
        path = str(best["path"])
        existing = next(
            (row for row in state.rows if str(row.get("path") or "") == path), None
        )
        if existing is not None:
            return existing
        symbols = self._session_symbols_for_path(path)
        symbol = symbols[0] if symbols else {}
        file_row = state.file_rows[path]
        existing = {
            "path": path,
            "canonical_rank": state.limit + 1,
            "canonical_score": 0.0,
            "domains": [item.value for item in classify_repository_path(path)],
            "roles": ["verify"]
            if domain is RepositoryDomain.TEST
            else ["edit", "related"],
            "name": symbol.get("name"),
            "qualname": symbol.get("qualname"),
            "signature": symbol.get("signature"),
            "start_line": symbol.get("start_line"),
            "end_line": symbol.get("end_line"),
            "evidence_visibility": str(file_row["evidence_visibility"]),
            "lexical_surface_projection": True,
            "lexical_surface_score": best_score,
            "lexical_surface_matches": best_matches,
        }
        state.rows.append(existing)
        return existing

    def _projected_task_surface(
        self, domain: RepositoryDomain, state: _TaskActionProjectionState
    ) -> tuple[dict[str, object] | None, bool]:
        candidates = self._task_surface_candidates(domain, state)
        if not candidates:
            return None, False
        row = self._task_surface_projection_row(domain, state, candidates[0])
        return row, not self._task_surface_is_unique(domain, candidates)

    @staticmethod
    def _is_task_identifier_anchor(token: str) -> bool:
        mixed_or_snake = "_" in token or any(ch.isupper() for ch in token[1:])
        ticket_like = not token.isupper() or any(ch.isdigit() for ch in token)
        return len(token) >= 3 and mixed_or_snake and ticket_like

    @classmethod
    def _task_identifier_anchor_tokens(cls, task: str) -> list[str]:
        return [
            token.lower()
            for token in _WORD_RE.findall(task)
            if cls._is_task_identifier_anchor(token)
        ]

    @staticmethod
    def _identifier_anchor_count(text: str, tokens: Sequence[str]) -> int:
        compact = re.sub(r"[^a-z0-9]+", "", text.lower())
        return sum(
            re.sub(r"[^a-z0-9]+", "", token.lower()) in compact for token in tokens
        )

    def _task_identifier_verification_row(
        self, rows: Sequence[dict[str, object]], tokens: Sequence[str]
    ) -> dict[str, object] | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)

        def match(row: dict[str, object]) -> tuple[int, int]:
            text = (
                " ".join(
                    str(row.get(key) or "").lower()
                    for key in ("path", "name", "qualname", "signature")
                )
                + " "
                + " ".join(
                    " ".join(
                        str(symbol.get(key) or "").lower()
                        for key in ("name", "qualname", "signature")
                    )
                    for symbol in self._session_symbols_for_path(
                        str(row.get("path") or "")
                    )
                )
            )
            return (
                self._identifier_anchor_count(text, tokens),
                -int(row.get("canonical_rank") or 10_000),
            )

        local_verify = max(
            (row for row in rows if RepositoryDomain.TEST.value in row["domains"]),
            key=match,
            default=None,
        )
        return (
            local_verify
            if local_verify is not None and match(local_verify)[0] > 0
            else None
        )

    @staticmethod
    def _normalized_relative_sql_reference(raw: str) -> str | None:
        normalized = posixpath.normpath(raw)
        if (
            posixpath.isabs(normalized)
            or normalized == ".."
            or normalized.startswith("../")
        ):
            return None
        if normalized.startswith("./"):
            normalized = normalized[2:]
        return normalized if normalized and normalized != "." else None

    def _literal_sql_references(self, verify_path: str) -> list[str]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        try:
            verify_source = (self.workspace / verify_path).read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            return []
        referenced_sql: list[str] = []
        for match in re.finditer(r"[\"']([^\"']+\.sql)[\"']", verify_source):
            normalized = self._normalized_relative_sql_reference(match.group(1))
            if normalized is None:
                continue
            referenced_row = self._session_file_row(normalized)
            if (
                (self.workspace / normalized).is_file()
                and referenced_row is not None
                and EvidenceVisibility(str(referenced_row["evidence_visibility"]))
                is not EvidenceVisibility.DENY
            ):
                referenced_sql.append(normalized)
        return list(dict.fromkeys(referenced_sql))

    def _literal_sql_reference_projection(
        self, verify: dict[str, object], rows: list[dict[str, object]], limit: int
    ) -> tuple[dict[str, object] | None, dict[str, object] | None]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        verify_path = str(verify["path"])
        referenced_sql = self._literal_sql_references(verify_path)
        if len(referenced_sql) != 1:
            return None, None
        owner_path = referenced_sql[0]
        existing = next(
            (row for row in rows if str(row.get("path")) == owner_path), None
        )
        if existing is None:
            file_row = self._session_file_row(owner_path)
            existing = {
                "path": owner_path,
                "canonical_rank": limit + 1,
                "canonical_score": 0.0,
                "domains": [
                    domain.value for domain in classify_repository_path(owner_path)
                ],
                "roles": ["edit", "related"],
                "name": None,
                "qualname": None,
                "signature": None,
                "start_line": None,
                "end_line": None,
                "evidence_visibility": (
                    str(file_row["evidence_visibility"])
                    if file_row is not None
                    else EvidenceVisibility.SOURCE.value
                ),
                "literal_reference_projection": True,
            }
            rows.append(existing)
        owner = {
            "path": owner_path,
            "depth": 1,
            "via": "references",
            "source_path": verify_path,
            "owner_path": [
                {"from": verify_path, "to": owner_path, "relation": "references"}
            ],
            "corroboration": [
                "verification-origin",
                "exact-file-reference",
                "task-sql-cue",
            ],
            "cycle_count": 0,
            "revisit_count": 0,
            "relation_graph_schema": "hashmarks.ownership-relation-graph.v1",
            "selected": owner_path,
            "secret_knowledge_used": False,
            "effect": "repository-owner-projection-only",
            "consumer_action": "external",
        }
        return existing, owner

    def _active_verification_locality(
        self, task: str, verify: dict[str, object] | None
    ) -> tuple[str, int] | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        verify_path = str(verify.get("path") or "") if isinstance(verify, dict) else ""
        if not verify_path:
            return None
        active_anchor = self._structural_owner_candidate(
            verify_path, max_depth=3, task=task
        )
        if active_anchor is None or not active_anchor.get("path"):
            return None
        return str(active_anchor["path"]), int(active_anchor.get("depth") or 1)

    def _projected_verification_locality_row(
        self, active_path: str, depth: int, rows: list[dict[str, object]], limit: int
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        existing = next(
            (row for row in rows if str(row.get("path") or "") == active_path), None
        )
        if existing is not None:
            return existing
        file_row = self._session_file_row(active_path)
        symbols = self._session_symbols_for_path(active_path)
        symbol = symbols[0] if symbols else {}
        projected = {
            "path": active_path,
            "canonical_rank": limit + depth,
            "canonical_score": 0.0,
            "domains": [
                domain.value for domain in classify_repository_path(active_path)
            ],
            "roles": ["related"],
            "name": symbol.get("name"),
            "qualname": symbol.get("qualname"),
            "signature": symbol.get("signature"),
            "start_line": symbol.get("start_line"),
            "end_line": symbol.get("end_line"),
            "evidence_visibility": (
                str(file_row["evidence_visibility"])
                if file_row is not None
                else EvidenceVisibility.SOURCE.value
            ),
            "verification_locality_projection": True,
        }
        rows.append(projected)
        return projected

    def _verification_locality_source_anchor(
        self,
        task: str,
        verify: dict[str, object] | None,
        rows: list[dict[str, object]],
        limit: int,
    ) -> dict[str, object] | None:
        active = self._active_verification_locality(task, verify)
        if active is None:
            return None
        active_path, depth = active
        return self._projected_verification_locality_row(
            active_path, depth, rows, limit
        )

    def _local_config_projection_row(
        self, local_path: str, limit: int
    ) -> dict[str, object] | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        file_row = self._session_file_row(local_path)
        if (
            file_row is None
            or EvidenceVisibility(str(file_row["evidence_visibility"]))
            is EvidenceVisibility.DENY
        ):
            return None
        local_domains = classify_repository_path(local_path)
        allowed = {
            RepositoryDomain.CONFIG,
            RepositoryDomain.BUILD,
            RepositoryDomain.PLAN,
            RepositoryDomain.CONTRACT,
        }
        if not set(local_domains).intersection(allowed):
            return None
        symbols = self._session_symbols_for_path(local_path)
        symbol = symbols[0] if symbols else {}
        return {
            "path": local_path,
            "canonical_rank": limit + 1,
            "canonical_score": 0.0,
            "domains": [domain.value for domain in local_domains],
            "roles": ["edit", "related"],
            "name": symbol.get("name"),
            "qualname": symbol.get("qualname"),
            "signature": symbol.get("signature"),
            "start_line": symbol.get("start_line"),
            "end_line": symbol.get("end_line"),
            "evidence_visibility": str(file_row["evidence_visibility"]),
            "locality_projection": True,
        }

    def _admit_config_locality_siblings(
        self,
        source_anchor: dict[str, object],
        rows: list[dict[str, object]],
        config_candidates: list[dict[str, object]],
        failed: set[str],
        limit: int,
    ) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        source_parent = Path(str(source_anchor["path"])).parent.as_posix()
        existing_paths = {str(row.get("path") or "") for row in config_candidates}
        for local_path in sorted(self.store.paths_under(source_parent)):
            if local_path in existing_paths or local_path in failed:
                continue
            local_row = self._local_config_projection_row(local_path, limit)
            if local_row is None:
                continue
            rows.append(local_row)
            config_candidates.append(local_row)
            existing_paths.add(local_path)

    @staticmethod
    def _config_locality_key(
        anchor: dict[str, object], row: dict[str, object]
    ) -> tuple[int, float, int]:
        generic_parts = {"src", "tests", "checks", "frontend", "backend"}
        anchor_parts = {
            part.lower()
            for part in Path(str(anchor["path"])).parts
            if part.lower() not in generic_parts
        }
        row_parts = {
            part.lower()
            for part in Path(str(row["path"])).parts
            if part.lower() not in generic_parts
        }
        return (
            len(anchor_parts & row_parts),
            float(row.get("canonical_score") or 0.0),
            -int(row.get("canonical_rank") or 10_000),
        )

    @staticmethod
    def _concrete_local_configs(
        local_candidates: Sequence[dict[str, object]],
    ) -> list[dict[str, object]]:
        concrete_domains = {
            RepositoryDomain.CONFIG.value,
            RepositoryDomain.BUILD.value,
            RepositoryDomain.PLAN.value,
        }
        return [
            row
            for row in local_candidates
            if concrete_domains.intersection(row["domains"])
        ]

    @classmethod
    def _unique_best_concrete_config(
        cls,
        concrete: Sequence[dict[str, object]],
        state: _TaskActionConfigState,
    ) -> dict[str, object] | None:
        if len(concrete) == 1:
            return concrete[0]
        if not concrete:
            return None
        ranked = sorted(
            concrete,
            key=lambda row: cls._task_action_config_specificity(row, state),
            reverse=True,
        )
        best_score = cls._task_action_config_specificity(ranked[0], state)
        if best_score <= 0.0:
            return None
        if (
            len(ranked) > 1
            and cls._task_action_config_specificity(ranked[1], state) == best_score
        ):
            return None
        return ranked[0]

    @classmethod
    def _local_config_for_anchor(
        cls,
        anchor: dict[str, object],
        config_candidates: Sequence[dict[str, object]],
        state: _TaskActionConfigState,
    ) -> dict[str, object] | None:
        local_candidates = [
            row
            for row in config_candidates
            if cls._config_locality_key(anchor, row)[0] > 0
        ]
        if not local_candidates:
            return None
        concrete = cls._concrete_local_configs(local_candidates)
        preferred = cls._unique_best_concrete_config(concrete, state)
        if preferred is not None:
            return preferred
        return max(
            local_candidates,
            key=lambda row: cls._config_locality_key(anchor, row),
        )

    def _task_action_config_state(
        self, task: str, rows: Sequence[dict[str, object]]
    ) -> _TaskActionConfigState:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        task_terms = [
            value.lower()
            for value in _WORD_RE.findall(task)
            if len(value) >= 4 and value.lower() not in _TASK_STOPWORDS
        ]
        row_text = {id(row): self._task_action_discrimination_text(row) for row in rows}
        term_rows = {
            term: sum(term in text for text in row_text.values()) for term in task_terms
        }
        return _TaskActionConfigState(
            task_terms=task_terms, row_text=row_text, term_rows=term_rows
        )

    @staticmethod
    def _task_action_config_specificity(
        row: dict[str, object], state: _TaskActionConfigState
    ) -> float:
        text = state.row_text[id(row)]
        return sum(
            1.0 / state.term_rows[term]
            for term in state.task_terms
            if state.term_rows[term] and term in text
        )

    @classmethod
    def _task_action_config_anchor(
        cls, rows: Sequence[dict[str, object]], state: _TaskActionConfigState
    ) -> dict[str, object] | None:
        excluded = {
            RepositoryDomain.CONFIG.value,
            RepositoryDomain.BUILD.value,
            RepositoryDomain.PLAN.value,
        }
        anchors = [
            row
            for row in rows
            if cls._task_action_config_specificity(row, state) > 0.0
            and not excluded.intersection(row["domains"])
        ]
        return max(
            anchors,
            key=lambda row: (
                cls._task_action_config_specificity(row, state),
                -int(row.get("canonical_rank") or 10_000),
            ),
            default=None,
        )

    @staticmethod
    def _task_action_initial_config_candidates(
        rows: Sequence[dict[str, object]], failed: set[str]
    ) -> list[dict[str, object]]:
        domains = {
            RepositoryDomain.CONFIG.value,
            RepositoryDomain.BUILD.value,
            RepositoryDomain.PLAN.value,
            RepositoryDomain.CONTRACT.value,
        }
        return [
            row
            for row in rows
            if RepositoryDomain.TEST.value not in row["domains"]
            and domains.intersection(row["domains"])
            and str(row.get("path") or "") not in failed
        ]

    @classmethod
    def _task_action_fallback_config_source_anchor(
        cls, rows: Sequence[dict[str, object]], state: _TaskActionConfigState
    ) -> dict[str, object] | None:
        source_domains = {RepositoryDomain.SOURCE.value, RepositoryDomain.SCRIPT.value}
        candidates = [
            row
            for row in rows
            if cls._task_action_config_specificity(row, state) > 0.0
            and RepositoryDomain.TEST.value not in row["domains"]
            and source_domains.intersection(row["domains"])
        ]
        return max(
            candidates,
            key=lambda row: (
                cls._task_action_config_specificity(row, state),
                -int(row.get("canonical_rank") or 10_000),
            ),
            default=None,
        )
