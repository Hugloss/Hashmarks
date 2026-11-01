"""Source-qualified dependency import observations over explicit bounded members."""

from __future__ import annotations

import ast
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
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
from .source_languages import SOURCE_LANGUAGES

if TYPE_CHECKING:
    from .repository_dependencies import RepositoryDependencies

_SUPPORTED_ECOSYSTEMS = frozenset({"npm", "pypi"})
_PACKAGE_NAME = re.compile(r"(?:@[A-Za-z0-9._~-]+/)?[A-Za-z0-9._~-]+\Z")
# Conservatively omit known bare runtime namespaces; this is not a runtime inventory.
_NODE_RUNTIME_NAMES = frozenset(
    "assert async_hooks buffer child_process cluster console constants crypto dgram "
    "diagnostics_channel dns domain events fs http http2 https inspector module net "
    "os path perf_hooks process punycode querystring readline repl stream "
    "string_decoder sys timers tls trace_events tty url util v8 vm wasi "
    "worker_threads zlib".split()
)


@dataclass(frozen=True)
class _Import:
    target: str
    line: int
    conditional: bool
    type_only: bool = False
    syntax_evidence: Mapping[str, object] = field(default_factory=dict)


@dataclass
class _SourceImports:
    member: dict[str, object]
    ecosystem: str | None
    imports: list[_Import]
    observation: dict[str, object]

    @property
    def path(self) -> str:
        return str(self.member["path"])


@dataclass(frozen=True)
class _Selections:
    selected: set[str]
    ecosystems: Mapping[str, str]
    profiles: Mapping[str, set[str]]

    def profile_nodes(self, ecosystem: str | None) -> set[str]:
        return self.profiles.get(ecosystem or "", set())

    def capability(self) -> dict[str, object]:
        unsupported = sorted(
            node
            for node in self.selected
            if self.ecosystems[node] not in _SUPPORTED_ECOSYSTEMS
        )
        return {
            "supported_ecosystems": sorted(_SUPPORTED_ECOSYSTEMS),
            "unsupported_node_ids": unsupported,
            "state": "unsupported"
            if len(unsupported) == len(self.selected)
            else "partial"
            if unsupported
            else "supported",
        }


def _npm_candidates(target: str) -> tuple[str, ...]:
    parts = target.split("/")
    root_size = 2 if target.startswith("@") else 1
    namespace = "/".join(parts[:root_size])
    if (
        not _PACKAGE_NAME.fullmatch(namespace)
        or namespace in _NODE_RUNTIME_NAMES
        or any(part in {"", ".", ".."} for part in parts)
        or any(character in target for character in ("\\", ":", "#", "?", "%"))
    ):
        return ()
    return tuple("/".join(parts[:end]) for end in range(len(parts), root_size - 1, -1))


def _source_observation(
    member: Mapping[str, object], ecosystem: str | None
) -> dict[str, object]:
    return {
        "path": member["path"],
        "ecosystem": ecosystem,
        "availability": "unavailable",
        "completeness": "unknown",
        "truncation": "unknown",
        "reasons": [member.get("reason") or "unsupported-source-language"],
    }


def _native_import(
    fact: Mapping[str, object], observation: Mapping[str, object]
) -> _Import:
    return _Import(
        str(fact["module_specifier"]),
        cast("int", fact["line"]),
        fact["parent_syntax_type"] != "program",
        bool(fact["type_only"]),
        {
            "observation_identity": observation["observation_identity"],
            "fact_identity": fact["evidence_identity"],
            "range": fact["range"],
            "declaration_kind": fact["declaration_kind"],
            "syntax_context": fact["syntax_context"],
        },
    )


