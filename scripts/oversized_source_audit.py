"""Measure structural source outliers without making them runtime authority."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path


def _definitions(tree: ast.AST) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        end = getattr(node, "end_lineno", node.lineno)
        rows.append(
            {
                "kind": type(node).__name__,
                "name": node.name,
                "start_line": node.lineno,
                "end_line": end,
                "lines": end - node.lineno + 1,
            }
        )
    return rows


def audit(root: Path) -> dict[str, object]:
    files: list[dict[str, object]] = []
    for path in sorted((root / "hashmarks").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        defs = _definitions(tree)
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": len(text.encode()),
                "lines": len(text.splitlines()),
                "definitions": len(defs),
                "largest_definition_lines": max(
                    (int(row["lines"]) for row in defs), default=0
                ),
                "largest_definitions": sorted(
                    defs, key=lambda row: (-int(row["lines"]), int(row["start_line"]))
                )[:5],
            }
        )
    ranked = sorted(files, key=lambda row: (-int(row["lines"]), str(row["path"])))
    return {
        "schema": "hashmarks.development-oversized-source-audit.v1",
        "authority": "development-quality-only",
        "policy": {
            "critical_file_lines": 2000,
            "high_file_lines": 1000,
            "review_file_lines": 700,
            "large_function_lines": 200,
            "note": "Thresholds nominate review; cohesion and separable responsibility decide refactoring.",
        },
        "python_file_count": len(ranked),
        "total_python_lines": sum(int(row["lines"]) for row in ranked),
        "critical_files": [row for row in ranked if int(row["lines"]) >= 2000],
        "high_files": [row for row in ranked if 1000 <= int(row["lines"]) < 2000],
        "review_files": [row for row in ranked if 700 <= int(row["lines"]) < 1000],
        "top_files": ranked[:20],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = audit(args.root.resolve())
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")  # noqa: T201 - intentional command output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
