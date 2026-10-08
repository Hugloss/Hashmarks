from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from hashmarks.operation_contract import operation_schema
from hashmarks.python_ast_cache import read_python_ast

from .results import CacheOwnershipResult, ImportOwnershipResult

if TYPE_CHECKING:
    from ..engine import CodeMap


class CacheOwnershipAnalyzer:
    def analyze(
        self,
        codemap: CodeMap,
        paths: Sequence[str] | None,
        all_rows: Sequence[dict[str, object]],
        import_result: ImportOwnershipResult,
    ) -> CacheOwnershipResult:
        python_paths = {
            str(row["path"]) for row in all_rows if row["language"] == "python"
        }
        if paths is None:
            rows = codemap.store.lexical_file_candidates(
                [
                    "cache",
                    "memo",
                    "registry",
                    "singleton",
                    "pool",
                    "lru_cache",
                    "cached_property",
                ],
                limit=max(256, min(10_000, len(python_paths) or 256)),
            )
            candidates = [
                str(row["path"]) for row in rows if row["language"] == "python"
            ]
        else:
            candidates = []
            for rel in paths:
                if rel in python_paths or (codemap.workspace / rel).suffix in {
                    ".py",
                    ".pyi",
                }:
                    candidates.append(rel)

        risky_targets = {
            str(f["target_path"])
            for f in import_result["findings"]
            if f.get("target_path")
            and f.get("code")
            in {
                "python-dynamic-module-identity-bypass",
                "python-duplicate-module-identity",
            }
        }

        findings: list[dict[str, object]] = []
        for rel in sorted(set(candidates)):
            try:
                snapshot = read_python_ast(codemap.workspace / rel, errors="replace")
            except (OSError, UnicodeError, SyntaxError, ValueError):
                continue

            from ..cache_ownership import analyze_python_cache_ownership

            findings.extend(
                item.as_dict()
                for item in analyze_python_cache_ownership(
                    path=rel,
                    source=snapshot.source,
                    import_risk_targets=risky_targets,
                    tree=snapshot.tree,
                )
            )

        generation, identity_generation, stale = codemap._generation_status()
        risky = sum(1 for f in findings if f["import_identity_risk"])
        unresolved = sum(1 for f in findings if f["invalidation"] == "not-proven")
        return {
            "schema": operation_schema("cache_ownership"),
            "generation": generation,
            "identity_generation": identity_generation,
            "stale": stale,
            "summary": {
                "files_considered": len(set(candidates)),
                "owners": len(findings),
                "import_identity_risks": risky,
                "invalidation_not_proven": unresolved,
            },
            "owners": findings,
        }
