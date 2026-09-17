from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from .adapters import adapter

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

MANIFEST_SCHEMA = "hashmarks.agent-experiment-manifest.v1"
BUNDLE_SCHEMA = "hashmarks.agent-experiment-bundle.v1"


def _digest(value: object) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class ExperimentLane:
    name: str
    harness: str
    model: str
    strategy: str
    reasoning_effort: str | None = None

    def __post_init__(self) -> None:
        if self.strategy not in {"native", "hashmarks", "selective-scout"}:
            raise ValueError("unsupported experiment strategy")
        adapter(self.harness)  # fail closed on unsupported harnesses


def experiment_manifest(
    *,
    corpus_identity: str,
    lanes: Iterable[ExperimentLane],
    secret_identity: str | None = None,
) -> dict[str, Any]:
    rows = [asdict(lane) for lane in lanes]
    if not rows:
        raise ValueError("experiment requires at least one lane")
    names = [row["name"] for row in rows]
    if len(names) != len(set(names)):
        raise ValueError("experiment lane names must be unique")
    public = {
        "schema": MANIFEST_SCHEMA,
        "corpus_identity": corpus_identity,
        "lanes": rows,
    }
    public["manifest_identity"] = _digest(public)
    # SECRET identity may be recorded for authority bookkeeping but never the secret contents.
    if secret_identity is not None:
        public["secret_identity"] = secret_identity
    return public


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    events = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at line {number}: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"JSONL event at line {number} must be an object")
        events.append(value)
    return events


def import_native_run(
    *,
    lane: ExperimentLane,
    task_id: str,
    session_id: str,
    repository_identity: str | None,
    event_path: Path,
) -> dict[str, Any]:
    native = load_jsonl(event_path)
    normalized = adapter(lane.harness).normalize_events(
        native,
        session_id=session_id,
        task_id=task_id,
        repository_identity=repository_identity,
    )
    trace = {
        "schema": "hashmarks.agent-event-trace.v1",
        "session_id": session_id,
        "task_id": task_id,
        "repository_identity": repository_identity,
        "actor_model": "external-agent-owns-solution/hashmarks-normalizes-evidence",
        "events": normalized,
    }
    return {
        "schema": BUNDLE_SCHEMA,
        "lane": asdict(lane),
        "native_event_sha256": "sha256:"
        + hashlib.sha256(event_path.read_bytes()).hexdigest(),
        "native_event_count": len(native),
        "normalized_event_count": len(normalized),
        "trace": trace,
        "trace_identity": _digest(trace),
    }


