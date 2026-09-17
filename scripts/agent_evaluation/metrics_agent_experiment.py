from __future__ import annotations

import argparse
import hashlib

try:
    from scripts._module_loader import import_sibling
except ModuleNotFoundError:  # direct script execution
    from _module_loader import import_sibling
import json
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA = "hashmarks.agent-experiment.v1"
REPORT_SCHEMA = "hashmarks.agent-experiment-report.v1"
MODES = {"baseline", "hashmarks"}


def _load_trace_module() -> Any:
    return import_sibling("metrics_agent_trace", __package__)


def _nonempty(value: Any, field: str, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string: {path}")
    return value


def _relative_file(root: Path, value: Any, field: str, manifest_path: Path) -> Path:
    raw = _nonempty(value, field, manifest_path)
    relative = Path(raw)
    if relative.is_absolute():
        raise ValueError(
            f"{field} must be relative to experiment directory: {manifest_path}"
        )
    resolved_root = root.resolve()
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(
            f"{field} escapes experiment directory: {manifest_path}"
        ) from exc
    if not resolved.is_file():
        raise ValueError(f"{field} file does not exist: {resolved}")
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"unsupported agent experiment manifest schema: {path}")
    for field in (
        "experiment_id",
        "model_identity",
        "model_config_identity",
        "runner_identity",
    ):
        _nonempty(value.get(field), f"manifest {field}", path)
    runs = value.get("runs")
    if not isinstance(runs, list) or not runs:
        raise ValueError(f"manifest runs must be a non-empty list: {path}")
    seen_run_ids: set[str] = set()
    seen_task_modes: set[tuple[str, str]] = set()
    for index, run in enumerate(runs):
        if not isinstance(run, dict):
            raise ValueError(f"manifest run {index} must be an object: {path}")
        for field in (
            "task_id",
            "task_revision",
            "repository_identity",
            "mode",
            "run_id",
            "trace",
            "verdict",
            "usage",
            "subject",
        ):
            _nonempty(run.get(field), f"manifest run {index} {field}", path)
        if run["mode"] not in MODES:
            raise ValueError(
                f"manifest run {index} mode must be baseline or hashmarks: {path}"
            )
        if run["run_id"] in seen_run_ids:
            raise ValueError(f"duplicate manifest run_id: {run['run_id']}")
        seen_run_ids.add(run["run_id"])
        task_mode = (run["task_id"], run["mode"])
        if task_mode in seen_task_modes:
            raise ValueError(
                f"duplicate manifest task/mode: {run['task_id']}:{run['mode']}"
            )
        seen_task_modes.add(task_mode)
    by_task: dict[str, set[str]] = {}
    for run in runs:
        by_task.setdefault(run["task_id"], set()).add(run["mode"])
    incomplete = sorted(task for task, modes in by_task.items() if modes != MODES)
    if incomplete:
        raise ValueError("manifest has unpaired tasks: " + ", ".join(incomplete))
    return value


def _validate_digest_binding(
    record: dict[str, Any], evidence_path: Path, kind: str
) -> None:
    expected = record.get("evidence_digest")
    actual = _sha256(evidence_path)
    if expected != actual:
        raise ValueError(
            f"{kind} raw evidence digest mismatch: expected {expected}, got {actual}"
        )


