from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Sequence

from hashmarks.operation_contract import operation_schema
from hashmarks.python_ast_cache import read_python_ast

from .results import CacheInvalidationResult, CacheOwnershipResult, Finding

if TYPE_CHECKING:
    from ..engine import CodeMap


class CacheInvalidationAnalyzer:
    def analyze(
        self,
        codemap: CodeMap,
        paths: Sequence[str] | None,
        all_rows: Sequence[dict[str, object]],
        cache_result: CacheOwnershipResult,
    ) -> CacheInvalidationResult:
        owners, owner_ids = self._cache_owner_modules(codemap, cache_result)
        candidates = self._python_candidates(codemap, paths, all_rows)
        findings = self._cache_invalidator_findings(codemap, candidates, owners)
        nodes = self._cache_owner_nodes(owners, owner_ids)
        edges, invalidated = self._cache_invalidation_edges(findings, owner_ids, nodes)
        unresolved = sorted(cid for cid in owner_ids.values() if cid not in invalidated)
        generation, identity_generation, stale = codemap._generation_status()
        return {
            "schema": operation_schema("cache_invalidation_ownership"),
            "generation": generation,
            "identity_generation": identity_generation,
            "stale": stale,
            "summary": {
                "files_considered": len(candidates),
                "cache_owners": len(owners),
                "invalidators": sum(
                    1 for node in nodes.values() if node.get("kind") == "invalidator"
                ),
                "invalidation_edges": len(edges),
                "owners_without_resolved_invalidator": len(unresolved),
            },
            "nodes": sorted(nodes.values(), key=lambda node: str(node["id"])),
            "edges": sorted(
                edges,
                key=lambda edge: (
                    str(edge["source"]),
                    str(edge["target"]),
                    int(edge["line"]),
                ),
            ),
            "unresolved_cache_owners": unresolved,
            "boundary": "repository-evidence-only; cache mutation/execution authority remains external",
        }

    def _cache_owner_modules(
        self, codemap: CodeMap, cache_result: CacheOwnershipResult
    ) -> tuple[list[Finding], dict[tuple[str, str], str]]:
        owners: list[Finding] = []
        owner_ids: dict[tuple[str, str], str] = {}
        for owner in cache_result["owners"]:
            path = str(owner["path"])
            module = codemap._python_module_for_path(path)
            if not module:
                continue
            enriched = dict(owner)
            enriched["module"] = module
            owners.append(enriched)
            owner_ids[(module, str(owner["owner"]))] = f"cache:{path}:{owner['owner']}"
        return owners, owner_ids

    def _python_candidates(
        self,
        codemap: CodeMap,
        paths: Sequence[str] | None,
        all_rows: Sequence[dict[str, object]],
    ) -> list[str]:
        python_paths = {
            str(row["path"]) for row in all_rows if row["language"] == "python"
        }
        if paths is None:
            return sorted(python_paths)
        candidates: list[str] = []
        for rel in paths:
            if rel in python_paths or (codemap.workspace / rel).suffix in {
                ".py",
                ".pyi",
            }:
                candidates.append(rel)
        return sorted(set(candidates))

    def _cache_invalidator_findings(
        self, codemap: CodeMap, candidates: list[str], owners: list[Finding]
    ) -> list[Finding]:
        findings: list[dict[str, object]] = []
        for rel in candidates:
            module = codemap._python_module_for_path(rel)
            if not module:
                continue
            path_obj = PurePosixPath(rel)
            current_package = (
                module
                if path_obj.stem == "__init__"
                else (module.rsplit(".", 1)[0] if "." in module else None)
            )
            try:
                snapshot = read_python_ast(codemap.workspace / rel, errors="replace")
            except (OSError, UnicodeError, SyntaxError, ValueError):
                continue
            from ..cache_invalidation import analyze_python_cache_invalidators

            findings.extend(
                item.as_dict()
                for item in analyze_python_cache_invalidators(
                    path=rel,
                    source=snapshot.source,
                    current_module=module,
                    current_package=current_package,
                    cache_owners=owners,
                    tree=snapshot.tree,
                )
            )
        return findings

    @staticmethod
    def _cache_owner_nodes(
        owners: list[Finding], owner_ids: dict[tuple[str, str], str]
    ) -> dict[str, dict[str, object]]:
        nodes: dict[str, dict[str, object]] = {}
        for owner in owners:
            cid = owner_ids[(str(owner["module"]), str(owner["owner"]))]
            nodes[cid] = {
                "id": cid,
                "kind": "cache",
                "path": owner["path"],
                "module": owner["module"],
                "owner": owner["owner"],
                "scope": owner["scope"],
                "invalidation": owner["invalidation"],
            }
        return nodes

    @staticmethod
    def _cache_invalidation_edges(
        findings: list[Finding],
        owner_ids: dict[tuple[str, str], str],
        nodes: dict[str, dict[str, object]],
    ) -> tuple[list[dict[str, object]], set[str]]:
        edges: list[dict[str, object]] = []
        invalidated: set[str] = set()
        for finding in findings:
            source_id = f"invalidator:{finding['path']}:{finding['invalidator']}"
            target_id = owner_ids.get(
                (str(finding["target_module"]), str(finding["target_owner"]))
            )
            if target_id is None:
                continue
            nodes.setdefault(
                source_id,
                {
                    "id": source_id,
                    "kind": "invalidator",
                    "path": finding["path"],
                    "owner": finding["invalidator"],
                },
            )
            edges.append(
                {
                    "source": source_id,
                    "target": target_id,
                    "relation": "invalidates-cache",
                    "method": finding["method"],
                    "confidence": finding["confidence"],
                    "line": finding["line"],
                }
            )
            invalidated.add(target_id)
        return edges, invalidated