def coverage_ledger(
    *,
    manifest: dict[str, Any],
    task_ids: Iterable[str],
    bundles: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError("unsupported experiment manifest schema")
    tasks = sorted({str(task) for task in task_ids})
    if not tasks:
        raise ValueError("coverage ledger requires at least one task")
    lane_names = [
        str(row.get("name"))
        for row in manifest.get("lanes", [])
        if isinstance(row, dict)
    ]
    expected = {(lane, task) for lane in lane_names for task in tasks}
    observed: set[tuple[str, str]] = set()
    duplicates: set[tuple[str, str]] = set()
    invalid = []
    for bundle in bundles:
        if not isinstance(bundle, dict) or bundle.get("schema") != BUNDLE_SCHEMA:
            invalid.append("unsupported-bundle-schema")
            continue
        lane = (
            (bundle.get("lane") or {}).get("name")
            if isinstance(bundle.get("lane"), dict)
            else None
        )
        trace = bundle.get("trace") if isinstance(bundle.get("trace"), dict) else {}
        task = trace.get("task_id")
        key = (str(lane), str(task))
        if key not in expected:
            invalid.append(f"unexpected:{key[0]}:{key[1]}")
            continue
        if key in observed:
            duplicates.add(key)
        observed.add(key)
    missing = sorted(expected - observed)
    return {
        "schema": "hashmarks.agent-experiment-coverage.v1",
        "manifest_identity": manifest.get("manifest_identity"),
        "expected_runs": len(expected),
        "observed_runs": len(observed),
        "complete": not missing and not duplicates and not invalid,
        "missing": [{"lane": lane, "task_id": task} for lane, task in missing],
        "duplicates": [
            {"lane": lane, "task_id": task} for lane, task in sorted(duplicates)
        ],
        "invalid": invalid,
    }


def require_complete_coverage(ledger: dict[str, Any]) -> None:
    if ledger.get("schema") != "hashmarks.agent-experiment-coverage.v1":
        raise ValueError("unsupported coverage ledger schema")
    if not ledger.get("complete"):
        raise ValueError("experiment coverage is incomplete")


def assemble_experiment_report(
    *,
    manifest: dict[str, Any],
    task_ids: Iterable[str],
    bundles: Iterable[dict[str, Any]],
    grades: dict[str, bool],
) -> dict[str, Any]:
    from .economics import GradedRun, pareto_dominance, summarize_lane, trace_economics

    task_list = sorted({str(task) for task in task_ids})
    bundle_list = list(bundles)
    ledger = coverage_ledger(manifest=manifest, task_ids=task_list, bundles=bundle_list)
    require_complete_coverage(ledger)
    if set(grades) != set(task_list):
        missing = sorted(set(task_list) - set(grades))
        extra = sorted(set(grades) - set(task_list))
        raise ValueError(
            f"SECRET grade task set mismatch: missing={missing} extra={extra}"
        )
    lane_meta = {
        str(row["name"]): row
        for row in manifest.get("lanes", [])
        if isinstance(row, dict) and "name" in row
    }
    by_lane: dict[str, list[dict[str, Any]]] = {name: [] for name in lane_meta}
    for bundle in bundle_list:
        lane = str(bundle["lane"]["name"])
        trace = bundle["trace"]
        task = str(trace["task_id"])
        by_lane[lane].append(
            trace_economics(trace, GradedRun(task, bool(grades[task])))
        )
    metrics = []
    rows = {}
    for lane in sorted(by_lane):
        meta = lane_meta[lane]
        lane_rows = sorted(by_lane[lane], key=lambda row: str(row["task_id"]))
        rows[lane] = lane_rows
        metrics.append(
            summarize_lane(
                lane,
                lane_rows,
                model=str(meta.get("model") or ""),
                strategy=str(meta.get("strategy") or ""),
            )
        )
    return {
        "schema": "hashmarks.agent-experiment-report.v1",
        "manifest_identity": manifest.get("manifest_identity"),
        "coverage": ledger,
        "complete": True,
        "lanes": metrics,
        "pareto_dominance": pareto_dominance(metrics),
        "rows": rows,
        "grading_note": "SECRET answers were joined after trace import; report contains outcomes/economics, not answer keys.",
    }


def experiment_certificate(
    *,
    manifest: dict[str, Any],
    bundles: Iterable[dict[str, Any]],
    report: dict[str, Any],
    secret_identity: str,
) -> dict[str, Any]:
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError("unsupported experiment manifest schema")
    if report.get("schema") != "hashmarks.agent-experiment-report.v1" or not report.get(
        "complete"
    ):
        raise ValueError("only a complete experiment report can be certified")
    if report.get("manifest_identity") != manifest.get("manifest_identity"):
        raise ValueError("report/manifest identity mismatch")
    if not isinstance(secret_identity, str) or not secret_identity.startswith(
        "sha256:"
    ):
        raise ValueError("secret_identity must be an explicit sha256 identity")
    trace_ids = []
    native_ids = []
    for bundle in bundles:
        if bundle.get("schema") != BUNDLE_SCHEMA:
            raise ValueError("unsupported experiment bundle schema")
        trace_id = bundle.get("trace_identity")
        native_id = bundle.get("native_event_sha256")
        if not isinstance(trace_id, str) or not trace_id.startswith("sha256:"):
            raise ValueError("bundle is missing trace identity")
        if not isinstance(native_id, str) or not native_id.startswith("sha256:"):
            raise ValueError("bundle is missing native event identity")
        trace_ids.append(trace_id)
        native_ids.append(native_id)
    payload = {
        "schema": "hashmarks.agent-experiment-certificate.v1",
        "manifest_identity": manifest.get("manifest_identity"),
        "secret_identity": secret_identity,
        "trace_identities": sorted(trace_ids),
        "native_event_identities": sorted(native_ids),
        "coverage_identity": _digest(report.get("coverage")),
        "report_identity": _digest(report),
    }
    payload["certificate_identity"] = _digest(payload)
    return payload


def verify_experiment_certificate(
    *,
    certificate: dict[str, Any],
    manifest: dict[str, Any],
    bundles: Iterable[dict[str, Any]],
    report: dict[str, Any],
    secret_identity: str,
) -> bool:
    expected = experiment_certificate(
        manifest=manifest,
        bundles=bundles,
        report=report,
        secret_identity=secret_identity,
    )
    return certificate == expected
