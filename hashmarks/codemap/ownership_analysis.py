from __future__ import annotations

import ast
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, cast

from hashmarks.operation_contract import operation_response, operation_schema
from hashmarks.paths import normalize_relative_path
from hashmarks.python_ast_cache import read_python_ast

from .decision_session import decision_scoped
from .ownership.cache_invalidation import CacheInvalidationAnalyzer
from .ownership.cache_ownership import CacheOwnershipAnalyzer
from .ownership.concurrency_risk import ConcurrencyRiskAnalyzer
from .ownership.import_ownership import ImportOwnershipAnalyzer

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .engine import CodeMap


class OwnershipAnalysisMixin:
    def _ownership_analysis_inputs(
        self, paths: Sequence[str] | None
    ) -> tuple[tuple[str, ...] | None, list[dict[str, object]]]:
        """Make requested paths current, then snapshot repository rows once.

        The returned rows are request-local composition input, not persistent cache
        state. Making explicit paths current before materializing rows preserves the
        lazy-refresh contract while allowing composed analyses to reuse one snapshot.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        normalized: tuple[str, ...] | None = None
        if paths is not None:
            current: list[str] = []
            for raw in paths:
                rel = normalize_relative_path(raw, allow_root=False)
                if not self._path_admitted_for_analysis(rel):
                    continue
                self._ensure_path_current(rel)
                current.append(rel)
            normalized = tuple(current)

        return normalized, self.store.all_file_rows()

    @operation_response("import_ownership")
    @decision_scoped
    def import_ownership_findings(
        self, paths: Sequence[str] | None = None
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._ensure_map_ready()
        normalized, all_rows = self._ownership_analysis_inputs(paths)
        result = ImportOwnershipAnalyzer().analyze(self, normalized, all_rows)
        return cast(dict[str, object], result)

    @staticmethod
    def _repository_finding_from_import(
        finding: dict[str, object],
    ) -> dict[str, object]:
        return {
            "category": "import-identity",
            "code": finding["code"],
            "severity": finding["severity"],
            "confidence": finding["confidence"],
            "path": finding["path"],
            "line": finding["line"],
            "reason": finding["reason"],
            "recommendation": finding["recommendation"],
            "source_schema": operation_schema("import_ownership"),
            "evidence": dict(finding),
        }

    @staticmethod
    def _repository_finding_from_concurrency(
        finding: dict[str, object],
    ) -> dict[str, object]:
        return {
            "category": "concurrency-risk",
            "code": finding["code"],
            "severity": "advisory",
            "confidence": finding["confidence"],
            "path": finding["path"],
            "line": finding["line"],
            "reason": finding["reason"],
            "recommendation": finding["recommendation"],
            "source_schema": operation_schema("concurrency_risk"),
            "evidence": dict(finding),
        }

    @staticmethod
    def _repository_finding_from_cache_owner(
        owner: dict[str, object],
    ) -> dict[str, object]:
        return {
            "category": "cache-ownership",
            "code": "python-cache-owner-import-identity-risk",
            "severity": "warning",
            "confidence": owner["confidence"],
            "path": owner["path"],
            "line": owner["line"],
            "reason": owner["reason"],
            "recommendation": owner["recommendation"],
            "source_schema": operation_schema("cache_ownership"),
            "evidence": dict(owner),
        }

    @staticmethod
    def _adjudicate_repository_finding(
        finding: dict[str, object],
    ) -> dict[str, object]:
        """Attach interpretation state without erasing analyzer observations."""
        evidence = finding.get("evidence")
        counter_evidence: list[dict[str, object]] = []
        if isinstance(evidence, dict) and bool(
            cast("dict[str, object]", evidence).get("guarded")
        ):
            counter_evidence.append(
                {
                    "kind": "visible-guard",
                    "effect": "contradicts-actionability",
                }
            )
        result = dict(finding)
        result["observation"] = "retained"
        result["counter_evidence"] = counter_evidence
        result["interpretation"] = {
            "actionability": ("not-actionable" if counter_evidence else "actionable"),
            "authority": "repository-evidence-only",
        }
        return result

    @operation_response("repository_findings")
    @decision_scoped
    def repository_findings(
        self, paths: Sequence[str] | None = None
    ) -> dict[str, object]:
        """Project actionable repository-analysis evidence from existing analyzers.

        This is composition only. It does not add scanners, execute repository code,
        infer fixes, or grant runtime/certification authority. Lower-signal analyzer
        output remains available from the dedicated ownership commands.
        """
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._ensure_map_ready()
        normalized, all_rows = self._ownership_analysis_inputs(paths)
        import_result = ImportOwnershipAnalyzer().analyze(self, normalized, all_rows)
        repository_import_result = (
            import_result
            if normalized is None
            else ImportOwnershipAnalyzer().analyze(self, None, all_rows)
        )
        cache_result = CacheOwnershipAnalyzer().analyze(
            self, normalized, all_rows, import_result=repository_import_result
        )
        concurrency_result = ConcurrencyRiskAnalyzer().analyze(
            self, normalized, all_rows
        )

        findings = [
            *(
                self._repository_finding_from_import(item)
                for item in import_result["findings"]
            ),
            *(
                self._repository_finding_from_cache_owner(item)
                for item in cache_result["owners"]
                if bool(item.get("import_identity_risk"))
            ),
            *(
                self._repository_finding_from_concurrency(item)
                for item in concurrency_result["findings"]
                if not bool(item.get("guarded"))
            ),
        ]
        findings = [self._adjudicate_repository_finding(item) for item in findings]
        severity_order = {"warning": 0, "advisory": 1}
        findings.sort(
            key=lambda item: (
                severity_order.get(str(item["severity"]), 9),
                str(item["path"]),
                int(item["line"]),
                str(item["code"]),
            )
        )
        categories: dict[str, int] = {}
        for finding in findings:
            category = str(finding["category"])
            categories[category] = categories.get(category, 0) + 1
        generation, identity_generation, stale = self._generation_status()
        return {
            "schema": operation_schema("repository_findings"),
            "generation": generation,
            "identity_generation": identity_generation,
            "stale": stale,
            "summary": {
                "findings": len(findings),
                "warnings": sum(
                    1 for item in findings if item["severity"] == "warning"
                ),
                "advisories": sum(
                    1 for item in findings if item["severity"] == "advisory"
                ),
                "categories": categories,
            },
            "analyzers": {
                "import_ownership": dict(import_result["summary"]),
                "cache_ownership": dict(cache_result["summary"]),
                "concurrency_risk": dict(concurrency_result["summary"]),
            },
            "findings": findings,
            "boundary": (
                "repository-evidence projection only; no execution, remediation, "
                "admission, certification, or agent authority"
            ),
        }

    @operation_response("concurrency_risk")
    @decision_scoped
    def concurrency_risk_findings(
        self, paths: Sequence[str] | None = None
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._ensure_map_ready()
        normalized, all_rows = self._ownership_analysis_inputs(paths)
        result = ConcurrencyRiskAnalyzer().analyze(self, normalized, all_rows)
        return cast(dict[str, object], result)

    def _python_module_for_path(self, path: str) -> str | None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        target = PurePosixPath(path)
        if target.suffix not in {".py", ".pyi"}:
            return None
        parts = list(target.parts)
        if not parts:
            return None
        if target.stem == "__init__":
            parts = parts[:-1]
        else:
            parts[-1] = target.stem
        if not parts:
            return None
        # Package components above a non-top-level module must be backed by
        # __init__.py/__init__.pyi; otherwise do not invent import identity.
        if len(parts) > 1 and not self._python_package_chain_exists(parts[:-1]):
            return None
        return ".".join(parts)

    def _python_package_chain_exists(self, packages: list[str]) -> bool:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        current = PurePosixPath()
        for package in packages:
            current = current / package
            if not (
                (self.workspace / current / "__init__.py").is_file()
                or (self.workspace / current / "__init__.pyi").is_file()
            ):
                return False
        return True

    @staticmethod
    def _ast_imports_owner(tree: ast.AST, module: str, owner_name: str) -> bool:
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == module:
                for alias in node.names:
                    if alias.name == owner_name:
                        return True
            elif isinstance(node, ast.Import):
                if any(alias.name == module for alias in node.names):
                    # Import identity is proven; refs(owner_name) already proves
                    # the symbol is present in this reader.
                    return True
        return False

    def _reader_imports_cache_owner(
        self, reader: str, owner_path: str, owner_name: str
    ) -> bool:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        module = self._python_module_for_path(owner_path)
        if not module:
            return False
        try:
            tree = read_python_ast(self.workspace / reader, errors="replace").tree
        except (OSError, UnicodeError, SyntaxError, ValueError):
            return False
        return self._ast_imports_owner(tree, module, owner_name)

    @staticmethod
    def _ownership_add_imports(nodes, edges, findings) -> None:
        for finding in findings:
            source = str(finding["path"])
            target = finding.get("target_path")
            nodes[("file", source, source)] = {
                "id": f"file:{source}",
                "kind": "file",
                "path": source,
                "role": "loader",
            }
            if not target:
                continue
            target = str(target)
            nodes[("file", target, target)] = {
                "id": f"file:{target}",
                "kind": "file",
                "path": target,
                "role": "module-owner",
            }
            edges.append(
                {
                    "source": f"file:{source}",
                    "target": f"file:{target}",
                    "relation": "loads-module",
                    "confidence": finding["confidence"],
                    "risk": finding["code"],
                }
            )

    @staticmethod
    def _ownership_add_cache_owners(nodes, edges, owners) -> None:
        for owner in owners:
            path = str(owner["path"])
            name = str(owner["owner"])
            nodes.setdefault(
                ("file", path, path),
                {"id": f"file:{path}", "kind": "file", "path": path, "role": "source"},
            )
            nodes[("cache", path, name)] = {
                "id": f"cache:{path}:{name}",
                "kind": "cache",
                "path": path,
                "owner": name,
                "scope": owner["scope"],
                "invalidation": owner["invalidation"],
            }
            edges.append(
                {
                    "source": f"file:{path}",
                    "target": f"cache:{path}:{name}",
                    "relation": "owns-cache",
                    "confidence": owner["confidence"],
                    "risk": "duplicate-module-identity"
                    if owner["import_identity_risk"]
                    else None,
                }
            )

    @staticmethod
    def _cache_owner_name_counts(owners) -> dict[str, int]:
        counts: dict[str, int] = {}
        for owner in owners:
            name = str(owner["owner"])
            counts[name] = counts.get(name, 0) + 1
        return counts

    def _ownership_add_cache_readers(
        self, nodes, edges, owners, selected: set[str]
    ) -> None:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        counts = self._cache_owner_name_counts(owners)
        for owner in owners:
            path = str(owner["path"])
            name = str(owner["owner"])
            duplicate = counts.get(name, 0) > 1
            for ref in self.store.refs(name, limit=32):
                reader = str(ref["path"])
                if reader == path:
                    continue
                outside_selection = bool(selected) and {reader, path}.isdisjoint(
                    selected
                )
                if outside_selection:
                    continue
                if duplicate and not self._reader_imports_cache_owner(
                    reader, path, name
                ):
                    continue
                nodes.setdefault(
                    ("file", reader, reader),
                    {
                        "id": f"file:{reader}",
                        "kind": "file",
                        "path": reader,
                        "role": "reader",
                    },
                )
                edges.append(
                    {
                        "source": f"file:{reader}",
                        "target": f"cache:{path}:{name}",
                        "relation": "references-cache-owner",
                        "confidence": "qualified-import"
                        if duplicate
                        else "lexical-symbol",
                        "risk": None,
                    }
                )

    @staticmethod
    def _ownership_add_invalidations(
        nodes, edges, invalidation_result
    ) -> tuple[set[str], set[str]]:
        cache_ids = {
            str(node["id"]) for node in nodes.values() if node.get("kind") == "cache"
        }
        resolved: set[str] = set()
        invalidation_nodes = {
            str(node["id"]): node for node in invalidation_result["nodes"]
        }
        for edge in invalidation_result["edges"]:
            target = str(edge["target"])
            if target not in cache_ids:
                continue
            source = str(edge["source"])
            invalidator = invalidation_nodes.get(source)
            if invalidator is not None:
                nodes.setdefault(("invalidator", source, source), dict(invalidator))
            edges.append(dict(edge))
            resolved.add(target)
        return cache_ids, resolved

    @staticmethod
    def _ownership_add_concurrency(nodes, edges, findings) -> int:
        unguarded = 0
        for finding in findings:
            path = str(finding["path"])
            function = str(finding["function"])
            line = int(finding["line"])
            nodes.setdefault(
                ("file", path, path),
                {"id": f"file:{path}", "kind": "file", "path": path, "role": "source"},
            )
            rid = f"risk:{path}:{function}:{line}"
            nodes[("concurrency-risk", rid, rid)] = {
                "id": rid,
                "kind": "concurrency-risk",
                "path": path,
                "function": function,
                "line": line,
                "code": finding["code"],
                "guarded": bool(finding["guarded"]),
                "read_call": finding["read_call"],
                "write_call": finding["write_call"],
                "confidence": finding["confidence"],
            }
            edges.append(
                {
                    "source": f"file:{path}",
                    "target": rid,
                    "relation": "contains-concurrency-risk",
                    "confidence": finding["confidence"],
                    "risk": finding["code"],
                    "guarded": bool(finding["guarded"]),
                    "line": line,
                }
            )
            unguarded += int(not bool(finding["guarded"]))
        return unguarded

    def _ownership_graph_sources(self, paths: Sequence[str] | None):
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        normalized, all_rows = self._ownership_analysis_inputs(paths)
        import_result = ImportOwnershipAnalyzer().analyze(self, normalized, all_rows)
        repository_import_result = (
            import_result
            if normalized is None
            else ImportOwnershipAnalyzer().analyze(self, None, all_rows)
        )
        cache_result = CacheOwnershipAnalyzer().analyze(
            self, normalized, all_rows, import_result=repository_import_result
        )
        repository_cache_result = (
            cache_result
            if normalized is None
            else CacheOwnershipAnalyzer().analyze(
                self, None, all_rows, import_result=repository_import_result
            )
        )
        invalidation_result = CacheInvalidationAnalyzer().analyze(
            self, normalized, all_rows, cache_result=repository_cache_result
        )
        concurrency_result = ConcurrencyRiskAnalyzer().analyze(
            self, normalized, all_rows
        )
        return import_result, cache_result, invalidation_result, concurrency_result

    @operation_response("repository_ownership")
    @decision_scoped
    def repository_ownership_graph(
        self, paths: Sequence[str] | None = None
    ) -> dict[str, object]:
        """Compose repository ownership evidence without inventing runtime authority."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._ensure_map_ready()
        import_result, cache_result, invalidation_result, concurrency_result = (
            self._ownership_graph_sources(paths)
        )
        nodes: dict[tuple[str, str, str], dict[str, object]] = {}
        edges: list[dict[str, object]] = []
        self._ownership_add_imports(nodes, edges, import_result["findings"])
        self._ownership_add_cache_owners(nodes, edges, cache_result["owners"])
        self._ownership_add_cache_readers(
            nodes, edges, cache_result["owners"], {str(x) for x in (paths or [])}
        )
        cache_ids, resolved = self._ownership_add_invalidations(
            nodes, edges, invalidation_result
        )
        unguarded = self._ownership_add_concurrency(
            nodes, edges, concurrency_result["findings"]
        )
        ambiguous = sorted(cache_ids - resolved)
        generation, identity_generation, stale = self._generation_status()
        return {
            "schema": operation_schema("repository_ownership"),
            "generation": generation,
            "identity_generation": identity_generation,
            "stale": stale,
            "summary": {
                "nodes": len(nodes),
                "edges": len(edges),
                "resolved_invalidation_owners": len(resolved),
                "unresolved_invalidation_owners": len(ambiguous),
                "concurrency_risks": len(concurrency_result["findings"]),
                "unguarded_concurrency_risks": unguarded,
            },
            "nodes": sorted(nodes.values(), key=lambda n: str(n["id"])),
            "edges": sorted(
                edges,
                key=lambda x: (
                    str(x["source"]),
                    str(x["target"]),
                    str(x["relation"]),
                    int(x.get("line", 0) or 0),
                ),
            ),
            "ambiguities": ambiguous,
            "boundary": "repository-evidence-only; no execution/admission/certification authority",
        }

    @operation_response("cache_invalidation_ownership")
    @decision_scoped
    def cache_invalidation_ownership_graph(
        self, paths: Sequence[str] | None = None
    ) -> dict[str, object]:
        """Resolve repository-visible cache invalidators to exact cache owners."""
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._ensure_map_ready()
        normalized, all_rows = self._ownership_analysis_inputs(paths)
        import_result = ImportOwnershipAnalyzer().analyze(self, None, all_rows)
        repository_cache_result = CacheOwnershipAnalyzer().analyze(
            self, None, all_rows, import_result=import_result
        )
        result = CacheInvalidationAnalyzer().analyze(
            self, normalized, all_rows, cache_result=repository_cache_result
        )
        return cast(dict[str, object], result)

    @operation_response("cache_ownership")
    @decision_scoped
    def cache_ownership_findings(
        self, paths: Sequence[str] | None = None
    ) -> dict[str, object]:
        if TYPE_CHECKING:
            self = cast("CodeMap", self)
        self._ensure_map_ready()
        normalized, all_rows = self._ownership_analysis_inputs(paths)
        import_result = ImportOwnershipAnalyzer().analyze(self, None, all_rows)
        result = CacheOwnershipAnalyzer().analyze(
            self, normalized, all_rows, import_result=import_result
        )
        return cast(dict[str, object], result)
