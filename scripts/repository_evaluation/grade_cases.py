from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.repository_evaluation.common import (
    GRADER_SCHEMA,
    REPORT_SCHEMA,
    RUN_SCHEMA,
    load_json,
    write_json,
)


def _classification(
    *,
    actual_path: str,
    ambiguous: bool,
    expected_path: str,
    expected_ambiguous: bool,
    wrong_resolved_classification: str,
) -> str:
    if expected_ambiguous:
        if not ambiguous:
            return "FALSE_UNIQUE"
        return "AMBIGUOUS_EXPECTED"
    if not actual_path:
        return "NO_ANSWER"
    if actual_path == expected_path:
        return "OVER_AMBIGUOUS" if ambiguous else "PASS"
    if ambiguous:
        return "WRONG_AMBIGUOUS"
    return wrong_resolved_classification


def grade_run(
    *, run: Mapping[str, object], grader: Mapping[str, object]
) -> dict[str, Any]:
    expected = grader.get("cases")
    if not isinstance(expected, Mapping):
        raise ValueError("repository evaluation grader cases must be an object")
    counters = {
        "PASS": 0,
        "FALSE_SAFE_EDIT": 0,
        "FALSE_UNIQUE": 0,
        "AMBIGUOUS_EXPECTED": 0,
        "OVER_AMBIGUOUS": 0,
        "WRONG_AMBIGUOUS": 0,
        "NO_ANSWER": 0,
        "OTHER_FAILURE": 0,
    }
    rows: list[dict[str, object]] = []
    seen: set[str] = set()

    for item in run.get("cases", []):
        if not isinstance(item, Mapping):
            raise ValueError("repository evaluation run case must be an object")
        case_id = str(item.get("id") or "")
        rule = expected.get(case_id)
        if not isinstance(rule, Mapping):
            raise ValueError(f"missing repository evaluation grader rule for {case_id}")
        result = item.get("result")
        action = result.get("action") if isinstance(result, Mapping) else None
        if not isinstance(action, Mapping):
            raise ValueError(f"missing task action result for {case_id}")
        edit = action.get("edit")
        ambiguity = action.get("ambiguity")
        edit = edit if isinstance(edit, Mapping) else {}
        ambiguity = ambiguity if isinstance(ambiguity, Mapping) else {}
        actual_path = str(edit.get("path") or "")
        actual_qualname = str(edit.get("qualname") or "")
        expected_path = str(rule.get("expected_edit_path") or "")
        expected_qualname = str(rule.get("expected_edit_qualname") or "")
        expected_ambiguous = bool(rule.get("must_be_ambiguous", False))
        ambiguous = bool(ambiguity.get("ambiguous"))
        wrong_classification = str(
            rule.get("classification_on_wrong_resolved_edit") or "FALSE_SAFE_EDIT"
        )
        classification = _classification(
            actual_path=actual_path,
            ambiguous=ambiguous,
            expected_path=expected_path,
            expected_ambiguous=expected_ambiguous,
            wrong_resolved_classification=wrong_classification,
        )
        if (
            classification == "PASS"
            and expected_qualname
            and actual_qualname != expected_qualname
        ):
            classification = "OTHER_FAILURE"
        counters.setdefault(classification, 0)
        counters[classification] += 1
        retrieval = result.get("retrieval") if isinstance(result, Mapping) else None
        retrieval_paths = {
            str(row.get("path") or "")
            for row in (retrieval or ())
            if isinstance(row, Mapping)
        }
        if classification in {"PASS", "AMBIGUOUS_EXPECTED", "OVER_AMBIGUOUS"}:
            failure_stage = "CORRECT"
        elif expected_path and expected_path not in retrieval_paths:
            failure_stage = "RETRIEVAL_MISS"
        elif classification in {"FALSE_UNIQUE", "WRONG_AMBIGUOUS", "NO_ANSWER"}:
            failure_stage = "AMBIGUITY_ERROR"
        else:
            failure_stage = "ACTION_PROJECTION_DISPLACEMENT"
        seen.add(case_id)
        rows.append(
            {
                "id": case_id,
                "classification": classification,
                "failure_stage": failure_stage,
                "actual_edit_path": actual_path,
                "actual_edit_qualname": actual_qualname,
                "actual_ambiguous": ambiguous,
                "expected_edit_path": expected_path,
                "expected_edit_qualname": expected_qualname,
                "expected_ambiguous": expected_ambiguous,
            }
        )

    missing = sorted(set(map(str, expected)) - seen)
    return {
        "schema": REPORT_SCHEMA,
        "suite": run.get("suite"),
        "protocol_identity": run.get("protocol_identity"),
        "repository_identity": run.get("repository_identity"),
        "producer_implementation_identity": run.get("producer_implementation_identity"),
        "producer_artifact_identity": run.get("producer_artifact_identity"),
        "timing_comparable": run.get("timing_comparable"),
        "counters": counters,
        "missing_cases": missing,
        "complete": not missing and counters.get("OTHER_FAILURE", 0) == 0,
        "cases": rows,
        "authority": "grader-only",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--grader", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run = load_json(args.run, schema=RUN_SCHEMA)
    grader = load_json(args.grader, schema=GRADER_SCHEMA)
    write_json(args.output, grade_run(run=run, grader=grader))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
