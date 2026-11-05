"""Source-qualified ECMAScript import uses with native compiler resolution.

The existing binding observer owns lexical uses and shadows. TypeScript owns
configuration and module resolution. Neither establishes runtime execution.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, cast
from weakref import WeakKeyDictionary

from .ecmascript_syntax import SyntaxProjection
from .providers import SourceSyntaxProvider, source_grammar
from .repository_observation import evidence_identity
from .source_binding_contract import MAX_BINDING_RESULTS

if TYPE_CHECKING:
    from .decision_session import ReadScope
    from .evidence_verification import (
        RepositoryVerification,
        _VerificationRelevanceState,
    )
    from .providers import StructuralNode

_SUFFIXES = frozenset({".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"})


def _used_import(row: Mapping[str, object]) -> tuple[str, str] | None:
    if (
        row["kind"] not in {"reference", "call-site"}
        or row["qualification"] != "qualified"
    ):
        return None
    target = row.get("target")
    if not isinstance(target, Mapping) or target.get("kind") != "import":
        return None
    module, name = target.get("module"), target.get("name")
    return (module, name) if isinstance(module, str) and isinstance(name, str) else None


def _named_exports(row: Mapping[str, object]) -> list[tuple[str, tuple[str, str]]]:
    module = row.get("module_specifier")
    if (
        row["kind"] != "module-declaration"
        or row.get("declaration_kind") != "export"
        or not isinstance(module, str)
    ):
        return []
    result = []
    for binding in cast("list[dict[str, object]]", row.get("export_bindings", [])):
        name, alias = binding.get("name"), binding.get("alias")
        if (
            isinstance(name, str)
            and isinstance(alias, str)
            and binding.get("type_only") is False
        ):
            result.append((alias, (module, name)))
    return result


def _static_statement(node: StructuralNode, projection: SyntaxProjection) -> bool:
    if node.type == "import_statement":
        return projection._module_type_only(node)
    selected = (
        node.child_by_field_name("declaration")
        if node.type == "export_statement"
        else node
    )
    return selected is not None and selected.type in {
        "interface_declaration",
        "type_alias_declaration",
    }


def _module_targets(
    import_site: tuple[str, str, str],
    resolved: Mapping[tuple[str, str], set[str]],
    exports: Mapping[tuple[str, str], list[tuple[str, str]]],
    exhausted: set[str],
) -> list[tuple[str, tuple[str, ...]]]:
    source, module, name = import_site
    via: tuple[str, ...] = ()
    visited: set[tuple[str, str, str]] = set()
    result = []
    for _ in range(8):
        key = source, module, name
        if key in visited:
            break
        visited.add(key)
        targets = resolved.get((source, module), set())
        if len(targets) != 1:
            break
        target = next(iter(targets))
        result.append((target, via))
        forwarded = exports.get((target, name), [])
        if len(forwarded) != 1:
            break
        source, (module, name) = target, forwarded[0]
        via = (*via, target)
    else:
        exhausted.add("ecmascript-named-reexport-hop-bound")
    return result


def _direct_consumers(
    resolved: Mapping[tuple[str, str], set[str]],
    exports: Mapping[tuple[str, str], list[tuple[str, str]]],
    uses: Mapping[str, list[tuple[str, str]]],
    exhausted: set[str],
) -> dict[str, list[tuple[str, str, tuple[str, ...]]]]:
    result: dict[str, list[tuple[str, str, tuple[str, ...]]]] = {}
    for source, bindings in uses.items():
        for module, name in bindings:
            for target, via in _module_targets(
                (source, module, name), resolved, exports, exhausted
            ):
                result.setdefault(target, []).append((source, name, via))
    return result


class VerificationEcmascriptMixin:
    _ecmascript_read_scopes: WeakKeyDictionary[ReadScope, dict[str, object]]

    def _verification_attach_ecmascript_static(
        self, path: str, payload: dict[str, object], supporting: list[dict[str, object]]
    ) -> None:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        if (
            Path(path).suffix not in {".ts", ".tsx", ".mts", ".cts"}
            or self.reads.scope is None
        ):
            return
        fact = self._verification_ecmascript_static_project(path)
        if fact is not None:
            payload["static_project"] = fact
            supporting.extend(
                cast("list[dict[str, object]]", fact["configuration_inputs"])
            )

    def _ecmascript_observation(self) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        scope = self.reads.scope
        assert scope is not None
        cache = getattr(self, "_ecmascript_read_scopes", None)
        if cache is None:
            cache = WeakKeyDictionary()
            self._ecmascript_read_scopes = cache
        if scope in cache:
            return cast("dict[str, object]", cache[scope])
        result = self._ecmascript_reference_projection()
        cache[scope] = result
        return result

    def _ecmascript_reference_projection(self) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        resolution = self.native._collect_typescript_resolution()
        resolved: dict[tuple[str, str], set[str]] = {}
        for edge in resolution.edges:
            if edge.specifier is not None:
                resolved.setdefault((edge.source, edge.specifier), set()).add(
                    edge.target
                )
        members: dict[str, dict[str, object]] = {}
        for path, _raw in resolution.inputs:
            member, _ = self.source.member(path)
            members[path] = member
        uses: dict[str, list[tuple[str, str]]] = {}
        exports: dict[tuple[str, str], list[tuple[str, str]]] = {}
        pure_types: dict[str, dict[str, object] | None] = {}
        binding_observations: dict[str, dict[str, object]] = {}
        for path in resolution.files:
            if Path(path).suffix not in _SUFFIXES:
                continue
            packet = self.source.bindings(path, limit=MAX_BINDING_RESULTS)
            if (packet["availability"], packet["completeness"]) != (
                "observed",
                "complete",
            ):
                continue
            member = cast("dict[str, object]", packet["member"])
            members[path] = member
            binding_observations[path] = {
                key: packet[key]
                for key in (
                    "observation_identity",
                    "parser",
                    "producer",
                    "freshness",
                    "completeness",
                    "truncation",
                    "member",
                )
            }
            self._ecmascript_member_references(path, packet, uses, exports)
            pure_types[path] = self._ecmascript_type_only(path, packet)
        exhausted: set[str] = set()
        consumers = _direct_consumers(resolved, exports, uses, exhausted)
        result: dict[str, object] = {
            "resolved": resolved,
            "uses": uses,
            "exports": exports,
            "members": members,
            "type_only": pure_types,
            "compiler": resolution.producer,
            "compilers": list(resolution.compilers),
            "warnings": list(resolution.warnings),
            "projects": list(resolution.projects),
            "binding_observations": binding_observations,
            "consumers": consumers,
            "search_bound_reasons": sorted(exhausted),
            "configuration_inputs": [members[path] for path, _raw in resolution.inputs],
        }
        return result

    @staticmethod
    def _ecmascript_member_references(
        path: str,
        packet: dict[str, object],
        uses: dict[str, list[tuple[str, str]]],
        exports: dict[tuple[str, str], list[tuple[str, str]]],
    ) -> None:
        for row in cast("list[dict[str, object]]", packet["facts"]):
            use = _used_import(row)
            if use is not None:
                uses.setdefault(path, []).append(use)
            for alias, forward in _named_exports(row):
                exports.setdefault((path, alias), []).append(forward)
        uses[path] = list(dict.fromkeys(uses.get(path, [])))

    def _ecmascript_type_only(
        self, path: str, packet: dict[str, object]
    ) -> dict[str, object] | None:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        provider = self.source.index.range_provider
        grammar = source_grammar(path)
        if not isinstance(provider, SourceSyntaxProvider) or grammar not in {
            "typescript",
            "tsx",
        }:
            return None
        member, raw = self.source._bounded_source_observation(path, 1_048_576)
        if raw is None or member != packet["member"]:
            return None
        tree = provider.syntax_tree(raw, grammar)
        if tree is None:
            return None
        projection = SyntaxProjection(raw)
        nodes = [
            node
            for node in tree.root_node.named_children
            if node.type not in {"comment", "empty_statement"}
        ]
        if not nodes or not all(_static_statement(node, projection) for node in nodes):
            return None
        return {
            "kind": "type-only-static-project",
            "parser": packet["parser"],
            "source_member": member,
            "syntax_completeness": "complete",
            "value_syntax": "none-observed-within-complete-member",
            "runtime_execution": "not-established",
            "negative_evidence_admissible": False,
        }

    def _verification_ecmascript_static_project(
        self, path: str
    ) -> dict[str, object] | None:
        observation = self._ecmascript_observation()
        if not observation["compilers"] or observation["warnings"]:
            return None
        fact = cast(
            "dict[str, dict[str, object] | None]", observation["type_only"]
        ).get(path)
        if fact is None:
            return None
        projects = [
            {key: value for key, value in project.items() if key != "files"}
            for project in cast("list[dict[str, object]]", observation["projects"])
            if path in cast("list[str]", project["files"])
        ]
        if not projects:
            return None
        packet = {
            **fact,
            "qualification": "qualified",
            "compiler": observation["compiler"],
            "projects": projects,
            "compilers": observation["compilers"],
            "configuration_inputs": observation["configuration_inputs"],
        }
        return {
            **packet,
            "evidence_identity": evidence_identity(
                "hashmarks.typescript-static-source.v1", packet
            ),
        }

    def _verification_collect_ecmascript_references(
        self, state: _VerificationRelevanceState
    ) -> None:
        if Path(state.edit_path).suffix not in _SUFFIXES:
            return
        state.search_bound_reasons.add("ecmascript-source-reference-scope")
        observation = self._ecmascript_observation()
        state.search_bound_reasons.update(
            cast("list[str]", observation["search_bound_reasons"])
        )
        if not observation["compilers"]:
            state.search_bound_reasons.add("native-typescript-resolution-unavailable")
            return
        for path, name, via in self._ecmascript_verifier_consumers(state, observation):
            self._ecmascript_reference_candidate(state, path, name, via, observation)

    def _ecmascript_verifier_consumers(
        self, state: _VerificationRelevanceState, observation: dict[str, object]
    ) -> Iterator[tuple[str, str, tuple[str, ...]]]:
        if TYPE_CHECKING:
            self = cast("RepositoryVerification", self)
        consumers = cast(
            "dict[str, list[tuple[str, str, tuple[str, ...]]]]",
            observation["consumers"],
        )
        pending: deque[tuple[str, tuple[str, ...]]] = deque([(state.edit_path, ())])
        visited: set[str] = set()
        for _ in range(256):
            if not pending:
                return
            target, downstream = pending.popleft()
            if target in visited:
                continue
            visited.add(target)
            for path, name, forwarding in consumers.get(target, []):
                via = (*forwarding, *downstream)
                if len(via) >= 8:
                    state.search_bound_reasons.add(
                        "ecmascript-source-reference-hop-bound"
                    )
                    continue
                if (
                    self._verification_path_kind(path, reconcile=False)["kind"]
                    == "verifier"
                ):
                    yield path, name, via
                else:
                    pending.append((path, (path, *via)))
        state.search_bound_reasons.add("ecmascript-source-reference-visit-bound")

    @staticmethod
    def _ecmascript_reference_candidate(
        state: _VerificationRelevanceState,
        path: str,
        name: str,
        via: tuple[str, ...],
        observation: dict[str, object],
    ) -> None:
        state.candidate_paths.add(path)
        state.refs_by_path.setdefault(path, set()).add(name)
        if via:
            state.indirect_refs_by_path.setdefault(path, set()).add(name)
            state.indirect_via_paths.setdefault(path, set()).update(via)
        state.ecmascript_reference_evidence[path] = {
            "syntactic_reference": True,
            "reference_strength": "qualified-indirect-source-reference"
            if via
            else "qualified-source-reference",
            "source_reference_evidence": {
                "scope": "source-qualified-used-value-import",
                "compiler": observation["compiler"],
                "compilers": observation["compilers"],
                "runtime_execution": "not-established",
                "via": list(via),
                "bounds": {"source_hops": 8, "source_reference_visits": 256},
                "binding_observations": {
                    name: cast(
                        "dict[str, dict[str, object]]",
                        observation["binding_observations"],
                    )[name]
                    for name in (path, *via, state.edit_path)
                    if name
                    in cast(
                        "dict[str, dict[str, object]]",
                        observation["binding_observations"],
                    )
                },
            },
        }
        state.import_owner_contributors.setdefault(path, set()).update(
            (
                state.edit_path,
                *via,
                *(
                    str(member["path"])
                    for member in cast(
                        "list[dict[str, object]]", observation["configuration_inputs"]
                    )
                ),
            )
        )
