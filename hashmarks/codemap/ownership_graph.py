from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, cast

from hashmarks.operation_contract import operation_response, operation_schema
from hashmarks.paths import normalize_relative_path

from .decision_session import ReadScopeOwner
from .model import EvidenceVisibility, SearchHit
from .ownership_analysis import OwnershipAnalysisMixin
from .ownership_candidates import OwnershipCandidatesMixin
from .ownership_nomination import OwnershipNominationMixin
from .ownership_relation_defaults import OWNERSHIP_RELATION_DEFAULT_OPTIONS
from .ownership_relation_types import (
    OwnershipCandidate,
    OwnershipNode,
    OwnershipPathHop,
    OwnershipRelationEdge,
    OwnershipRelationGraph,
    StructuralOwnerCandidate,
)
from .query_primitives import _WORD_RE, _query_terms
from .query_router import QueryRoute
from .repository_domains import RepositoryDomain, classify_repository_path

if TYPE_CHECKING:
    from .decision_session import DecisionScope, ReadScope
    from .find_engine import RepositorySearch
    from .import_resolution import RepositoryImports
    from .repository_source import RepositorySource
    from .structural_locality import RepositoryStructure
    from .task_action_types import TaskObservation


@dataclass
class _OwnershipImportReuse:
    """Disposable ownership import reuse bound to one read scope."""

    scope: ReadScope | None = None
    entries: dict[tuple[int, str, str], tuple[str, ...]] = field(default_factory=dict)


@dataclass
class _OwnershipGraphState:
    start: str
    task_terms: set[str]
    nodes: dict[str, OwnershipNode]
    edges: list[OwnershipRelationEdge]
    candidates: dict[str, OwnershipCandidate]
    parents: dict[str, tuple[str, str]]
    seen: set[str]
    search_bound_reasons: set[str] = field(default_factory=set)


@dataclass
class _OwnershipExpansion:
    path: str
    depth: int
    ancestry: tuple[str, ...]
    frontier: list[tuple[str, int, tuple[str, ...]]]


