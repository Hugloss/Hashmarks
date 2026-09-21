from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, cast

from hashmarks.ownership_decision import (
    OwnershipDecisionState,
    ownership_authority_contract,
    ownership_decision_trace,
)

from .model import EvidenceVisibility, SearchHit
from .query_primitives import _TASK_STOPWORDS
from .repository_domains import RepositoryDomain, classify_repository_path
from .task_action_evidence import TaskActionEvidenceMixin
from .task_action_projection import TaskActionProjectionMixin
from .task_action_types import (
    _TaskActionAmbiguityPayloadState,
    _TaskActionDiscriminationState,
    _TaskActionProjectionState,
)

if TYPE_CHECKING:
    from .engine import CodeMap

_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_QUALIFIED_IDENTIFIER_RE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+"
)


class TaskActionMixin(TaskActionProjectionMixin, TaskActionEvidenceMixin):
    def _task_action_discrimination_state(
        self, task: str, rows: Sequence[dict[str, object]]
    ) -> _TaskActionDiscriminationState:
        task_terms = [
            value.lower()
            for value in _WORD_RE.findall(task)
            if len(value) >= 4 and value.lower() not in _TASK_STOPWORDS
        ]
        row_text = {id(row): self._task_action_discrimination_text(row) for row in rows}
        term_rows = {
            term: sum(term in text for text in row_text.values()) for term in task_terms
        }
        return _TaskActionDiscriminationState(
            task_terms=task_terms, row_text=row_text, term_rows=term_rows
        )

    def _task_action_discrimination_text(self, row: dict[str, object]) -> str:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        metadata = " ".join(
            str(row.get(key) or "").lower()
            for key in ("path", "name", "qualname", "signature")
        )
        symbols = " ".join(
            " ".join(
                str(symbol.get(key) or "").lower()
                for key in ("name", "qualname", "signature")
            )
            for symbol in self._session_symbols_for_path(str(row.get("path") or ""))
        )
        return f"{metadata} {symbols}"

    def _task_action_row_text(
        self, row: dict[str, object], state: _TaskActionDiscriminationState
    ) -> str:
        cached = state.row_text.get(id(row))
        if cached is not None:
            return cached
        text = self._task_action_discrimination_text(row)
        state.row_text[id(row)] = text
        return text

    def _task_action_specificity(
        self, row: dict[str, object], state: _TaskActionDiscriminationState
    ) -> float:
        text = self._task_action_row_text(row, state)
        return sum(
            1.0 / state.term_rows[term]
            for term in state.task_terms
            if state.term_rows[term] and term in text
        )

    def _has_distinctive_task_anchor(
        self, row: dict[str, object], state: _TaskActionDiscriminationState
    ) -> bool:
        text = self._task_action_row_text(row, state)
        return any(
            term in text and state.term_rows.get(term, 0) <= 8
            for term in state.task_terms
        )

    def _has_identifier_anchor(
        self,
        row: dict[str, object],
        state: _TaskActionDiscriminationState,
        verification_anchor_tokens: Sequence[str],
    ) -> bool:
        if not verification_anchor_tokens:
            return False
        text = self._task_action_row_text(row, state)
        compact = re.sub(r"[^a-z0-9]+", "", text.lower())
        return any(
            re.sub(r"[^a-z0-9]+", "", token.lower()) in compact
            for token in verification_anchor_tokens
        )

    @staticmethod
    def _task_action_archive_parts() -> set[str]:
        return {"archive", "legacy", "deprecated", "vendor"}

    @classmethod
    def _task_action_is_archive_path(cls, path: str) -> bool:
        return bool(
            set(Path(path).parts).intersection(cls._task_action_archive_parts())
        )

    def _task_action_is_live_anchored_edit(
        self,
        row: dict[str, object],
        failed: set[str],
        discrimination: _TaskActionDiscriminationState,
        verification_anchor_tokens: Sequence[str],
    ) -> bool:
        path = str(row.get("path") or "")
        if (
            "edit" not in row.get("roles", [])
            or path in failed
            or self._task_action_is_archive_path(path)
        ):
            return False
        return self._has_identifier_anchor(
            row, discrimination, verification_anchor_tokens
        ) or self._has_distinctive_task_anchor(row, discrimination)

    def _task_action_live_anchored_edits(
        self,
        rows: Sequence[dict[str, object]],
        failed: set[str],
        discrimination: _TaskActionDiscriminationState,
        verification_anchor_tokens: Sequence[str],
    ) -> list[dict[str, object]]:
        return [
            row
            for row in rows
            if self._task_action_is_live_anchored_edit(
                row, failed, discrimination, verification_anchor_tokens
            )
        ]

    def _task_action_archive_live_owner_choice(
        self,
        edit: dict[str, object] | None,
        rows: Sequence[dict[str, object]],
        failed: set[str],
        discrimination: _TaskActionDiscriminationState,
        verification_anchor_tokens: Sequence[str],
    ) -> tuple[dict[str, object] | None, bool]:
        edit_path = str(edit.get("path") or "") if isinstance(edit, dict) else ""
        if not edit_path or not self._task_action_is_archive_path(edit_path):
            return edit, False
        live_edits = self._task_action_live_anchored_edits(
            rows, failed, discrimination, verification_anchor_tokens
        )
        if len(live_edits) == 1:
            return live_edits[0], False
        return edit, len(live_edits) > 1

    def _task_action_specific_test_candidate(
        self,
        rows: Sequence[dict[str, object]],
        discrimination: _TaskActionDiscriminationState,
    ) -> dict[str, object] | None:
        candidates = [
            row
            for row in rows
            if self._has_distinctive_task_anchor(row, discrimination)
            and RepositoryDomain.TEST.value in row["domains"]
        ]
        return max(
            candidates,
            key=lambda row: (
                self._task_action_specificity(row, discrimination),
                -int(row.get("canonical_rank") or 10_000),
            ),
            default=None,
        )

    def _task_action_specific_source_candidate(
        self,
        task: str,
        rows: Sequence[dict[str, object]],
        discrimination: _TaskActionDiscriminationState,
    ) -> dict[str, object] | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        candidates = [
            row
            for row in rows
            if self._has_distinctive_task_anchor(row, discrimination)
            and ("edit" in row["roles"] or "related" in row["roles"])
        ][:8]
        resolutions = {
            id(row): self._structural_owner_candidate(
                str(row.get("path") or ""), max_depth=3, task=task
            )
            for row in candidates
            if row.get("path")
        }
        return max(
            candidates,
            key=lambda row: (
                resolutions.get(id(row)) is not None,
                len((resolutions.get(id(row)) or {}).get("corroboration") or []),
                self._task_action_specificity(row, discrimination),
                -int(row.get("canonical_rank") or 10_000),
            ),
            default=None,
        )

    def _task_action_specific_entry_candidate(
        self,
        task: str,
        rows: Sequence[dict[str, object]],
        discrimination: _TaskActionDiscriminationState,
    ) -> dict[str, object] | None:
        test_candidate = self._task_action_specific_test_candidate(rows, discrimination)
        if test_candidate is not None:
            return test_candidate
        return self._task_action_specific_source_candidate(task, rows, discrimination)

    def _task_action_local_island(
        self, task: str, hits: Sequence[SearchHit], limit: int
    ) -> bool:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        island_paths = [
            hit.path for hit in self._task_local_lexical_island_hits(task, limit=limit)
        ]
        return bool(island_paths) and island_paths == [hit.path for hit in hits]

    @staticmethod
    def _task_action_is_go_package_row(
        row: dict[str, object], verify_parent: Path
    ) -> bool:
        path = str(row.get("path") or "")
        return (
            path.endswith(".go")
            and not path.endswith("_test.go")
            and Path(path).parent == verify_parent
        )

    @classmethod
    def _task_action_go_package_rows(
        cls, verify_path: str, rows: Sequence[dict[str, object]]
    ) -> list[dict[str, object]]:
        if not verify_path.endswith("_test.go"):
            return []
        verify_parent = Path(verify_path).parent
        return [
            row
            for row in rows
            if cls._task_action_is_go_package_row(row, verify_parent)
        ]

    def _task_action_go_specific_entry(
        self,
        package_rows: Sequence[dict[str, object]],
        discrimination: _TaskActionDiscriminationState,
    ) -> dict[str, object] | None:
        specific_rows = [
            row
            for row in package_rows
            if self._task_action_specificity(row, discrimination) > 0.0
        ]
        return max(
            specific_rows,
            key=lambda row: (
                self._task_action_specificity(row, discrimination),
                -int(row.get("canonical_rank") or 10_000),
            ),
            default=None,
        )

    def _task_action_go_entry(
        self,
        verify_path: str,
        rows: Sequence[dict[str, object]],
        discrimination: _TaskActionDiscriminationState,
        task_local_island: bool,
    ) -> dict[str, object] | None:
        package_rows = self._task_action_go_package_rows(verify_path, rows)
        go_entry = self._task_action_go_specific_entry(package_rows, discrimination)
        if go_entry is None and len(package_rows) == 1 and task_local_island:
            return package_rows[0]
        return go_entry

    def _task_action_live_current_edit(
        self,
        edit: dict[str, object] | None,
        discrimination: _TaskActionDiscriminationState,
        verification_anchor_tokens: Sequence[str],
    ) -> bool:
        if not isinstance(edit, dict):
            return False
        path = str(edit.get("path") or "")
        if not path or self._task_action_is_archive_path(path):
            return False
        return self._has_identifier_anchor(
            edit, discrimination, verification_anchor_tokens
        ) or self._has_distinctive_task_anchor(edit, discrimination)

    def _task_action_projected_owner_row(
        self,
        owner_path: str,
        resolved: Mapping[str, object],
        rows: list[dict[str, object]],
        limit: int,
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        existing = next(
            (row for row in rows if str(row.get("path")) == owner_path),
            None,
        )
        if existing is not None:
            return existing
        symbols = self._session_symbols_for_path(owner_path)
        symbol = symbols[0] if symbols else {}
        file_row = self._session_file_row(owner_path)
        projected = {
            "path": owner_path,
            "canonical_rank": limit + int(resolved["depth"]),
            "canonical_score": 0.0,
            "domains": [
                domain.value for domain in classify_repository_path(owner_path)
            ],
            "roles": ["edit", "related"],
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
            "structural_projection": True,
        }
        rows.append(projected)
        return projected

    @staticmethod
    def _task_action_structural_owner_evidence(
        resolved: Mapping[str, object], owner_path: str
    ) -> dict[str, object]:
        return {
            **resolved,
            "selected": owner_path,
            "secret_knowledge_used": False,
            "effect": "repository-owner-projection-only",
            "consumer_action": "external",
        }

    def _task_action_current_edit_has_identifier_anchor(
        self,
        edit: dict[str, object] | None,
        discrimination: _TaskActionDiscriminationState,
        verification_anchor_tokens: Sequence[str],
    ) -> bool:
        return bool(
            isinstance(edit, dict)
            and self._has_identifier_anchor(
                edit, discrimination, verification_anchor_tokens
            )
        )

    @staticmethod
    def _task_action_should_promote_contract_surface(
        current_edit_has_identifier_anchor: bool,
        explicit_policy_surface: bool,
        explicit_architecture_contract: bool,
        cue_words: set[str],
        strong_config_cues: set[str],
        authority_cues: set[str],
    ) -> bool:
        explicit_policy_config_surface = bool(
            explicit_policy_surface and cue_words.intersection(strong_config_cues)
        )
        return bool(
            explicit_architecture_contract
            or explicit_policy_config_surface
            or (
                cue_words.intersection(authority_cues)
                and not current_edit_has_identifier_anchor
            )
        )

    @staticmethod
    def _task_action_contract_edit_candidate(
        rows: Sequence[dict[str, object]], failed: set[str]
    ) -> dict[str, object] | None:
        return next(
            (
                row
                for row in rows
                if "contract" in row["roles"]
                and RepositoryDomain.DOC.value not in row["domains"]
                and RepositoryDomain.TEST.value not in row["domains"]
                and not str(row["path"]).lower().startswith("benchmarks/")
                and str(row["path"]) not in failed
            ),
            None,
        )

    @staticmethod
    def _task_action_locality_parts(path: str) -> set[str]:
        generic = {
            "src",
            "tests",
            "test",
            "checks",
            "frontend",
            "backend",
            "lib",
            "app",
        }
        return {
            part.lower()
            for part in Path(path).parent.parts
            if part.lower() not in generic
        }

    @staticmethod
    def _task_action_paths(
        edit: dict[str, object] | None,
        verify: dict[str, object] | None,
    ) -> list[str]:
        return [
            str(row.get("path") or "")
            for row in (edit, verify)
            if isinstance(row, dict) and row.get("path")
        ]

    @classmethod
    def _task_action_contract_is_local(
        cls,
        contract: dict[str, object],
        edit: dict[str, object] | None,
        verify: dict[str, object] | None,
    ) -> bool:
        contract_path = str(contract.get("path") or "")
        action_paths = cls._task_action_paths(edit, verify)
        if contract_path in action_paths:
            return True
        contract_parts = cls._task_action_locality_parts(contract_path)
        action_parts = set().union(
            *(cls._task_action_locality_parts(path) for path in action_paths)
        )
        return bool(contract_parts.intersection(action_parts))

    def _task_action_verification_projection_row(
        self,
        selected_path: str,
        rows: list[dict[str, object]],
        limit: int,
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        existing = next(
            (row for row in rows if str(row.get("path") or "") == selected_path),
            None,
        )
        if existing is not None:
            return existing
        file_row = self._session_file_row(selected_path)
        symbols = self._session_symbols_for_path(selected_path)
        symbol = symbols[0] if symbols else {}
        projected = {
            "path": selected_path,
            "canonical_rank": limit + 1,
            "canonical_score": 0.0,
            "domains": [
                domain.value for domain in classify_repository_path(selected_path)
            ],
            "roles": ["verify"],
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
            "verification_projection": True,
        }
        rows.append(projected)
        return projected

    @staticmethod
    def _task_action_verification_test_symbol(
        row: dict[str, object], selected_verification: Mapping[str, object]
    ) -> dict[str, object]:
        test_symbol = selected_verification.get("test_symbol")
        if not isinstance(test_symbol, str) or not test_symbol:
            return row
        return {**row, "verification_test_symbol": test_symbol}

    def _task_action_finalize_verification_selection(
        self,
        selected_verification: object,
        rows: list[dict[str, object]],
        limit: int,
    ) -> dict[str, object] | None:
        if not isinstance(selected_verification, dict):
            return None
        selected_path = str(selected_verification.get("path") or "")
        if not selected_path:
            return None
        selected_row = self._task_action_verification_projection_row(
            selected_path, rows, limit
        )
        return self._task_action_verification_test_symbol(
            selected_row, selected_verification
        )

    def _task_action_local_owner_tests(
        self,
        rows: Sequence[dict[str, object]],
        discrimination: _TaskActionDiscriminationState,
    ) -> list[dict[str, object]]:
        return [
            row
            for row in rows
            if RepositoryDomain.TEST.value in row.get("domains", [])
            and any(
                term in self._task_action_row_text(row, discrimination)
                and discrimination.term_rows.get(term, 0) <= 8
                for term in discrimination.task_terms
            )
        ][:8]

    def _task_action_resolve_local_owner_origin(
        self,
        task: str,
        origin: dict[str, object],
        failed: set[str],
        limit: int,
        primary_origin: Mapping[str, object] | None = None,
    ) -> tuple[str, dict[str, object], dict[str, object]] | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        origin_path = str(origin.get("path") or "")
        if not origin_path:
            return None
        primary_path = str(primary_origin.get("path") or "") if primary_origin else ""
        primary_resolved = primary_origin.get("resolved") if primary_origin else None
        if origin_path == primary_path and isinstance(primary_resolved, Mapping):
            resolved = dict(primary_resolved)
        else:
            resolved = self._structural_owner_candidate(
                origin_path, max_depth=3, task=task
            )
        if resolved is None:
            return None
        owner_path = str(resolved.get("path") or "")
        if not owner_path or owner_path in failed:
            return None
        origin_evidence = {
            "path": origin_path,
            "owner_path": owner_path,
            "canonical_rank": int(origin.get("canonical_rank") or limit + 1),
        }
        return owner_path, resolved, origin_evidence

    def _task_action_local_structural_owner_evidence(
        self,
        task: str,
        rows: Sequence[dict[str, object]],
        failed: set[str],
        discrimination: _TaskActionDiscriminationState,
        limit: int,
        primary_origin: Mapping[str, object] | None = None,
    ) -> tuple[dict[str, dict[str, object]], list[dict[str, object]]]:
        owners: dict[str, dict[str, object]] = {}
        origins: list[dict[str, object]] = []
        for origin in self._task_action_local_owner_tests(rows, discrimination):
            resolved = self._task_action_resolve_local_owner_origin(
                task, origin, failed, limit, primary_origin
            )
            if resolved is None:
                continue
            owner_path, owner_evidence, origin_evidence = resolved
            owners.setdefault(owner_path, owner_evidence)
            origins.append(origin_evidence)
        return owners, origins

    @classmethod
    def _task_action_exact_identifier_terms(cls, task: str) -> list[str]:
        """Return explicit identifier references without promoting generic task words."""
        qualified = _QUALIFIED_IDENTIFIER_RE.findall(task)
        masked = task
        for value in qualified:
            masked = masked.replace(value, " ")
        standalone = [
            token
            for token in _WORD_RE.findall(masked)
            if cls._is_task_identifier_anchor(token)
        ]
        return list(dict.fromkeys(value.lower() for value in [*qualified, *standalone]))

    def _task_action_reference_backed_source_projection(
        self,
        row: Mapping[str, object],
        symbol_names: set[str],
    ) -> dict[str, object] | None:
        """Recover exact source ownership only from existing import authority.

        A path-shaped test name is not enough to grant edit authority.  When a
        row is both TEST and SOURCE, a non-test source import must resolve
        uniquely back to that exact path through the existing import-owner
        resolver.  This keeps ordinary tests verification-only while allowing
        production modules such as qualification helpers to prove their actual
        implementation role.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        path = str(row.get("path") or "")
        domains = set(map(str, row.get("domains") or ()))
        if (
            not path
            or RepositoryDomain.TEST.value not in domains
            or RepositoryDomain.SOURCE.value not in domains
            or not symbol_names
        ):
            return None
        refs = self._session_refs_many(sorted(symbol_names), limit_per_target=128)
        for symbol_name in sorted(symbol_names):
            for ref in refs.get(symbol_name, ()):
                source_path = self._task_action_proven_source_import(ref, path)
                if source_path is not None:
                    roles = list(dict.fromkeys([*(row.get("roles") or ()), "edit"]))
                    return {
                        **row,
                        "roles": roles,
                        "reference_backed_source_projection": True,
                        "reference_backed_source_path": source_path,
                    }
        return None

    def _task_action_proven_source_import(
        self, ref: Mapping[str, object], owner_path: str
    ) -> str | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if str(ref.get("kind") or "") != "import":
            return None
        source_path = str(ref.get("path") or "")
        target = str(ref.get("target") or "")
        if not source_path or not target or source_path == owner_path:
            return None
        source_domains = set(classify_repository_path(source_path))
        if (
            RepositoryDomain.TEST in source_domains
            or RepositoryDomain.SOURCE not in source_domains
        ):
            return None
        owners, ambiguous = self._resolve_import_owner_evidence(source_path, target)
        if not ambiguous and list(dict.fromkeys(owners)) == [owner_path]:
            return source_path
        return None

    def _task_action_ambiguous_plain_identifiers(
        self, task: str, rows: Sequence[dict[str, object]], failed: set[str]
    ) -> set[str]:
        masked = task
        for value in _QUALIFIED_IDENTIFIER_RE.findall(task):
            masked = masked.replace(value, " ")
        plain_tokens = {
            token.lower()
            for token in _WORD_RE.findall(masked)
            if len(token) >= 4 and token.lower() not in _TASK_STOPWORDS
        }
        exact_row_paths: dict[str, set[str]] = {}
        for row in rows:
            path = str(row.get("path") or "")
            if (
                not path
                or path in failed
                or "edit" not in row.get("roles", [])
                or RepositoryDomain.TEST.value in row.get("domains", [])
                or self._task_action_is_archive_path(path)
            ):
                continue
            name = str(row.get("name") or "").lower()
            if name in plain_tokens:
                exact_row_paths.setdefault(name, set()).add(path)
        return {token for token, paths in exact_row_paths.items() if len(paths) > 1}

    @staticmethod
    def _task_action_path_module_aliases(path: str) -> set[str]:
        module_parts = Path(path).with_suffix("").parts
        aliases = {Path(path).stem.lower()}
        aliases.update(
            ".".join(part.lower() for part in module_parts[index:])
            for index in range(len(module_parts))
        )
        return {alias for alias in aliases if alias}

    def _task_action_qualified_identifier_matches_symbol(
        self,
        path: str,
        symbol: Mapping[str, object],
        qualified_terms: Sequence[str],
    ) -> bool:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        identities = tuple(
            dict.fromkeys(
                value.lower()
                for value in (
                    str(symbol.get("qualname") or ""),
                    str(symbol.get("name") or ""),
                )
                if value
            )
        )
        if not identities:
            return False

        module_aliases = self._task_action_path_module_aliases(path)
        file_row = self._session_file_row(path)
        module_name = (
            str(file_row.get("module_name") or "").lower()
            if isinstance(file_row, Mapping)
            else ""
        )
        if module_name:
            module_aliases.add(module_name)

        for term in qualified_terms:
            lowered = term.lower()
            for identity in identities:
                if lowered == identity:
                    return True
                suffix = f".{identity}"
                if not lowered.endswith(suffix):
                    continue
                qualifier = lowered[: -len(suffix)]
                if qualifier in module_aliases:
                    return True
                if module_name and module_name.endswith(f".{qualifier}"):
                    return True
        return False

    def _task_action_qualified_identifier_index_candidates(
        self,
        qualified_terms: Sequence[str],
        failed: set[str],
        *,
        canonical_rank: int,
    ) -> list[dict[str, object]]:
        """Recover explicit qualified symbols from the maintained exact index.

        Canonical lexical retrieval can be saturated by test surfaces. A task that
        explicitly names module.symbol may therefore recover that exact indexed
        source without granting arbitrary prose edit authority. Discovery is
        bounded to exact terminal symbol identities; the existing qualifier
        predicate then proves module/class locality. Zero or multiple matching
        owners remain unresolved/ambiguous through the existing machinery.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        terminal_names = tuple(
            dict.fromkeys(
                term.rsplit(".", 1)[-1].lower()
                for term in qualified_terms
                if "." in term
            )
        )
        if not terminal_names:
            return []
        indexed = self._session_exact_symbol_candidates(terminal_names, limit=1024)
        candidates: list[dict[str, object]] = []
        seen: set[tuple[str, str]] = set()
        for symbol in indexed:
            path = str(symbol.get("path") or "")
            if not path or path in failed or self._task_action_is_archive_path(path):
                continue
            if not self._task_action_qualified_identifier_matches_symbol(
                path, symbol, qualified_terms
            ):
                continue
            domains = [domain.value for domain in classify_repository_path(path)]
            if (
                RepositoryDomain.SOURCE.value not in domains
                and RepositoryDomain.SCRIPT.value not in domains
            ):
                continue
            file_row = self._session_file_row(path)
            if (
                isinstance(file_row, Mapping)
                and str(file_row.get("evidence_visibility") or "")
                == EvidenceVisibility.DENY.value
            ):
                continue
            key = (
                path,
                str(symbol.get("qualname") or symbol.get("name") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                {
                    "path": path,
                    "canonical_rank": canonical_rank,
                    "canonical_score": 0.0,
                    "domains": domains,
                    "roles": ["edit", "related"],
                    "name": symbol.get("name"),
                    "qualname": symbol.get("qualname"),
                    "signature": symbol.get("signature"),
                    "start_line": symbol.get("start_line"),
                    "end_line": symbol.get("end_line"),
                    "evidence_visibility": (
                        str(file_row["evidence_visibility"])
                        if isinstance(file_row, Mapping)
                        else EvidenceVisibility.SOURCE.value
                    ),
                    "exact_identifier_projection": True,
                    "qualified_identifier_index_projection": True,
                }
            )
        return candidates

    def _task_action_plain_identifier_index_candidates(
        self,
        terms: set[str],
        failed: set[str],
        *,
        canonical_rank: int,
    ) -> list[dict[str, object]]:
        """Recover strong explicit identifiers omitted by bounded retrieval.

        Only identifiers already admitted by the exact-identifier task parser
        may use this path. Generic prose therefore gains no discovery authority.
        Test-shaped rows retain the existing reference-backed production proof,
        while ordinary source/script symbols may participate directly.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        plain_terms = tuple(sorted(term for term in terms if "." not in term))
        if not plain_terms:
            return []
        indexed = self._session_exact_symbol_candidates(plain_terms, limit=1024)
        candidates: list[dict[str, object]] = []
        seen: set[tuple[str, str]] = set()
        for symbol in indexed:
            path = str(symbol.get("path") or "")
            name = str(symbol.get("name") or "").lower()
            qualname = str(symbol.get("qualname") or "").lower()
            if (
                not path
                or path in failed
                or self._task_action_is_archive_path(path)
                or (name not in terms and qualname not in terms)
            ):
                continue
            domains = [domain.value for domain in classify_repository_path(path)]
            if (
                RepositoryDomain.SOURCE.value not in domains
                and RepositoryDomain.SCRIPT.value not in domains
            ):
                continue
            file_row = self._session_file_row(path)
            if (
                isinstance(file_row, Mapping)
                and str(file_row.get("evidence_visibility") or "")
                == EvidenceVisibility.DENY.value
            ):
                continue
            candidate: dict[str, object] = {
                "path": path,
                "canonical_rank": canonical_rank,
                "canonical_score": 0.0,
                "domains": domains,
                "roles": ["edit", "related"],
                "name": symbol.get("name"),
                "qualname": symbol.get("qualname"),
                "signature": symbol.get("signature"),
                "start_line": symbol.get("start_line"),
                "end_line": symbol.get("end_line"),
                "evidence_visibility": (
                    str(file_row["evidence_visibility"])
                    if isinstance(file_row, Mapping)
                    else EvidenceVisibility.SOURCE.value
                ),
                "exact_identifier_projection": True,
                "plain_identifier_index_projection": True,
            }
            if RepositoryDomain.TEST.value in domains:
                projected = self._task_action_reference_backed_source_projection(
                    candidate,
                    {str(symbol.get("name") or "")},
                )
                if projected is None:
                    continue
                candidate = projected
            key = (
                path,
                str(symbol.get("qualname") or symbol.get("name") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            candidates.append(candidate)
        return candidates

    @staticmethod
    def _task_action_requested_edit_span(task: str) -> str:
        """Return the bounded request span that names the edit surface."""
        dependency_first = re.match(
            r"^\s*(?:use|call|apply)\s+.+?\s+(?:in|from|inside|within)\s+(.+)$",
            task,
            flags=re.IGNORECASE,
        )
        dependency_tail = re.search(
            r"\s(?:so|using|with|by|via|through|to use|to call)\s",
            task,
            flags=re.IGNORECASE,
        )
        return (
            dependency_first.group(1)
            if dependency_first
            else task[: dependency_tail.start()]
            if dependency_tail
            else task
        )

    @classmethod
    def _task_action_requested_exact_identifier_edits(
        cls,
        task: str,
        candidates: Sequence[dict[str, object]],
    ) -> list[dict[str, object]]:
        """Keep dependency identifiers as evidence when one edit role is explicit."""
        span = cls._task_action_requested_edit_span(task).lower()
        matched = [
            candidate
            for candidate in candidates
            if any(
                re.search(
                    rf"(?<![a-z0-9_]){re.escape(str(candidate.get(key) or '').lower())}(?![a-z0-9_])",
                    span,
                )
                for key in ("name", "qualname")
                if candidate.get(key)
            )
        ]
        return matched if len(matched) == 1 else list(candidates)

    def _task_action_exact_identifier_edit_candidates(
        self,
        task: str,
        rows: Sequence[dict[str, object]],
        failed: set[str],
    ) -> list[dict[str, object]]:
        """Project exact active source symbols already present in canonical task rows.

        This is discrimination only: it neither discovers new paths nor reranks
        canonical retrieval. Test-only, archived, failed, lexical/comment-only,
        and merely substring-related evidence cannot become exact edit authority.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        terms = set(self._task_action_exact_identifier_terms(task))
        qualified_terms = tuple(
            dict.fromkeys(
                value.lower() for value in _QUALIFIED_IDENTIFIER_RE.findall(task)
            )
        )
        # A plain method name can still be an exact identifier even when it lacks
        # underscore/case cues (for example ``close`` or ``resolve``).  Promote
        # such a token only as an ambiguity signal when canonical retrieval
        # already contains at least two live source definitions with that exact
        # symbol name.  This adds no discovery/ranking authority and prevents
        # lexical order from manufacturing a unique edit owner.
        terms.update(self._task_action_ambiguous_plain_identifiers(task, rows, failed))
        if not terms:
            return []
        candidates: list[dict[str, object]] = []
        for row in rows:
            path = str(row.get("path") or "")
            if not path or path in failed or self._task_action_is_archive_path(path):
                continue
            matches = [
                symbol
                for symbol in self._session_symbols_for_path(path)
                if str(symbol.get("name") or "").lower() in terms
                or str(symbol.get("qualname") or "").lower() in terms
                or self._task_action_qualified_identifier_matches_symbol(
                    path, symbol, qualified_terms
                )
            ]
            if not matches:
                continue
            candidate_row = row
            if "edit" not in row.get(
                "roles", []
            ) or RepositoryDomain.TEST.value in row.get("domains", []):
                symbol_names = {
                    str(symbol.get("name") or "")
                    for symbol in matches
                    if symbol.get("name")
                }
                candidate_row = self._task_action_reference_backed_source_projection(
                    row, symbol_names
                )
                if candidate_row is None:
                    continue
            symbol = max(
                matches,
                key=lambda value: (
                    str(value.get("qualname") or "").lower() in terms,
                    str(value.get("name") or "").lower() in terms,
                    "." in str(value.get("qualname") or ""),
                    -int(value.get("start_line") or 0),
                ),
            )
            candidates.append(
                {
                    **candidate_row,
                    "name": symbol.get("name"),
                    "qualname": symbol.get("qualname"),
                    "signature": symbol.get("signature"),
                    "start_line": symbol.get("start_line"),
                    "end_line": symbol.get("end_line"),
                    "exact_identifier_projection": True,
                }
            )
        projection_rank = (
            max(
                (int(row.get("canonical_rank") or 0) for row in rows),
                default=0,
            )
            + 1
        )
        indexed = [
            *self._task_action_qualified_identifier_index_candidates(
                qualified_terms,
                failed,
                canonical_rank=projection_rank,
            ),
            *self._task_action_plain_identifier_index_candidates(
                terms,
                failed,
                canonical_rank=projection_rank,
            ),
        ]
        existing = {
            (
                str(row.get("path") or ""),
                str(row.get("qualname") or row.get("name") or ""),
            )
            for row in candidates
        }
        candidates.extend(
            row
            for row in indexed
            if (
                str(row.get("path") or ""),
                str(row.get("qualname") or row.get("name") or ""),
            )
            not in existing
        )
        return self._task_action_requested_exact_identifier_edits(task, candidates)

    def _task_action_structural_exact_identifier_owner(
        self,
        resolved: Mapping[str, object],
        exact_identifier_edits: Sequence[Mapping[str, object]],
    ) -> str | None:
        """Return a structurally selected duplicate only with exact import proof.

        Multiple task-local exact symbols are ambiguous by default.  Existing
        structural evidence may narrow them only when the final ownership hop is
        backed by one non-ambiguous exact import identity for the selected symbol.
        A facade/re-export therefore remains ambiguous: its resolver frontier
        contains both the facade and implementation owner rather than one exact
        source path.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        selected_path = str(resolved.get("path") or "")
        source_path = str(resolved.get("source_path") or "")
        if not selected_path or not source_path:
            return None
        selected = next(
            (
                row
                for row in exact_identifier_edits
                if str(row.get("path") or "") == selected_path
            ),
            None,
        )
        if selected is None:
            return None
        symbol_names = {
            str(selected.get(key) or "").rsplit(".", 1)[-1]
            for key in ("name", "qualname")
            if selected.get(key)
        }
        if not symbol_names:
            return None
        # JS/TS structural ownership already carries adapter-backed exact module
        # resolution.  Preserve that language-native proof when its final hop is
        # the exact source -> selected import edge.  Python continues through the
        # import-owner frontier below so facade/re-export ambiguity stays closed.
        if self._task_action_polyglot_import_proves_owner(
            resolved, source_path, selected_path
        ) or self._task_action_python_import_proves_owner(
            source_path, selected_path, symbol_names
        ):
            return selected_path
        return None

    @staticmethod
    def _task_action_polyglot_import_proves_owner(
        resolved: Mapping[str, object], source_path: str, selected_path: str
    ) -> bool:
        source_suffix = Path(source_path).suffix.lower()
        corroboration = set(map(str, resolved.get("corroboration") or ()))
        owner_path = list(resolved.get("owner_path") or ())
        if (
            source_suffix in {".go", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
            and "exact-module-resolution" in corroboration
            and owner_path
        ):
            final_hop = owner_path[-1]
            if (
                isinstance(final_hop, Mapping)
                and str(final_hop.get("from") or "") == source_path
                and str(final_hop.get("to") or "") == selected_path
                and str(final_hop.get("relation") or "") == "imports"
            ):
                return True
        return False

    def _task_action_python_import_proves_owner(
        self, source_path: str, selected_path: str, symbol_names: set[str]
    ) -> bool:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        for edge in self.store.edges_from(source_path):
            if str(edge.get("kind") or "") != "import":
                continue
            if str(edge.get("target_short") or "") not in symbol_names:
                continue
            target = str(edge.get("target") or "")
            if not target:
                continue
            owners, ambiguous = self._resolve_import_owner_evidence(source_path, target)
            if not ambiguous and list(dict.fromkeys(owners)) == [selected_path]:
                return True
        return False

    def _task_action_identifier_edit_candidates(
        self,
        rows: Sequence[dict[str, object]],
        failed: set[str],
        discrimination: _TaskActionDiscriminationState,
        verification_anchor_tokens: Sequence[str],
    ) -> list[dict[str, object]]:
        return [
            row
            for row in rows[:8]
            if "edit" in row.get("roles", [])
            and RepositoryDomain.TEST.value not in row.get("domains", [])
            and str(row.get("path") or "") not in failed
            and self._has_identifier_anchor(
                row, discrimination, verification_anchor_tokens
            )
        ]

    @staticmethod
    def _task_action_explicit_field_contract(
        edit: dict[str, object] | None,
        verification_anchor_tokens: Sequence[str],
        cue_words: set[str],
    ) -> bool:
        return bool(
            isinstance(edit, dict)
            and "/models/" in f"/{str(edit.get('path') or '')}"
            and any("_" in token for token in verification_anchor_tokens)
            and cue_words.intersection(
                {"field", "fields", "validation", "model", "contract"}
            )
        )

    @staticmethod
    def _task_action_decisive_qualified_verification(
        verification_relevance: Mapping[str, object],
        verification_identity_ambiguity: bool,
    ) -> bool:
        selected = verification_relevance.get("selected")
        return bool(
            verification_relevance.get("selection_changed")
            and isinstance(selected, dict)
            and (selected.get("direct_reference") or selected.get("indirect_reference"))
            and not verification_identity_ambiguity
        )

    @staticmethod
    def _task_action_repository_rare_anchor(
        projection_state: _TaskActionProjectionState,
        task_terms: Sequence[str],
    ) -> bool:
        return any(
            0 < int(projection_state.document_frequency.get(term, 0)) <= 8
            for term in task_terms
        )

    @staticmethod
    def _task_action_weak_contract_anchor_ambiguity(
        edit: dict[str, object] | None,
        verification_anchor_tokens: Sequence[str],
        structural_owner: Mapping[str, object] | None,
        explicit_surface_selected: bool,
        repository_rare_anchor: bool,
        decisive_qualified_verification: bool,
    ) -> bool:
        selected_roles = set(edit.get("roles", [])) if isinstance(edit, dict) else set()
        unanchored_contract = bool(
            edit is not None
            and "contract" in selected_roles
            and not verification_anchor_tokens
        )
        unresolved_surface = bool(
            structural_owner is None and not explicit_surface_selected
        )
        weak_repository_evidence = bool(
            not repository_rare_anchor and not decisive_qualified_verification
        )
        return unanchored_contract and unresolved_surface and weak_repository_evidence

    @staticmethod
    def _task_action_global_ambiguity(
        edit: dict[str, object] | None,
        competing: Sequence[dict[str, object]],
        structural_owner: Mapping[str, object] | None,
        localized_config_edit: bool,
        decisive_identifier_surface: bool,
        ambiguity_flags: Sequence[bool],
    ) -> bool:
        competing_action_roles = bool(
            edit is not None
            and competing
            and int(edit["canonical_rank"]) > 2
            and structural_owner is None
            and not localized_config_edit
            and not decisive_identifier_surface
        )
        return edit is None or any(ambiguity_flags) or competing_action_roles

    @staticmethod
    def _task_action_competing_ambiguity_candidate(
        row: dict[str, object],
    ) -> dict[str, object]:
        roles = list(row.get("roles") or [])
        if "verify" in roles:
            plausibility = "verification-surface-resembles-authority"
            discriminator = (
                "prefer the implementation/contract owner unless the task "
                "explicitly asks to modify verification behavior"
            )
        elif "contract" in roles:
            plausibility = "contract-or-configuration-may-govern-behavior"
            discriminator = (
                "inspect whether the requested behavior is declared here or "
                "implemented behind this contract"
            )
        else:
            plausibility = "alternate-edit-authority"
            discriminator = (
                "inspect symbol ownership, callers, and repository relationships "
                "to determine the actual implementation owner"
            )
        return {
            **row,
            "plausibility": plausibility,
            "discriminator": discriminator,
        }

    @classmethod
    def _task_action_ambiguity_candidates(
        cls,
        edit: dict[str, object] | None,
        competing: Sequence[dict[str, object]],
        per_role: int,
    ) -> list[dict[str, object]]:
        candidates: list[dict[str, object]] = []
        if edit is not None:
            candidates.append(
                {
                    **edit,
                    "plausibility": "current-best-edit-authority",
                    "discriminator": (
                        "inspect ownership/definition evidence and verify whether this "
                        "path owns the requested behavior"
                    ),
                }
            )
        remaining = max(0, per_role - len(candidates))
        candidates.extend(
            cls._task_action_competing_ambiguity_candidate(row)
            for row in competing[:remaining]
        )
        return candidates

    @staticmethod
    def _task_action_ambiguity_reason(
        edit: dict[str, object] | None,
        ordered_flags: Sequence[tuple[str, bool]],
        ambiguous: bool,
    ) -> str:
        if edit is None:
            return "no-edit-candidate"
        flagged_reason = next(
            (reason for reason, active in ordered_flags if active),
            None,
        )
        if flagged_reason is not None:
            return flagged_reason
        return "competing-action-roles" if ambiguous else "resolved-by-role"

    @staticmethod
    def _task_action_bounds_payload(limit: int, per_role: int) -> dict[str, int]:
        return {"limit": limit, "per_role": per_role}

    @staticmethod
    def _task_action_discovery_effect(
        verification_relevance: Mapping[str, object],
    ) -> str:
        selected = verification_relevance.get("selected")
        projected = bool(
            verification_relevance.get("selection_changed")
            and isinstance(selected, dict)
            and selected.get("canonical_rank") is None
        )
        return "bounded-verification-reference-projection" if projected else "none"

    @staticmethod
    def _task_action_sorted_verification_origins(
        origins: Sequence[dict[str, object]],
    ) -> list[dict[str, object]]:
        return sorted(
            origins,
            key=lambda row: (
                int(row["canonical_rank"]),
                str(row["path"]),
                str(row["owner_path"]),
            ),
        )

    @classmethod
    def _task_action_ambiguity_payload(
        cls,
        state: _TaskActionAmbiguityPayloadState,
    ) -> dict[str, object]:
        return {
            "schema": "hashmarks.action-ambiguity.v2",
            "ambiguous": state.ambiguous,
            "reason": state.reason,
            "candidates": (list(state.candidates) if state.ambiguous else []),
            "alternatives": list(state.alternatives),
            "task_local_structural_owners": sorted(state.structural_owners),
            "task_local_verification_origins": (
                cls._task_action_sorted_verification_origins(state.verification_origins)
                if state.multi_structural_owner_ambiguity
                else []
            ),
            "discrimination_question": (
                "Which worker-visible path actually owns the requested behavior, "
                "and what repository evidence distinguishes ownership from "
                "verification or compatibility surfaces?"
                if state.ambiguous
                else None
            ),
            "secret_knowledge_used": False,
        }

    @staticmethod
    def _task_action_competing_rows(
        edit: dict[str, object] | None,
        rows: Sequence[dict[str, object]],
    ) -> list[dict[str, object]]:
        if edit is None:
            return []
        return [
            row
            for row in rows[:5]
            if row["path"] != edit["path"]
            and (
                "edit" in row["roles"]
                or "verify" in row["roles"]
                or "contract" in row["roles"]
            )
        ]

    @staticmethod
    def _task_action_multi_identifier_edit_ambiguity(
        identifier_edit_paths: set[str],
        structural_owner: Mapping[str, object] | None,
        decisive_qualified_verification: bool,
        explicit_surface_selected: bool,
        competing_ambiguity_flags: Sequence[bool],
    ) -> bool:
        return bool(
            len(identifier_edit_paths) > 1
            and structural_owner is None
            and not decisive_qualified_verification
            and not explicit_surface_selected
            and not any(competing_ambiguity_flags)
        )

    @staticmethod
    def _task_action_ownership_payload_fields(
        edit: Mapping[str, object] | None,
        competing: Sequence[Mapping[str, object]],
        structural_owner: Mapping[str, object] | None,
        ambiguous: bool,
        ambiguity_reason: str,
    ) -> dict[str, object]:
        explicit_target_basis = (
            str(edit.get("explicit_target_basis") or "")
            if isinstance(edit, Mapping)
            else ""
        )
        owner_eligible = explicit_target_basis != "explicit-test-edit"
        trace = ownership_decision_trace(
            OwnershipDecisionState(
                edit=edit,
                competing=competing,
                structural_owner=structural_owner,
                ambiguous=ambiguous,
                ambiguity_reason=(
                    ambiguity_reason
                    if owner_eligible
                    else "explicit-target-not-ownership"
                ),
                owner_eligible=owner_eligible,
            )
        )
        return {
            "ownership_decision_trace": trace,
            "ownership_authority": ownership_authority_contract(trace),
        }
