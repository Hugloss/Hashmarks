from __future__ import annotations

import argparse
import hashlib
import logging
from dataclasses import dataclass, field

from hashmarks._command_output import log_command_output

try:
    from scripts._module_loader import import_sibling
except ModuleNotFoundError:  # direct script execution
    from _module_loader import import_sibling
import json
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SET_SCHEMA = "hashmarks.agent-experiment-set.v2"
REPORT_SCHEMA = "hashmarks.agent-experiment-set-report.v2"
PUBLIC_MIN_EXPERIMENTS = 3
PUBLIC_MIN_REPOSITORIES = 3
PUBLIC_MIN_UNIQUE_TASKS = 30


@dataclass
class _SetAggregation:
    experiment_ids: set[str] = field(default_factory=set)
    manifest_digests: set[str] = field(default_factory=set)
    run_ids: set[str] = field(default_factory=set)
    task_keys: set[tuple[str, str, str]] = field(default_factory=set)
    repositories: set[str] = field(default_factory=set)
    experiment_reports: list[dict[str, Any]] = field(default_factory=list)
    total_baseline_tokens: int = 0
    total_hashmarks_tokens: int = 0

    def admit_manifest(self, path: Path, digest: str, experiment_id: str) -> None:
        if digest in self.manifest_digests:
            raise ValueError(f"duplicate experiment manifest bytes: {path}")
        self.manifest_digests.add(digest)
        if experiment_id in self.experiment_ids:
            raise ValueError(f"duplicate experiment_id: {experiment_id}")
        self.experiment_ids.add(experiment_id)

    def admit_runs(self, experiment: dict[str, Any]) -> None:
        for run in experiment["runs"]:
            run_id = run["run_id"]
            if run_id in self.run_ids:
                raise ValueError(f"run_id reused across experiment set: {run_id}")
            self.run_ids.add(run_id)
            self.repositories.add(run["repository_identity"])
            if run["mode"] == "baseline":
                self._admit_task(run)

    def _admit_task(self, run: dict[str, Any]) -> None:
        key = (run["repository_identity"], run["task_id"], run["task_revision"])
        if key in self.task_keys:
            raise ValueError(
                "task identity reused across experiment set: " + ":".join(key)
            )
        self.task_keys.add(key)

    def admit_report(
        self, experiment_id: str, digest: str, report: dict[str, Any]
    ) -> None:
        summary = report["comparison"]["summary"]
        if not summary.get("token_reduction_claim_eligible"):
            raise ValueError(f"experiment {experiment_id} is not token-claim eligible")
        baseline = summary.get("baseline_model_input_tokens")
        hashmarks = summary.get("hashmarks_model_input_tokens")
        if (
            not isinstance(baseline, int)
            or not isinstance(hashmarks, int)
            or baseline <= 0
        ):
            raise ValueError(
                f"experiment {experiment_id} lacks exact aggregate model-input tokens"
            )
        self.total_baseline_tokens += baseline
        self.total_hashmarks_tokens += hashmarks
        self.experiment_reports.append(
            {
                "experiment_id": experiment_id,
                "manifest_sha256": digest,
                "repositories": report["repositories"],
                "tasks": report["tasks"],
                "baseline_model_input_tokens": baseline,
                "hashmarks_model_input_tokens": hashmarks,
                "model_input_token_reduction": summary[
                    "average_model_input_token_reduction"
                ],
            }
        )


def _load_experiment_module() -> Any:
    return import_sibling("metrics_agent_experiment", __package__)


