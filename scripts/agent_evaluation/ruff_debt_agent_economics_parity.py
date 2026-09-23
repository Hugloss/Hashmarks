from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_RUFF_DEBT_PATH = ROOT / "scripts" / "ruff_debt.py"
_RUFF_DEBT_SPEC = importlib.util.spec_from_file_location(
    "hashmarks_ruff_debt", _RUFF_DEBT_PATH
)
if _RUFF_DEBT_SPEC is None or _RUFF_DEBT_SPEC.loader is None:
    raise RuntimeError(
        f"cannot load Hashmarks Ruff debt implementation: {_RUFF_DEBT_PATH}"
    )
ruff_debt = importlib.util.module_from_spec(_RUFF_DEBT_SPEC)
_RUFF_DEBT_SPEC.loader.exec_module(ruff_debt)
AGENT_ECONOMICS = ROOT / ".agent-economics" / "scripts"

# This is a dogfood/parity harness, not Hashmarks acceptance authority.
# Materialize agentsCookbook under .agent-economics before running it.

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


def _ranked_hotspots(payload: dict[str, object]) -> list[dict[str, object]]:
    summary = dict(dict(payload["derived"])["summary"])
    details = [dict(row) for row in dict(payload["evidence"])["detailed_findings"]]
    by_path: dict[str, list[dict[str, object]]] = {}
    for row in details:
        by_path.setdefault(str(row["path"]), []).append(row)
    ranked: list[dict[str, object]] = []
    for path, raw in dict(summary["files"]).items():
        item = dict(raw)
        rules = Counter(str(row["rule"]) for row in by_path.get(path, []))
        ranked.append(
            {
                "path": path,
                "locations": int(item["locations"]),
                "rule_findings": int(item["rule_findings"]),
                "excess": int(item["excess"]),
                "rules": dict(sorted(rules.items())),
            }
        )
    return sorted(
        ranked,
        key=lambda row: (
            -int(row["excess"]),
            -int(row["rule_findings"]),
            str(row["path"]),
        ),
    )


def main() -> int:
    quality_debt_audit = _load_quality_debt()
    payload = quality_debt_audit(
        repository_root=ROOT,
        roots=("hashmarks", "scripts", "benchmarks"),
        limits=ruff_debt.LIMITS,
        max_file_lines=ruff_debt.MAX_PYTHON_FILE_LINES,
        file_line_roots=("hashmarks",),
        excludes=(),
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
    if measured != expected:
        print(
            json.dumps(
                {"legacy": expected, "agent_economics": measured},
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    ranked = _ranked_hotspots(payload)
    print(
        "Agent Economics Ruff debt parity: PASS "
        f"(excess={measured['excess']}, files={len(measured['files'])})"
    )
    print(json.dumps({"ranked_hotspots": ranked}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
