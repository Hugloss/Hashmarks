# Imports below follow the standalone script path bootstrap.
# ruff: noqa: E402
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from hashmarks.codemap import (
    CodeMap,
)

SCHEMA = "hashmarks.verification-relevance-scale.v1"


def _sha256_json(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _materialize(root: Path, distractors: int, feature: int) -> tuple[str, str]:
    namespace = f"feature{feature:04d}"
    local = root / "packages" / namespace
    (local / "tests").mkdir(parents=True)
    (root / "tests" / "regression").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n", encoding="utf-8"
    )
    (local / "service.py").write_text(
        "def apply_policy(value):\n    return value\n", encoding="utf-8"
    )
    expected = f"packages/{namespace}/tests/test_contract.py"
    (root / expected).write_text(
        f"from packages.{namespace}.service import apply_policy\n\n"
        "def test_contract():\n    assert apply_policy(1) == 1\n",
        encoding="utf-8",
    )
    for index in range(distractors):
        path = (
            root
            / "tests"
            / "regression"
            / f"test_apply_policy_{namespace}_regression_{index:04d}.py"
        )
        path.write_text(
            f"from packages.{namespace}.service import apply_policy\n\n"
            f"def test_apply_policy_{namespace}_regression():\n    assert apply_policy(1) == 1\n",
            encoding="utf-8",
        )
    return f"Fix apply_policy behavior for {namespace}", expected


def collect(*, sizes: tuple[int, ...] = (10, 50, 100, 500)) -> dict[str, object]:
    base = Path(tempfile.mkdtemp(prefix="hashmarks-verification-scale-"))
    rows: list[dict[str, object]] = []
    try:
        for offset, distractors in enumerate(sizes, 1):
            workspace = base / f"n{distractors}"
            workspace.mkdir()
            task, expected = _materialize(workspace, distractors, feature=40 + offset)
            with CodeMap(workspace) as codemap:
                timings = {}
                started = time.perf_counter()
                codemap.sync()
                timings["sync_ms"] = (time.perf_counter() - started) * 1000.0
                started = time.perf_counter()
                action = codemap.task_action_map(task, limit=20)
                timings["action_ms"] = (time.perf_counter() - started) * 1000.0
                relevance = action["verification_relevance"]
                selected = (
                    relevance.get("selected") if isinstance(relevance, dict) else None
                )
                paths = {
                    "selected": str(selected.get("path") or "")
                    if isinstance(selected, dict)
                    else "",
                    "canonical": str(relevance.get("current_canonical_verify") or "")
                    if isinstance(relevance, dict)
                    else "",
                }
                plan = (
                    codemap.verification_plan(
                        paths["selected"],
                        symbol=(str(selected.get("test_symbol") or "") or None)
                        if isinstance(selected, dict)
                        else None,
                    )
                    if paths["selected"]
                    else {"available": False}
                )
            rows.append(
                {
                    "distractor_tests": distractors,
                    "total_test_surfaces": distractors + 1,
                    "task_sha256": hashlib.sha256(task.encode("utf-8")).hexdigest(),
                    "expected_local_verification": expected,
                    "baseline_canonical_verify": paths["canonical"],
                    "baseline_correct": paths["canonical"] == expected,
                    "selected_verify": paths["selected"],
                    "selected_correct": paths["selected"] == expected,
                    "selection_changed": bool(relevance.get("selection_changed")),
                    "selection_reason": relevance.get("selection_reason"),
                    "candidate_count": int(relevance.get("candidate_count") or 0),
                    "returned_candidates": len(relevance.get("candidates") or []),
                    "verification_plan_available": bool(plan.get("available")),
                    "verification_scope": plan.get("scope"),
                    **timings,
                }
            )
    finally:
        shutil.rmtree(base, ignore_errors=True)

    baseline_correct = sum(bool(row["baseline_correct"]) for row in rows)
    selected_correct = sum(bool(row["selected_correct"]) for row in rows)
    output: dict[str, object] = {
        "schema": SCHEMA,
        "sizes": list(sizes),
        "tasks": len(rows),
        "baseline_correct": baseline_correct,
        "baseline_correct_rate": baseline_correct / len(rows) if rows else 0.0,
        "selected_correct": selected_correct,
        "selected_correct_rate": selected_correct / len(rows) if rows else 0.0,
        "unsafe_regressions": sum(
            bool(row["baseline_correct"]) and not bool(row["selected_correct"])
            for row in rows
        ),
        "selection_changes": sum(bool(row["selection_changed"]) for row in rows),
        "mean_action_ms": sum(float(row["action_ms"]) for row in rows) / len(rows)
        if rows
        else 0.0,
        "max_action_ms": max((float(row["action_ms"]) for row in rows), default=0.0),
        "max_candidate_count": max(
            (int(row["candidate_count"]) for row in rows), default=0
        ),
        "rows": rows,
        "authority": "PUBLIC task plus deterministic repository evidence; expected paths used only by scorer",
        "secret_knowledge_used_by_selector": False,
    }
    output["result_identity"] = f"sha256:{_sha256_json(output)}"
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    args = parser.parse_args()
    result = collect()
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")  # noqa: T201 - intentional command output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
