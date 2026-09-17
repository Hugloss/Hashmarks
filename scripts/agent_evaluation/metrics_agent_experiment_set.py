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

SET_SCHEMA = "hashmarks.agent-experiment-set.v2"
REPORT_SCHEMA = "hashmarks.agent-experiment-set-report.v2"
PUBLIC_MIN_EXPERIMENTS = 3
PUBLIC_MIN_REPOSITORIES = 3
PUBLIC_MIN_UNIQUE_TASKS = 30


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
        raise ValueError(f"{field} must be relative to experiment-set directory: {manifest_path}")
    resolved_root = root.resolve()
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"{field} escapes experiment-set directory: {manifest_path}") from exc
    if not resolved.is_file():
        raise ValueError(f"{field} file does not exist: {resolved}")
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


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
        if not isinstance(entry, dict):
            raise ValueError(f"experiment-set entry {index} must be an object: {path}")
        rel = _nonempty(entry.get("manifest"), f"experiment-set entry {index} manifest", path)
        expected_digest = _nonempty(entry.get("manifest_sha256"), f"experiment-set entry {index} manifest_sha256", path)
        if not expected_digest.startswith("sha256:") or len(expected_digest) != 71:
            raise ValueError(f"experiment-set entry {index} manifest_sha256 must be sha256:<64 hex>: {path}")
        try:
            int(expected_digest[7:], 16)
        except ValueError as exc:
            raise ValueError(f"experiment-set entry {index} manifest_sha256 must be sha256:<64 hex>: {path}") from exc
        if rel in seen_paths:
            raise ValueError(f"duplicate experiment manifest entry: {rel}")
        seen_paths.add(rel)
    return value


