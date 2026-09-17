from __future__ import annotations

import argparse
import hashlib

try:
    from scripts._module_loader import import_sibling
except ModuleNotFoundError:  # direct script execution
    from _module_loader import import_sibling
import json
from collections import Counter
from pathlib import Path
from typing import Any

EVIDENCE_SCHEMA = "hashmarks.agent-retrieval-evidence.v1"
REPORT_SCHEMA = "hashmarks.agent-retrieval-regret-report.v2"
DISCOVERY_KINDS = {
    "file_read",
    "hashmarks_source",
    "hashmarks_context",
    "hashmarks_find",
    "repository_search",
    "grep",
}
READ_KINDS = {"file_read", "hashmarks_source"}
SEARCH_KINDS = {
    "grep",
    "glob",
    "repository_search",
    "hashmarks_find",
    "hashmarks_grep",
    "hashmarks_context",
}


def _load_trace_module() -> Any:
    return import_sibling("metrics_agent_trace", __package__)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return "sha256:" + digest


def _nonempty(value: Any, field: str, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string: {path}")
    return value


def _relative_path(value: str, field: str, path: Path) -> str:
    normalized = value.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized or normalized.startswith("/") or ".." in Path(normalized).parts:
        raise ValueError(f"{field} must be repository-relative: {path}")
    return normalized


def load_evidence(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != EVIDENCE_SCHEMA:
        raise ValueError(f"unsupported retrieval evidence schema: {path}")
    for field in (
        "task_id",
        "task_revision",
        "repository_identity",
        "evidence_authority_identity",
    ):
        _nonempty(value.get(field), field, path)
    required = value.get("required_paths")
    if not isinstance(required, list) or not required:
        raise ValueError(f"required_paths must be a non-empty list: {path}")
    normalized: list[str] = []
    for item in required:
        text = _relative_path(
            _nonempty(item, "required_path", path), "required_path", path
        )
        normalized.append(text)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"required_paths contains duplicates: {path}")
    value["required_paths"] = normalized
    return value


def _event_paths(event: dict[str, Any]) -> list[str]:
    values: list[str] = []
    if isinstance(event.get("path"), str):
        values.append(event["path"])
    for field in ("paths", "returned_paths", "evidence_paths"):
        raw = event.get(field)
        if isinstance(raw, list):
            values.extend(x for x in raw if isinstance(x, str))
    normalized: list[str] = []
    for value in values:
        text = value.replace("\\", "/")
        while text.startswith("./"):
            text = text[2:]
        if text and not text.startswith("/") and ".." not in Path(text).parts:
            normalized.append(text)
    return normalized


def _event_tokens(event: dict[str, Any]) -> int:
    return int(event.get("estimated_tokens", 0))


def analyze(trace_path: Path, evidence_path: Path) -> dict[str, Any]:
    trace_module = _load_trace_module()
    trace = trace_module.load_trace(trace_path)
    evidence = load_evidence(evidence_path)
    for field in ("task_id", "task_revision", "repository_identity"):
        if trace.get(field) != evidence[field]:
            raise ValueError(
                f"trace/evidence {field} mismatch: expected {evidence[field]!r}, got {trace.get(field)!r}"
            )

    required = set(evidence["required_paths"])
    discovered: set[str] = set()
    first_index: int | None = None
    first_tokens: int | None = None
    all_index: int | None = None
    all_tokens: int | None = None
    cumulative_tokens = 0
    navigation_start_ns: int | None = None
    navigation_finish_ns: int | None = None
    first_evidence_started_ns: int | None = None
    all_evidence_started_ns: int | None = None
    searches_before = 0
    reads_before = 0
    searches_before_all = 0
    reads_before_all = 0
    read_counter: Counter[str] = Counter()
    query_counter: Counter[str] = Counter()
    irrelevant_read_tokens = 0
    irrelevant_reads = 0
    duplicate_query_tokens = 0
    duplicate_read_tokens = 0
    required_discovery_order: list[dict[str, Any]] = []
    repeated_queries: list[dict[str, Any]] = []
    repeated_reads: list[dict[str, Any]] = []

    for index, event in enumerate(trace["events"]):
        kind = event["kind"]
        tokens = _event_tokens(event)
        paths = _event_paths(event)
        started_at_ns = event.get("started_at_ns")
        finished_at_ns = event.get("finished_at_ns")
        if isinstance(started_at_ns, int) and navigation_start_ns is None:
            navigation_start_ns = started_at_ns
        if isinstance(finished_at_ns, int):
            navigation_finish_ns = max(
                navigation_finish_ns or finished_at_ns, finished_at_ns
            )
        if kind in SEARCH_KINDS:
            query = event.get("query")
            if isinstance(query, str) and query.strip():
                normalized_query = " ".join(query.lower().split())
                if query_counter[normalized_query] > 0:
                    duplicate_query_tokens += tokens
                    repeated_queries.append(
                        {
                            "query": normalized_query,
                            "event_index": index,
                            "estimated_tokens": tokens,
                        }
                    )
                query_counter[normalized_query] += 1
        if kind in READ_KINDS:
            for path in paths:
                if read_counter[path] > 0:
                    duplicate_read_tokens += tokens
                    repeated_reads.append(
                        {"path": path, "event_index": index, "estimated_tokens": tokens}
                    )
                read_counter[path] += 1
            if not any(path in required for path in paths):
                irrelevant_reads += 1
                irrelevant_read_tokens += tokens

        new_required = (
            sorted((set(paths) & required) - discovered)
            if kind in DISCOVERY_KINDS
            else []
        )
        if new_required:
            if first_index is None:
                first_index = index
                first_tokens = cumulative_tokens
                if isinstance(started_at_ns, int):
                    first_evidence_started_ns = started_at_ns
            for path in new_required:
                required_discovery_order.append(
                    {
                        "path": path,
                        "event_index": index,
                        "tokens_before_discovery": cumulative_tokens,
                    }
                )
            discovered.update(new_required)
            if discovered == required and all_index is None:
                all_index = index
                all_tokens = cumulative_tokens
                if isinstance(started_at_ns, int):
                    all_evidence_started_ns = started_at_ns

        if first_index is None:
            if kind in SEARCH_KINDS:
                searches_before += 1
            if kind in READ_KINDS:
                reads_before += 1
        if all_index is None:
            if kind in SEARCH_KINDS:
                searches_before_all += 1
            if kind in READ_KINDS:
                reads_before_all += 1
        cumulative_tokens += tokens

    duplicate_reads = sum(max(0, count - 1) for count in read_counter.values())
    duplicate_queries = sum(max(0, count - 1) for count in query_counter.values())
    missing = sorted(required - discovered)
    complete = not missing
    return {
        "schema": REPORT_SCHEMA,
        "trace_sha256": _sha256(trace_path),
        "evidence_sha256": _sha256(evidence_path),
        "task_id": evidence["task_id"],
        "task_revision": evidence["task_revision"],
        "repository_identity": evidence["repository_identity"],
        "mode": trace["mode"],
        "run_id": trace.get("run_id"),
        "evidence_authority_identity": evidence["evidence_authority_identity"],
        "summary": {
            "required_path_count": len(required),
            "required_paths_discovered": len(discovered),
            "required_evidence_complete": complete,
            "missing_required_paths": missing,
            "tokens_before_first_required_evidence": first_tokens,
            "events_before_first_required_evidence": first_index,
            "searches_before_first_required_evidence": searches_before
            if first_index is not None
            else None,
            "reads_before_first_required_evidence": reads_before
            if first_index is not None
            else None,
            "tokens_before_all_required_evidence": all_tokens,
            "events_before_all_required_evidence": all_index,
            "searches_before_all_required_evidence": searches_before_all
            if all_index is not None
            else None,
            "reads_before_all_required_evidence": reads_before_all
            if all_index is not None
            else None,
            "duplicate_queries": duplicate_queries,
            "duplicate_query_estimated_tokens": duplicate_query_tokens,
            "duplicate_reads": duplicate_reads,
            "duplicate_read_estimated_tokens": duplicate_read_tokens,
            "irrelevant_reads": irrelevant_reads,
            "irrelevant_read_estimated_tokens": irrelevant_read_tokens,
            "total_estimated_exploration_tokens": cumulative_tokens,
            "navigation_ms_before_first_required_evidence": (
                None
                if navigation_start_ns is None or first_evidence_started_ns is None
                else (first_evidence_started_ns - navigation_start_ns) / 1_000_000.0
            ),
            "navigation_ms_before_all_required_evidence": (
                None
                if navigation_start_ns is None or all_evidence_started_ns is None
                else (all_evidence_started_ns - navigation_start_ns) / 1_000_000.0
            ),
            "total_navigation_ms": (
                None
                if navigation_start_ns is None or navigation_finish_ns is None
                else (navigation_finish_ns - navigation_start_ns) / 1_000_000.0
            ),
        },
        "required_discovery_order": required_discovery_order,
        "observed_opportunities": {
            "repeated_queries": repeated_queries,
            "repeated_reads": repeated_reads,
            "note": "opportunity categories can overlap and must not be summed into a token-saving claim",
        },
    }


def compare(baseline: dict[str, Any], hashmarks: dict[str, Any]) -> dict[str, Any]:
    for field in ("task_id", "task_revision", "repository_identity", "evidence_sha256"):
        if baseline.get(field) != hashmarks.get(field):
            raise ValueError(f"regret comparison {field} mismatch")
    b = baseline["summary"]
    h = hashmarks["summary"]
    if not b["required_evidence_complete"] or not h["required_evidence_complete"]:
        raise ValueError(
            "regret comparison requires complete required evidence in both modes"
        )
    metric_keys = (
        "tokens_before_first_required_evidence",
        "searches_before_first_required_evidence",
        "reads_before_first_required_evidence",
        "tokens_before_all_required_evidence",
        "searches_before_all_required_evidence",
        "reads_before_all_required_evidence",
        "duplicate_queries",
        "duplicate_query_estimated_tokens",
        "duplicate_reads",
        "duplicate_read_estimated_tokens",
        "irrelevant_reads",
        "irrelevant_read_estimated_tokens",
    )
    reductions = {key + "_reduction": int(b[key]) - int(h[key]) for key in metric_keys}
    return {
        "schema": "hashmarks.agent-retrieval-regret-comparison.v2",
        "task_id": baseline["task_id"],
        "baseline": baseline,
        "hashmarks": hashmarks,
        "reductions": reductions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure agent retrieval regret against independently defined required evidence"
    )
    parser.add_argument("trace", type=Path)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = analyze(args.trace, args.evidence)
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)  # noqa: T201 - intentional command output


if __name__ == "__main__":
    main()
