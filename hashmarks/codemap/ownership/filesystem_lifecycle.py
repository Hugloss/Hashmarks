"""Revision-qualified composition of filesystem facts with canonical CodeMap."""

from __future__ import annotations

import ast
import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from hashmarks._version import __version__
from hashmarks.paths import normalize_relative_path
from hashmarks.producer_identity import native_producer_implementation_identity
from hashmarks.python_ast_cache import PythonAstSnapshot, read_python_ast

from ..filesystem_lifecycle import FilesystemSourceAnalyzer, FunctionSource, dotted
from ..filesystem_lifecycle_contract import (
    DEFAULT_BOUNDS,
    RULES,
    SCHEMA,
    LifecycleBounds,
    LifecyclePacket,
    lifecycle_identity,
    validate_lifecycle_observation,
)

if TYPE_CHECKING:
    from ..engine import CodeMap


@dataclass
class _Module:
    snapshot: PythonAstSnapshot
    revision: str
    functions: dict[str, FunctionSource]


class _Functions(ast.NodeVisitor):
    def __init__(self, path: str, revision: str) -> None:
        self.path = path
        self.revision = revision
        self.stack: list[str] = []
        self.functions: dict[str, FunctionSource] = {}

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.stack.append(node.name)
        name = ".".join(self.stack)
        self.functions[name] = FunctionSource(self.path, name, self.revision, node)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()


def _unique(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        row
        for _, row in sorted(
            {json.dumps(row, sort_keys=True): row for row in rows}.items()
        )
    ]