def run_experiment_set(manifest_path: Path, *, strict_raw_evidence: bool = True) -> dict[str, Any]:
    experiment_module = _load_experiment_module()
    manifest = load_set_manifest(manifest_path)
    root = manifest_path.parent

    experiment_ids: set[str] = set()
    manifest_digests: set[str] = set()
    run_ids: set[str] = set()
    task_keys: set[tuple[str, str, str]] = set()
    repositories: set[str] = set()
    experiment_reports: list[dict[str, Any]] = []
    total_baseline_tokens = 0
    total_hashmarks_tokens = 0

    expected_fields = {
        "model_identity": manifest["model_identity"],
        "model_config_identity": manifest["model_config_identity"],
        "task_policy_identity": manifest["task_policy_identity"],
    }
    optional_consistency = {
        field: manifest.get(field)
        for field in ("runner_identity", "grader_identity", "provider_identity", "benchmark_protocol_identity")
        if manifest.get(field) is not None
    }

    for index, entry in enumerate(manifest["experiments"]):
        experiment_path = _relative_file(root, entry["manifest"], f"experiment {index} manifest", manifest_path)
        digest = _sha256(experiment_path)
        if digest != entry["manifest_sha256"]:
            raise ValueError(
                f"experiment manifest digest mismatch: expected {entry['manifest_sha256']}, got {digest}"
            )
        if digest in manifest_digests:
            raise ValueError(f"duplicate experiment manifest bytes: {experiment_path}")
        manifest_digests.add(digest)

        experiment = experiment_module.load_manifest(experiment_path)
        experiment_id = experiment["experiment_id"]
        if experiment_id in experiment_ids:
            raise ValueError(f"duplicate experiment_id: {experiment_id}")
        experiment_ids.add(experiment_id)

        for field, expected in {**expected_fields, **optional_consistency}.items():
            actual = experiment.get(field)
            if actual != expected:
                raise ValueError(
                    f"experiment {experiment_id} {field} mismatch: expected {expected!r}, got {actual!r}"
                )

        report = experiment_module.run_experiment(experiment_path, strict_raw_evidence=strict_raw_evidence)
        summary = report["comparison"]["summary"]
        if not summary.get("token_reduction_claim_eligible"):
            raise ValueError(f"experiment {experiment_id} is not token-claim eligible")
        base = summary.get("baseline_model_input_tokens")
        hm = summary.get("hashmarks_model_input_tokens")
        if not isinstance(base, int) or not isinstance(hm, int) or base <= 0:
            raise ValueError(f"experiment {experiment_id} lacks exact aggregate model-input tokens")
        total_baseline_tokens += base
        total_hashmarks_tokens += hm

        for run in experiment["runs"]:
            run_id = run["run_id"]
            if run_id in run_ids:
                raise ValueError(f"run_id reused across experiment set: {run_id}")
            run_ids.add(run_id)
            repositories.add(run["repository_identity"])
            if run["mode"] == "baseline":
                key = (run["repository_identity"], run["task_id"], run["task_revision"])
                if key in task_keys:
                    raise ValueError(
                        "task identity reused across experiment set: " + ":".join(key)
                    )
                task_keys.add(key)

        experiment_reports.append({
            "experiment_id": experiment_id,
            "manifest_sha256": digest,
            "repositories": report["repositories"],
            "tasks": report["tasks"],
            "baseline_model_input_tokens": base,
            "hashmarks_model_input_tokens": hm,
            "model_input_token_reduction": summary["average_model_input_token_reduction"],
        })

    aggregate_reduction = 1.0 - (total_hashmarks_tokens / total_baseline_tokens)

    # v2 adds replication/statistical authority without changing v1 semantics.
    # Repeated runs are grouped by an explicit replication_group.  Repetitions
    # never count as additional repository/task breadth; they only describe
    # within-task run-to-run variation.
    import math
    import random

    groups: dict[str, list[dict[str, Any]]] = {}
    for index, entry in enumerate(manifest["experiments"]):
        group = _nonempty(entry.get("replication_group"), f"experiment-set entry {index} replication_group", manifest_path)
        groups.setdefault(group, []).append(experiment_reports[index])
    min_repeats = manifest.get("replication_policy", {}).get("min_repeats_per_group", 3)
    if not isinstance(min_repeats, int) or min_repeats < 2:
        raise ValueError("replication_policy min_repeats_per_group must be an integer >= 2")
    confidence = manifest.get("replication_policy", {}).get("confidence", 0.95)
    if not isinstance(confidence, (int, float)) or not 0.5 < confidence < 1.0:
        raise ValueError("replication_policy confidence must be between 0.5 and 1.0")
    bootstrap_samples = manifest.get("replication_policy", {}).get("bootstrap_samples", 10000)
    if not isinstance(bootstrap_samples, int) or bootstrap_samples < 1000:
        raise ValueError("replication_policy bootstrap_samples must be an integer >= 1000")

    group_reports = []
    eligible_groups = 0
    for group_id in sorted(groups):
        rows = groups[group_id]
        reductions = [r["model_input_token_reduction"] for r in rows]
        eligible = len(rows) >= min_repeats
        if eligible:
            eligible_groups += 1
        group_reports.append({
            "replication_group": group_id,
            "repeat_count": len(rows),
            "replication_eligible": eligible,
            "mean_model_input_token_reduction": sum(reductions) / len(reductions),
            "min_model_input_token_reduction": min(reductions),
            "max_model_input_token_reduction": max(reductions),
        })

    # Deterministic paired bootstrap over experiment-level reductions.  This
    # interval is descriptive evidence for the exact retained experiment set;
    # it is not a population/generalization claim.
    ci = None
    if len(experiment_reports) >= 2:
        values = [r["model_input_token_reduction"] for r in experiment_reports]
        seed = int(hashlib.sha256(manifest_path.read_bytes()).hexdigest()[:16], 16)
        rng = random.Random(seed)
        means = []
        n = len(values)
        for _ in range(bootstrap_samples):
            means.append(sum(values[rng.randrange(n)] for _ in range(n)) / n)
        means.sort()
        alpha = (1.0 - float(confidence)) / 2.0
        lo = means[max(0, min(len(means)-1, int(math.floor(alpha * len(means)))))]
        hi = means[max(0, min(len(means)-1, int(math.ceil((1.0-alpha) * len(means))) - 1))]
        ci = {
            "method": "deterministic-experiment-bootstrap",
            "confidence": float(confidence),
            "samples": bootstrap_samples,
            "lower": lo,
            "upper": hi,
            "scope": "exact-retained-experiments-only",
        }
    replication = {
        "group_count": len(groups),
        "eligible_group_count": eligible_groups,
        "min_repeats_per_group": min_repeats,
        "groups": group_reports,
        "descriptive_confidence_interval": ci,
        "statistical_claim_eligible": bool(groups) and eligible_groups == len(groups) and ci is not None,
        "warning": "replication does not increase repository/task breadth and this interval does not establish population generalization",
    }

    internal_eligible = bool(experiment_reports)
    public_blockers: list[str] = []
    if len(experiment_reports) < PUBLIC_MIN_EXPERIMENTS:
        public_blockers.append(f"experiments {len(experiment_reports)} < required {PUBLIC_MIN_EXPERIMENTS}")
    if len(repositories) < PUBLIC_MIN_REPOSITORIES:
        public_blockers.append(f"repositories {len(repositories)} < required {PUBLIC_MIN_REPOSITORIES}")
    if len(task_keys) < PUBLIC_MIN_UNIQUE_TASKS:
        public_blockers.append(f"unique_tasks {len(task_keys)} < required {PUBLIC_MIN_UNIQUE_TASKS}")

    return {
        "schema": REPORT_SCHEMA,
        "experiment_set_id": manifest["experiment_set_id"],
        "manifest_sha256": _sha256(manifest_path),
        "model_identity": manifest["model_identity"],
        "model_config_identity": manifest["model_config_identity"],
        "task_policy_identity": manifest["task_policy_identity"],
        "benchmark_protocol_identity": manifest.get("benchmark_protocol_identity"),
        "experiments": experiment_reports,
        "summary": {
            "experiment_count": len(experiment_reports),
            "repository_count": len(repositories),
            "unique_task_count": len(task_keys),
            "run_count": len(run_ids),
            "baseline_model_input_tokens": total_baseline_tokens,
            "hashmarks_model_input_tokens": total_hashmarks_tokens,
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


def gate(report: dict[str, Any], *, require_public_broad_claim: bool = False) -> list[str]:
    summary = report["summary"]
    failures: list[str] = []
    if not summary["internal_controlled_claim_eligible"]:
        failures.append("experiment set is not eligible for an internal controlled claim")
    if require_public_broad_claim and not summary["public_broad_claim_eligible"]:
        failures.extend(summary["public_broad_claim_blockers"])
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and aggregate canonical Hashmarks real-agent experiments")
    parser.add_argument("experiment_set", type=Path, help="hashmarks.agent-experiment-set.v2 manifest")
    parser.add_argument("--allow-missing-raw-evidence", action="store_true", help="do not require retained raw grader/provider evidence bytes")
    parser.add_argument("--require-public-broad-claim", action="store_true", help="fail unless fixed public breadth floors are met")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = run_experiment_set(args.experiment_set, strict_raw_evidence=not args.allow_missing_raw_evidence)
    failures = gate(payload, require_public_broad_claim=args.require_public_broad_claim)
    if failures:
        raise SystemExit("experiment-set gate failed: " + "; ".join(failures))
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
