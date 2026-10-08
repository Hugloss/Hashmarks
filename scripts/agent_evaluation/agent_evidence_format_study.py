"""Export paired evidence-format arms and summarize *externally graded* agent runs.

This script never runs an agent, exposes grading oracles in tool payloads, or
claims that byte savings imply improved answer quality. The external harness
owns model execution and grading.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from hashmarks.evidence_presentation import present_repository_evidence

_VARIANTS = ("native-json", "typed-json", "compact-json", "grouped-text")


def emit_trials(manifest: dict[str, Any]) -> list[dict[str, object]]:
    """Keep the same task and source packet fixed across all four arms."""
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 1000:
        raise ValueError("cases must be a nonempty bounded list")
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("each case must be an object")
        case_id, prompt, packet = case.get("id"), case.get("prompt"), case.get("packet")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            raise ValueError("case ids must be unique and nonblank")
        if not isinstance(prompt, str) or not prompt:
            raise ValueError("every case must have a nonblank prompt")
        if not isinstance(packet, dict) or not isinstance(packet.get("schema"), str):
            raise ValueError("each case requires a schema-bearing packet")
        seen.add(case_id)
        rendered = {
            mode: present_repository_evidence(packet, format=mode)
            for mode in ("structured", "compact", "text")
        }
        evidence = {
            "native-json": packet,
            "typed-json": rendered["structured"],
            "compact-json": rendered["compact"],
            "grouped-text": rendered["text"]["text"],
        }
        for variant in _VARIANTS:
            rows.append({
                "case_id": case_id,
                "variant": variant,
                "prompt": prompt,
                "tool_response": evidence[variant],
                "study_axis": "presentation-and-information-density",
                "source_schema": packet["schema"],
            })
    return rows


def summarize_grades(grades: list[dict[str, Any]]) -> dict[str, object]:
    """Summarize only complete paired runs; grading is provided by the harness."""
    pairs: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for grade in grades:
        case_id, model, variant = (
            grade.get("case_id"), grade.get("model"), grade.get("variant")
        )
        if not all(isinstance(x, str) and x for x in (case_id, model, variant)):
            raise ValueError("grades require case_id, model and variant")
        if variant not in _VARIANTS:
            raise ValueError("unknown trial variant")
        key = (case_id, model)
        if variant in pairs[key]:
            raise ValueError("duplicate grade for model, case and variant")
        pairs[key][variant] = grade
    complete = [rows for rows in pairs.values() if set(rows) == set(_VARIANTS)]
    incomplete = len(pairs) - len(complete)
    results: list[dict[str, object]] = []
    for variant in _VARIANTS:
        arm = [rows[variant] for rows in complete]
        if any(
            not isinstance(row.get("correct"), bool)
            or not isinstance(row.get("unsupported_claims"), int)
            or not isinstance(row.get("tokens"), int)
            or row["unsupported_claims"] < 0
            or row["tokens"] < 0
            for row in arm
        ):
            raise ValueError("paired grades require boolean correct and nonnegative integer metrics")
        results.append({
            "variant": variant,
            "paired_runs": len(arm),
            "correct": sum(bool(row["correct"]) for row in arm),
            "unsupported_claims": sum(row["unsupported_claims"] for row in arm),
            "total_tokens": sum(row["tokens"] for row in arm),
        })
    return {
        "schema": "hashmarks.agent-evidence-format-study.v1",
        "complete_pairs": len(complete),
        "incomplete_pairs_excluded": incomplete,
        "arms": results,
        "ranking_authority": "external-consumer",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("emit", "summarize"))
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    value = json.loads(args.input.read_text(encoding="utf-8"))
    if args.operation == "emit":
        records = emit_trials(value)
        serialized = "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in records
        )
    else:
        if not isinstance(value, list):
            raise ValueError("grades must be an array")
        serialized = json.dumps(
            summarize_grades(value), sort_keys=True, indent=2
        ) + "\n"
    args.output.write_text(serialized, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
