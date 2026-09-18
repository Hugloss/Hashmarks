from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from scripts import ruff_debt

ROOT = Path(__file__).resolve().parents[1]
AGENT_ECONOMICS = ROOT / ".agent-economics" / "scripts"

# This is a dogfood/parity harness, not Hashmarks acceptance authority.
# Materialize agentsCookbook under .agent-economics before running it.
EXCLUDES = ("benchmarks/agent_evaluation/retained",)


def _load_quality_debt():
    if not AGENT_ECONOMICS.exists():
        raise RuntimeError(
            "agentsCookbook is not materialized at .agent-economics; "
            "parity proof requires the external measurement implementation"
        )
    sys.path.insert(0, str(AGENT_ECONOMICS))
    from agent_economics.quality_debt import quality_debt_audit

    return quality_debt_audit


def _legacy_shape(summary: dict[str, object]) -> dict[str, object]:
    files: dict[str, dict[str, int]] = {}
    for path, row in dict(summary["files"]).items():
        item = dict(row)
        files[path] = {
            "functions": int(item["locations"]),
            "rule_findings": int(item["rule_findings"]),
            "excess": int(item["excess"]),
        }
    roots = Counter(
        path.split("/", 1)[0]
        for path, row in files.items()
        for _ in range(row["functions"])
    )
    return {
        "functions": int(summary["locations"]),
        "rule_findings": int(summary["rule_findings"]),
        "excess": int(summary["excess"]),
        "by_root": dict(sorted(roots.items())),
        "oversized_files": dict(summary["oversized_files"]),
        "files": dict(sorted(files.items())),
    }


def main() -> int:
    quality_debt_audit = _load_quality_debt()
    payload = quality_debt_audit(
        repository_root=ROOT,
        roots=("hashmarks", "scripts", "benchmarks"),
        limits=ruff_debt.LIMITS,
        max_file_lines=ruff_debt.MAX_PYTHON_FILE_LINES,
        file_line_roots=("hashmarks",),
        excludes=EXCLUDES,
    )
    measured = _legacy_shape(dict(payload["derived"])["summary"])
    legacy = ruff_debt._summary(ruff_debt.inventory())
    expected = {
        key: legacy[key]
        for key in (
            "functions",
            "rule_findings",
            "excess",
            "by_root",
            "oversized_files",
            "files",
        )
    }
    if measured != expected:\n        print(\n            json.dumps(\n                {"legacy": expected, "agent_economics": measured},\n                indent=2,\n                sort_keys=True,\n            )\n        )\n        return 1\n    print(
        "Agent Economics Ruff debt parity: PASS "
        f"(excess={measured['excess']}, files={len(measured['files'])})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