def _nonempty(value: Any, field: str, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string: {path}")
    return value


def _relative_file(root: Path, value: Any, field: str, manifest_path: Path) -> Path:
    raw = _nonempty(value, field, manifest_path)
    relative = Path(raw)
    if relative.is_absolute():
        raise ValueError(
            f"{field} must be relative to experiment-set directory: {manifest_path}"
        )
    resolved_root = root.resolve()
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(
            f"{field} escapes experiment-set directory: {manifest_path}"
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


def _validate_set_entry(
    entry: Any, index: int, path: Path, seen_paths: set[str]
) -> None:
    if not isinstance(entry, dict):
        raise ValueError(f"experiment-set entry {index} must be an object: {path}")
    rel = _nonempty(
        entry.get("manifest"), f"experiment-set entry {index} manifest", path
    )
    expected_digest = _nonempty(
        entry.get("manifest_sha256"),
        f"experiment-set entry {index} manifest_sha256",
        path,
    )
    if not expected_digest.startswith("sha256:") or len(expected_digest) != 71:
        raise ValueError(
            f"experiment-set entry {index} manifest_sha256 must be sha256:<64 hex>: {path}"
        )
    try:
        int(expected_digest[7:], 16)
    except ValueError as exc:
        raise ValueError(
            f"experiment-set entry {index} manifest_sha256 must be sha256:<64 hex>: {path}"
        ) from exc
    if rel in seen_paths:
        raise ValueError(f"duplicate experiment manifest entry: {rel}")
    seen_paths.add(rel)


def load_set_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != SET_SCHEMA:
        raise ValueError(f"unsupported agent experiment-set manifest schema: {path}")
    for field in (
        "experiment_set_id",
        "model_identity",
        "model_config_identity",
        "task_policy_identity",
    ):
        _nonempty(value.get(field), f"experiment-set {field}", path)
    experiments = value.get("experiments")
    if not isinstance(experiments, list) or not experiments:
        raise ValueError(f"experiment-set experiments must be a non-empty list: {path}")
    seen_paths: set[str] = set()
    for index, entry in enumerate(experiments):
        _validate_set_entry(entry, index, path, seen_paths)
    return value


def _replication_policy(manifest: dict[str, Any]) -> tuple[int, float, int]:
    policy = manifest.get("replication_policy", {})
    min_repeats = policy.get("min_repeats_per_group", 3)
    confidence = policy.get("confidence", 0.95)
    bootstrap_samples = policy.get("bootstrap_samples", 10000)
    if not isinstance(min_repeats, int) or min_repeats < 2:
        raise ValueError(
            "replication_policy min_repeats_per_group must be an integer >= 2"
        )
    if not isinstance(confidence, (int, float)) or not 0.5 < confidence < 1.0:
        raise ValueError("replication_policy confidence must be between 0.5 and 1.0")
    if not isinstance(bootstrap_samples, int) or bootstrap_samples < 1000:
        raise ValueError(
            "replication_policy bootstrap_samples must be an integer >= 1000"
        )
    return min_repeats, float(confidence), bootstrap_samples


def _bootstrap_interval(
    manifest_path: Path,
    experiment_reports: list[dict[str, Any]],
    confidence: float,
    bootstrap_samples: int,
) -> dict[str, Any] | None:
    import math
    import random

    if len(experiment_reports) < 2:
        return None
    values = [report["model_input_token_reduction"] for report in experiment_reports]
    seed = int(hashlib.sha256(manifest_path.read_bytes()).hexdigest()[:16], 16)
    rng = random.Random(seed)
    sample_size = len(values)
    means = [
        sum(values[rng.randrange(sample_size)] for _ in range(sample_size))
        / sample_size
        for _ in range(bootstrap_samples)
    ]
    means.sort()
    alpha = (1.0 - confidence) / 2.0
    lower_index = max(0, min(len(means) - 1, int(math.floor(alpha * len(means)))))
    upper_index = max(
        0, min(len(means) - 1, int(math.ceil((1.0 - alpha) * len(means))) - 1)
    )
    return {
        "method": "deterministic-experiment-bootstrap",
        "confidence": confidence,
        "samples": bootstrap_samples,
        "lower": means[lower_index],
        "upper": means[upper_index],
        "scope": "exact-retained-experiments-only",
    }


def _replication_report(
    manifest: dict[str, Any],
    manifest_path: Path,
    experiment_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    # Repetitions describe variation and never add repository/task breadth.
    groups: dict[str, list[dict[str, Any]]] = {}
    for index, entry in enumerate(manifest["experiments"]):
        group = _nonempty(
            entry.get("replication_group"),
            f"experiment-set entry {index} replication_group",
            manifest_path,
        )
        groups.setdefault(group, []).append(experiment_reports[index])
    min_repeats, confidence, bootstrap_samples = _replication_policy(manifest)

    group_reports = []
    eligible_groups = 0
    for group_id in sorted(groups):
        rows = groups[group_id]
        reductions = [r["model_input_token_reduction"] for r in rows]
        eligible = len(rows) >= min_repeats
        if eligible:
            eligible_groups += 1
        group_reports.append(
            {
                "replication_group": group_id,
                "repeat_count": len(rows),
                "replication_eligible": eligible,
                "mean_model_input_token_reduction": sum(reductions) / len(reductions),
                "min_model_input_token_reduction": min(reductions),
                "max_model_input_token_reduction": max(reductions),
            }
        )

    ci = _bootstrap_interval(
        manifest_path, experiment_reports, confidence, bootstrap_samples
    )
    return {
        "group_count": len(groups),
        "eligible_group_count": eligible_groups,
        "min_repeats_per_group": min_repeats,
        "groups": group_reports,
        "descriptive_confidence_interval": ci,
        "statistical_claim_eligible": bool(groups)
        and eligible_groups == len(groups)
        and ci is not None,
        "warning": "replication does not increase repository/task breadth and this interval does not establish population generalization",
    }


def _set_consistency_fields(manifest: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "model_identity": manifest["model_identity"],
        "model_config_identity": manifest["model_config_identity"],
        "task_policy_identity": manifest["task_policy_identity"],
    }
    fields.update(
        {
            name: manifest[name]
            for name in (
                "runner_identity",
                "grader_identity",
                "provider_identity",
                "benchmark_protocol_identity",
            )
            if manifest.get(name) is not None
        }
    )
    return fields


def _load_bound_experiment(
    root: Path,
    manifest_path: Path,
    entry: dict[str, Any],
    index: int,
    experiment_module: Any,
) -> tuple[Path, str, dict[str, Any]]:
    experiment_path = _relative_file(
        root, entry["manifest"], f"experiment {index} manifest", manifest_path
    )
    digest = _sha256(experiment_path)
    if digest != entry["manifest_sha256"]:
        raise ValueError(
            "experiment manifest digest mismatch: "
            f"expected {entry['manifest_sha256']}, got {digest}"
        )
    return experiment_path, digest, experiment_module.load_manifest(experiment_path)


def _validate_experiment_consistency(
    experiment: dict[str, Any], expected_fields: dict[str, Any]
) -> None:
    experiment_id = experiment["experiment_id"]
    for field_name, expected in expected_fields.items():
        actual = experiment.get(field_name)
        if actual != expected:
            raise ValueError(
                f"experiment {experiment_id} {field_name} mismatch: "
                f"expected {expected!r}, got {actual!r}"
            )


def _public_claim_blockers(state: _SetAggregation) -> list[str]:
    blockers = []
    if len(state.experiment_reports) < PUBLIC_MIN_EXPERIMENTS:
        blockers.append(
            f"experiments {len(state.experiment_reports)} < required {PUBLIC_MIN_EXPERIMENTS}"
        )
    if len(state.repositories) < PUBLIC_MIN_REPOSITORIES:
        blockers.append(
            f"repositories {len(state.repositories)} < required {PUBLIC_MIN_REPOSITORIES}"
        )
    if len(state.task_keys) < PUBLIC_MIN_UNIQUE_TASKS:
        blockers.append(
            f"unique_tasks {len(state.task_keys)} < required {PUBLIC_MIN_UNIQUE_TASKS}"
        )
    return blockers


def run_experiment_set(
    manifest_path: Path, *, strict_raw_evidence: bool = True
) -> dict[str, Any]:
    experiment_module = _load_experiment_module()
    manifest = load_set_manifest(manifest_path)
    root = manifest_path.parent
    state = _SetAggregation()
    expected_fields = _set_consistency_fields(manifest)

    for index, entry in enumerate(manifest["experiments"]):
        experiment_path, digest, experiment = _load_bound_experiment(
            root, manifest_path, entry, index, experiment_module
        )
        experiment_id = experiment["experiment_id"]
        state.admit_manifest(experiment_path, digest, experiment_id)
        _validate_experiment_consistency(experiment, expected_fields)
        report = experiment_module.run_experiment(
            experiment_path, strict_raw_evidence=strict_raw_evidence
        )
        state.admit_runs(experiment)
        state.admit_report(experiment_id, digest, report)

    aggregate_reduction = 1.0 - (
        state.total_hashmarks_tokens / state.total_baseline_tokens
    )
    replication = _replication_report(manifest, manifest_path, state.experiment_reports)
    internal_eligible = bool(state.experiment_reports)
    public_blockers = _public_claim_blockers(state)

    return {
        "schema": REPORT_SCHEMA,
        "experiment_set_id": manifest["experiment_set_id"],
        "manifest_sha256": _sha256(manifest_path),
        "model_identity": manifest["model_identity"],
        "model_config_identity": manifest["model_config_identity"],
        "task_policy_identity": manifest["task_policy_identity"],
        "benchmark_protocol_identity": manifest.get("benchmark_protocol_identity"),
        "experiments": state.experiment_reports,
        "summary": {
            "experiment_count": len(state.experiment_reports),
            "repository_count": len(state.repositories),
            "unique_task_count": len(state.task_keys),
            "run_count": len(state.run_ids),
            "baseline_model_input_tokens": state.total_baseline_tokens,
            "hashmarks_model_input_tokens": state.total_hashmarks_tokens,
            "aggregate_model_input_token_reduction": aggregate_reduction,
            "internal_controlled_claim_eligible": internal_eligible,
            "public_broad_claim_eligible": internal_eligible and not public_blockers,
            "public_broad_claim_blockers": public_blockers,
            "replication": replication,
            "public_minimums": {
                "experiments": PUBLIC_MIN_EXPERIMENTS,
                "repositories": PUBLIC_MIN_REPOSITORIES,
                "unique_tasks": PUBLIC_MIN_UNIQUE_TASKS,
            },
        },
    }


def gate(
    report: dict[str, Any], *, require_public_broad_claim: bool = False
) -> list[str]:
    summary = report["summary"]
    failures: list[str] = []
    if not summary["internal_controlled_claim_eligible"]:
        failures.append(
            "experiment set is not eligible for an internal controlled claim"
        )
    if require_public_broad_claim and not summary["public_broad_claim_eligible"]:
        failures.extend(summary["public_broad_claim_blockers"])
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate and aggregate canonical Hashmarks real-agent experiments"
    )
    parser.add_argument(
        "experiment_set", type=Path, help="hashmarks.agent-experiment-set.v2 manifest"
    )
    parser.add_argument(
        "--allow-missing-raw-evidence",
        action="store_true",
        help="do not require retained raw grader/provider evidence bytes",
    )
    parser.add_argument(
        "--require-public-broad-claim",
        action="store_true",
        help="fail unless fixed public breadth floors are met",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = run_experiment_set(
        args.experiment_set, strict_raw_evidence=not args.allow_missing_raw_evidence
    )
    failures = gate(payload, require_public_broad_claim=args.require_public_broad_claim)
    if failures:
        raise SystemExit("experiment-set gate failed: " + "; ".join(failures))
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    log_command_output(logger, rendered)


if __name__ == "__main__":
    main()