class RepositoryOwnership(
    OwnershipAnalysisMixin,
    OwnershipCandidatesMixin,
    OwnershipNominationMixin,
    ReadScopeOwner,
):
    """Own repository ownership observations, import reuse and candidate proof facts."""

    def __init__(
        self,
        source: RepositorySource,
        imports: RepositoryImports,
        structure: RepositoryStructure,
        search: RepositorySearch,
    ) -> None:
        self.search = search
        self.source = source
        self.imports = imports
        self.structure = structure
        self.files = source.files
        self.store = source.store
        self.index = source.index
        self.workspace = source.workspace
        self._ownership_import_reuse = _OwnershipImportReuse()

    @property
    def reads(self) -> DecisionScope:
        return self.source.reads

    @staticmethod
    def _entry_role_domains() -> dict[str, tuple[RepositoryDomain, ...]]:
        return {
            "authority": (RepositoryDomain.OWNERSHIP,),
            "contract": (RepositoryDomain.CONTRACT,),
            "config_build": (
                RepositoryDomain.CONFIG,
                RepositoryDomain.BUILD,
                RepositoryDomain.PLAN,
            ),
            "verification": (RepositoryDomain.TEST,),
            "implementation": (RepositoryDomain.SOURCE, RepositoryDomain.SCRIPT),
            "orientation": (RepositoryDomain.ARCHITECTURE, RepositoryDomain.DOC),
        }

    def _entry_role_symbol_specificity(
        self, role: str, path: str, task_terms: set[str]
    ) -> int:
        if role != "implementation" or not task_terms:
            return 0
        evidence_terms: set[str] = set()
        for symbol in self.reads.symbols_for_path(path)[:64]:
            for field in ("name", "qualname", "signature"):
                evidence_terms.update(_query_terms(str(symbol.get(field) or "")))
        return len(task_terms.intersection(evidence_terms))

    @staticmethod
    def _entry_role_quality(role: str, domains: tuple[RepositoryDomain, ...]) -> int:
        values = set(domains)
        if role == "contract":
            if RepositoryDomain.DOC not in values:
                return 0
            stronger = {
                RepositoryDomain.CONFIG,
                RepositoryDomain.SOURCE,
                RepositoryDomain.SCRIPT,
                RepositoryDomain.OWNERSHIP,
            }
            return 1 if values & stronger else 2
        doc_penalty_roles = {"config_build", "implementation", "verification"}
        if role in doc_penalty_roles:
            return 0 if RepositoryDomain.DOC not in values else 2
        if role == "authority":
            return 0 if RepositoryDomain.OWNERSHIP in values else 2
        return 0

    @staticmethod
    def _entry_role_match(
        role: str,
        accepted: Sequence[RepositoryDomain],
        domains: tuple[RepositoryDomain, ...],
        path: str,
    ) -> bool:
        role_match = bool(set(domains).intersection(accepted))
        if role == "implementation" and RepositoryDomain.TEST in domains:
            return False
        if role != "config_build":
            return role_match
        name = Path(path).name.lower()
        return role_match or ".config." in name or name.startswith("config.")

    def _entry_role_rows(
        self,
        hits: Sequence[SearchHit],
        role_domains: dict[str, tuple[RepositoryDomain, ...]],
        task_terms: set[str],
    ) -> dict[str, list[dict[str, object]]]:
        candidates: dict[str, list[dict[str, object]]] = {
            role: [] for role in role_domains
        }
        for rank, hit in enumerate(hits, 1):
            domains = classify_repository_path(hit.path)
            domain_values = [domain.value for domain in domains]
            for role, accepted in role_domains.items():
                if not self._entry_role_match(role, accepted, domains, hit.path):
                    continue
                candidates[role].append(
                    {
                        "path": hit.path,
                        "canonical_rank": rank,
                        "domains": domain_values,
                        "role_quality": self._entry_role_quality(role, domains),
                        "role_symbol_specificity": self._entry_role_symbol_specificity(
                            role, hit.path, task_terms
                        ),
                    }
                )
        role_rows: dict[str, list[dict[str, object]]] = {}
        for role, rows in candidates.items():
            rows.sort(
                key=lambda row: (
                    int(cast("int", row["role_quality"])),
                    -int(cast("int", row["role_symbol_specificity"])),
                    int(cast("int", row["canonical_rank"])),
                    str(row["path"]),
                )
            )
            role_rows[role] = rows
        return role_rows

    @staticmethod
    def _entry_intent_roles() -> dict[str, tuple[str, ...]]:
        return {
            "config": (
                "config_build",
                "contract",
                "verification",
                "implementation",
                "orientation",
            ),
            "test": (
                "verification",
                "config_build",
                "implementation",
                "contract",
                "orientation",
            ),
            "conceptual": (
                "authority",
                "contract",
                "orientation",
                "implementation",
                "verification",
                "config_build",
            ),
            "relationship": (
                "implementation",
                "contract",
                "verification",
                "config_build",
                "orientation",
            ),
            "structural": (
                "implementation",
                "contract",
                "verification",
                "config_build",
                "orientation",
            ),
            "identifier": (
                "implementation",
                "contract",
                "verification",
                "config_build",
                "orientation",
            ),
            "path": (
                "implementation",
                "config_build",
                "contract",
                "verification",
                "orientation",
            ),
            "hybrid": (
                "implementation",
                "contract",
                "config_build",
                "verification",
                "authority",
                "orientation",
            ),
        }

    @staticmethod
    def _entry_domain_roles() -> dict[RepositoryDomain, str]:
        return {
            RepositoryDomain.OWNERSHIP: "authority",
            RepositoryDomain.CONTRACT: "contract",
            RepositoryDomain.CONFIG: "config_build",
            RepositoryDomain.BUILD: "config_build",
            RepositoryDomain.PLAN: "config_build",
            RepositoryDomain.TEST: "verification",
            RepositoryDomain.SOURCE: "implementation",
            RepositoryDomain.SCRIPT: "implementation",
            RepositoryDomain.ARCHITECTURE: "orientation",
            RepositoryDomain.DOC: "orientation",
        }

    @classmethod
    def _entry_preferred_roles(cls, route: QueryRoute) -> list[str]:
        mapping = cls._entry_domain_roles()
        preferred: list[str] = []
        for domain in route.preferred_domains:
            role = mapping.get(domain)
            if role is not None and role not in preferred:
                preferred.append(role)
        return preferred

    @staticmethod
    def _entry_low_confidence_roles(
        preferred: list[str], defaults: list[str]
    ) -> list[str]:
        strong = [role for role in preferred if role in {"authority", "contract"}]
        ordered = strong + [role for role in defaults if role not in strong]
        ordered.extend(role for role in preferred if role not in ordered)
        return ordered

    @classmethod
    def _entry_ordered_roles(cls, route: QueryRoute) -> list[str]:
        preferred = cls._entry_preferred_roles(route)
        intent_roles = cls._entry_intent_roles()
        defaults = list(intent_roles.get(route.intent.value, intent_roles["hybrid"]))
        if route.confidence == "low":
            return cls._entry_low_confidence_roles(preferred, defaults)
        return preferred + [role for role in defaults if role not in preferred]

    @staticmethod
    def _entry_recommended(
        role_rows: dict[str, list[dict[str, object]]], ordered_roles: list[str]
    ) -> list[dict[str, object]]:
        recommended: list[dict[str, object]] = []
        seen_paths: set[str] = set()
        for role in ordered_roles:
            for row in role_rows[role]:
                path = str(row["path"])
                if path in seen_paths:
                    continue
                seen_paths.add(path)
                recommended.append({"role": role, **row})
                break
        return recommended

    @staticmethod
    def _entry_role_cues() -> dict[str, frozenset[str]]:
        return {
            "authority": frozenset(
                {
                    "agent",
                    "agents",
                    "authority",
                    "authoritative",
                    "owner",
                    "owners",
                    "ownership",
                    "govern",
                    "governs",
                }
            ),
            "contract": frozenset(
                {
                    "contract",
                    "contracts",
                    "schema",
                    "schemas",
                    "policy",
                    "policies",
                    "invariant",
                    "invariants",
                    "requirement",
                    "requirements",
                }
            ),
            "config_build": frozenset(
                {
                    "build",
                    "config",
                    "configuration",
                    "environment",
                    "manifest",
                    "makefile",
                    "package",
                    "packaging",
                    "release",
                    "setting",
                    "settings",
                    "toml",
                    "yaml",
                    "yml",
                }
            ),
            "verification": frozenset(
                {
                    "coverage",
                    "spec",
                    "specs",
                    "test",
                    "tests",
                    "testing",
                }
            ),
            "implementation": frozenset(
                {
                    "class",
                    "code",
                    "function",
                    "implementation",
                    "method",
                    "source",
                    "symbol",
                }
            ),
            "orientation": frozenset(
                {
                    "architecture",
                    "design",
                    "doc",
                    "docs",
                    "documentation",
                    "overview",
                    "readme",
                }
            ),
        }

    @classmethod
    def _entry_explicit_roles(
        cls, task: str, role_rows: dict[str, list[dict[str, object]]]
    ) -> list[str]:
        cue_words = {value.lower() for value in _WORD_RE.findall(task)}
        return [
            role
            for role, cues in cls._entry_role_cues().items()
            if cue_words.intersection(cues) and role_rows.get(role)
        ]

    @staticmethod
    def _is_distinctive_entry_token(token: str) -> bool:
        if len(token) < 3:
            return False
        shaped = "_" in token or any(ch.isupper() for ch in token[1:])
        if not shaped:
            return False
        return not token.isupper() or any(ch.isdigit() for ch in token)

    @classmethod
    def _entry_distinctive_tokens(cls, task: str) -> list[str]:
        return [
            token.lower()
            for token in _WORD_RE.findall(task)
            if cls._is_distinctive_entry_token(token)
        ]

    def _entry_row_text(self, row: dict[str, object]) -> tuple[str, str]:
        path = str(row.get("path") or "")
        symbol_text = " ".join(
            " ".join(
                str(symbol.get(key) or "").lower()
                for key in ("name", "qualname", "signature")
            )
            for symbol in self.reads.symbols_for_path(path)
        )
        row_text = " ".join(
            [
                *(
                    str(row.get(key) or "").lower()
                    for key in ("path", "name", "qualname", "signature")
                ),
                symbol_text,
            ]
        )
        return path, row_text

    @staticmethod
    def _verification_anchor_tokens(matches: list[str]) -> list[str]:
        return [
            token
            for token in matches
            if token.startswith("test_") or token.endswith("_test")
        ]

    @staticmethod
    def _implementation_anchor_tokens(matches: list[str]) -> list[str]:
        return [
            token
            for token in matches
            if not token.startswith("test_") and not token.endswith("_test")
        ]

    @classmethod
    def _entry_role_anchor_filter(
        cls, role: str, path: str, matches: list[str]
    ) -> list[str]:
        if role == "verification":
            return cls._verification_anchor_tokens(matches)
        if role == "implementation":
            return cls._implementation_anchor_tokens(matches)
        path_text = path.lower()
        return [token for token in matches if token in path_text]

    def _entry_anchor_matches(
        self, row: dict[str, object], distinctive_tokens: list[str]
    ) -> list[str]:
        role = str(row["role"])
        path, row_text = self._entry_row_text(row)
        matches = [token for token in distinctive_tokens if token in row_text]
        return self._entry_role_anchor_filter(role, path, matches)

    @staticmethod
    def _entry_ambiguity_reason(
        explicit_roles: list[str], resolved_role: str | None, ambiguous: bool
    ) -> str:
        if len(explicit_roles) >= 2 and resolved_role is not None:
            return "resolved-by-distinctive-role-anchor"
        if ambiguous:
            return "multiple-explicit-role-cues"
        return "single-or-no-explicit-role-cue"

    @staticmethod
    def _entry_resolution(
        ambiguous: bool,
        resolved_role: str | None,
        role_rows: dict[str, list[dict[str, object]]],
        role_anchor_tokens: dict[str, list[str]],
    ) -> dict[str, object]:
        if resolved_role is not None:
            return {
                "status": "resolved",
                "role": resolved_role,
                "path": str(role_rows[resolved_role][0]["path"]),
                "task_anchor_tokens": role_anchor_tokens[resolved_role],
                "authority": "worker-visible-distinctive-role-anchor",
            }
        return {"status": "unresolved" if ambiguous else "not-required"}

    def _entry_anchor_resolution(
        self,
        task: str,
        explicit_roles: list[str],
        role_rows: dict[str, list[dict[str, object]]],
    ) -> tuple[str | None, dict[str, list[str]]]:
        distinctive = self._entry_distinctive_tokens(task)
        if not distinctive:
            return None, {}
        self.reads.preload_symbols(
            [str(row["path"]) for role in explicit_roles for row in role_rows[role]]
        )
        role_anchor_tokens: dict[str, list[str]] = {}
        first_row_anchored: set[str] = set()
        for role in explicit_roles:
            for index, candidate in enumerate(role_rows[role]):
                matches = self._entry_anchor_matches(
                    {"role": role, **candidate}, distinctive
                )
                if matches:
                    role_anchor_tokens[role] = matches
                    if index == 0:
                        first_row_anchored.add(role)
                    break
        anchored_roles = sorted(role_anchor_tokens)
        resolved_role = (
            anchored_roles[0]
            if len(anchored_roles) == 1 and anchored_roles[0] in first_row_anchored
            else None
        )
        return resolved_role, role_anchor_tokens

    def _entry_ambiguity(
        self,
        task: str,
        role_rows: dict[str, list[dict[str, object]]],
        *,
        retrieval_completeness: str,
        retrieval_truncation: str,
    ) -> dict[str, object]:
        explicit_roles = self._entry_explicit_roles(task, role_rows)
        alternatives = [{"role": role, **role_rows[role][0]} for role in explicit_roles]
        alternatives.sort(
            key=lambda row: (
                int(cast("int", row["canonical_rank"])),
                str(row["role"]),
                str(row["path"]),
            )
        )
        if retrieval_completeness != "complete":
            return {
                "schema": "hashmarks.entry-point-ambiguity.v4",
                "ambiguous": None,
                "reason": "canonical-retrieval-bound-not-exhausted",
                "completeness": retrieval_completeness,
                "truncation": retrieval_truncation,
                "explicit_roles": explicit_roles,
                "alternatives": alternatives,
                "resolution": {
                    "status": "unknown",
                    "reason": "canonical-retrieval-bound-not-exhausted",
                },
                "discrimination_question": None,
                "secret_knowledge_used": False,
            }

        resolved_role, role_anchor_tokens = self._entry_anchor_resolution(
            task, explicit_roles, role_rows
        )
        ambiguous = len(explicit_roles) >= 2 and resolved_role is None
        return {
            "schema": "hashmarks.entry-point-ambiguity.v4",
            "ambiguous": ambiguous,
            "reason": self._entry_ambiguity_reason(
                explicit_roles, resolved_role, ambiguous
            ),
            "completeness": "complete",
            "truncation": "complete",
            "explicit_roles": explicit_roles,
            "alternatives": alternatives,
            "resolution": self._entry_resolution(
                ambiguous, resolved_role, role_rows, role_anchor_tokens
            ),
            "discrimination_question": (
                "Which explicit repository role owns the requested change, and what worker-visible identifier, path, or structural evidence distinguishes it?"
                if ambiguous
                else None
            ),
            "secret_knowledge_used": False,
        }

    def entry_points_for_candidates(
        self,
        observation: TaskObservation,
        *,
        limit: int = 20,
        per_role: int = 2,
    ) -> dict[str, object]:
        """Project canonical task hits into bounded worker-facing roles."""
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if per_role < 1:
            raise ValueError("per_role must be >= 1")
        if per_role > 8:
            raise ValueError("per_role must be <= 8")
        if self.reads.scope is not observation.scope:
            raise RuntimeError("entry candidates belong to a different read scope")
        query, retrieval = observation.query, observation.retrieval
        task, route = query.text, query.route
        hits = retrieval.hits
        retrieval_completeness = "complete" if retrieval.complete else "incomplete"
        task_terms = set(query.terms)
        role_domains = self._entry_role_domains()
        all_role_rows = self._entry_role_rows(hits, role_domains, task_terms)
        role_rows = {role: rows[:per_role] for role, rows in all_role_rows.items()}
        recommended = self._entry_recommended(
            role_rows, self._entry_ordered_roles(route)
        )
        return {
            "schema": "hashmarks.task-entry-points.v4",
            "task": task,
            "intent": route.intent.value,
            "confidence": route.confidence,
            "preferred_domains": [domain.value for domain in route.preferred_domains],
            "canonical": [hit.as_dict() for hit in hits],
            "roles": role_rows,
            "recommended": recommended,
            "ambiguity": self._entry_ambiguity(
                task,
                all_role_rows,
                retrieval_completeness=retrieval_completeness,
                retrieval_truncation=retrieval.truncation,
            ),
            "bounds": {
                "limit": limit,
                "per_role": per_role,
                "canonical_completeness": retrieval_completeness,
                "canonical_truncation": retrieval.truncation,
                "bound_reasons": list(retrieval.bound_reasons),
            },
            "ranking_effect": "none",
            "discovery_effect": "none",
        }

    def _ownership_evidence_visible(self, path: str) -> bool:
        file_row = self.reads.file_row(path)
        if file_row is None:
            return False
        try:
            return (
                EvidenceVisibility(str(file_row["evidence_visibility"]))
                is not EvidenceVisibility.DENY
            )
        except ValueError:
            return False

    def _ownership_node(self, state: _OwnershipGraphState, path: str) -> OwnershipNode:
        current = state.nodes.get(path)
        if current is not None:
            return current
        domains = [domain.value for domain in classify_repository_path(path)]
        symbols = self.reads.symbols_for_path(path)
        if len(symbols) > 12:
            state.search_bound_reasons.add("node-symbol-limit")
        symbol_terms: set[str] = set()
        for symbol in symbols[:12]:
            symbol_terms.update(
                _query_terms(str(symbol.get("qualname") or symbol.get("name") or ""))
            )
        path_terms = set(_query_terms(path.replace("/", " ")))
        current = OwnershipNode(
            path=path,
            domains=domains,
            task_locality_terms=sorted(
                state.task_terms.intersection(path_terms | symbol_terms)
            ),
        )
        state.nodes[path] = current
        return current

    def _python_ownership_import_path(
        self, source_path: str, target: str
    ) -> str | None:
        source = Path(source_path)
        parts = target.split(".")
        if not target.startswith("."):
            if len(parts) < 2:
                return None
            return Path(*parts[:-1]).with_suffix(".py").as_posix()
        lead = len(target) - len(target.lstrip("."))
        tail = target.lstrip(".").split(".")
        if len(tail) < 2:
            return None
        base = source.parent
        for _ in range(max(0, lead - 1)):
            base = base.parent
        return base.joinpath(*tail[:-1]).with_suffix(".py").as_posix()

    def _visible_resolved_import_paths(
        self, source_path: str, target: str
    ) -> list[str]:
        return [
            candidate
            for candidate in self.imports._resolve_import_paths(source_path, target)
            if self._ownership_evidence_visible(candidate)
        ]

    def _exact_ownership_import_paths(self, source_path: str, target: str) -> list[str]:
        if not target:
            return []
        cache_key: tuple[int, str, str] | None = None
        if self.reads.depth > 0 and self.reads.generation is not None:
            if self._ownership_import_reuse.scope is not self.reads.scope:
                self._ownership_import_reuse.entries.clear()
                self._ownership_import_reuse.scope = self.reads.scope
            cache_key = (self.reads.generation, source_path, target)
            cached = self._ownership_import_reuse.entries.get(cache_key)
            if cached is not None:
                self.reads.count("ownership_import_paths_hit")
                return list(cached)
            self.reads.count("ownership_import_paths_miss")
        result = self._uncached_exact_ownership_import_paths(source_path, target)
        if cache_key is not None:
            self._ownership_import_reuse.entries[cache_key] = tuple(result)
        return result

    def _uncached_exact_ownership_import_paths(
        self, source_path: str, target: str
    ) -> list[str]:
        source_row = self.reads.file_row(source_path)
        language = None if source_row is None else str(source_row["language"] or "")
        if language != "python":
            return self._visible_resolved_import_paths(source_path, target)
        candidates = self.imports._python_import_module_candidates(source_path, target)
        if candidates:
            direct = self.reads.module_paths(candidates[0])
            if direct:
                return (
                    [path for path in direct if self._ownership_evidence_visible(path)]
                    if len(direct) == 1
                    else []
                )
        resolved, unresolved = self.imports._resolve_import_owner_evidence(
            source_path, target
        )
        return (
            []
            if unresolved
            else [path for path in resolved if self._ownership_evidence_visible(path)]
        )

    @staticmethod
    def _ownership_call_shorts(
        expandable: Sequence[tuple[str, int, tuple[str, ...]]],
        edge_map: Mapping[str, Sequence[dict[str, object]]],
    ) -> list[str]:
        return sorted(
            {
                str(edge.get("target_short") or "")
                for path, _, _ in expandable
                for edge in edge_map.get(path, ())
                if str(edge.get("kind") or "") == "call"
                and str(edge.get("target_short") or "")
            }
        )

    @staticmethod
    def _index_ownership_symbols(
        state: _OwnershipGraphState,
        call_symbols: Sequence[dict[str, object]],
        wanted: set[str],
    ) -> dict[str, list[dict]]:
        symbols_by_short: dict[str, list[dict]] = {}
        for symbol in call_symbols:
            aliases = {
                str(symbol.get("name") or "").lower(),
                str(symbol.get("qualname") or "").rsplit(".", 1)[-1].lower(),
            }
            for alias in aliases.intersection(wanted):
                bucket = symbols_by_short.setdefault(alias, [])
                if len(bucket) < 12:
                    bucket.append(symbol)
                else:
                    state.search_bound_reasons.add("symbol-alias-limit")
        return symbols_by_short

    def _ownership_symbol_map(
        self,
        state: _OwnershipGraphState,
        expandable: Sequence[tuple[str, int, tuple[str, ...]]],
        edge_map: Mapping[str, Sequence[dict[str, object]]],
    ) -> dict[str, list[dict]]:
        call_shorts = self._ownership_call_shorts(expandable, edge_map)
        if not call_shorts:
            return {}
        symbol_limit = max(12, min(5000, 12 * len(call_shorts)))
        call_symbols = self.reads.exact_symbol_candidates(
            call_shorts, limit=symbol_limit + 1
        )
        if len(call_symbols) > symbol_limit:
            state.search_bound_reasons.add("symbol-candidate-limit")
        return self._index_ownership_symbols(
            state,
            call_symbols[:symbol_limit],
            {value.lower() for value in call_shorts},
        )

    @staticmethod
    def _ownership_symbol_target(
        path: str, symbol: dict, imported_paths: set[str]
    ) -> str | None:
        candidate = str(symbol.get("path") or "")
        visibility = str(
            symbol.get("evidence_visibility") or EvidenceVisibility.DENY.value
        )
        visible = EvidenceVisibility(visibility) is not EvidenceVisibility.DENY
        if (
            not candidate
            or candidate == path
            or candidate not in imported_paths
            or not visible
        ):
            return None
        return candidate

    @classmethod
    def _ownership_call_targets(
        cls,
        path: str,
        edge: dict,
        imported_paths: set[str],
        symbols_by_short: Mapping[str, Sequence[dict[str, object]]],
    ) -> list[tuple[str, str]]:
        short = str(edge.get("target_short") or "")
        if not short:
            return []
        targets = [
            target
            for symbol in symbols_by_short.get(short.lower(), ())
            if (target := cls._ownership_symbol_target(path, symbol, imported_paths))
            is not None
        ]
        return [(target, "import-constrained-symbol") for target in targets]

    def _ownership_targets_for_edge(
        self,
        path: str,
        edge: dict,
        resolved_imports: dict[str, list[str]],
        imported_paths: set[str],
        symbols_by_short: dict[str, list[dict]],
    ) -> list[tuple[str, str]]:
        kind = str(edge.get("kind") or "")
        if kind == "import":
            target = str(edge.get("target") or "")
            return [
                (exact, "exact-module") for exact in resolved_imports.get(target, ())
            ]
        if kind == "call":
            return self._ownership_call_targets(
                path, edge, imported_paths, symbols_by_short
            )
        return []

    @staticmethod
    def _ownership_candidate_row(
        state: _OwnershipGraphState,
        target_path: str,
        target_node: OwnershipNode,
        depth: int,
        relation: str,
        resolution: str,
    ) -> None:
        domains = set(target_node["domains"])
        source_domain = (
            RepositoryDomain.SOURCE.value in domains
            or RepositoryDomain.SCRIPT.value in domains
        )
        if RepositoryDomain.TEST.value in domains or not source_domain:
            return
        row = state.candidates.setdefault(
            target_path,
            {
                "path": target_path,
                "depth": depth,
                "relations": [],
                "exact_edges": 0,
                "task_locality_terms": list(target_node["task_locality_terms"]),
            },
        )
        row["depth"] = max(int(row["depth"]), depth)
        relations = row["relations"]
        if relation not in relations:
            relations.append(relation)
        if resolution == "exact-module":
            row["exact_edges"] = int(row["exact_edges"]) + 1

    def _record_ownership_target(
        self,
        state: _OwnershipGraphState,
        expansion: _OwnershipExpansion,
        target_path: str,
        resolution: str,
        kind: str,
    ) -> None:
        target_node = self._ownership_node(state, target_path)
        next_depth = expansion.depth + 1
        cycle = target_path in expansion.ancestry
        revisited = target_path in state.seen
        relation = "imports" if kind == "import" else "calls"
        state.edges.append(
            {
                "from": expansion.path,
                "to": target_path,
                "relation": relation,
                "depth": next_depth,
                "resolution": resolution,
                "cycle": cycle,
                "revisited": revisited,
            }
        )
        self._ownership_candidate_row(
            state, target_path, target_node, next_depth, relation, resolution
        )
        if revisited:
            return
        state.seen.add(target_path)
        state.parents.setdefault(target_path, (expansion.path, relation))
        expansion.frontier.append(
            (target_path, next_depth, expansion.ancestry + (target_path,))
        )

    @staticmethod
    def _ownership_import_targets(path_edges: Sequence[dict[str, object]]) -> list[str]:
        return list(
            dict.fromkeys(
                str(edge.get("target") or "")
                for edge in path_edges
                if str(edge.get("kind") or "") == "import"
                and str(edge.get("target") or "")
            )
        )

    def _ownership_import_resolution(
        self, path: str, path_edges: Sequence[dict[str, object]]
    ) -> tuple[dict[str, list[str]], set[str]]:
        targets = self._ownership_import_targets(path_edges)
        resolved = {
            target: self._exact_ownership_import_paths(path, target)
            for target in targets
        }
        imported = {exact for rows in resolved.values() for exact in rows}
        return resolved, imported

    def _expand_ownership_path(
        self,
        state: _OwnershipGraphState,
        item: tuple[str, int, tuple[str, ...]],
        edge_map: Mapping[str, Sequence[dict[str, object]]],
        symbols_by_short: dict[str, list[dict[str, object]]],
        frontier: list[tuple[str, int, tuple[str, ...]]],
    ) -> None:
        path, depth, ancestry = item
        path_edges = edge_map.get(path, ())
        resolved, imported_paths = self._ownership_import_resolution(path, path_edges)
        expansion = _OwnershipExpansion(path, depth, ancestry, frontier)
        for edge in path_edges:
            kind = str(edge.get("kind") or "")
            targets = self._ownership_targets_for_edge(
                path, edge, resolved, imported_paths, symbols_by_short
            )
            for target_path, resolution in dict.fromkeys(targets):
                self._record_ownership_target(
                    state, expansion, target_path, resolution, kind
                )

    def _preload_direct_ownership_import_modules(
        self,
        expandable: Sequence[tuple[str, int, tuple[str, ...]]],
        edge_map: Mapping[str, Sequence[dict[str, object]]],
    ) -> None:
        """Preload only the exact module probe each ownership import will ask first."""
        modules: set[str] = set()
        for path, _, _ in expandable:
            source_row = self.reads.file_row(path)
            if source_row is None or str(source_row.get("language") or "") != "python":
                continue
            for target in self._ownership_import_targets(edge_map.get(path, ())):
                candidates = self.imports._python_import_module_candidates(path, target)
                if candidates:
                    modules.add(candidates[0])
        if len(modules) >= 2:
            self.reads.preload_module_paths(modules)

    def _expand_ownership_level(
        self,
        state: _OwnershipGraphState,
        current_frontier: list[tuple[str, int, tuple[str, ...]]],
        max_depth: int,
    ) -> list[tuple[str, int, tuple[str, ...]]]:
        expandable = [item for item in current_frontier if item[1] < max_depth]
        if not expandable:
            return []
        paths = [path for path, _, _ in expandable]
        self.reads.file_rows(paths)
        probed_edge_map = self.reads.edges_for_paths_many(paths, limit_per_path=101)
        edge_map = {}
        for path in paths:
            path_edges = list(probed_edge_map.get(path, ()))
            if len(path_edges) > 100:
                state.search_bound_reasons.add("edge-per-path-limit")
            edge_map[path] = path_edges[:100]
        self._preload_direct_ownership_import_modules(expandable, edge_map)
        symbols_by_short = self._ownership_symbol_map(state, expandable, edge_map)
        frontier: list[tuple[str, int, tuple[str, ...]]] = []
        for item in expandable:
            self._expand_ownership_path(
                state, item, edge_map, symbols_by_short, frontier
            )
        return frontier

    def _rank_ownership_candidates(
        self, state: _OwnershipGraphState
    ) -> list[OwnershipCandidate]:
        start_domains = set(self._ownership_node(state, state.start)["domains"])
        started_from_verification = RepositoryDomain.TEST.value in start_domains
        ranked: list[OwnershipCandidate] = []
        for row in state.candidates.values():
            locality = list(row.get("task_locality_terms") or [])
            corroboration = ["active-reachability"]
            if started_from_verification:
                corroboration.append("verification-origin")
            if locality:
                corroboration.append("task-locality")
            if int(row.get("exact_edges") or 0):
                corroboration.append("exact-module-resolution")
            if "calls" in row.get("relations", []):
                corroboration.append("call-edge")
            row["corroboration"] = corroboration
            row["corroborated"] = bool(
                {"verification-origin", "task-locality", "call-edge"}.intersection(
                    corroboration
                )
            )
            ranked.append(row)
        ranked.sort(
            key=lambda row: (
                not bool(row.get("corroborated")),
                -int(row.get("depth") or 0),
                -len(row.get("task_locality_terms") or []),
                -int(row.get("exact_edges") or 0),
                str(row.get("path") or ""),
            )
        )
        return ranked

    @staticmethod
    def _ownership_edge_delegates(
        edge: OwnershipRelationEdge, base_path: str, base_depth: int
    ) -> bool:
        return (
            str(edge.get("from") or "") == base_path
            and int(edge.get("depth") or 0) == base_depth + 1
            and not bool(edge.get("cycle"))
        )

    @staticmethod
    def _ownership_edge_refines(
        edge: OwnershipRelationEdge, target_locality: set[str], base_locality: set[str]
    ) -> bool:
        if (
            edge.get("relation") == "calls"
            and edge.get("resolution") == "import-constrained-symbol"
        ):
            return True
        return (
            edge.get("relation") == "imports"
            and edge.get("resolution") == "exact-module"
            and bool(target_locality - base_locality)
        )

    @classmethod
    def _delegated_target_for_edge(
        cls,
        edge: OwnershipRelationEdge,
        base_path: str,
        base_depth: int,
        base_locality: set[str],
        ranked_by_path: dict[str, OwnershipCandidate],
    ) -> str | None:
        if not cls._ownership_edge_delegates(edge, base_path, base_depth):
            return None
        target = str(edge.get("to") or "")
        target_row = ranked_by_path.get(target)
        if target_row is None:
            return None
        locality = set(target_row.get("task_locality_terms") or [])
        return (
            target
            if cls._ownership_edge_refines(edge, locality, base_locality)
            else None
        )

    @classmethod
    def _delegated_ownership_targets(
        cls,
        state: _OwnershipGraphState,
        ranked: list[OwnershipCandidate],
        selected: OwnershipCandidate,
    ) -> set[str]:
        base_path = str(selected.get("path") or "")
        base_depth = int(selected.get("depth") or 0)
        base_locality = set(selected.get("task_locality_terms") or [])
        ranked_by_path = {str(row.get("path") or ""): row for row in ranked}
        return {
            target
            for edge in state.edges
            if (
                target := cls._delegated_target_for_edge(
                    edge, base_path, base_depth, base_locality, ranked_by_path
                )
            )
            is not None
        }

    @staticmethod
    def _delegated_candidates(
        ranked: Sequence[OwnershipCandidate], targets: set[str]
    ) -> list[OwnershipCandidate]:
        return [
            row
            for row in ranked
            if str(row.get("path") or "") in targets
            and bool(row.get("corroborated"))
            and row.get("task_locality_terms")
        ]

    @staticmethod
    def _baseline_ownership_candidate(
        ranked: Sequence[OwnershipCandidate],
    ) -> OwnershipCandidate | None:
        baseline = [row for row in ranked if int(row.get("depth") or 0) <= 2]
        return next((row for row in baseline if row.get("corroborated")), None)

    @classmethod
    def _select_ownership_candidate(
        cls,
        state: _OwnershipGraphState,
        ranked: list[OwnershipCandidate],
        max_depth: int,
    ) -> tuple[OwnershipCandidate | None, str]:
        selected = cls._baseline_ownership_candidate(ranked)
        search_complete = not state.search_bound_reasons
        if selected is None:
            return (
                None,
                "unresolved" if search_complete else "unresolved-search-incomplete",
            )
        if max_depth < 3:
            return selected, "bounded-two-hop-corroboration"
        targets = cls._delegated_ownership_targets(state, ranked, selected)
        delegated = cls._delegated_candidates(ranked, targets)
        if len(delegated) == 1 and search_complete:
            return delegated[0], "unique-task-local-delegation-continuation"
        if not search_complete:
            return selected, "bounded-two-hop-corroboration-search-incomplete"
        return selected, "bounded-two-hop-corroboration"

    @staticmethod
    def _ownership_path(
        state: _OwnershipGraphState, selected: OwnershipCandidate | None
    ) -> list[OwnershipPathHop]:
        if selected is None:
            return []
        cursor = str(selected["path"])
        reverse: list[OwnershipPathHop] = []
        while cursor != state.start and cursor in state.parents:
            parent, relation = state.parents[cursor]
            reverse.append({"from": parent, "to": cursor, "relation": relation})
            cursor = parent
        return list(reversed(reverse))

    @staticmethod
    def _selected_ownership_path(selected: OwnershipCandidate | None) -> str | None:
        return None if selected is None else str(selected["path"])

    @operation_response("ownership_relation_graph")
    def relations(
        self,
        task: str,
        start_path: str,
        *,
        max_depth: int = OWNERSHIP_RELATION_DEFAULT_OPTIONS.max_depth,
    ) -> OwnershipRelationGraph:
        """Project a bounded, cycle-safe ownership relation graph."""
        start = normalize_relative_path(start_path, allow_root=False)
        max_depth = max(1, min(int(max_depth), 4))
        start_row = self.reads.file_row(start)
        if (
            start_row is not None
            and EvidenceVisibility(str(start_row["evidence_visibility"]))
            is EvidenceVisibility.DENY
        ):
            raise PermissionError(f"path is not agent-visible: {start}")
        state = _OwnershipGraphState(
            start, set(_query_terms(task)), {}, [], {}, {}, {start}
        )
        self._ownership_node(state, start)
        frontier: list[tuple[str, int, tuple[str, ...]]] = [(start, 0, (start,))]
        while frontier:
            frontier = self._expand_ownership_level(state, frontier, max_depth)
        ranked = self._rank_ownership_candidates(state)
        selected, selection_reason = self._select_ownership_candidate(
            state, ranked, max_depth
        )
        owner_path = self._ownership_path(state, selected)
        search_complete = not state.search_bound_reasons
        return {
            "schema": operation_schema("ownership_relation_graph"),
            "task": task,
            "start_path": start,
            "max_depth": max_depth,
            "nodes": sorted(state.nodes.values(), key=lambda row: str(row["path"])),
            "edges": state.edges,
            "candidates": ranked,
            "selected": self._selected_ownership_path(selected),
            "selection_reason": selection_reason,
            "completeness": "complete" if search_complete else "incomplete",
            "truncation": "complete" if search_complete else "truncated",
            "negative_evidence_admissible": search_complete,
            "uniqueness_admissible": search_complete,
            "search_bound_reasons": sorted(state.search_bound_reasons),
            "bounds": {
                "max_depth": max_depth,
                "edges_per_path": 100,
                "node_symbols": 12,
                "symbols_per_alias": 12,
                "symbol_candidates": 5000,
            },
            "owner_path": owner_path,
            "cycle_count": sum(1 for edge in state.edges if edge["cycle"]),
            "revisit_count": sum(1 for edge in state.edges if edge["revisited"]),
            "cycle_policy": "bounded-ancestor-cycle-cutoff-plus-revisit-deduplication",
            "relation_authority": "imports-and-calls-are-evidence-not-ownership-truth",
            "secret_knowledge_used": False,
        }

    @staticmethod
    def _selected_owner_row(
        graph: OwnershipRelationGraph, selected_path: object
    ) -> OwnershipCandidate | None:
        candidates = graph.get("candidates")
        if not isinstance(candidates, list):
            return None
        return next(
            (
                row
                for row in candidates
                if isinstance(row, dict) and row.get("path") == selected_path
            ),
            None,
        )

    @staticmethod
    def _last_owner_path_row(
        owner_path: Sequence[OwnershipPathHop],
    ) -> Mapping[str, object]:
        return owner_path[-1] if owner_path else {}

    @staticmethod
    def _owner_projection_value(
        row: Mapping[str, object], key: str, default: object
    ) -> object:
        value = row.get(key)
        return default if value is None else value

    def _structural_owner_candidate(
        self,
        start_path: str,
        *,
        max_depth: int = OWNERSHIP_RELATION_DEFAULT_OPTIONS.max_depth,
        task: str = "",
    ) -> StructuralOwnerCandidate | None:
        """Project the selected typed ownership relation into the action anchor shape."""
        graph = self.relations(task, start_path, max_depth=max_depth)
        return self._structural_owner_from_graph(graph, start_path)

    def _structural_owner_from_graph(
        self, graph: OwnershipRelationGraph, start_path: str
    ) -> StructuralOwnerCandidate | None:
        """Retain graph qualification while projecting a selected candidate."""
        selected_path = graph.get("selected")
        if not selected_path:
            return None
        selected = self._selected_owner_row(graph, selected_path)
        if selected is None:
            return None
        owner_path = list(graph["owner_path"])
        last = self._last_owner_path_row(owner_path)
        via = self._owner_projection_value(last, "relation", "relation-graph")
        source_path = self._owner_projection_value(last, "from", start_path)
        depth = selected["depth"]
        corroboration = selected.get("corroboration", [])
        return {
            "path": str(selected_path),
            "depth": int(depth),
            "via": str(via).removesuffix("s"),
            "source_path": str(source_path),
            "owner_path": owner_path,
            "corroboration": list(corroboration),
            "cycle_count": graph["cycle_count"],
            "revisit_count": graph["revisit_count"],
            "relation_graph_schema": graph["schema"],
            "relation_graph_completeness": graph["completeness"],
            "relation_graph_truncation": graph["truncation"],
            "relation_graph_search_bound_reasons": list(graph["search_bound_reasons"]),
        }
