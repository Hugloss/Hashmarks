from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from hashmarks.operation_contract import operation_schema
from hashmarks.python_ast_cache import read_python_ast

from ..repository_domains import RepositoryDomain, classify_repository_path
from .results import ConcurrencyRiskResult

if TYPE_CHECKING:
    from ..engine import CodeMap


class ConcurrencyRiskAnalyzer:
    def analyze(
        self,
        codemap: CodeMap,
        paths: Sequence[str] | None,
        all_rows: Sequence[dict[str, object]],
    ) -> ConcurrencyRiskResult:
        python_paths = {
            str(row["path"]) for row in all_rows if row["language"] == "python"
        }
        candidates = self._candidates(codemap, paths, python_paths)

        findings = []
        for rel in candidates:
            try:
                snapshot = read_python_ast(codemap.workspace / rel, errors="replace")
            except (OSError, UnicodeError, SyntaxError, ValueError):
                continue

            from ..concurrency_risk import analyze_python_concurrency_risk

            findings.extend(
                x.as_dict()
                for x in analyze_python_concurrency_risk(
                    path=rel, source=snapshot.source, tree=snapshot.tree
                )
            )

        generation, identity_generation, stale = codemap._generation_status()
        return {
            "schema": operation_schema("concurrency_risk"),
            "generation": generation,
            "identity_generation": identity_generation,
            "stale": stale,
            "summary": {
                "files_considered": len(candidates),
                "sequences": len(findings),
                "unguarded": sum(1 for x in findings if not x["guarded"]),
            },
            "findings": findings,
            "boundary": "static risk nomination only; concurrency admission/execution remains external",
        }

    @staticmethod
    def _candidates(
        codemap: CodeMap,
        paths: Sequence[str] | None,
        python_paths: set[str],
    ) -> list[str]:
        if paths is None:
            rows = codemap.store.lexical_file_candidates(
                [
                    "read",
                    "get",
                    "generation",
                    "write",
                    "set",
                    "update",
                    "commit",
                    "execute",
                ],
                limit=max(256, min(10_000, len(python_paths) or 256)),
            )
            candidates = []
            for row in rows:
                path = str(row["path"])
                if row["language"] != "python":
                    continue
                if RepositoryDomain.TEST in classify_repository_path(path):
                    continue
                candidates.append(path)
        else:
            candidates = []
            for rel in paths:
                if rel in python_paths:
                    candidates.append(rel)

        return sorted(set(candidates))
