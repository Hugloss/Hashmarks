"""Native-pytest collection handoff for parallel *development CI* only.

This consumer partitions a proven complete native collection. Hashmarks owns
repository/test isolation evidence; GitHub Actions and ordinary pytest own
scheduling, processes, execution, failures and results.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

import pytest

from hashmarks._development.test_shards import ISOLATED_NODEIDS

SCHEMA = "hashmarks.ci-native-full-shards.v1"
SHARD_COUNT = 4


class _NativeCollector:
    def __init__(self) -> None:
        self.nodeids: list[str] = []

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        self.nodeids = [item.nodeid for item in session.items]


def _native_collection() -> list[str]:
    """Query pytest itself; static AST test names are never completeness proof."""
    collector = _NativeCollector()
    captured = io.StringIO()
    with redirect_stdout(captured), redirect_stderr(captured):
        code = pytest.main(["tests", "--collect-only", "-q"], plugins=[collector])
    if code != pytest.ExitCode.OK or not collector.nodeids:
        raise ValueError(
            "native pytest collection unavailable: " + captured.getvalue()[-2500:]
        )
    return collector.nodeids


def _identity(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _test_file(root: Path, nodeid: str) -> str:
    path = nodeid.split("::", 1)[0]
    candidate = Path(path)
    if "::" not in nodeid or candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"unsafe native pytest node: {nodeid}")
    if len(candidate.parts) < 2 or candidate.parts[0] != "tests":
        raise ValueError(f"pytest node outside the test domain: {nodeid}")
    if not candidate.name.startswith("test_") or candidate.suffix != ".py":
        raise ValueError(f"unrecognized pytest file: {nodeid}")
    if not (root / candidate).is_file():
        raise ValueError(f"missing native pytest file: {nodeid}")
    return candidate.as_posix()


def _test_function(nodeid: str) -> str:
    """Remove a pytest parameter case suffix, never an arbitrary test level."""
    return nodeid.split("[", 1)[0]


def _weight(root: Path, path: str, count: int) -> int:
    return count + min(60, (root / path).stat().st_size // 256)


def _empty_shards(count: int) -> list[dict[str, Any]]:
    return [
        {
            "index": index,
            "normal_args": [],
            "isolated_nodeids": [],
            "native_nodeids": [],
            "weight": 0,
        }
        for index in range(count)
    ]


def _least_loaded(shards: list[dict[str, Any]]) -> dict[str, Any]:
    return min(shards, key=lambda item: (item["weight"], item["index"]))


def _group_native_members(
    root: Path, nodeids: Sequence[str]
) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for nodeid in nodeids:
        path = _test_file(root, nodeid)
        grouped.setdefault(path, []).append(nodeid)
    return grouped


def _admit_isolation(
    nodeids: Sequence[str], isolated: Sequence[str]
) -> set[str]:
    required = set(isolated)
    observed = {
        _test_function(nodeid)
        for nodeid in nodeids
        if _test_function(nodeid) in required
    }
    if required != observed:
        raise ValueError("process-sensitive pytest membership changed")
    return required


def _assign_normal_members(
    root: Path,
    grouped: Mapping[str, list[str]],
    isolated: set[str],
    shards: list[dict[str, Any]],
) -> None:
    ordered = sorted(
        grouped.items(),
        key=lambda row: (-_weight(root, row[0], len(row[1])), row[0]),
    )
    for path, members in ordered:
        ordinary = [row for row in members if _test_function(row) not in isolated]
        if not ordinary:
            continue
        args = ordinary if len(ordinary) != len(members) else [path]
        shard = _least_loaded(shards)
        shard["normal_args"].extend(args)
        shard["native_nodeids"].extend(ordinary)
        shard["weight"] += _weight(root, path, len(ordinary))


def _assign_singletons(
    nodeids: Sequence[str], isolated: set[str], shards: list[dict[str, Any]]
) -> None:
    singles = sorted(row for row in nodeids if _test_function(row) in isolated)
    for nodeid in singles:
        shard = _least_loaded(shards)
        shard["isolated_nodeids"].append(nodeid)
        shard["native_nodeids"].append(nodeid)
        shard["weight"] += 10


def _validate_and_sort(
    shards: list[dict[str, Any]], nodeids: Sequence[str]
) -> None:
    assigned = [nodeid for shard in shards for nodeid in shard["native_nodeids"]]
    if sorted(assigned) != sorted(nodeids):
        raise ValueError("full-suite sharding lost or duplicated native members")
    for shard in shards:
        shard["normal_args"].sort()
        shard["isolated_nodeids"].sort()
        shard["native_nodeids"].sort()
    if any(not shard["native_nodeids"] for shard in shards):
        raise ValueError("a full-suite shard has no native pytest members")


def _build_plan(
    root: Path,
    nodeids: Sequence[str],
    *,
    isolated: Sequence[str] = ISOLATED_NODEIDS,
    shard_count: int = SHARD_COUNT,
) -> dict[str, Any]:
    """Partition all collected nodeids, retaining one process per isolated node."""
    if shard_count < 1 or not nodeids or len(set(nodeids)) != len(nodeids):
        raise ValueError("invalid or duplicate native pytest collection")
    grouped = _group_native_members(root, nodeids)
    isolated_names = _admit_isolation(nodeids, isolated)
    shards = _empty_shards(shard_count)
    _assign_normal_members(root, grouped, isolated_names, shards)
    _assign_singletons(nodeids, isolated_names, shards)
    _validate_and_sort(shards, nodeids)
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "candidate_sha": _git_head(root),
        "shard_count": shard_count,
        "native_collection_identity": _identity({"native_nodeids": sorted(nodeids)}),
        "native_test_count": len(nodeids),
        "shards": shards,
        "execution_authority": "external-native-pytest",
    }
    payload["plan_identity"] = _identity(payload)
    return payload


def _git_head(root: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
        timeout=30,
    ).strip()


def _bound_plan(root: Path, path: Path, *, shard_count: int) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    fresh = _build_plan(root, _native_collection(), shard_count=shard_count)
    if loaded != fresh:
        raise ValueError("shard evidence differs from current native collection")
    return fresh


def _nul(paths: Sequence[str], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(b"".join(path.encode("utf-8") + b"\0" for path in paths))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "emit"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--shards", type=int, default=SHARD_COUNT)
    parser.add_argument("--shard", type=int)
    parser.add_argument("--normal-output", type=Path)
    parser.add_argument("--isolated-output", type=Path)
    args = parser.parse_args()
    root = Path.cwd().resolve()
    if args.action == "plan":
        plan = _build_plan(root, _native_collection(), shard_count=args.shards)
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(
            json.dumps(plan, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        sys.stdout.write(
            json.dumps(
                {
                    "mode": "qualified-full-parallel",
                    "native_tests": plan["native_test_count"],
                    "shards": plan["shard_count"],
                },
                sort_keys=True,
            )
            + "\n"
        )
        return 0
    if (
        args.shard is None
        or args.normal_output is None
        or args.isolated_output is None
        or args.shard < 0
        or args.shard >= args.shards
    ):
        parser.error("emit requires a valid shard and both NUL output paths")
    plan = _bound_plan(root, args.manifest, shard_count=args.shards)
    row = plan["shards"][args.shard]
    _nul(row["normal_args"], args.normal_output)
    _nul(row["isolated_nodeids"], args.isolated_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
