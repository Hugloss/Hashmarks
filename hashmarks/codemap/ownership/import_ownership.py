from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from hashmarks.operation_contract import operation_schema
from hashmarks.python_ast_cache import read_python_ast

from .results import ImportOwnershipResult

if TYPE_CHECKING:
    from ..engine import CodeMap


class ImportOwnershipAnalyzer:
    def analyze(
        self,
        codemap: CodeMap,
        paths: Sequence[str] | None,
        all_rows: Sequence[dict[str, object]],
    ) -> ImportOwnershipResult:
        repository_paths = {str(row["path"]) for row in all_rows}
        python_paths = {
            str(row["path"]) for row in all_rows if row["language"] == "python"
        }
        if paths is not None:
            candidates = []
            for rel in paths:
                if rel in python_paths or (codemap.workspace / rel).suffix in {
                    ".py",
                    ".pyi",
                }:
                    candidates.append(rel)
        else:
            rows = codemap.store.lexical_file_candidates(
                ["spec_from_file_location", "module_from_spec", "exec_module"],
                limit=max(256, min(10_000, len(python_paths) or 256)),
            )
            candidates = [
                str(row["path"]) for row in rows if row["language"] == "python"
            ]

        findings: list[dict[str, object]] = []
        for rel in sorted(set(candidates)):
            codemap._ensure_path_current(rel)
            source_path = codemap.workspace / rel
            try:
                snapshot = read_python_ast(source_path, errors="replace")
            except (OSError, UnicodeError, SyntaxError, ValueError):
                continue

            from ..import_ownership import analyze_python_import_ownership

            findings.extend(
                finding.as_dict()
                for finding in analyze_python_import_ownership(
                    path=rel,
                    source=snapshot.source,
                    repository_paths=repository_paths,
                    tree=snapshot.tree,
                )
            )

        generation, identity_generation, stale = codemap._generation_status()
        warnings = sum(1 for finding in findings if finding["severity"] == "warning")
        advisories = len(findings) - warnings
        return {
            "schema": operation_schema("import_ownership"),
            "generation": generation,
            "identity_generation": identity_generation,
            "stale": stale,
            "summary": {
                "files_considered": len(set(candidates)),
                "findings": len(findings),
                "warnings": warnings,
                "advisories": advisories,
            },
            "findings": findings,
        }