def _ecmascript_imports(
    packet: Mapping[str, object],
) -> tuple[list[_Import], list[str]]:
    imports: list[_Import] = []
    reasons: set[str] = set()
    for fact in cast("Sequence[Mapping[str, object]]", packet["facts"]):
        if fact["kind"] == "module-declaration":
            if isinstance(fact["module_specifier"], str):
                imports.append(_native_import(fact, packet))
            else:
                reasons.add("nonliteral-module-declaration-not-observed")
        elif fact["kind"] == "call-site":
            callee = cast("Mapping[str, object] | None", fact["callee"])
            if callee is not None and callee["text"] in {"import", "require"}:
                reasons.add("dynamic-or-commonjs-loading-not-observed")
    return imports, sorted(reasons)


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
) -> _Selections:
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
    components = {
        str(row["component_id"]): str(row["ecosystem"])
        for row in cast("Sequence[Mapping[str, object]]", observation["components"])
    }
    known = {
        str(row["node_id"]): components[str(row["component_id"])]
        for row in cast("Sequence[Mapping[str, object]]", observation["selections"])
    }
    if len(selected) != len(node_ids) or not selected <= known.keys():
        raise ValueError(
            "dependency consumer node IDs must be unique known dependency selections"
        )
    profiles = {
        ecosystem: {node for node, value in known.items() if value == ecosystem}
        for ecosystem in _SUPPORTED_ECOSYSTEMS
    }
    return _Selections(selected, known, profiles)


class DependencyConsumersMixin(ReadScopeOwner):
    def _dependency_python_source(self, path: str) -> _SourceImports:
        if TYPE_CHECKING:
            self = cast("RepositoryDependencies", self)
        member, raw = self.source._bounded_source_observation(path, 1_048_576)
        observation = _source_observation(member, "pypi")
        result = _SourceImports(member, "pypi", [], observation)
        if raw is None or member["state"] != "known-present":
            return result
        try:
            parsed = read_python_ast(self.source.workspace / path)
        except (OSError, SyntaxError, UnicodeError):
            observation["reasons"] = ["native-python-parse-failed"]
            return result
        if parsed.source != raw.decode("utf-8").replace("\r\n", "\n").replace(
            "\r", "\n"
        ):
            raise UnstableFileError(
                "dependency consumer source changed during observation"
            )
        result.imports = [_Import(*row) for row in _source_imports(parsed.tree)]
        observation.update(
            availability="observed",
            completeness="complete",
            truncation="complete",
            reasons=[],
        )
        return result

    def _dependency_ecmascript_source(self, path: str) -> _SourceImports:
        if TYPE_CHECKING:
            self = cast("RepositoryDependencies", self)
        packet = self.source.ecmascript(path, limit=500)
        member = cast("dict[str, object]", packet["member"])
        imported, reasons = _ecmascript_imports(packet)
        observation = {
            "path": path,
            "ecosystem": "npm",
            "availability": packet["availability"],
            "completeness": packet["completeness"],
            "truncation": "complete"
            if packet["truncation"] == "not-truncated"
            else packet["truncation"],
            "reasons": reasons + ([packet["reason"]] if packet["reason"] else []),
            "observation_identity": packet["observation_identity"],
            "parser": packet["parser"],
        }
        if reasons:
            observation["completeness"] = "incomplete"
        return _SourceImports(member, "npm", imported, observation)

    def _dependency_consumer_source(self, path: str) -> _SourceImports:
        if TYPE_CHECKING:
            self = cast("RepositoryDependencies", self)
        language = SOURCE_LANGUAGES.get(Path(path).suffix.lower())
        if language == "python":
            return self._dependency_python_source(path)
        if language in {"javascript", "typescript"}:
            return self._dependency_ecmascript_source(path)
        member, _raw = self.source._bounded_source_observation(path, 1_048_576)
        return _SourceImports(member, None, [], _source_observation(member, None))

    def _dependency_import_candidates(
        self, source: _SourceImports, imported: _Import
    ) -> tuple[str, ...]:
        if TYPE_CHECKING:
            self = cast("RepositoryDependencies", self)
        if source.ecosystem == "npm":
            return _npm_candidates(imported.target)
        if (
            imported.target.startswith(".")
            or self.imports._resolve_import_paths(source.path, imported.target)
            or self.imports._python_import_identity_ambiguous(
                source.path, imported.target
            )
        ):
            return ()
        return self.imports._python_import_module_candidates(
            source.path, imported.target
        )

    def _dependency_consumer_row(
        self,
        source: _SourceImports,
        imported: _Import,
        ownership: Sequence[Mapping[str, object]],
        selections: _Selections,
    ) -> dict[str, object] | None:
        if TYPE_CHECKING:
            self = cast("RepositoryDependencies", self)
        candidates = self._dependency_import_candidates(source, imported)
        matches = self._import_ownership_matches(ownership, candidates, None)
        profile_nodes = selections.profile_nodes(source.ecosystem)
        matches = [
            row
            for row in matches
            if set(cast("Sequence[str]", row["owners"])) <= profile_nodes
        ]
        if not any(
            selections.selected.intersection(cast("Sequence[str]", row["owners"]))
            for row in matches
        ):
            return None
        return {
            "source_path": source.path,
            "source_member": dict(source.member),
            "ecosystem": source.ecosystem,
            "import_target": imported.target,
            "line": imported.line,
            "conditional_or_deferred": imported.conditional,
            "type_only": imported.type_only,
            "import_claim_authority": "source-observed-static-import",
            "runtime_resolution": "not-observed",
            "syntax_evidence": dict(imported.syntax_evidence),
            "matched_modules": [dict(row) for row in matches],
            **_ownership_summary(matches),
        }

    def _dependency_consumer_rows(
        self,
        sources: Sequence[_SourceImports],
        ownership: Sequence[Mapping[str, object]],
        selections: _Selections,
        limit: int,
    ) -> tuple[list[dict[str, object]], int]:
        rows: list[dict[str, object]] = []
        count = 0
        for source in sources:
            for imported in source.imports:
                row = self._dependency_consumer_row(
                    source, imported, ownership, selections
                )
                if row is not None:
                    count += 1
                    if len(rows) < limit:
                        rows.append(row)
        return rows, count

    def _dependency_consumer_recheck(self, sources: Sequence[_SourceImports]) -> None:
        if TYPE_CHECKING:
            self = cast("RepositoryDependencies", self)
        for source in sources:
            current, _raw = self.source._bounded_source_observation(
                source.path, 1_048_576
            )
            if current != source.member:
                raise UnstableFileError(
                    "dependency consumer source changed during observation"
                )

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
        selections = _selected_nodes(observation, node_ids, limit, max_depth)
        ownership = cast(
            "Sequence[Mapping[str, object]]", observation["module_ownership"]
        )
        sources = [self._dependency_consumer_source(path) for path in paths]
        returned, count = self._dependency_consumer_rows(
            sources, ownership, selections, limit
        )
        downstream = [
            {
                "source_path": path,
                "relationships": self.relationships.affected(path, max_depth=max_depth),
            }
            for path in sorted({str(row["source_path"]) for row in returned})
        ]
        self._dependency_consumer_recheck(sources)
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
            "selected_node_ids": sorted(selections.selected),
            "capability": selections.capability(),
            "source_scope": _consumer_source_scope(sources),
            "consumers": returned,
            "observed_consumer_count": count,
            "observed_consumer_count_scope": "observed-static-import-facts",
            "truncation": "truncated"
            if count > limit
            or any(row.observation["truncation"] == "truncated" for row in sources)
            else "complete",
            "downstream_relationships": downstream,
            "dependency_provenance": _dependency_provenance(observation, source_ids),
            "consumer_scope": _consumer_scope(sources, selections),
            "authority": "repository-intelligence-only",
            "producer_authority": "caller-claimed",
            "execution_authority": "external",
            "result_authority": "external",
            "certification_authority": "external",
        }


