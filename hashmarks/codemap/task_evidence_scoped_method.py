"""Non-authoritative method retrieval within one explicit class scope."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

from .model import EvidenceVisibility

if TYPE_CHECKING:
    from .engine import CodeMap


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

    def _task_evidence_attach_enclosing_functions(
        self, packet: dict[str, object]
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
            if (
                self._task_evidence_visibility(path)
                not in {EvidenceVisibility.SOURCE, EvidenceVisibility.OUTLINE}
                or self.policy.decide(path).evidence_visibility
                is EvidenceVisibility.DENY
            ):
                continue
            context = self._task_evidence_enclosing_functions(path, symbol)
            if context is not None and self._indexed_path_current(path):
                row["enclosing_declarations"] = context

    def _task_evidence_class_declarations(
        self, path: str, parent: Mapping[str, object]
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
        return {
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

    def _task_evidence_attach_class_declarations(
        self, packet: dict[str, object]
    ) -> None:
        """Keep the first retrieved class's members visible without reranking it."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        retrieval = packet.get("retrieval")
        if not isinstance(retrieval, dict):
            return
        for row in retrieval.get("results", [])[:3]:
            path, symbol = row.get("path"), row.get("symbol")
            if not path or not symbol or not self._indexed_path_current(path):
                continue
            visibility = self._task_evidence_visibility(path)
            if (
                visibility
                not in {EvidenceVisibility.SOURCE, EvidenceVisibility.OUTLINE}
                or self.policy.decide(path).evidence_visibility
                is EvidenceVisibility.DENY
            ):
                continue
            declaration = self.store.symbol_at(path, symbol)
            if (
                declaration is None
                or declaration.get("kind") != "class"
                or not isinstance(declaration.get("start_line"), int)
                or not isinstance(declaration.get("end_line"), int)
                or (declaration.get("start_line"), declaration.get("end_line"))
                != (row.get("start_line"), row.get("end_line"))
            ):
                continue
            context = self._task_evidence_class_declarations(path, declaration)
            if self._indexed_path_current(path):
                row["class_declarations"] = context
            return

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
        self, owner: Mapping[str, object]
    ) -> Mapping[str, object] | None:
        """Rebind the admitted locator to an exact, visible current symbol."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        path = str(owner.get("path") or "")
        qualname = str(owner.get("qualname") or "")
        if not path or not qualname:
            return None
        if self._task_evidence_visibility(path) not in {
            EvidenceVisibility.SOURCE,
            EvidenceVisibility.OUTLINE,
        }:
            return None
        if (
            self.policy.decide(path).evidence_visibility is EvidenceVisibility.DENY
            or not self._indexed_path_current(path)
        ):
            return None
        return self.store.symbol_at(path, qualname)

    def _task_evidence_attach_scip_discovery(
        self,
        packet: dict[str, object],
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
            current = self._task_evidence_current_scip_symbol(owner)
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
                    "exact-owner-scip-definition-outgoing"
                    if discovery is not None
                    else "explicit-producer-claims-associated-with-owner"
                ),
                "associated_observed_relationship_count": compact[
                    "observed_relationship_count"
                ],
                "associated_observed_relationship_count_scope": (
                    "explicit-producer-claims-associated-with-owner"
                ),
                "evidence": compact,
                "evidence_refs": {
                    "ownership": "/ownership",
                    "source": "/ownership/source_evidence",
                    "verification": "/verification",
                },
            }