class FilesystemLifecycleAnalyzer:
    def __init__(
        self, codemap: CodeMap, bounds: LifecycleBounds = DEFAULT_BOUNDS
    ) -> None:
        self.codemap = codemap
        self.bounds = bounds
        self.modules: dict[str, _Module | None] = {}
        self.failures: list[dict[str, object]] = []
        self.api_cache: dict[tuple[str, str], str | None] = {}
        self.edges: dict[tuple[str, str], list[dict[str, object]]] = {}
        self.resolutions: dict[tuple[str, str, int, int], FunctionSource | None] = {}
        self.allowed_symbols: set[tuple[str, str]] | None = None

    def _failure(self, path: str, reason: str) -> None:
        row: dict[str, object] = {"path": path, "reason": reason}
        if row not in self.failures:
            self.failures.append(row)

    def _module(self, path: str) -> _Module | None:
        if path in self.modules:
            return self.modules[path]
        self.modules[path] = None
        member, raw = self.codemap._repository_member_observation(
            path, include_bytes=True
        )
        if member["state"] != "known-present" or raw is None:
            self._failure(path, str(member.get("reason") or member["state"]))
            return None
        try:
            snapshot = read_python_ast(self.codemap.workspace / path)
            source = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        except (OSError, UnicodeError, SyntaxError, ValueError) as exc:
            self._failure(path, f"source-unavailable:{type(exc).__name__}")
            return None
        if snapshot.source != source:
            self._failure(path, "ast-member-revision-mismatch")
            return None
        revision = str(member["member_revision"])
        visitor = _Functions(path, revision)
        visitor.visit(snapshot.tree)
        self._module_body(visitor, snapshot.tree)
        result = _Module(snapshot, revision, visitor.functions)
        self.modules[path] = result
        return result

    @staticmethod
    def _module_body(visitor: _Functions, tree: ast.Module) -> None:
        body = [
            node
            for node in tree.body
            if not isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            )
        ]
        if not body:
            return
        node = ast.FunctionDef(
            name="<module>",
            args=ast.arguments(
                posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]
            ),
            body=body,
            decorator_list=[],
            lineno=1,
        )
        visitor.functions["<module>"] = FunctionSource(
            visitor.path, "<module>", visitor.revision, node
        )

    def api(self, path: str, name: str) -> str | None:
        key = (path, name)
        if key not in self.api_cache:
            self.api_cache[key] = self._api(path, name, set())
        return self.api_cache[key]

    def _external_api(self, path: str, target: str) -> str | None:
        root = target.split(".")[0]
        if root not in {"os", "pathlib"}:
            return None
        if self.codemap._resolve_import_paths(
            path, root
        ) or self.codemap._python_import_identity_ambiguous(path, root):
            return None
        return target

    def _api(self, path: str, name: str, seen: set[tuple[str, str]]) -> str | None:
        key = (path, name)
        if key in seen or len(seen) >= 8:
            self._failure(path, "import-identity-cyclic-or-bounded")
            return None
        seen = {*seen, key}
        if name.startswith("@"):
            return self._external_api(path, name[1:])
        module = self._module(path)
        if module is None:
            return None
        root, _, suffix = name.partition(".")
        mutated = self._mutated_api(module.snapshot.tree, root)
        if mutated:
            self._failure(path, "source-visible-api-rebinding")
        kind, targets = self.codemap._python_export_binding(path, root)
        if kind not in {"module", "reexport"}:
            return None
        if len(targets) != 1 or mutated:
            return None
        target = targets[0] + ("." + suffix if suffix else "")
        return self._external_api(path, target) or self._reexport_api(
            path, target, seen
        )

    @staticmethod
    def _mutated_api(tree: ast.Module, root: str) -> bool:
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(
                node.ctx, (ast.Store, ast.Del)
            ):
                if dotted(node).split(".")[0] == root:
                    return True
            if isinstance(node, ast.Call) and dotted(node.func) in {
                "setattr",
                "delattr",
            }:
                if node.args and dotted(node.args[0]) == root:
                    return True
        return False

    def _reexport_api(
        self, path: str, target: str, seen: set[tuple[str, str]]
    ) -> str | None:
        owners = self.codemap._resolve_import_paths(path, target)
        if (
            self.codemap._python_import_identity_ambiguous(path, target)
            or len(owners) != 1
        ):
            return None
        owner = owners[0]
        if self.codemap.policy.decide(owner).evidence_visibility.value != "source":
            return None
        row = self.codemap._session_file_row(owner)
        module_name = str(row.get("module_name") or "") if row else ""
        absolute = target
        if target.startswith("."):
            absolute = self.codemap._python_relative_module_candidate(path, target)
        suffix = absolute.removeprefix(module_name + ".")
        if suffix == absolute:
            return None
        return self._api(owner, suffix, seen)

    def resolve(self, source: FunctionSource, call: ast.Call) -> FunctionSource | None:
        key = (source.path, source.qualname, call.lineno, call.col_offset)
        if key not in self.resolutions:
            self.resolutions[key] = self._resolve(source, call)
        return self.resolutions[key]

    def _resolve(self, source: FunctionSource, call: ast.Call) -> FunctionSource | None:
        key = (source.path, source.qualname)
        if key not in self.edges:
            self.edges[key] = [
                dict(row)
                for row in self.codemap.store.edges_from(*key)
                if row["kind"] == "call"
            ]
        matching = [
            row
            for row in self.edges[key]
            if row.get("line") == call.lineno and row.get("target") == dotted(call.func)
        ]
        if len(matching) != 1:
            return None
        resolved, _, _, complete = self.codemap._resolve_call_target(matching[0])
        if resolved is None or not complete:
            return None
        target_key = (str(resolved["path"]), str(resolved["qualname"]))
        if (
            self.codemap.policy.decide(target_key[0]).evidence_visibility.value
            != "source"
        ):
            return None
        if self.allowed_symbols is not None and target_key not in self.allowed_symbols:
            return None
        module = self._module(str(resolved["path"]))
        if module is None:
            return None
        return module.functions.get(str(resolved["qualname"]))

    def _current(self, path: str, module: _Module) -> bool:
        # Metadata only detects drift of the already content-bound snapshot;
        # it never supplies source identity or freshness authority itself.
        if isinstance(self.codemap._repository_member_source(path), dict):
            return False
        try:
            info = (self.codemap.workspace / path).stat()
        except OSError:
            return False
        identity = (
            info.st_dev,
            info.st_ino,
            info.st_size,
            info.st_mtime_ns,
            info.st_ctime_ns,
        )
        return identity == module.snapshot.identity

    def analyze(
        self,
        paths: Sequence[str] | None = None,
        symbols: set[tuple[str, str]] | None = None,
    ) -> LifecyclePacket:
        self.allowed_symbols = symbols
        if paths is None:
            paths = [
                str(row["path"])
                for row in self.codemap.store.all_file_rows()
                if row["language"] == "python"
                and self.codemap.policy.decide(
                    str(row["path"])
                ).evidence_visibility.value
                != "deny"
            ]
        scope = sorted(
            {normalize_relative_path(path, allow_root=False) for path in paths}
        )
        candidates = scope[: self.bounds.candidate_paths]
        analyzer = FilesystemSourceAnalyzer(self.resolve, self.api, self.bounds)
        for path in candidates:
            self._analyze_path(path, symbols, analyzer)
        return self._packet(scope, candidates, analyzer)

    def _analyze_path(
        self,
        path: str,
        symbols: set[tuple[str, str]] | None,
        analyzer: FilesystemSourceAnalyzer,
    ) -> None:
        if not path.endswith((".py", ".pyi")):
            self._failure(path, "unsupported-language")
            return
        module = self._module(path)
        if module is None:
            return
        for name, function in sorted(module.functions.items()):
            if symbols is None or (path, name) in symbols:
                analyzer.analyze(function)

    def _packet(
        self,
        scope: list[str],
        candidates: list[str],
        analyzer: FilesystemSourceAnalyzer,
    ) -> LifecyclePacket:
        observations = _unique(analyzer.observations)
        self._inspection_evidence(observations, analyzer.operations)
        retained = observations[: self.bounds.observations]
        drifted = [
            path
            for path, module in self.modules.items()
            if module is not None and not self._current(path, module)
        ]
        for path in drifted:
            self._failure(path, "source-changed-during-observation")
        generation, _, stale = self.codemap._generation_status()
        unresolved = _unique([*analyzer.unresolved, *self.failures])
        truncated = len(candidates) < len(scope) or len(retained) < len(observations)
        truncated = truncated or any(
            "limit" in str(row.get("reason")) or "bounded" in str(row.get("reason"))
            for row in unresolved
        )
        packet = self._base_packet(scope, generation, True if drifted else stale)
        packet.update(
            {
                "coverage": {
                    "completeness": "incomplete"
                    if unresolved or truncated
                    else "complete-within-supported-scope",
                    "truncated": truncated,
                    "negative_evidence_admissible": False,
                    "runtime_protection": "unverified",
                },
                "operations": _unique(analyzer.operations),
                "observations": retained,
                "unresolved": unresolved,
                "accounting": {
                    "requested_paths": len(scope),
                    "considered_paths": len(candidates),
                    "bounded_paths": len(scope) - len(candidates),
                    "analyzed_paths": sum(
                        module is not None for module in self.modules.values()
                    ),
                    "failed_paths": sum(
                        module is None for module in self.modules.values()
                    ),
                    "observed": len(observations),
                    "returned": len(retained),
                    "omitted": len(observations) - len(retained),
                },
            }
        )
        packet["observation_identity"] = lifecycle_identity(packet)
        return validate_lifecycle_observation(packet)

    def _inspection_evidence(
        self, observations: list[dict[str, object]], operations: list[dict[str, object]]
    ) -> None:
        verifiers: dict[str, object] = {}
        for observation in observations:
            use = observation["use"]
            assert isinstance(use, dict)
            path = str(use["path"])
            if path not in verifiers:
                verifiers[path] = self.codemap.tests(path, max_depth=3).get("tests", [])
            observation["verification"] = {
                "paths": verifiers[path],
                "authority": "structural-relevance-only",
                "completeness": "not-claimed",
            }
            observation["mutation_evidence"] = _unique(
                [
                    row
                    for row in operations
                    if row["kind"] == "mutation"
                    and row.get("reference") == use.get("reference")
                ]
            )

    def _base_packet(
        self, scope: list[str], generation: int, stale: bool | None
    ) -> LifecyclePacket:
        return {
            "schema": SCHEMA,
            "repository_identity": "sha256:"
            + self.codemap._workspace_fingerprint_from_store(),
            "generation": generation,
            "stale": stale,
            "producer": {
                "version": __version__,
                "rules": RULES,
                "implementation_identity": native_producer_implementation_identity(),
            },
            "scope": scope,
            "bounds": self.bounds.as_dict(),
            "source_revisions": {
                path: module.revision
                for path, module in sorted(self.modules.items())
                if module
            },
            "coverage": {},
            "operations": [],
            "observations": [],
            "unresolved": [],
            "accounting": {},
            "authority": "repository-evidence-only",
            "execution_effect": "none",
            "observation_identity": "",
        }


