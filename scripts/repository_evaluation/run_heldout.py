"""Run the pinned multi-repository observer corpus against extracted source trees."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hashmarks.test_shards import repository_content_identity
from scripts.repository_evaluation.common import (
    CASES_SCHEMA,
    GRADER_SCHEMA,
    load_json,
    write_json,
)
from scripts.repository_evaluation.grade_cases import grade_run
from scripts.repository_evaluation.run_cases import run_cases

SUITE_SCHEMA = "hashmarks.repository-evaluation-heldout.v1"
REPORT_SCHEMA = "hashmarks.repository-evaluation-heldout-report.v1"
SUITE_PATH = (
    Path(__file__).resolve().parents[2]
    / "benchmarks/repository_evaluation/manifests/heldout-v1/suite.json"
)
PASS_CLASSES = {"PASS", "AMBIGUOUS_EXPECTED"}


def _sources(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        name, separator, path = value.partition("=")
        if not separator or not name or not path or name in result:
            raise ValueError("--source requires unique REPOSITORY=EXTRACTED_DIRECTORY")
        result[name] = Path(path).resolve()
    return result


def _check_source_labels(
    source: Path, cases: dict[str, Any], grader: dict[str, Any]
) -> None:
    for case in cases["cases"]:
        case_id = str(case["id"])
        rule = grader["cases"][case_id]
        symbol = str(rule["source_symbol"])
        paths = rule["source_declaration_paths"]
        if not isinstance(paths, list) or not paths:
            raise ValueError(f"{case_id}: missing source declaration paths")
        if bool(rule.get("must_be_ambiguous")) and len(paths) < 2:
            raise ValueError(f"{case_id}: ambiguity needs distinct declaration paths")
        for relative in paths:
            path = source / str(relative)
            if not path.is_file() or not re.search(
                rf"\b(?:def|function)\s+{re.escape(symbol)}\b",
                path.read_text(encoding="utf-8"),
            ):
                raise ValueError(f"{case_id}: source declaration missing at {relative}")
        verifier = rule.get("expected_verify_path")
        if verifier and not (source / str(verifier)).is_file():
            raise ValueError(f"{case_id}: expected verifier missing at {verifier}")


def _run_repository(
    name: str, definition: dict[str, Any], source: Path, output_dir: Path
) -> tuple[dict[str, Any], list[dict[str, str]], list[dict[str, str]]]:
    actual_identity = repository_content_identity(source)
    if actual_identity != definition["content_identity"]:
        raise ValueError(
            f"{name}: source identity mismatch; expected "
            f"{definition['content_identity']}, got {actual_identity}"
        )
    manifest_dir = SUITE_PATH.parent
    cases_path = manifest_dir / definition["cases_file"]
    cases = load_json(cases_path, schema=CASES_SCHEMA)
    grader = load_json(manifest_dir / definition["grader_file"], schema=GRADER_SCHEMA)
    if set(grader["cases"]) != {case["id"] for case in cases["cases"]}:
        raise ValueError(f"{name}: case and grader membership differs")
    _check_source_labels(source, cases, grader)
    run = run_cases(
        workspace=source,
        cases_path=cases_path,
        receipts_dir=output_dir / name / "receipts",
    )
    report = grade_run(run=run, grader=grader)
    write_json(output_dir / name / "run.json", run)
    write_json(output_dir / name / "report.json", report)
    if not report["complete"] or len(report["cases"]) != len(cases["cases"]):
        raise ValueError(f"{name}: incomplete graded case membership")
    failures, shadows = _classify_report(report, grader)
    metadata = {
        "language": definition["language"],
        "source_identity": actual_identity,
        "case_count": len(report["cases"]),
        "counters": report["counters"],
    }
    return metadata, failures, shadows


def _classify_report(
    report: dict[str, Any], grader: dict[str, Any]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    failures: list[dict[str, str]] = []
    shadows: list[dict[str, str]] = []
    for row in report["cases"]:
        case_id = row["id"]
        classification = str(row["classification"])
        state = grader["cases"][case_id]["qualification_state"]
        outcome = {"id": case_id, "classification": classification}
        if state == "shadow":
            shadows.append(outcome)
        elif state == "qualification":
            if classification not in PASS_CLASSES:
                failures.append(outcome)
        else:
            raise ValueError(f"{case_id}: invalid qualification state {state}")
    return failures, shadows


def run_heldout(*, sources: dict[str, Path], output_dir: Path) -> dict[str, Any]:
    suite = load_json(SUITE_PATH, schema=SUITE_SCHEMA)
    repositories = suite["repositories"]
    if set(sources) != set(repositories):
        raise ValueError(
            "exactly these source trees are required: "
            + ", ".join(sorted(repositories))
        )
    reports: dict[str, Any] = {}
    qualification_failures: list[dict[str, str]] = []
    shadow_outcomes: list[dict[str, str]] = []
    language_counts: Counter[str] = Counter()
    for name, definition in repositories.items():
        metadata, failures, shadows = _run_repository(
            name, definition, sources[name], output_dir
        )
        reports[name] = metadata
        qualification_failures.extend(failures)
        shadow_outcomes.extend(shadows)
        language_counts[str(metadata["language"])] += int(metadata["case_count"])

    summary = {
        "schema": REPORT_SCHEMA,
        "suite": suite["suite"],
        "complete": language_counts == {"python": 12, "typescript": 12}
        and not shadow_outcomes,
        "qualification_case_count": sum(language_counts.values())
        - len(shadow_outcomes),
        "qualification_passed": not qualification_failures,
        "language_counts": dict(sorted(language_counts.items())),
        "repositories": reports,
        "qualification_failures": qualification_failures,
        "shadow_outcomes": shadow_outcomes,
        "authority": "repository-intelligence-measurement-only",
    }
    write_json(output_dir / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", action="append", required=True, default=[])
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    summary = run_heldout(
        sources=_sources(args.source), output_dir=args.output_dir.resolve()
    )
    return 0 if summary["complete"] and summary["qualification_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
