"""Export frozen trials and summarize externally graded evidence-format studies.

Model execution, host serialization capture and grading belong to the external
harness. Byte counts alone do not establish comprehension or agent benefit.
"""

from __future__ import annotations

import argparse
import hashlib
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
_TRIAL_FIELDS = (
    "case_id",
    "variant",
    "prompt",
    "tool_response",
    "study_axis",
    "source_schema",
)
_MAX_VISIBLE_CAPTURE_BYTES = 1_048_576


def trial_identity(trial: dict[str, Any]) -> str:
    """Digest the frozen study trial, not a repository or verifier authority."""
    raw = json.dumps(
        {name: trial[name] for name in _TRIAL_FIELDS},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


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
            trial = {
                "case_id": case_id,
                "variant": variant,
                "prompt": prompt,
                "tool_response": response,
                "study_axis": axis,
                "source_schema": packet["schema"],
            }
            trial["trial_identity"] = trial_identity(trial)
            records.append(trial)
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
        if "trial_identity" in trial and trial["trial_identity"] != trial_identity(
            trial
        ):
            raise ValueError("trial identity mismatch")
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


def _capture_equivalent(trial: dict[str, Any], visible: str) -> bool:
    """Content comparison, never proof of what the external model actually saw."""
    if trial["study_axis"] == "encoding-only":
        return visible == trial["tool_response"]
    try:
        parsed = json.loads(visible)
    except (ValueError, TypeError):
        return False
    return parsed == trial["tool_response"]


def _validate_host_capture(
    capture: object,
    trial_by_key: dict[tuple[str, str], dict[str, Any]],
    models: list[str],
) -> tuple[tuple[str, str, str], dict[str, Any], str]:
    if not isinstance(capture, dict):
        raise ValueError("each host capture must be an object")
    case, model, variant = (
        capture.get("case_id"),
        capture.get("model"),
        capture.get("variant"),
    )
    if not all(isinstance(v, str) and v for v in (case, model, variant)):
        raise ValueError("host captures require case_id, model and variant")
    if model not in models or (case, variant) not in trial_by_key:
        raise ValueError("unexpected host capture")
    trial = trial_by_key[case, variant]
    if not isinstance(capture.get("trial_identity"), str) or capture[
        "trial_identity"
    ] != trial_identity(trial):
        raise ValueError("host capture trial identity mismatch")
    visible = capture.get("model_visible_response")
    if not isinstance(visible, str):
        raise ValueError("model_visible_response must be a string")
    if len(visible.encode("utf-8")) > _MAX_VISIBLE_CAPTURE_BYTES:
        raise ValueError("model_visible_response exceeds capture byte limit")
    return (case, model, variant), trial, visible


def _capture_audit(
    captures: list[dict[str, Any]],
    *,
    trials: list[dict[str, Any]],
    models: list[str],
) -> tuple[dict[str, object], set[tuple[str, str, str]]]:
    """Bind caller-supplied host captures to frozen trials; no host authentication."""
    trial_by_key = {(row["case_id"], row["variant"]): row for row in trials}
    observations: dict[tuple[str, str, str], bool] = {}
    mismatches: list[dict[str, str]] = []
    capture_digests: list[dict[str, object]] = []
    for capture in captures:
        key, trial, visible = _validate_host_capture(capture, trial_by_key, models)
        if key in observations:
            raise ValueError("duplicate host capture")
        equivalent = _capture_equivalent(trial, visible)
        observations[key] = equivalent
        capture_digests.append(
            {
                "case_id": key[0],
                "model": key[1],
                "variant": key[2],
                "model_visible_sha256": "sha256:"
                + hashlib.sha256(visible.encode("utf-8")).hexdigest(),
                "content_equivalent": equivalent,
            }
        )
        if not equivalent:
            mismatches.append({"case_id": key[0], "model": key[1], "variant": key[2]})
    verified = {key for key, valid in observations.items() if valid}
    return (
        {
            "authority": "consumer-supplied-capture-content-only",
            "host_authenticity_proven": False,
            "expected_captures": len(trials) * len(models),
            "observed_captures": len(observations),
            "content_equivalent_captures": len(verified),
            "capture_digests": capture_digests,
            "content_mismatches": mismatches,
            "missing_captures": [
                {"case_id": row["case_id"], "model": model, "variant": row["variant"]}
                for row in trials
                for model in models
                if (row["case_id"], model, row["variant"]) not in observations
            ],
        },
        verified,
    )


def _capture_subset(
    captures: list[dict[str, Any]] | None,
    trials: list[dict[str, Any]],
    models: list[str],
    pairs: dict[tuple[str, str], dict[str, dict[str, Any]]],
    expected: dict[str, set[str]],
    complete_keys: list[tuple[str, str]],
) -> dict[str, object]:
    if captures is None:
        return {
            "capture_audit": None,
            "capture_equivalent_complete_pairs": None,
            "capture_equivalent_arms": None,
            "capture_unqualified_complete_pairs": None,
        }
    report, equivalent = _capture_audit(captures, trials=trials, models=models)
    captured_pairs: list[dict[str, dict[str, Any]]] = []
    unqualified: list[dict[str, str]] = []
    for case, model in complete_keys:
        if all((case, model, variant) in equivalent for variant in expected[case]):
            captured_pairs.append(pairs[case, model])
        else:
            unqualified.append({"case_id": case, "model": model})
    variants = [
        row["variant"] for row in trials if row["case_id"] == next(iter(expected))
    ]
    return {
        "capture_audit": report,
        "capture_equivalent_complete_pairs": len(captured_pairs),
        "capture_equivalent_arms": [
            _arm(variant, captured_pairs) for variant in variants
        ],
        "capture_unqualified_complete_pairs": unqualified,
    }


def summarize_grades(
    grades: list[dict[str, Any]],
    *,
    trials: list[dict[str, Any]],
    models: list[str],
    captures: list[dict[str, Any]] | None = None,
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
    complete, complete_keys, excluded = [], [], []
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
                complete_keys.append((case, model))
    variants = [
        row["variant"] for row in trials if row["case_id"] == next(iter(expected))
    ]
    capture_fields = _capture_subset(
        captures, trials, models, pairs, expected, complete_keys
    )
    return {
        "schema": "hashmarks.agent-evidence-format-study.v1",
        "study_axis": trials[0]["study_axis"],
        "expected_pairs": len(expected) * len(models),
        "complete_pairs": len(complete),
        "incomplete_pairs_excluded": len(excluded),
        "excluded_pairs": excluded,
        "arms": [_arm(variant, complete) for variant in variants],
        **capture_fields,
        "ranking_authority": "external-consumer",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("emit", "summarize"))
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--axis", choices=AXES, default="production-response")
    parser.add_argument("--trials", type=Path)
    parser.add_argument("--captures", type=Path)
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
        captures = (
            json.loads(args.captures.read_text(encoding="utf-8"))
            if args.captures is not None
            else None
        )
        if captures is not None and not isinstance(captures, list):
            raise ValueError("--captures must contain a JSON array")
        serialized = (
            json.dumps(
                summarize_grades(
                    value, trials=trials, models=args.model, captures=captures
                ),
                sort_keys=True,
                indent=2,
            )
            + "\n"
        )
    args.output.write_text(serialized, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