def run_experiment(
    manifest_path: Path, *, strict_raw_evidence: bool = False
) -> dict[str, Any]:
    trace_module = _load_trace_module()
    manifest = load_manifest(manifest_path)
    root = manifest_path.parent
    trace_paths: list[Path] = []
    verdict_paths: list[Path] = []
    usage_paths: list[Path] = []
    repositories: set[str] = set()

    for run in manifest["runs"]:
        trace_path = _relative_file(root, run["trace"], "trace", manifest_path)
        verdict_path = _relative_file(root, run["verdict"], "verdict", manifest_path)
        usage_path = _relative_file(root, run["usage"], "usage", manifest_path)
        subject_path = _relative_file(root, run["subject"], "subject", manifest_path)
        trace = trace_module.load_trace(trace_path)
        verdict = trace_module.load_verdict(verdict_path)
        usage = trace_module.load_usage(usage_path)

        expected = {
            "task_id": run["task_id"],
            "task_revision": run["task_revision"],
            "repository_identity": run["repository_identity"],
            "mode": run["mode"],
            "run_id": run["run_id"],
            "model_identity": manifest["model_identity"],
            "model_config_identity": manifest["model_config_identity"],
            "runner_identity": manifest["runner_identity"],
        }
        for field, expected_value in expected.items():
            if trace.get(field) != expected_value:
                raise ValueError(
                    f"trace {field} mismatch for run {run['run_id']}: expected {expected_value!r}, got {trace.get(field)!r}"
                )
        for record_name, record in (("verdict", verdict), ("usage", usage)):
            for field in ("task_id", "mode", "run_id"):
                if record.get(field) != expected[field]:
                    raise ValueError(
                        f"{record_name} {field} mismatch for run {run['run_id']}: expected {expected[field]!r}, got {record.get(field)!r}"
                    )

        subject_digest = _sha256(subject_path)
        if verdict.get("subject_digest") != subject_digest:
            raise ValueError(
                f"verdict subject_digest mismatch for run {run['run_id']}: "
                f"expected {subject_digest}, got {verdict.get('subject_digest')}"
            )

        grader_identity = manifest.get("grader_identity")
        if (
            grader_identity is not None
            and verdict.get("grader_identity") != grader_identity
        ):
            raise ValueError(
                f"verdict grader_identity mismatch for run {run['run_id']}"
            )
        provider_identity = manifest.get("provider_identity")
        if (
            provider_identity is not None
            and usage.get("provider_identity") != provider_identity
        ):
            raise ValueError(
                f"usage provider_identity mismatch for run {run['run_id']}"
            )

        for field, record, kind in (
            ("grader_evidence", verdict, "grader"),
            ("provider_evidence", usage, "provider"),
        ):
            if field in run:
                evidence_path = _relative_file(root, run[field], field, manifest_path)
                _validate_digest_binding(record, evidence_path, kind)
            elif strict_raw_evidence:
                raise ValueError(
                    f"manifest run {run['run_id']} requires {field} in strict raw-evidence mode"
                )

        trace_paths.append(trace_path)
        verdict_paths.append(verdict_path)
        usage_paths.append(usage_path)
        repositories.add(run["repository_identity"])

    comparison = trace_module.compare(
        trace_paths,
        verdict_paths=verdict_paths,
        usage_paths=usage_paths,
        require_complete_pairs=True,
        require_external_verdict=True,
        require_external_usage=True,
    )
    failures = trace_module.gate(comparison, min_pairs=len(manifest["runs"]) // 2)
    if failures:
        raise ValueError("experiment evidence gate failed: " + "; ".join(failures))

    return {
        "schema": REPORT_SCHEMA,
        "experiment_id": manifest["experiment_id"],
        "manifest_sha256": _sha256(manifest_path),
        "runner_identity": manifest["runner_identity"],
        "runner_version": manifest.get("runner_version"),
        "model_identity": manifest["model_identity"],
        "model_config_identity": manifest["model_config_identity"],
        "task_policy_identity": manifest.get("task_policy_identity"),
        "benchmark_protocol_identity": manifest.get("benchmark_protocol_identity"),
        "repositories": len(repositories),
        "tasks": len(manifest["runs"]) // 2,
        "raw_evidence_required": strict_raw_evidence,
        "comparison": comparison,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate and compare a canonical Hashmarks real-agent experiment"
    )
    parser.add_argument(
        "experiment", type=Path, help="hashmarks.agent-experiment.v1 manifest"
    )
    parser.add_argument(
        "--strict-raw-evidence",
        action="store_true",
        help="require raw grader/provider evidence bytes and verify their SHA-256 bindings",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = run_experiment(
        args.experiment, strict_raw_evidence=args.strict_raw_evidence
    )
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)  # noqa: T201 - intentional command output


if __name__ == "__main__":
    main()
