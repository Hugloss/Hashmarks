"""Bounded lexical source disclosure; Source owns bytes and line authority."""

from __future__ import annotations

import ast
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from itertools import islice
from typing import TYPE_CHECKING, cast

from hashmarks.python_ast_cache import read_python_ast

from .model import EvidenceVisibility
from .query_primitives import _TASK_STOPWORDS

if TYPE_CHECKING:
    from .repository_tasks import RepositoryTasks
    from .task_evidence_types import RetrievalLocator, TaskEvidenceDraft

_MAX_SOURCE_BYTES = 262_144
_MAX_SOURCE_NODES = 4096
_MAX_SOURCE_ANCHORS = 3


def _loaded_names(tree: ast.Module) -> tuple[dict[int, set[str]], bool]:
    nodes = list(islice(ast.walk(tree), _MAX_SOURCE_NODES + 1))
    names: dict[int, set[str]] = defaultdict(set)
    for node in nodes[:_MAX_SOURCE_NODES]:
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            names[node.lineno].add(node.id)
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            names[node.lineno].add(node.attr)
    return names, len(nodes) > _MAX_SOURCE_NODES


def _declared_field_spans(row: Mapping[str, object]) -> list[tuple[int, int]]:
    context = cast("Mapping[str, object]", row.get("field_declarations", {}))
    return [
        (cast("int", field["line"]), cast("int", field["end_line"]))
        for group in cast("list[dict[str, object]]", context.get("groups", []))
        for field in cast(
            "list[dict[str, object]]",
            cast("Mapping[str, object]", group["value"])["fields"],
        )
    ]


class TaskEvidenceSourceContextMixin:
    def _task_source_context_lines(
        self, path: str, task: str, row: Mapping[str, object]
    ) -> tuple[list[int], dict[str, object]] | None:
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        query = self._task_evidence_retrieval_query(task)
        terms, query_truncated = self.search._task_natural_term_candidates(
            query, include_derivations=True
        )
        groups = self._task_evidence_distinct_query_groups(
            tuple(
                tuple(
                    variant
                    for variant in self.search._task_natural_term_variants(
                        word, include_derivations=True
                    )
                    if variant in terms
                )
                for word in re.findall(r"[A-Za-z]+", query.lower())
                if word not in _TASK_STOPWORDS
            )
        )
        if len(groups) < 2:
            return None
        self.source.ensure_current(path)
        member, _ = self.source.member(path)
        if (
            member.get("state") != "known-present"
            or member.get("evidence_visibility") != "source"
        ):
            return None
        try:
            if (self.workspace / path).stat().st_size > _MAX_SOURCE_BYTES:
                return None
            snapshot = read_python_ast(self.workspace / path)
        except (OSError, UnicodeError, SyntaxError, ValueError):
            return None
        self.source.ensure_current(path)
        current_member, _ = self.source.member(path)
        if current_member != member:
            return None
        names, nodes_truncated = _loaded_names(snapshot.tree)
        excluded = _declared_field_spans(row)
        selected = self._task_source_ranked_lines(names, groups, excluded)
        return selected[:_MAX_SOURCE_ANCHORS], {
            "basis": "loaded-identifier-terms-at-source-line",
            "coverage": "incomplete",
            "ownership_authority": False,
            "negative_evidence_admissible": False,
            "candidate_node_bound": _MAX_SOURCE_NODES,
            "candidate_nodes_truncated": nodes_truncated,
            "query_terms_truncated": query_truncated,
            "observed_candidates_in_scanned_nodes": len(selected),
            "returned": min(len(selected), _MAX_SOURCE_ANCHORS),
            "omitted_candidates_in_scanned_nodes": max(
                0, len(selected) - _MAX_SOURCE_ANCHORS
            ),
            "bound": _MAX_SOURCE_ANCHORS,
        }

    def _task_source_ranked_lines(
        self,
        names: Mapping[int, set[str]],
        groups: Sequence[tuple[str, ...]],
        excluded: Sequence[tuple[int, int]],
    ) -> list[int]:
        if TYPE_CHECKING:
            self = cast("RepositoryTasks", self)
        candidates = [
            (
                tuple(
                    index
                    for index, group in enumerate(groups)
                    if self._task_evidence_natural_match_count(
                        " ".join(sorted(words)), (group,)
                    )
                ),
                line,
            )
            for line, words in names.items()
            if not any(start <= line <= end for start, end in excluded)
        ]
        frequencies = Counter(index for matched, _ in candidates for index in matched)
        return [
            line
            for matched, line in sorted(
                candidates,
                key=lambda row: (
                    -len(row[0]),
                    sum(frequencies[index] for index in row[0]),
                    row[1],
                ),
            )
            if matched
        ]

    def _task_evidence_attach_source_context(self, packet: TaskEvidenceDraft) -> None:
        codemap = cast("RepositoryTasks", self)
        target = packet["explicit_target"]
        path = target["path"]
        if target["basis"] != "literal-path" or not path or not path.endswith(".py"):
            return
        if (
            not codemap.index.is_current(path)
            or codemap._task_evidence_visibility(path) is not EvidenceVisibility.SOURCE
            or codemap.files.decide(path).evidence_visibility
            is not EvidenceVisibility.SOURCE
        ):
            return
        row = next(
            (row for row in packet["retrieval"]["results"] if row["path"] == path), None
        )
        if row is None:
            return
        selected = codemap._task_source_context_lines(path, packet["task"], row)
        if selected is None:
            return
        if not selected[0]:
            if (
                selected[1]["candidate_nodes_truncated"]
                or selected[1]["query_terms_truncated"]
            ):
                row["source_selection"] = selected[1]
            return
        observation = codemap.source.observe(
            path, lines=selected[0], anchor_context_lines=1, max_bytes=_MAX_SOURCE_BYTES
        )
        if codemap.index.is_current(path) and observation["availability"] == "observed":
            row["source_observation"] = observation
            row["source_selection"] = selected[1]