def _consumer_source_scope(sources: Sequence[_SourceImports]) -> dict[str, object]:
    return {
        "paths": [row.path for row in sources],
        "members": [row.member for row in sources],
        "observations": [row.observation for row in sources],
        "unavailable": [
            row.path for row in sources if row.observation["availability"] != "observed"
        ],
        "completeness": "complete"
        if all(row.observation["completeness"] == "complete" for row in sources)
        else "incomplete",
    }


def _consumer_scope(
    sources: Sequence[_SourceImports], selections: _Selections
) -> dict[str, object]:
    reasons = [
        "explicit-source-scope",
        "dynamic-imports-and-custom-loaders-not-observed",
        "metadata-owner-scope-not-exhaustive",
        "downstream-relations-bounded-and-advisory",
        "supported-static-import-profiles-only",
    ]
    if any(row.ecosystem == "npm" for row in sources):
        reasons.extend(
            [
                "positive-package-namespace-correspondence-only",
                "node-subpath-exports-and-runtime-resolution-not-observed",
                "node-builtins-and-nonpackage-specifiers-not-matched",
                "typescript-path-mappings-not-resolved",
                "workspace-context-and-installation-visibility-not-resolved",
            ]
        )
    if selections.capability()["unsupported_node_ids"]:
        reasons.append("unsupported-selected-ecosystem")
    return {
        "completeness": "incomplete",
        "negative_evidence": "not-admissible",
        "reasons": reasons,
    }
