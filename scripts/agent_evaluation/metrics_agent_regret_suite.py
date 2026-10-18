from __future__ import annotations

import argparse
import hashlib
import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypedDict, TypeGuard

from hashmarks._command_output import log_command_output
from scripts._module_loader import import_sibling

if TYPE_CHECKING:
    from scripts.agent_evaluation.metrics_agent_regret import (
        RegretComparison,
        RegretReport,
    )
    from scripts.agent_evaluation.metrics_agent_regret import (
        analyze as analyze_trace,
    )
    from scripts.agent_evaluation.metrics_agent_regret import (
        compare as compare_reports,
    )
else:
    _regret = import_sibling("metrics_agent_regret", __package__)
    analyze_trace = _regret.analyze
    compare_reports = _regret.compare

logger = logging.getLogger(__name__)

MANIFEST_SCHEMA = "hashmarks.agent-retrieval-regret-suite.v1"
REPORT_SCHEMA = "hashmarks.agent-retrieval-regret-suite-report.v1"


class RegretManifest(TypedDict):
    schema: str
    suite_id: str
    entries: list[object]


class OpportunityTotal(TypedDict):
    kind: str
    observed_estimated_tokens: int


class RegretSuiteSummary(TypedDict):
    runs: int
    tasks: int
    paired_tasks: int
    complete_required_evidence_runs: int
    incomplete_required_evidence_runs: int
    observed_opportunity_totals: dict[str, int]
    observed_opportunities_ranked: list[OpportunityTotal]
    opportunities_overlap: bool
    claim_boundary: str


class RegretSuiteReport(TypedDict):
    schema: str
    manifest_sha256: str
    suite_id: str
    reports: list[RegretReport]
    comparisons: list[RegretComparison]
    summary: RegretSuiteSummary


OpportunityMetric = Literal[
    "tokens_before_all_required_evidence",
    "duplicate_query_estimated_tokens",
    "duplicate_read_estimated_tokens",
    "irrelevant_read_estimated_tokens",
]


def _digest_bytes(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _nonempty(value: object, field: str, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string: {path}")
    return value


def _resolve_member(base: Path, raw: object, field: str, manifest_path: Path) -> Path:
    text = _nonempty(raw, field, manifest_path).replace("\\", "/")
    member = Path(text)
    if member.is_absolute() or ".." in member.parts:
        raise ValueError(
            f"{field} must stay inside the suite directory: {manifest_path}"
        )
    resolved = (base / member).resolve()
    try:
        resolved.relative_to(base.resolve())
    except ValueError as exc:
        raise ValueError(
            f"{field} escapes the suite directory: {manifest_path}"
        ) from exc
    return resolved


def _validate_manifest(value: object, path: Path) -> TypeGuard[RegretManifest]:
    if not isinstance(value, dict) or value.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"unsupported regret suite schema: {path}")
    _nonempty(value.get("suite_id"), "suite_id", path)
    entries = value.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"entries must be a non-empty list: {path}")
    return True


def load_manifest(path: Path) -> RegretManifest:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not _validate_manifest(value, path):
        raise ValueError(f"invalid regret suite: {path}")
    return value


def _entry_report(
    base: Path,
    entry: object,
    index: int,
    manifest_path: Path,
) -> RegretReport:
    if not isinstance(entry, dict):
        raise ValueError(f"entry {index} must be an object: {manifest_path}")
    trace_path = _resolve_member(
        base, entry.get("trace"), f"entries[{index}].trace", manifest_path
    )
    evidence_path = _resolve_member(
        base, entry.get("evidence"), f"entries[{index}].evidence", manifest_path
    )
    for member_path, field in (
        (trace_path, "trace_sha256"),
        (evidence_path, "evidence_sha256"),
    ):
        expected = _nonempty(
            entry.get(field), f"entries[{index}].{field}", manifest_path
        )
        actual = _digest_bytes(member_path)
        if expected != actual:
            raise ValueError(
                f"entry {index} {field} mismatch: expected {expected}, got {actual}"
            )
    return analyze_trace(trace_path, evidence_path)


def _comparisons(
    reports: list[RegretReport],
) -> tuple[dict[str, dict[str, RegretReport]], list[RegretComparison]]:
    by_task: dict[str, dict[str, RegretReport]] = defaultdict(dict)
    for report in reports:
        by_task[str(report["task_id"])][str(report["mode"])] = report
    comparisons = [
        compare_reports(modes["baseline"], modes["hashmarks"])
        for _task_id, modes in sorted(by_task.items())
        if set(modes) == {"baseline", "hashmarks"}
    ]
    return by_task, comparisons


def _opportunities(
    reports: list[RegretReport],
) -> tuple[list[RegretReport], dict[str, int], list[OpportunityTotal]]:
    complete = [
        report for report in reports if report["summary"]["required_evidence_complete"]
    ]
    opportunity_fields: dict[str, OpportunityMetric] = {
        "late_all_required_evidence": "tokens_before_all_required_evidence",
        "repeated_queries": "duplicate_query_estimated_tokens",
        "repeated_reads": "duplicate_read_estimated_tokens",
        "irrelevant_reads": "irrelevant_read_estimated_tokens",
    }
    totals = {
        name: sum(report["summary"][field] or 0 for report in complete)
        for name, field in opportunity_fields.items()
    }
    ranked: list[OpportunityTotal] = [
        {"kind": name, "observed_estimated_tokens": value}
        for name, value in sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    ]
    return complete, totals, ranked


def analyze(manifest_path: Path) -> RegretSuiteReport:
    manifest = load_manifest(manifest_path)
    base = manifest_path.parent.resolve()
    reports: list[RegretReport] = []
    seen: set[tuple[str, str]] = set()
    for index, entry in enumerate(manifest["entries"]):
        report = _entry_report(base, entry, index, manifest_path)
        key = (str(report["task_id"]), str(report["mode"]))
        if key in seen:
            raise ValueError(f"duplicate task/mode in regret suite: {key[0]}:{key[1]}")
        seen.add(key)
        reports.append(report)

    by_task, comparisons = _comparisons(reports)
    complete, totals, ranked = _opportunities(reports)
    return {
        "schema": REPORT_SCHEMA,
        "manifest_sha256": _digest_bytes(manifest_path),
        "suite_id": manifest["suite_id"],
        "reports": reports,
        "comparisons": comparisons,
        "summary": {
            "runs": len(reports),
            "tasks": len(by_task),
            "paired_tasks": len(comparisons),
            "complete_required_evidence_runs": len(complete),
            "incomplete_required_evidence_runs": len(reports) - len(complete),
            "observed_opportunity_totals": totals,
            "observed_opportunities_ranked": ranked,
            "opportunities_overlap": True,
            "claim_boundary": "observed opportunity totals overlap and are triage evidence only; they are not additive token savings or correctness authority",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate independently grounded retrieval-regret traces into an optimization triage report"
    )
    parser.add_argument("suite", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = analyze(args.suite)
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    log_command_output(logger, rendered)


if __name__ == "__main__":
    main()
