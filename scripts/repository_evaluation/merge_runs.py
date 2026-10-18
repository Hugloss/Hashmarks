from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.repository_evaluation.common import RUN_SCHEMA, load_json, write_json

_IDENTITY_KEYS = (
    "suite",
    "protocol_identity",
    "repository_identity",
    "producer_implementation_identity",
    "producer_artifact_identity",
    "cases_sha256",
)


def _require_matching_identity(
    runs: Sequence[Mapping[str, object]], first: Mapping[str, object]
) -> None:
    for run in runs[1:]:
        for key in _IDENTITY_KEYS:
            if run.get(key) != first.get(key):
                raise ValueError(f"repository evaluation run identity mismatch: {key}")


def _integer(run: Mapping[str, object], key: str, default: int = 0) -> int:
    value = run.get(key) or default
    if not isinstance(value, (int, float, str)):
        raise ValueError(f"repository evaluation {key} must be numeric")
    return int(value)


def _merge_membership(
    runs: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], int, set[int]]:
    rows: dict[str, object] = {}
    shard_count = max(_integer(run, "shard_count", 1) for run in runs)
    seen_shards: set[int] = set()
    for run in runs:
        if _integer(run, "shard_count", 1) != shard_count:
            raise ValueError("repository evaluation shard-count mismatch")
        seen_shards.add(_integer(run, "shard_index"))
        cases = run.get("cases", [])
        if not isinstance(cases, list):
            raise ValueError("repository evaluation cases must be a list")
        for row in cases:
            if not isinstance(row, Mapping):
                raise ValueError("repository evaluation run case must be an object")
            case_id = str(row.get("id") or "")
            if not case_id or case_id in rows:
                raise ValueError(
                    f"duplicate or empty repository evaluation case: {case_id}"
                )
            rows[case_id] = dict(row)
    return rows, shard_count, seen_shards


def merge_runs(runs: Sequence[Mapping[str, object]]) -> dict[str, Any]:
    if not runs:
        raise ValueError("at least one repository evaluation run is required")
    first = runs[0]
    _require_matching_identity(runs, first)
    rows, shard_count, seen_shards = _merge_membership(runs)
    expected_shards = set(range(shard_count))
    return {
        "schema": RUN_SCHEMA,
        **{key: first.get(key) for key in _IDENTITY_KEYS},
        "codemap_generation": first.get("codemap_generation"),
        "reused_cases": sum(_integer(run, "reused_cases") for run in runs),
        "new_cases": sum(_integer(run, "new_cases") for run in runs),
        "timing_comparable": all(bool(run.get("timing_comparable")) for run in runs),
        "elapsed_ns": sum(_integer(run, "elapsed_ns") for run in runs),
        "shard_count": shard_count,
        "merged_shards": sorted(seen_shards),
        "complete": seen_shards == expected_shards,
        "cases": [rows[key] for key in sorted(rows)],
        "authority": "repository-intelligence-measurement-only",
        "execution_authority": "external",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runs = [load_json(path, schema=RUN_SCHEMA) for path in args.run]
    write_json(args.output, merge_runs(runs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
