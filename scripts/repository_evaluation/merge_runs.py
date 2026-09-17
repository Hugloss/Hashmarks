from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Mapping

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.repository_evaluation.common import RUN_SCHEMA, load_json, write_json


def merge_runs(runs: list[Mapping[str, object]]) -> dict[str, Any]:
    if not runs:
        raise ValueError("at least one repository evaluation run is required")
    first = runs[0]
    identity_keys = (
        "suite", "protocol_identity", "repository_identity",
        "producer_implementation_identity", "producer_artifact_identity", "cases_sha256",
    )
    for run in runs[1:]:
        for key in identity_keys:
            if run.get(key) != first.get(key):
                raise ValueError(f"repository evaluation run identity mismatch: {key}")
    rows: dict[str, object] = {}
    shard_count = max(int(run.get("shard_count") or 1) for run in runs)
    seen_shards: set[int] = set()
    for run in runs:
        if int(run.get("shard_count") or 1) != shard_count:
            raise ValueError("repository evaluation shard-count mismatch")
        seen_shards.add(int(run.get("shard_index") or 0))
        for row in run.get("cases", []):
            if not isinstance(row, Mapping):
                raise ValueError("repository evaluation run case must be an object")
            case_id = str(row.get("id") or "")
            if not case_id or case_id in rows:
                raise ValueError(f"duplicate or empty repository evaluation case: {case_id}")
            rows[case_id] = dict(row)
    expected_shards = set(range(shard_count))
    return {
        "schema": RUN_SCHEMA,
        **{key: first.get(key) for key in identity_keys},
        "codemap_generation": first.get("codemap_generation"),
        "reused_cases": sum(int(run.get("reused_cases") or 0) for run in runs),
        "new_cases": sum(int(run.get("new_cases") or 0) for run in runs),
        "timing_comparable": all(bool(run.get("timing_comparable")) for run in runs),
        "elapsed_ns": sum(int(run.get("elapsed_ns") or 0) for run in runs),
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
