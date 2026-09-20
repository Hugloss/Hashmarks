from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, cast

from hashmarks._version import __version__
from hashmarks.paths import normalize_relative_path
from hashmarks.producer_identity import native_producer_implementation_identity
from hashmarks.python_ast_cache import read_python_ast

from .model import EvidenceVisibility

if TYPE_CHECKING:
    from .engine import CodeMap

STRUCTURAL_LOCALITY_SCHEMA = "hashmarks.structural-locality.v1"
STRUCTURAL_LOCALITY_DELTA_SCHEMA = "hashmarks.structural-locality-delta.v1"


def _identity(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _symbol_id(row: Mapping[str, object]) -> str:
    return f"{row['path']}::{row['qualname']}"


def _union_line_count(rows: Sequence[Mapping[str, object]]) -> int:
    by_path: dict[str, list[tuple[int, int]]] = {}
    for row in rows:
        lines = row.get("lines")
        if (
            not isinstance(lines, Sequence)
            or isinstance(lines, (str, bytes, bytearray))
            or len(lines) != 2
        ):
            continue
        by_path.setdefault(str(row["path"]), []).append(
            (int(lines[0]), int(lines[1]))
        )
    total = 0
    for spans in by_path.values():
        current_start: int | None = None
        current_end: int | None = None
        for start, end in sorted(spans):
            if current_start is None:
                current_start, current_end = start, end
                continue
            assert current_end is not None
            if start <= current_end + 1:
                current_end = max(current_end, end)
                continue
            total += current_end - current_start + 1
            current_start, current_end = start, end
        if current_start is not None and current_end is not None:
            total += current_end - current_start + 1
    return total


def _body_without_docstring(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    body = list(node.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    return body


def _is_call_value(node: ast.AST | None) -> bool:
    if isinstance(node, ast.Call):
        return True
    return isinstance(node, ast.Await) and isinstance(node.value, ast.Call)


def _forwarding_only_python_symbol(
    path: Path, *, start_line: int, name: str
) -> tuple[bool | None, str]:
    try:
        tree = read_python_ast(path, errors="replace").tree
    except (OSError, SyntaxError, ValueError):
        return None, "python-ast-unavailable"
    candidates = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and int(getattr(node, "lineno", -1)) == start_line
        and node.name == name
    ]
    if len(candidates) != 1:
        return None, "python-symbol-node-ambiguous"
    body = _body_without_docstring(candidates[0])
    if len(body) != 1:
        return False, "python-ast"
    statement = body[0]
    if isinstance(statement, ast.Return):
        return _is_call_value(statement.value), "python-ast"
    if isinstance(statement, ast.Expr):
        return _is_call_value(statement.value), "python-ast"
    return False, "python-ast"


def _freshness(stale: object) -> str:
    if stale is False:
        return "current"
    if stale is True:
        return "stale"
    return "unknown"


class StructuralLocalityMixin:
    """Project bounded structural-locality facts without refactor recommendations."""

    @staticmethod
    def _validate_locality_bounds(
        max_depth: int, call_limit_per_symbol: int, ref_limit_per_symbol: int
    ) -> None:
        if max_depth < 0 or max_depth > 8:
            raise ValueError("max_depth must be between 0 and 8")
        if call_limit_per_symbol < 1 or call_limit_per_symbol > 1024:
            raise ValueError("call_limit_per_symbol must be between 1 and 1024")
        if ref_limit_per_symbol < 1 or ref_limit_per_symbol > 1024:
            raise ValueError("ref_limit_per_symbol must be between 1 and 1024")

    def _exact_locality_target(self, target: str) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if "::" not in target:
            raise ValueError(
                "structural locality requires an exact path::qualname target"
            )
        raw_path, qualname = target.split("::", 1)
        path = normalize_relative_path(raw_path.strip().replace("\\", "/"), allow_root=False)
        qualname = qualname.strip()
        if not qualname:
            raise ValueError("target path and qualname must be non-empty")
        self._ensure_path_current(path)
        row = self.store.symbol_at(path, qualname)
        if row is None:
            raise KeyError(f"symbol not found: {target}")
        if EvidenceVisibility(str(row["evidence_visibility"])) is EvidenceVisibility.DENY:
            raise PermissionError(f"symbol exists but repository evidence is denied: {target}")
        return dict(row)

    def _visible_named_symbol_candidates(self, name: str) -> list[dict[str, object]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        return [
            dict(row)
            for row in self.store.symbols_named(name, limit=64)
            if EvidenceVisibility(str(row["evidence_visibility"]))
            is not EvidenceVisibility.DENY
        ]

    def _python_function_locally_binds(
        self, path: str, source: str, name: str
    ) -> bool:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if not path.endswith(".py") or not source or not name:
            return False
        try:
            tree = read_python_ast(self.workspace / path, errors="replace").tree
        except (OSError, SyntaxError, UnicodeError, ValueError):
            return True
        function_name = source.rsplit(".", 1)[-1]
        matching = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function_name
        ]
        if len(matching) != 1:
            return True
        function = matching[0]
        arguments = [
            *function.args.posonlyargs,
            *function.args.args,
            *function.args.kwonlyargs,
        ]
        if function.args.vararg is not None:
            arguments.append(function.args.vararg)
        if function.args.kwarg is not None:
            arguments.append(function.args.kwarg)
        if any(argument.arg == name for argument in arguments):
            return True
        for node in ast.walk(function):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                if node.id == name:
                    return True
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    if (alias.asname or alias.name.rsplit(".", 1)[-1]) == name:
                        return True
        return False

    def _python_plain_call_binding(
        self,
        *,
        source_path: str,
        source_qualname: str,
        short: str,
        candidates: list[dict[str, object]],
    ) -> tuple[dict[str, object] | None, list[str]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        if self._python_function_locally_binds(source_path, source_qualname, short):
            return None, sorted(_symbol_id(row) for row in candidates)
        kind, targets = self._python_export_binding(source_path, short)
        if kind == "local":
            local = [row for row in candidates if str(row.get("path") or "") == source_path]
            if len(local) == 1:
                return local[0], [_symbol_id(local[0])]
            return None, sorted(_symbol_id(row) for row in local or candidates)
        if kind == "reexport" and len(targets) == 1:
            owners, unresolved = self._resolve_import_owner_evidence(
                source_path, targets[0]
            )
            if unresolved:
                return None, sorted(_symbol_id(row) for row in candidates)
            owned = [
                row
                for row in candidates
                if str(row.get("path") or "") in set(owners)
            ]
            if len(owned) == 1:
                return owned[0], [_symbol_id(owned[0])]
            return None, sorted(_symbol_id(row) for row in owned or candidates)
        return None, sorted(_symbol_id(row) for row in candidates)

    def _python_qualified_call_binding(
        self,
        *,
        source_path: str,
        source_qualname: str,
        target: str,
        candidates: list[dict[str, object]],
    ) -> tuple[dict[str, object] | None, list[str]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        root = target.split(".", 1)[0]
        if not root or self._python_function_locally_binds(
            source_path, source_qualname, root
        ):
            return None, sorted(_symbol_id(row) for row in candidates)
        kind, targets = self._python_export_binding(source_path, root)
        if kind == "local":
            qualified = [
                row
                for row in candidates
                if str(row.get("path") or "") == source_path
                and str(row.get("qualname") or "") == target
            ]
        elif kind == "reexport" and len(targets) == 1:
            owners, unresolved = self._resolve_import_owner_evidence(
                source_path, targets[0]
            )
            if unresolved:
                return None, sorted(_symbol_id(row) for row in candidates)
            owner_paths = set(owners)
            qualified = [
                row
                for row in candidates
                if str(row.get("path") or "") in owner_paths
                and str(row.get("qualname") or "") == target
            ]
        else:
            qualified = []
        if len(qualified) == 1:
            return qualified[0], [_symbol_id(qualified[0])]
        return None, sorted(_symbol_id(row) for row in qualified or candidates)

    def _resolve_call_target(
        self, edge: Mapping[str, object]
    ) -> tuple[dict[str, object] | None, list[str]]:
        target = str(edge.get("target") or "").strip()
        short = target.rsplit(".", 1)[-1]
        if not short:
            return None, []
        candidates = self._visible_named_symbol_candidates(short)
        source_path = str(edge.get("path") or "")
        source_qualname = str(edge.get("source") or "")
        source_row = self.store.file_row(source_path)
        language = "" if source_row is None else str(source_row["language"] or "")
        if language == "python" and target != short:
            return self._python_qualified_call_binding(
                source_path=source_path,
                source_qualname=source_qualname,
                target=target,
                candidates=candidates,
            )
        if language == "python":
            return self._python_plain_call_binding(
                source_path=source_path,
                source_qualname=source_qualname,
                short=short,
                candidates=candidates,
            )
        return None, sorted(_symbol_id(row) for row in candidates)

    def _locality_callers(
        self, row: Mapping[str, object], *, ref_limit: int
    ) -> tuple[list[dict[str, object]], bool, list[dict[str, object]]]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        name = str(row["name"])
        target_id = _symbol_id(row)
        raw_refs = [dict(ref) for ref in self.store.refs(name, limit=ref_limit)]
        reference_bound_complete = len(raw_refs) < ref_limit
        raw = [
            ref for ref in raw_refs if str(ref.get("kind") or "") == "call"
        ]
        callers: dict[tuple[str, str], dict[str, object]] = {}
        unresolved: list[dict[str, object]] = []
        for ref in raw:
            resolved, candidates = self._resolve_call_target(ref)
            if resolved is None or _symbol_id(resolved) != target_id:
                if target_id in candidates or not candidates:
                    unresolved.append(
                        {
                            "path": str(ref.get("path") or ""),
                            "source": ref.get("source"),
                            "line": ref.get("line"),
                            "target": ref.get("target"),
                            "candidate_symbol_ids": candidates,
                        }
                    )
                continue
            key = (str(ref.get("path") or ""), str(ref.get("source") or "<module>"))
            callers[key] = {
                "path": key[0],
                "source": None if key[1] == "<module>" else key[1],
                "line": ref.get("line"),
                "confidence": ref.get("confidence"),
            }
        return (
            [callers[key] for key in sorted(callers)],
            reference_bound_complete,
            sorted(
                unresolved,
                key=lambda item: (
                    str(item["path"]),
                    int(item["line"] or 0),
                    str(item["source"] or ""),
                ),
            ),
        )

    def _locality_node(
        self,
        row: Mapping[str, object],
        *,
        navigation_depth: int,
        ref_limit: int,
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        path = str(row["path"])
        file_row = self.store.file_row(path)
        digest = "" if file_row is None else str(file_row["file_digest"])
        forwarding: bool | None = None
        forwarding_provider = "unsupported-language"
        language = "" if file_row is None else str(file_row["language"])
        if language == "python":
            forwarding, forwarding_provider = _forwarding_only_python_symbol(
                self.workspace / path,
                start_line=int(row["start_line"]),
                name=str(row["name"]),
            )
        callers, caller_reference_bound_complete, unresolved_callers = self._locality_callers(
            row, ref_limit=ref_limit
        )
        source_semantic = {
            "path": path,
            "qualname": str(row["qualname"]),
            "file_digest": digest,
            "lines": [int(row["start_line"]), int(row["end_line"])],
        }
        semantic = {
            "path": path,
            "qualname": str(row["qualname"]),
            "name": str(row["name"]),
            "kind": str(row["kind"]),
            "signature": str(row["signature"]),
            "lines": [int(row["start_line"]), int(row["end_line"])],
            "navigation_depth": navigation_depth,
            "file_digest": digest,
            "forwarding_only": forwarding,
            "forwarding_provider": forwarding_provider,
            "exact_callers": callers,
            "exact_caller_count": len(callers),
            "caller_reference_bound_complete": caller_reference_bound_complete,
            "unresolved_caller_candidates": unresolved_callers,
        }
        return {
            "symbol_id": _symbol_id(row),
            **semantic,
            "symbol_source_identity": _identity(source_semantic),
            "symbol_evidence_identity": _identity(semantic),
        }

    def structural_locality(
        self,
        target: str,
        *,
        max_depth: int = 2,
        call_limit_per_symbol: int = 64,
        ref_limit_per_symbol: int = 256,
        refresh: bool = True,
    ) -> dict[str, object]:
        """Return bounded structural facts reachable from one exact symbol.

        The projection deliberately does not label a refactor good/bad, propose an
        edit, or infer semantic responsibility. Ambiguous static call targets stay
        unresolved instead of being counted as reuse or ownership.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._validate_locality_bounds(
            max_depth, call_limit_per_symbol, ref_limit_per_symbol
        )
        if refresh:
            self.sync()
        else:
            self._ensure_map_ready()
        target_row = self._exact_locality_target(target)

        queue: list[tuple[dict[str, object], int]] = [(target_row, 0)]
        nodes: dict[str, dict[str, object]] = {}
        edges: list[dict[str, object]] = []
        unresolved_calls: list[dict[str, object]] = []
        external_or_unindexed_calls: list[dict[str, object]] = []
        while queue:
            row, depth = queue.pop(0)
            symbol_id = _symbol_id(row)
            if symbol_id in nodes:
                continue
            node = self._locality_node(
                row, navigation_depth=depth, ref_limit=ref_limit_per_symbol
            )
            nodes[symbol_id] = node
            if depth >= max_depth:
                continue
            outgoing = [
                dict(edge)
                for edge in self.store.edges_from(
                    str(row["path"]), str(row["qualname"])
                )
                if str(edge.get("kind") or "") == "call"
            ]
            truncated = len(outgoing) > call_limit_per_symbol
            for edge in outgoing[:call_limit_per_symbol]:
                resolved, candidates = self._resolve_call_target(edge)
                record = {
                    "source_symbol_id": symbol_id,
                    "path": str(edge.get("path") or ""),
                    "line": edge.get("line"),
                    "target_text": str(edge.get("target") or ""),
                    "confidence": str(edge.get("confidence") or ""),
                    "resolved_symbol_id": None
                    if resolved is None
                    else _symbol_id(resolved),
                    "candidate_symbol_ids": candidates,
                }
                edges.append(record)
                if resolved is None:
                    if candidates:
                        unresolved_calls.append(record)
                    else:
                        external_or_unindexed_calls.append(record)
                    continue
                queue.append((resolved, depth + 1))
            if truncated:
                unresolved_calls.append(
                    {
                        "source_symbol_id": symbol_id,
                        "reason": "call-limit-reached",
                        "limit": call_limit_per_symbol,
                    }
                )

        ordered_nodes = sorted(
            nodes.values(),
            key=lambda item: (
                int(item["navigation_depth"]),
                str(item["path"]),
                int(item["lines"][0]),
                str(item["qualname"]),
            ),
        )
        files = sorted({str(row["path"]) for row in ordered_nodes})
        verification = self.tests(str(target_row["path"]), max_depth=3)
        verification_paths = sorted(
            {str(path) for path in verification.get("tests", [])}
        )
        dimensions = {
            "symbol_count": len(ordered_nodes),
            "file_count": len(files),
            "max_navigation_depth": max(
                (int(row["navigation_depth"]) for row in ordered_nodes), default=0
            ),
            "forwarding_only_symbol_count": sum(
                1 for row in ordered_nodes if row["forwarding_only"] is True
            ),
            "forwarding_unknown_symbol_count": sum(
                1 for row in ordered_nodes if row["forwarding_only"] is None
            ),
            "context_lines": _union_line_count(ordered_nodes),
            "verifier_file_count": len(verification_paths),
            "cross_file_symbol_count": sum(
                1
                for row in ordered_nodes
                if str(row["path"]) != str(target_row["path"])
            ),
            "unresolved_call_count": len(unresolved_calls),
            "external_or_unindexed_call_count": len(external_or_unindexed_calls),
            "target_exact_caller_count": int(
                nodes[_symbol_id(target_row)]["exact_caller_count"]
            ),
        }
        repository_identity = "sha256:" + self._workspace_fingerprint_from_store()
        configuration = {
            "max_depth": max_depth,
            "call_limit_per_symbol": call_limit_per_symbol,
            "ref_limit_per_symbol": ref_limit_per_symbol,
            "verification_max_depth": 3,
            "target_resolution": "exact-path-qualname",
            "call_resolution": "unambiguous-indexed-symbol-only",
            "refresh": refresh,
        }
        freshness_fields = self._query_freshness_fields()
        freshness_state = "current" if refresh else _freshness(freshness_fields.get("stale"))
        semantic = {
            "schema": STRUCTURAL_LOCALITY_SCHEMA,
            "provider": "hashmarks",
            "provider_version": __version__,
            "provider_implementation_identity": native_producer_implementation_identity(),
            "repository_identity": repository_identity,
            "source_identity": nodes[_symbol_id(target_row)]["symbol_source_identity"],
            "measurement_configuration_identity": _identity(configuration),
            "target": target,
            "target_symbol_id": _symbol_id(target_row),
            "freshness": {
                **freshness_fields,
                "state": freshness_state,
                "basis": "explicit-sync" if refresh else "observer-status",
            },
            "bounds": configuration,
            "nodes": ordered_nodes,
            "edges": sorted(
                edges,
                key=lambda item: (
                    str(item["source_symbol_id"]),
                    int(item["line"] or 0),
                    str(item["target_text"]),
                ),
            ),
            "unresolved_calls": sorted(
                unresolved_calls,
                key=lambda item: (
                    str(item.get("source_symbol_id") or ""),
                    int(item.get("line") or 0),
                    str(item.get("target_text") or item.get("reason") or ""),
                ),
            ),
            "external_or_unindexed_calls": sorted(
                external_or_unindexed_calls,
                key=lambda item: (
                    str(item.get("source_symbol_id") or ""),
                    int(item.get("line") or 0),
                    str(item.get("target_text") or ""),
                ),
            ),
            "verification_paths": verification_paths,
            "dimensions": dimensions,
            "claims": {
                "refactor_recommendation": False,
                "semantic_responsibility_inferred": False,
                "ambiguous_calls_promoted_to_exact": False,
                "execution_authority": False,
            },
        }
        return {**semantic, "evidence_identity": _identity(semantic)}


def _packet_identity_valid(packet: Mapping[str, object]) -> bool:
    identity = packet.get("evidence_identity")
    if not isinstance(identity, str) or not identity:
        return False
    semantic = {
        str(key): value for key, value in packet.items() if key != "evidence_identity"
    }
    return identity == _identity(semantic)


def structural_locality_delta(
    before: Mapping[str, object], after: Mapping[str, object]
) -> dict[str, object]:
    """Compare two structural-locality packets without interpreting the tradeoff."""
    issues: list[str] = []
    if before.get("schema") != STRUCTURAL_LOCALITY_SCHEMA:
        issues.append("before-schema")
    if after.get("schema") != STRUCTURAL_LOCALITY_SCHEMA:
        issues.append("after-schema")
    if before.get("provider") != "hashmarks":
        issues.append("before-provider")
    if after.get("provider") != "hashmarks":
        issues.append("after-provider")
    if before.get("provider_version") != after.get("provider_version"):
        issues.append("provider-version")
    if (
        before.get("provider_implementation_identity")
        != after.get("provider_implementation_identity")
    ):
        issues.append("provider-implementation")
    if not _packet_identity_valid(before):
        issues.append("before-evidence-identity")
    if not _packet_identity_valid(after):
        issues.append("after-evidence-identity")
    if before.get("target") != after.get("target"):
        issues.append("target")
    if (
        before.get("measurement_configuration_identity")
        != after.get("measurement_configuration_identity")
    ):
        issues.append("measurement-configuration")
    if before.get("repository_identity") == after.get("repository_identity"):
        issues.append("repository-state-not-distinct")
    for label, packet in (("before", before), ("after", after)):
        freshness = packet.get("freshness")
        if not isinstance(freshness, Mapping) or freshness.get("state") != "current":
            issues.append(f"{label}-freshness")
        if not isinstance(packet.get("evidence_identity"), str):
            issues.append(f"{label}-identity")

    before_nodes = {
        str(row.get("symbol_id")): row
        for row in before.get("nodes", [])
        if isinstance(row, Mapping) and row.get("symbol_id")
    }
    after_nodes = {
        str(row.get("symbol_id")): row
        for row in after.get("nodes", [])
        if isinstance(row, Mapping) and row.get("symbol_id")
    }
    before_dimensions = before.get("dimensions")
    after_dimensions = after.get("dimensions")
    dimension_delta: dict[str, int] = {}
    if not isinstance(before_dimensions, Mapping) or not isinstance(
        after_dimensions, Mapping
    ):
        issues.append("dimensions")
    else:
        for key in sorted(set(before_dimensions) & set(after_dimensions)):
            left = before_dimensions.get(key)
            right = after_dimensions.get(key)
            if (
                isinstance(left, int)
                and not isinstance(left, bool)
                and isinstance(right, int)
                and not isinstance(right, bool)
            ):
                dimension_delta[str(key)] = right - left

    before_verifiers = {
        str(value) for value in before.get("verification_paths", []) if value
    }
    after_verifiers = {
        str(value) for value in after.get("verification_paths", []) if value
    }
    semantic = {
        "schema": STRUCTURAL_LOCALITY_DELTA_SCHEMA,
        "target": before.get("target"),
        "before_evidence_identity": before.get("evidence_identity"),
        "after_evidence_identity": after.get("evidence_identity"),
        "before_repository_identity": before.get("repository_identity"),
        "after_repository_identity": after.get("repository_identity"),
        "measurement_configuration_identity": before.get(
            "measurement_configuration_identity"
        ),
        "comparable": not issues,
        "incomparability_reasons": sorted(set(issues)),
        "introduced_symbol_ids": sorted(set(after_nodes) - set(before_nodes)),
        "removed_symbol_ids": sorted(set(before_nodes) - set(after_nodes)),
        "dimension_delta": dimension_delta,
        "verification_paths_added": sorted(after_verifiers - before_verifiers),
        "verification_paths_removed": sorted(before_verifiers - after_verifiers),
        "claims": {
            "architectural_improvement": False,
            "refactor_recommendation": False,
            "consumer_policy_applied": False,
        },
    }
    return {**semantic, "evidence_identity": _identity(semantic)}
