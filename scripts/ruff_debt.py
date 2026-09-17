from __future__ import annotations

import ast
from collections import Counter
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hashmarks.python_ast_cache import read_python_ast

LIMITS = {
    "C901": 8,
    "PLR0911": 6,
    "PLR0912": 8,
    "PLR0913": 6,
    "PLR0914": 15,
    "PLR0915": 40,
    "PLR0916": 5,
}
ROOTS = (Path("hashmarks"), Path("scripts"), Path("benchmarks"))


class _FunctionBody(ast.NodeVisitor):
    def __init__(self, root: ast.AST) -> None:
        self.root = root
        self.nodes: list[ast.AST] = []

    def generic_visit(self, node: ast.AST) -> None:
        if node is not self.root and isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
        ):
            return
        self.nodes.append(node)
        super().generic_visit(node)


def _complexity(nodes: list[ast.AST]) -> int:
    score = 1
    for node in nodes:
        if isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp, ast.Assert)):
            score += 1
        elif isinstance(node, ast.BoolOp):
            score += max(0, len(node.values) - 1)
        elif isinstance(node, ast.Try):
            score += len(node.handlers)
        elif isinstance(node, ast.Match):
            score += len(node.cases)
        elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            score += sum(1 + len(generator.ifs) for generator in node.generators)
    return score


def _branch_count(nodes: list[ast.AST]) -> int:
    branch_types = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.Match, ast.IfExp)
    return sum(isinstance(item, branch_types) for item in nodes)


def _assigned_count(nodes: list[ast.AST]) -> int:
    return len({
        item.id
        for item in nodes
        if isinstance(item, ast.Name) and isinstance(item.ctx, (ast.Store, ast.Del))
    })


def _metrics(node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, int]:
    visitor = _FunctionBody(node)
    visitor.visit(node)
    nodes = visitor.nodes
    return {
        "C901": _complexity(nodes),
        "PLR0911": sum(isinstance(item, ast.Return) for item in nodes),
        "PLR0912": _branch_count(nodes),
        "PLR0913": len(node.args.args) + len(node.args.kwonlyargs) + len(node.args.posonlyargs),
        "PLR0914": _assigned_count(nodes),
        "PLR0915": sum(isinstance(item, ast.stmt) for item in nodes) - 1,
        "PLR0916": max((len(item.values) for item in nodes if isinstance(item, ast.BoolOp)), default=0),
    }


def inventory() -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for root in ROOTS:
        for path in sorted(root.rglob("*.py")):
            tree = read_python_ast(path).tree
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                metrics = _metrics(node)
                violations = {
                    rule: value for rule, value in metrics.items() if value > LIMITS[rule]
                }
                if violations:
                    findings.append(
                        {
                            "path": path.as_posix(),
                            "line": node.lineno,
                            "function": node.name,
                            "violations": violations,
                        }
                    )
    return findings


def _summary(findings: list[dict[str, object]]) -> dict[str, object]:
    files: dict[str, dict[str, int]] = {}
    for finding in findings:
        path = str(finding["path"])
        row = files.setdefault(path, {"functions": 0, "rule_findings": 0, "excess": 0})
        row["functions"] += 1
        violations = dict(finding["violations"])
        row["rule_findings"] += len(violations)
        row["excess"] += sum(int(value) - LIMITS[rule] for rule, value in violations.items())
    roots = Counter(path.split("/", 1)[0] for path in files for _ in range(files[path]["functions"]))
    return {
        "schema": "hashmarks.ruff-debt.v1",
        "limits": LIMITS,
        "functions": len(findings),
        "rule_findings": sum(len(dict(item["violations"])) for item in findings),
        "excess": sum(
            int(value) - LIMITS[rule]
            for item in findings
            for rule, value in dict(item["violations"]).items()
        ),
        "by_root": dict(sorted(roots.items())),
        "files": dict(sorted(files.items())),
    }


def _baseline_failures(summary: dict[str, object], baseline: dict[str, object]) -> list[str]:
    current_files = dict(summary["files"])
    baseline_files = dict(baseline["files"])
    failures: list[str] = []
    for path, current in current_files.items():
        before = baseline_files.get(path)
        if before is None:
            failures.append(f"new debt file: {path} excess={current['excess']}")
            continue
        if current["excess"] > before["excess"]:
            failures.append(f"debt increased: {path} {before['excess']} -> {current['excess']}")
    if int(summary["excess"]) > int(baseline["excess"]):
        failures.append(f"total debt increased: {baseline['excess']} -> {summary['excess']}")
    return failures


def _parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="Conservative local mirror of the strict Ruff debt budget.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--summary-only", action="store_true")
    parser.add_argument("--write-baseline", type=Path)
    parser.add_argument("--baseline", type=Path)
    return parser.parse_args()


def _write_baseline(path: Path | None, summary: dict[str, object]) -> None:
    if path is not None:
        path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _report_baseline(args, summary: dict[str, object]) -> int | None:
    if args.baseline is None:
        return None
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    failures = _baseline_failures(summary, baseline)
    if args.json:
        print(json.dumps({"summary": summary, "failures": failures}, sort_keys=True))
    else:
        print(f"Ruff debt excess: {summary['excess']} (baseline {baseline['excess']})")
        for failure in failures:
            print(f"FAIL: {failure}")
    return 1 if failures else 0


def _report_inventory(findings: list[dict[str, object]], summary: dict[str, object], as_json: bool) -> int:
    if as_json:
        print(json.dumps(summary, sort_keys=True))
        return 1 if findings else 0
    keys = ("functions", "rule_findings", "excess", "by_root")
    print(json.dumps({key: summary[key] for key in keys}, sort_keys=True))
    for finding in findings:
        rules = ", ".join(f"{rule}={value}" for rule, value in finding["violations"].items())
        print(f"{finding['path']}:{finding['line']}:{finding['function']}: {rules}")
    return 1 if findings else 0


def main() -> int:
    args = _parse_args()
    findings = inventory()
    summary = _summary(findings)
    _write_baseline(args.write_baseline, summary)
    if args.summary_only:
        keys = ("functions", "rule_findings", "excess", "by_root")
        print(json.dumps({key: summary[key] for key in keys}, sort_keys=True))
        return 0
    baseline_result = _report_baseline(args, summary)
    if baseline_result is not None:
        return baseline_result
    return _report_inventory(findings, summary, args.json)


if __name__ == "__main__":
    raise SystemExit(main())
