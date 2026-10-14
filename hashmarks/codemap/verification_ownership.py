"""Projection of existing edit authority and bounded verifier correspondence.

These are repository-derived CodeMap links, without new inferred relationships,
verification sufficiency or execution authority.
"""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, TypedDict, cast

from hashmarks.operation_contract import operation_response, operation_schema

from .verification_defaults import VERIFICATION_RELEVANCE_DEFAULTS

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .engine import CodeMap
    from .task_evidence_types import TaskVerificationPlan


class _VerificationOwner(TypedDict):
    path: str
    score: object
    reason: object
    plan: TaskVerificationPlan
    covers_edit_candidates: list[str]
    coverage_evidence: str | None


class VerificationOwnershipMixin:
    @staticmethod
    def _verification_edit_paths(action: Mapping[str, object]) -> list[str]:
        edit = action.get("edit")
        if not isinstance(edit, dict):
            return []
        path = edit.get("path")
        return [str(path)] if isinstance(path, str) else []

    @staticmethod
    def _authority_rows(
        authority: dict[str, object] | None,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        if not isinstance(authority, dict):
            return [], []
        nodes = authority.get("nodes")
        edges = authority.get("edges")
        node_rows = (
            [row for row in nodes if isinstance(row, dict)]
            if isinstance(nodes, list)
            else []
        )
        edge_rows = (
            [row for row in edges if isinstance(row, dict)]
            if isinstance(edges, list)
            else []
        )
        return node_rows, edge_rows

    @staticmethod
    def _authority_node_ids(path: str, nodes: list[dict[str, object]]) -> set[str]:
        file_id = f"file:{path}"
        return {
            str(row["id"])
            for row in nodes
            if isinstance(row.get("id"), str)
            and (row.get("path") == path or row.get("id") == file_id)
        }

    @staticmethod
    def _authority_relations(
        path: str, edges: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        file_id = f"file:{path}"
        return [
            dict(row)
            for row in edges
            if row.get("source") == file_id or row.get("target") == file_id
        ]

    @staticmethod
    def _relation_node_ids(relations: list[dict[str, object]]) -> set[str]:
        ids: set[str] = set()
        for row in relations:
            for value in (row.get("source"), row.get("target")):
                if isinstance(value, str):
                    ids.add(value)
        return ids

    @classmethod
    def _authority_entry(
        cls,
        path: str,
        nodes: list[dict[str, object]],
        edges: list[dict[str, object]],
        ownership_resolution: object,
    ) -> dict[str, object]:
        relations = cls._authority_relations(path, edges)
        node_ids = cls._authority_node_ids(path, nodes) | cls._relation_node_ids(
            relations
        )
        entry: dict[str, object] = {
            "path": path,
            "authority_node_ids": sorted(node_ids),
            "authority_relations": sorted(
                relations,
                key=lambda row: (
                    str(row.get("source") or ""),
                    str(row.get("target") or ""),
                    str(row.get("relation") or ""),
                ),
            ),
        }
        if (
            isinstance(ownership_resolution, dict)
            and ownership_resolution.get("path") == path
        ):
            entry["ownership_resolution"] = dict(ownership_resolution)
        return entry

    def _edit_authorities(
        self,
        edit_paths: list[str],
        authority: dict[str, object] | None,
        ownership_resolution: object,
    ) -> list[dict[str, object]]:
        nodes, edges = self._authority_rows(authority)
        return [
            self._authority_entry(path, nodes, edges, ownership_resolution)
            for path in edit_paths
        ]

    @staticmethod
    def _coverage_for_candidate(
        item: dict[str, object], edit_paths: list[str]
    ) -> tuple[list[str], str | None]:
        if not edit_paths:
            return [], None
        if bool(item.get("direct_reference")):
            return list(edit_paths), "direct-reference"
        if bool(item.get("indirect_reference")):
            return list(edit_paths), "bounded-indirect-reference"
        return [], None

    def _verification_owner_row(
        self, item: dict[str, object], edit_paths: list[str]
    ) -> _VerificationOwner | None:
        self = cast("CodeMap", self)
        path = item.get("path")
        if not isinstance(path, str):
            return None
        coverage, evidence = self._coverage_for_candidate(item, edit_paths)
        return {
            "path": path,
            "score": item.get("score"),
            "reason": item.get("reason"),
            "plan": self.verification_plan(
                path,
                symbol=cast("str | None", item.get("name")),
                qualname=cast("str | None", item.get("qualname")),
            ),
            "covers_edit_candidates": coverage,
            "coverage_evidence": evidence,
        }

    def _verification_owner_rows(
        self, relevance: Mapping[str, object], edit_paths: list[str]
    ) -> tuple[list[_VerificationOwner], int]:
        candidates = relevance.get("candidates")
        if not isinstance(candidates, list):
            return [], 0
        rows = [
            row
            for item in candidates
            if isinstance(item, dict)
            and (row := self._verification_owner_row(item, edit_paths)) is not None
        ]
        links = sum(len(row.get("covers_edit_candidates", [])) for row in rows)
        return rows, links

    @staticmethod
    def _linked_edit_paths(verifiers: list[_VerificationOwner]) -> set[str]:
        return {
            covered
            for verifier in verifiers
            for covered in verifier.get("covers_edit_candidates", [])
            if isinstance(covered, str)
        }

    @staticmethod
    def _verification_summary_state(
        relevance: Mapping[str, object], returned_owners: int
    ) -> tuple[bool | None, bool | None]:
        """Derive summary claims before the bounded owner projection."""
        count = relevance.get("candidate_count")
        observed_count = (
            count if type(count) is int and count >= returned_owners else None
        )
        qualified = relevance.get("negative_evidence_admissible") is True
        unowned = (
            False
            if returned_owners
            else True
            if qualified and observed_count == 0
            else None
        )
        ambiguous = (
            True
            if (observed_count or returned_owners) > 1 and not relevance.get("selected")
            else False
            if qualified and observed_count is not None
            else None
        )
        return unowned, ambiguous

    @operation_response("verification_ownership")
    def verification_ownership_graph(
        self,
        task: str,
        *,
        limit: int = VERIFICATION_RELEVANCE_DEFAULTS.limit,
        candidate_limit: int = VERIFICATION_RELEVANCE_DEFAULTS.candidate_limit,
    ) -> dict[str, object]:
        """Expose verification owners and their evidence-backed edit-authority links."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        relevance = self.verification_relevance(
            task, limit=limit, candidate_limit=candidate_limit
        )
        action = self.task_action_map(task, limit=limit)
        edit_paths = sorted(set(self._verification_edit_paths(action)))
        authority = self.repository_ownership_graph(edit_paths) if edit_paths else None
        edit_authorities = self._edit_authorities(
            edit_paths, authority, action.get("ownership_resolution")
        )
        verifiers, verification_links = self._verification_owner_rows(
            relevance, edit_paths
        )
        linked_paths = self._linked_edit_paths(verifiers)
        unowned, ambiguous = self._verification_summary_state(relevance, len(verifiers))
        generation, identity_generation, stale = self._generation_status()
        return {
            "schema": operation_schema("verification_ownership"),
            "generation": generation,
            "identity_generation": identity_generation,
            "stale": stale,
            "task": task,
            "edit_candidates": edit_paths,
            "edit_authorities": edit_authorities,
            "verification_owners": verifiers,
            "verification_qualification": {
                key: deepcopy(relevance.get(key))
                for key in (
                    "authority",
                    "completeness",
                    "truncation",
                    "negative_evidence_admissible",
                    "qualified_identity_ambiguous",
                    "candidate_count",
                    "bounds",
                    "search_bound_reasons",
                    "selection_reason",
                )
                if key in relevance
            },
            "summary": {
                "edit_candidates": len(edit_paths),
                "edit_authorities": len(edit_authorities),
                "verification_owners": len(verifiers),
                "verification_links": verification_links,
                "unlinked_edit_candidates": len(set(edit_paths) - linked_paths),
                "unowned": unowned,
                "ambiguous": ambiguous,
            },
            "boundary": "verification/authority repository evidence only; Hashmarks does not execute or certify verification",
        }
