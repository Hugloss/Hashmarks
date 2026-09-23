from __future__ import annotations

import argparse
import hashlib
import logging

from hashmarks._command_output import log_command_output

try:
    from scripts._module_loader import import_sibling
except ModuleNotFoundError:  # direct script execution
    from _module_loader import import_sibling
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

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


@dataclass
class RegretObservations:
    required: set[str]
    discovered: set[str] = field(default_factory=set)
    first_index: int | None = None
    first_tokens: int | None = None
    all_index: int | None = None
    all_tokens: int | None = None
    cumulative_tokens: int = 0
    navigation_start_ns: int | None = None
    navigation_finish_ns: int | None = None
    first_evidence_started_ns: int | None = None
    all_evidence_started_ns: int | None = None
    searches_before: int = 0
    reads_before: int = 0
    searches_before_all: int = 0
    reads_before_all: int = 0
    read_counter: Counter[str] = field(default_factory=Counter)
    query_counter: Counter[str] = field(default_factory=Counter)
    irrelevant_read_tokens: int = 0
    irrelevant_reads: int = 0
    duplicate_query_tokens: int = 0
    duplicate_read_tokens: int = 0
    required_discovery_order: list[dict[str, Any]] = field(default_factory=list)
    repeated_queries: list[dict[str, Any]] = field(default_factory=list)
    repeated_reads: list[dict[str, Any]] = field(default_factory=list)

    def _observe_timing(self, event: dict[str, Any]) -> int | None:
        started = event.get("started_at_ns")
        finished = event.get("finished_at_ns")
        if isinstance(started, int) and self.navigation_start_ns is None:
            self.navigation_start_ns = started
        if isinstance(finished, int):
            self.navigation_finish_ns = max(
                self.navigation_finish_ns or finished, finished
            )
        return started if isinstance(started, int) else None

    def _observe_query(self, index: int, event: dict[str, Any], tokens: int) -> None:
        query = event.get("query")
        if not isinstance(query, str) or not query.strip():
            return
        normalized = " ".join(query.lower().split())
        if self.query_counter[normalized] > 0:
            self.duplicate_query_tokens += tokens
            self.repeated_queries.append(
                {
                    "query": normalized,
                    "event_index": index,
                    "estimated_tokens": tokens,
                }
            )
        self.query_counter[normalized] += 1

    def _observe_reads(self, index: int, paths: list[str], tokens: int) -> None:
        for path in paths:
            if self.read_counter[path] > 0:
                self.duplicate_read_tokens += tokens
                self.repeated_reads.append(
                    {"path": path, "event_index": index, "estimated_tokens": tokens}
                )
            self.read_counter[path] += 1
        if not any(path in self.required for path in paths):
            self.irrelevant_reads += 1
            self.irrelevant_read_tokens += tokens

    def _observe_discovery(
        self, index: int, paths: list[str], started_at_ns: int | None
    ) -> None:
        new_required = sorted((set(paths) & self.required) - self.discovered)
        if not new_required:
            return
        if self.first_index is None:
            self.first_index = index
            self.first_tokens = self.cumulative_tokens
            self.first_evidence_started_ns = started_at_ns
        self.required_discovery_order.extend(
            {
                "path": path,
                "event_index": index,
                "tokens_before_discovery": self.cumulative_tokens,
            }
            for path in new_required
        )
        self.discovered.update(new_required)
        if self.discovered == self.required and self.all_index is None:
            self.all_index = index
            self.all_tokens = self.cumulative_tokens
            self.all_evidence_started_ns = started_at_ns

    def observe(self, index: int, event: dict[str, Any]) -> None:
        kind = event["kind"]
        tokens = _event_tokens(event)
        paths = _event_paths(event)
        started_at_ns = self._observe_timing(event)
        if kind in SEARCH_KINDS:
            self._observe_query(index, event, tokens)
        if kind in READ_KINDS:
            self._observe_reads(index, paths, tokens)
        if kind in DISCOVERY_KINDS:
            self._observe_discovery(index, paths, started_at_ns)
        if self.first_index is None:
            self.searches_before += int(kind in SEARCH_KINDS)
            self.reads_before += int(kind in READ_KINDS)
        if self.all_index is None:
            self.searches_before_all += int(kind in SEARCH_KINDS)
            self.reads_before_all += int(kind in READ_KINDS)
        self.cumulative_tokens += tokens

    def summary(self) -> dict[str, Any]:
        missing = sorted(self.required - self.discovered)
        return {
            "required_path_count": len(self.required),
            "required_paths_discovered": len(self.discovered),
            "required_evidence_complete": not missing,
            "missing_required_paths": missing,
            "tokens_before_first_required_evidence": self.first_tokens,
            "events_before_first_required_evidence": self.first_index,
            "searches_before_first_required_evidence": self.searches_before
            if self.first_index is not None
            else None,
            "reads_before_first_required_evidence": self.reads_before
            if self.first_index is not None
            else None,
            "tokens_before_all_required_evidence": self.all_tokens,
            "events_before_all_required_evidence": self.all_index,
            "searches_before_all_required_evidence": self.searches_before_all
            if self.all_index is not None
            else None,
            "reads_before_all_required_evidence": self.reads_before_all
            if self.all_index is not None
            else None,
            "duplicate_queries": sum(
                max(0, count - 1) for count in self.query_counter.values()
            ),
            "duplicate_query_estimated_tokens": self.duplicate_query_tokens,
            "duplicate_reads": sum(
                max(0, count - 1) for count in self.read_counter.values()
            ),
            "duplicate_read_estimated_tokens": self.duplicate_read_tokens,
            "irrelevant_reads": self.irrelevant_reads,
            "irrelevant_read_estimated_tokens": self.irrelevant_read_tokens,
            "total_estimated_exploration_tokens": self.cumulative_tokens,
            "navigation_ms_before_first_required_evidence": _elapsed_ms(
                self.navigation_start_ns, self.first_evidence_started_ns
            ),
            "navigation_ms_before_all_required_evidence": _elapsed_ms(
                self.navigation_start_ns, self.all_evidence_started_ns
            ),
            "total_navigation_ms": _elapsed_ms(
                self.navigation_start_ns, self.navigation_finish_ns
            ),
        }


def _elapsed_ms(start: int | None, finish: int | None) -> float | None:
    return None if start is None or finish is None else (finish - start) / 1_000_000.0


def analyze(trace_path: Path, evidence_path: Path) -> dict[str, Any]:
    trace_module = _load_trace_module()
    trace = trace_module.load_trace(trace_path)
    evidence = load_evidence(evidence_path)
    for field in ("task_id", "task_revision", "repository_identity"):
        if trace.get(field) != evidence[field]:
            raise ValueError(
                f"trace/evidence {field} mismatch: expected {evidence[field]!r}, got {trace.get(field)!r}"
            )

    observations = RegretObservations(set(evidence["required_paths"]))
    for index, event in enumerate(trace["events"]):
        observations.observe(index, event)
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
        "summary": observations.summary(),
        "required_discovery_order": observations.required_discovery_order,
        "observed_opportunities": {
            "repeated_queries": observations.repeated_queries,
            "repeated_reads": observations.repeated_reads,
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
    log_command_output(logger, rendered)


if __name__ == "__main__":
    main()