def locality_lifecycle(
    codemap: CodeMap,
    nodes: list[dict[str, object]],
    max_depth: int,
    call_limit: int,
    reference_limit: int,
) -> LifecyclePacket:
    """Compose lifecycle evidence within an already selected locality graph."""
    symbols = {(str(row["path"]), str(row["qualname"])) for row in nodes}
    bounds = replace(
        DEFAULT_BOUNDS,
        max_depth=max_depth,
        calls_per_symbol=call_limit,
        references_per_symbol=reference_limit,
    )
    return FilesystemLifecycleAnalyzer(codemap, bounds).analyze(
        sorted({path for path, _ in symbols}), symbols
    )


def lifecycle_findings(packet: LifecyclePacket) -> list[dict[str, object]]:
    findings = []
    for observation in packet["observations"]:
        use = observation["use"]
        assert isinstance(use, dict)
        lines = use["lines"]
        assert isinstance(lines, list)
        findings.append(
            {
                "category": "resource-lifecycle",
                "code": "python-filesystem-check-use",
                "severity": "advisory",
                "confidence": "source-reference-only",
                "path": use["path"],
                "line": lines[0],
                "reason": observation["observed"],
                "source_schema": SCHEMA,
                "evidence": observation,
                "observation_identity": packet["observation_identity"],
                "observation": "retained",
                "interpretation": {"authority": "repository-evidence-only"},
            }
        )
    return findings
