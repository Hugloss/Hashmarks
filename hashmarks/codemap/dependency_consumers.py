"""Source-qualified dependency import observations over explicit bounded members."""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

from hashmarks.file_store import UnstableFileError
from hashmarks.operation_contract import operation_response, operation_schema
from hashmarks.paths import normalize_relative_path
from hashmarks.python_ast_cache import read_python_ast

from .decision_session import ReadScopeOwner, decision_scoped
from .dependency_resolution_correlation import (
    _dependency_provenance,
    _ownership_summary,
)
from .python_exports import python_import_target

if TYPE_CHECKING:
    from .repository_dependencies import RepositoryDependencies


def _source_imports(tree: ast.Module) -> list[tuple[str, int, bool]]:
    direct = {id(node) for node in tree.body}
    imports: list[tuple[str, int, bool]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(
                (alias.name, node.lineno, id(node) not in direct)
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            imports.extend(
                (
                    python_import_target(node, alias.name),
                    node.lineno,
                    id(node) not in direct,
                )
                for alias in node.names
            )
    return sorted(set(imports))


def _paths(values: Sequence[str]) -> list[str]:
    if (
        not isinstance(values, Sequence)
        or isinstance(values, (str, bytes))
        or not 1 <= len(values) <= 64
    ):
        raise ValueError("dependency consumers require 1 to 64 explicit source paths")
    if any(not isinstance(path, str) for path in values):
        raise ValueError("dependency consumer source paths must be strings")
    paths = [normalize_relative_path(path, allow_root=False) for path in values]
    if len(set(paths)) != len(paths):
        raise ValueError("duplicate dependency consumer source path")
    return sorted(paths)


def _selected_nodes(
    observation: Mapping[str, object],
    node_ids: Sequence[str],
    limit: int,
    max_depth: int,
) -> tuple[set[str], set[str]]:
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("dependency consumer limit must be between 1 and 1000")
    if type(max_depth) is not int or not 1 <= max_depth <= 12:
        raise ValueError("dependency consumer depth must be between 1 and 12")
    if (
        not isinstance(node_ids, Sequence)
        or isinstance(node_ids, (str, bytes))
        or not 1 <= len(node_ids) <= 64
    ):
        raise ValueError("dependency consumers require 1 to 64 selected node IDs")
    if any(not isinstance(node_id, str) or not node_id.strip() for node_id in node_ids):
        raise ValueError("dependency consumer node IDs must be nonblank strings")
    selected = set(node_ids)
    python_components = {
        str(row["component_id"])
        for row in cast("Sequence[Mapping[str, object]]", observation["components"])
        if row["ecosystem"] == "pypi"
    }
    known = {
        str(row["node_id"])
        for row in cast("Sequence[Mapping[str, object]]", observation["selections"])
        if row["component_id"] in python_components
    }
    if len(selected) != len(node_ids) or not selected <= known:
        raise ValueError(
            "dependency consumer node IDs must be unique known Python distribution selections"
        )
    return selected, known


class DependencyConsumersMixin(ReadScopeOwner):
    def _dependency_consumer_source(
        self, path: str
    ) -> tuple[dict[str, object], ast.Module | None]:
        if TYPE_CHECKING:
            self = cast("RepositoryDependencies", self)
        member, raw = self.source._bounded_source_observation(path, 1_048_576)
        if (
            raw is None
            or member["state"] != "known-present"
            or not path.endswith((".py", ".pyi"))
        ):
            return member, None
        try:
            parsed = read_python_ast(self.source.workspace / path)
        except (OSError, SyntaxError, UnicodeError):
            return member, None
        if parsed.source != raw.decode("utf-8").replace("\r\n", "\n").replace(
            "\r", "\n"
        ):
            raise UnstableFileError(
                "dependency consumer source changed during observation"
            )
        return member, parsed.tree

    def _dependency_consumer_row(
        self,
        path: str,
        member: Mapping[str, object],
        imported: tuple[str, int, bool],
        ownership: Sequence[Mapping[str, object]],
        node_ids: set[str],
        python_nodes: set[str],
    ) -> dict[str, object] | None:
        if TYPE_CHECKING:
            self = cast("RepositoryDependencies", self)
        target, line, conditional = imported
        if target.startswith(".") or self.imports._resolve_import_paths(path, target):
            return None
        candidates = self.imports._python_import_module_candidates(path, target)
        matches = self._import_ownership_matches(ownership, candidates, None)
        matches = [
            row
            for row in matches
            if set(cast("Sequence[str]", row["owners"])) <= python_nodes
        ]
        if not any(
            node_ids.intersection(cast("Sequence[str]", row["owners"]))
            for row in matches
        ):
            return None
        return {
            "source_path": path,
            "source_member": dict(member),
            "import_target": target,
            "line": line,
            "conditional_or_deferred": conditional,
            "import_claim_authority": "source-observed-static-import",
            "matched_modules": [dict(row) for row in matches],
            **_ownership_summary(matches),
        }

    def _dependency_consumer_rows(
        self,
        paths: Sequence[str],
        ownership: Sequence[Mapping[str, object]],
        selected: set[str],
        limit: int,
        python_nodes: set[str],
    ) -> tuple[list[dict[str, object]], list[str], list[dict[str, object]], int]:
        members: list[dict[str, object]] = []
        unavailable: list[str] = []
        rows: list[dict[str, object]] = []
        count = 0
        for path in paths:
            member, tree = self._dependency_consumer_source(path)
            members.append(member)
            if tree is None:
                unavailable.append(path)
                continue
            for imported in _source_imports(tree):
                row = self._dependency_consumer_row(
                    path, member, imported, ownership, selected, python_nodes
                )
                if row is not None:
                    count += 1
                    if len(rows) < limit:
                        rows.append(row)
        return members, unavailable, rows, count

    @operation_response("dependency_consumers")
    @decision_scoped
    def consumers(
        self,
        observation: Mapping[str, object],
        *,
        source_paths: Sequence[str],
        node_ids: Sequence[str],
        limit: int = 100,
        max_depth: int = 8,
    ) -> dict[str, object]:
        """Observe imports, preserving metadata and consumer-scope uncertainty.

        Paths are caller-selected scope, not claimed imports. Only current native
        source syntax creates an import row. Downstream relations retain the
        existing relationship owner's bounded advisory meaning.
        """
        if TYPE_CHECKING:
            self = cast("RepositoryDependencies", self)
        paths = _paths(source_paths)
        self._require_current_dependency_observation_v3(observation)
        selected, python_nodes = _selected_nodes(
            observation, node_ids, limit, max_depth
        )
        ownership = cast(
            "Sequence[Mapping[str, object]]", observation["module_ownership"]
        )
        members, unavailable, returned, count = self._dependency_consumer_rows(
            paths, ownership, selected, limit, python_nodes
        )
        downstream = [
            {
                "source_path": path,
                "relationships": self.relationships.affected(path, max_depth=max_depth),
            }
            for path in sorted({str(row["source_path"]) for row in returned})
        ]
        for path, member in zip(paths, members, strict=True):
            current, _raw = self.source._bounded_source_observation(path, 1_048_576)
            if current != member:
                raise UnstableFileError(
                    "dependency consumer source changed during observation"
                )
        self._require_current_dependency_observation_v3(observation)
        source_ids = {
            str(source)
            for row in returned
            for source in cast("Sequence[str]", row["evidence_sources"])
        }
        return {
            "schema": operation_schema("dependency_consumers"),
            "observation_identity": observation["observation_identity"],
            "repository_binding": dict(
                cast("Mapping[str, object]", observation["repository_binding"])
            ),
            "selected_node_ids": sorted(selected),
            "source_scope": {
                "paths": paths,
                "members": members,
                "unavailable": unavailable,
                "completeness": "incomplete" if unavailable else "complete",
            },
            "consumers": returned,
            "observed_consumer_count": count,
            "truncation": "truncated" if count > limit else "complete",
            "downstream_relationships": downstream,
            "dependency_provenance": _dependency_provenance(observation, source_ids),
            "consumer_scope": {
                "completeness": "incomplete",
                "negative_evidence": "not-admissible",
                "reasons": [
                    "explicit-source-scope",
                    "dynamic-imports-and-custom-loaders-not-observed",
                    "metadata-owner-scope-not-exhaustive",
                    "downstream-relations-bounded-and-advisory",
                    "only-pypi-module-namespace-observed",
                ],
            },
            "authority": "repository-intelligence-only",
            "producer_authority": "caller-claimed",
            "execution_authority": "external",
            "result_authority": "external",
            "certification_authority": "external",
        }
