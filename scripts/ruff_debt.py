from __future__ import annotations

import json
import re
import subprocess
import tomllib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOTS = (Path("hashmarks"), Path("scripts"), Path("benchmarks"))
_OBSERVED_LIMIT = re.compile(r"\((\d+)\s*(?:>|/)\s*(\d+)\)$")


def _quality_config() -> tuple[dict[str, int], int]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    tool = data["tool"]
    ruff_lint = tool["ruff"]["lint"]
    mccabe = ruff_lint["mccabe"]
    pylint = ruff_lint["pylint"]
    quality = tool["hashmarks"]["quality"]
    limits = {
        "C901": int(mccabe["max-complexity"]),
        "PLR0911": int(pylint["max-returns"]),
        "PLR0912": int(pylint["max-branches"]),
        "PLR0913": int(pylint["max-args"]),
        "PLR0914": int(pylint["max-locals"]),
        "PLR0915": int(pylint["max-statements"]),
        "PLR0916": int(pylint["max-bool-expr"]),
    }
    return limits, int(quality["max-python-file-lines"])


LIMITS, MAX_PYTHON_FILE_LINES = _quality_config()


def inventory() -> list[dict[str, object]]:
    command = [
        "ruff",
        "check",
        *(str(root) for root in ROOTS),
        "--preview",
        "--select",
        ",".join(LIMITS),
        "--config",
        "lint.per-file-ignores = {}",
        "--output-format",
        "json",
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"Ruff inventory failed: {result.stderr.strip()}")
    grouped: dict[tuple[str, int], dict[str, object]] = {}
    for diagnostic in json.loads(result.stdout):
        rule = diagnostic["code"]
        path = Path(diagnostic["filename"]).relative_to(ROOT).as_posix()
        line = int(diagnostic["location"]["row"])
        match = _OBSERVED_LIMIT.search(diagnostic["message"])
        if match is None or int(match.group(2)) != LIMITS[rule]:
            raise ValueError(
                f"unrecognized Ruff {rule} diagnostic: {diagnostic['message']}"
            )
        key = (path, line)
        row = grouped.setdefault(
            key,
            {"path": path, "line": line, "violations": {}},
        )
        row["violations"][rule] = int(match.group(1))
    return [grouped[key] for key in sorted(grouped)]


def _oversized_production_files() -> dict[str, int]:
    oversized: dict[str, int] = {}
    for path in sorted(Path("hashmarks").rglob("*.py")):
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count > MAX_PYTHON_FILE_LINES:
            oversized[path.as_posix()] = line_count
    return oversized


def _summary(findings: list[dict[str, object]]) -> dict[str, object]:
    files: dict[str, dict[str, int]] = {}
    for finding in findings:
        path = str(finding["path"])
        row = files.setdefault(path, {"functions": 0, "rule_findings": 0, "excess": 0})
        row["functions"] += 1
        violations = dict(finding["violations"])
        row["rule_findings"] += len(violations)
        row["excess"] += sum(
            int(value) - LIMITS[rule] for rule, value in violations.items()
        )
    roots = Counter(
        path.split("/", 1)[0] for path in files for _ in range(files[path]["functions"])
    )
    return {
        "schema": "hashmarks.ruff-debt.v3",
        "limits": LIMITS,
        "max_python_file_lines": MAX_PYTHON_FILE_LINES,
        "oversized_files": _oversized_production_files(),
        "functions": len(findings),
        "rule_findings": sum(len(dict(item["violations"])) for item in findings),
        "excess": sum(
            int(value) - LIMITS[rule]
            for item in findings
            for rule, value in dict(item["violations"]).items()
        ),
        "by_root": dict(sorted(roots.items())),
        "files": dict(sorted(files.items())),
        "findings": findings,
    }


def _baseline_failures(
    summary: dict[str, object], baseline: dict[str, object]
) -> list[str]:
    if baseline.get("schema") != summary["schema"]:
        return ["debt baseline schema mismatch; regenerate from exact Ruff inventory"]
    if baseline.get("limits") != summary["limits"]:
        return ["Ruff limits changed; review the configured thresholds and baseline"]
    current_files = dict(summary["files"])
    baseline_files = dict(baseline["files"])
    failures: list[str] = []
    for path, current in current_files.items():
        before = baseline_files.get(path)
        if before is None:
            failures.append(f"new debt file: {path} excess={current['excess']}")
            continue
        if current["excess"] > before["excess"]:
            failures.append(
                f"debt increased: {path} {before['excess']} -> {current['excess']}"
            )
    if int(summary["excess"]) > int(baseline["excess"]):
        failures.append(
            f"total debt increased: {baseline['excess']} -> {summary['excess']}"
        )
    for path, lines in dict(summary["oversized_files"]).items():
        failures.append(
            f"production file too long: {path} {lines} > {MAX_PYTHON_FILE_LINES} lines"
        )
    return failures


def _parse_args():
    import argparse

    parser = argparse.ArgumentParser(
        description="Exact Ruff diagnostic inventory and no-growth budget."
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--summary-only", action="store_true")
    parser.add_argument("--write-baseline", type=Path)
    parser.add_argument("--baseline", type=Path)
    return parser.parse_args()


def _write_baseline(path: Path | None, summary: dict[str, object]) -> None:
    if path is not None:
        path.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def _report_baseline(args, summary: dict[str, object]) -> int | None:
    if args.baseline is None:
        return None
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    failures = _baseline_failures(summary, baseline)
    if args.json:
        print(json.dumps({"summary": summary, "failures": failures}, sort_keys=True))
    else:
        print(f"Ruff debt excess: {summary['excess']} (baseline {baseline['excess']})")
        print(
            "Production file line ceiling: "
            f"{MAX_PYTHON_FILE_LINES} (oversized={len(dict(summary['oversized_files']))})"
        )
        for failure in failures:
            print(f"FAIL: {failure}")
    return 1 if failures else 0


def _report_inventory(
    findings: list[dict[str, object]], summary: dict[str, object], as_json: bool
) -> int:
    oversized = dict(summary["oversized_files"])
    if as_json:
        print(json.dumps(summary, sort_keys=True))
        return 1 if findings or oversized else 0
    keys = (
        "functions",
        "rule_findings",
        "excess",
        "by_root",
        "max_python_file_lines",
        "oversized_files",
    )
    print(json.dumps({key: summary[key] for key in keys}, sort_keys=True))
    for finding in findings:
        rules = ", ".join(
            f"{rule}={value}" for rule, value in finding["violations"].items()
        )
        print(f"{finding['path']}:{finding['line']}: {rules}")
    return 1 if findings or oversized else 0


def main() -> int:
    args = _parse_args()
    findings = inventory()
    summary = _summary(findings)
    _write_baseline(args.write_baseline, summary)
    if args.summary_only:
        keys = (
            "functions",
            "rule_findings",
            "excess",
            "by_root",
            "max_python_file_lines",
            "oversized_files",
        )
        print(json.dumps({key: summary[key] for key in keys}, sort_keys=True))
        return 0
    baseline_result = _report_baseline(args, summary)
    if baseline_result is not None:
        return baseline_result
    return _report_inventory(findings, summary, args.json)


if __name__ == "__main__":
    raise SystemExit(main())
