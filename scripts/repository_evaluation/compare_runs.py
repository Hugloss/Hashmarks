from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.repository_evaluation.common import (
    COMPARISON_SCHEMA,
    RUN_SCHEMA,
    load_json,
    write_json,
)


def _by_id(run: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    rows: dict[str, Mapping[str, object]] = {}
    cases = run.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("comparison cases must be a list")
    for row in cases:
        if not isinstance(row, Mapping):
            continue
        case_id = str(row.get("id") or "")
        if case_id:
            rows[case_id] = row
    return rows


def _semantic_projection(row: Mapping[str, object]) -> dict[str, object]:
    result = row.get("result")
    action = result.get("action") if isinstance(result, Mapping) else None
    if not isinstance(action, Mapping):
        return {}
    raw_edit = action.get("edit")
    edit = raw_edit if isinstance(raw_edit, Mapping) else {}
    raw_verify = action.get("verify")
    verify = raw_verify if isinstance(raw_verify, Mapping) else {}
    raw_ambiguity = action.get("ambiguity")
    ambiguity = raw_ambiguity if isinstance(raw_ambiguity, Mapping) else {}
    authority = action.get("ownership_authority")
    authority = authority if isinstance(authority, Mapping) else {}
    return {
        "edit_path": edit.get("path"),
        "edit_qualname": edit.get("qualname"),
        "verify_path": verify.get("path"),
        "ambiguous": bool(ambiguity.get("ambiguous")),
        "ambiguity_reason": ambiguity.get("reason"),
        "safe_to_edit": bool(authority.get("safe_to_edit")),
    }


def compare_runs(
    *,
    baseline: Mapping[str, object],
    candidate: Mapping[str, object],
) -> dict[str, Any]:
    left = _by_id(baseline)
    right = _by_id(candidate)
    ids = sorted(set(left) | set(right))
    rows = []
    for case_id in ids:
        before = _semantic_projection(left.get(case_id, {}))
        after = _semantic_projection(right.get(case_id, {}))
        rows.append(
            {
                "id": case_id,
                "baseline": before,
                "candidate": after,
                "semantic_changed": before != after,
            }
        )
    clean_timing = bool(
        baseline.get("timing_comparable") and candidate.get("timing_comparable")
    )
    return {
        "schema": COMPARISON_SCHEMA,
        "baseline_protocol_identity": baseline.get("protocol_identity"),
        "candidate_protocol_identity": candidate.get("protocol_identity"),
        "baseline_producer_implementation_identity": baseline.get(
            "producer_implementation_identity"
        ),
        "candidate_producer_implementation_identity": candidate.get(
            "producer_implementation_identity"
        ),
        "case_set_equal": set(left) == set(right),
        "timing_comparable": clean_timing,
        "timing_note": (
            "both runs are clean/no-reuse"
            if clean_timing
            else "timing suppressed because at least one run reused receipts"
        ),
        "cases": rows,
        "authority": "comparison-only",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    baseline = load_json(args.baseline, schema=RUN_SCHEMA)
    candidate = load_json(args.candidate, schema=RUN_SCHEMA)
    write_json(args.output, compare_runs(baseline=baseline, candidate=candidate))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
