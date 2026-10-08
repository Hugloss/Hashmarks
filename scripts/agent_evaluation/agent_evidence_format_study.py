"""Export frozen trials and summarize externally graded evidence-format studies.

Model execution, host serialization capture and grading belong to the external
harness. Byte counts alone do not establish comprehension or agent benefit.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

from hashmarks.evidence_presentation import (
    evidence_projection_text,
    present_repository_evidence,
    presentation_response,
)
from hashmarks.operation_contract import operation_schema, validate_operation_response

AXES = ("production-response", "encoding-only")
_PRODUCTION_VARIANTS = ("native-json", "typed-json", "compact-json", "grouped-text")
_ENCODING_VARIANTS = ("typed-json", "compact-json", "grouped-text")


def _case(case: object, seen: set[str]) -> tuple[str, str, dict[str, Any]]:
    if not isinstance(case, dict):
        raise ValueError("each case must be an object")
    case_id, prompt, packet = case.get("id"), case.get("prompt"), case.get("packet")
    if not isinstance(case_id, str) or not case_id.strip() or case_id in seen:
        raise ValueError("case ids must be unique and nonblank")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("every case must have a nonblank prompt")
    if not isinstance(packet, dict) or not isinstance(packet.get("schema"), str):
        raise ValueError("each case requires a schema-bearing packet")
    seen.add(case_id)
    return case_id, prompt, packet


def _production_arms(case: dict[str, Any], packet: dict[str, Any]) -> dict[str, object]:
    operation, mode = case.get("operation"), case.get("result_mode")
    if not isinstance(operation, str) or not isinstance(mode, str):
        raise ValueError("production-response requires operation and result_mode")
    validate_operation_response(operation, packet, mode=mode)
    if operation == "repository_intelligence_query":
        from hashmarks.codemap.repository_intelligence_query import (
            repository_query_response,
        )

        packet = repository_query_response(packet["surface"], packet["result"])
    return {
        variant: presentation_response(
            operation, deepcopy(packet), format=format, result_mode=mode
        )
        for variant, format in zip(
            _PRODUCTION_VARIANTS, ("none", "structured", "compact", "text"), strict=True
        )
    }


def _encoding_arms(packet: dict[str, Any]) -> dict[str, object]:
    source = (
        packet["result"]
        if packet.get("schema") == operation_schema("repository_intelligence_query")
        else packet
    )
    # One compact selection supplies identical records and qualifications to all encodings.
    projection = present_repository_evidence(source, format="text")
    if not projection["supported"]:
        raise ValueError("encoding-only requires a supported evidence schema")
    projection.pop("text")
    projection["format"] = "compact"
    return {
        "typed-json": json.dumps(
            projection, sort_keys=True, ensure_ascii=False, indent=2
        ),
        "compact-json": json.dumps(
            projection, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ),
        "grouped-text": evidence_projection_text(projection),
    }


def emit_trials(
    manifest: dict[str, Any], *, axis: str = "production-response"
) -> list[dict[str, object]]:
    """Freeze one producer response per case; formatting performs no observations."""
    if axis not in AXES:
        raise ValueError(f"axis must be one of {AXES}")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 1000:
        raise ValueError("cases must be a nonempty bounded list")
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for case in cases:
        case_id, prompt, packet = _case(case, seen)
        arms = (
            _production_arms(case, packet)
            if axis == "production-response"
            else _encoding_arms(packet)
        )
        for variant, response in arms.items():
            records.append(
                {
                    "case_id": case_id,
                    "variant": variant,
                    "prompt": prompt,
                    "tool_response": response,
                    "study_axis": axis,
                    "source_schema": packet["schema"],
                }
            )
    return records


def _trial_key(trial: object) -> tuple[str, str, str]:
    if not isinstance(trial, dict):
        raise ValueError("malformed trial manifest")
    case, variant, axis = (
        trial.get("case_id"),
        trial.get("variant"),
        trial.get("study_axis"),
    )
    if (
        not isinstance(case, str)
        or not case
        or not isinstance(axis, str)
        or axis not in AXES
    ):
        raise ValueError("malformed trial manifest")
    variants = (
        _PRODUCTION_VARIANTS if axis == "production-response" else _ENCODING_VARIANTS
    )
    if not isinstance(variant, str) or variant not in variants:
        raise ValueError("unknown trial variant")
    return case, variant, axis


def _expected_trials(
    trials: list[dict[str, Any]], models: list[str]
) -> dict[str, set[str]]:
    if (
        not trials
        or not models
        or any(not isinstance(m, str) or not m.strip() for m in models)
        or len(set(models)) != len(models)
    ):
        raise ValueError("nonempty trials and unique expected models are required")
    expected: dict[str, set[str]] = defaultdict(set)
    axes: set[str] = set()
    for trial in trials:
        case, variant, axis = _trial_key(trial)
        if variant in expected[case]:
            raise ValueError("duplicate expected trial")
        axes.add(axis)
        expected[case].add(variant)
    if len(axes) != 1:
        raise ValueError("summarize one study axis at a time")
    required = set(
        _PRODUCTION_VARIANTS if axes == {"production-response"} else _ENCODING_VARIANTS
    )
    if any(variants != required for variants in expected.values()):
        raise ValueError("trial manifest must contain every arm per case")
    return dict(expected)


def _validate_grade(grade: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(grade, dict):
        raise ValueError("each grade must be an object")
    if not all(
        isinstance(grade.get(key), str) and grade[key]
        for key in ("case_id", "model", "variant")
    ):
        raise ValueError("grades require case_id, model and variant")
    status = grade.get("status", "completed")
    if not isinstance(status, str) or status not in {
        "completed",
        "failure",
        "nonresponse",
    }:
        raise ValueError("unknown grade status")
    if status == "completed" and not isinstance(grade.get("correct"), bool):
        raise ValueError("completed grades require boolean correct")
    for key in ("unsupported_claims", "tokens"):
        value = grade.get(key)
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError("metrics must be nonnegative integers or unknown")
    return {
        **grade,
        "status": status,
        "correct": grade.get("correct") is True if status == "completed" else False,
    }


def _arm(variant: str, complete: list[dict[str, dict[str, Any]]]) -> dict[str, object]:
    rows = [pair[variant] for pair in complete]
    result: dict[str, object] = {
        "variant": variant,
        "paired_runs": len(rows),
        "correct": sum(row["correct"] for row in rows),
        "failures": sum(row["status"] == "failure" for row in rows),
        "nonresponses": sum(row["status"] == "nonresponse" for row in rows),
    }
    for key, label in (
        ("tokens", "total_tokens"),
        ("unsupported_claims", "unsupported_claims"),
    ):
        known = [row[key] for row in rows if row.get(key) is not None]
        result[label] = sum(known) if len(known) == len(rows) else None
        result[label + "_observed_sum"] = sum(known)
        result[label + "_unknown_runs"] = len(rows) - len(known)
    return result


def summarize_grades(
    grades: list[dict[str, Any]], *, trials: list[dict[str, Any]], models: list[str]
) -> dict[str, object]:
    """Account for every expected case/model, including completely missing runs."""
    expected = _expected_trials(trials, models)
    pairs: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for raw in grades:
        grade = _validate_grade(raw)
        case, model, variant = grade["case_id"], grade["model"], grade["variant"]
        if case not in expected or model not in models or variant not in expected[case]:
            raise ValueError("unexpected case, model or trial variant")
        if variant in pairs[case, model]:
            raise ValueError("duplicate grade for model, case and variant")
        pairs[case, model][variant] = grade
    complete, excluded = [], []
    for case, variants in expected.items():
        for model in models:
            pair = pairs[case, model]
            missing = sorted(variants - pair.keys())
            if missing:
                excluded.append(
                    {"case_id": case, "model": model, "missing_variants": missing}
                )
            else:
                complete.append(pair)
    variants = [
        row["variant"] for row in trials if row["case_id"] == next(iter(expected))
    ]
    return {
        "schema": "hashmarks.agent-evidence-format-study.v1",
        "study_axis": trials[0]["study_axis"],
        "expected_pairs": len(expected) * len(models),
        "complete_pairs": len(complete),
        "incomplete_pairs_excluded": len(excluded),
        "excluded_pairs": excluded,
        "arms": [_arm(variant, complete) for variant in variants],
        "ranking_authority": "external-consumer",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("emit", "summarize"))
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--axis", choices=AXES, default="production-response")
    parser.add_argument("--trials", type=Path)
    parser.add_argument("--model", action="append", default=[])
    args = parser.parse_args(argv)
    value = json.loads(args.input.read_text(encoding="utf-8"))
    if args.operation == "emit":
        serialized = "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in emit_trials(value, axis=args.axis)
        )
    else:
        if not isinstance(value, list) or args.trials is None:
            raise ValueError(
                "summarize requires grades array, --trials and expected --model values"
            )
        trials = [
            json.loads(line)
            for line in args.trials.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        serialized = (
            json.dumps(
                summarize_grades(value, trials=trials, models=args.model),
                sort_keys=True,
                indent=2,
            )
            + "\n"
        )
    args.output.write_text(serialized, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
