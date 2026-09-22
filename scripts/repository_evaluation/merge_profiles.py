from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.repository_evaluation.common import write_json
from scripts.repository_evaluation.profile_cases import (
    PAIRED_PROFILE_SCHEMA,
    PROFILE_SCHEMA,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


def _identity_fields(schema: object) -> list[str]:
    common = [
        "schema",
        "suite",
        "cases_sha256",
        "producer_implementation_identity",
        "warmups",
        "shard_count",
    ]
    if schema == PROFILE_SCHEMA:
        return [*common, "samples", "repository_identity"]
    if schema == PAIRED_PROFILE_SCHEMA:
        return [
            *common,
            "pairs",
            "max_control_mad_pct",
            "repository_identity_a",
            "repository_identity_b",
        ]
    raise ValueError("unsupported profile schema")


def _merged_rows(profiles: list[Mapping[str, object]]) -> list[dict[str, object]]:
    rows = []
    seen = set()
    for doc in sorted(profiles, key=lambda item: int(item.get("shard_index") or 0)):
        for row in doc.get("cases", []):
            case_id = str(row["id"])
            if case_id in seen:
                raise ValueError("duplicate profile case")
            seen.add(case_id)
            rows.append(dict(row))
    return rows


def merge_profiles(profiles: list[Mapping[str, object]]) -> dict[str, Any]:
    if not profiles:
        raise ValueError("no profiles to merge")
    first = profiles[0]
    identity_fields = _identity_fields(first.get("schema"))
    for doc in profiles[1:]:
        if any(doc.get(key) != first.get(key) for key in identity_fields):
            raise ValueError("profile identity mismatch")
    shard_count = int(first.get("shard_count") or 1)
    indices = [int(doc.get("shard_index") or 0) for doc in profiles]
    if len(set(indices)) != len(indices):
        raise ValueError("duplicate profile shard")
    if sorted(indices) != list(range(shard_count)):
        raise ValueError("incomplete profile shards")
    rows = _merged_rows(profiles)
    out = {key: first.get(key) for key in identity_fields}
    out.update(
        {
            "shard_count": shard_count,
            "shard_index": None,
            "complete": True,
            "cases": sorted(rows, key=lambda r: str(r["id"])),
            "authority": "performance-measurement-only",
        }
    )
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("profiles", nargs="+", type=Path)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    docs = []
    for path in a.profiles:
        import json

        value = json.loads(path.read_text())
        schema = value.get("schema")
        if schema not in {PROFILE_SCHEMA, PAIRED_PROFILE_SCHEMA}:
            raise ValueError(f"unsupported schema in {path}")
        docs.append(value)
    write_json(a.output, merge_profiles(docs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
