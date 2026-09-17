from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.benchmark_shards_lib import (
    create_manifest,
    load_manifest,
    merge_shards,
    pending_shards,
    run_next,
    run_warmup,
    warmup_complete,
    write_manifest,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic resumable benchmark shard runner")
    sub = parser.add_subparsers(dest="command_name", required=True)

    plan = sub.add_parser("plan", help="Create or verify an immutable shard plan")
    plan.add_argument("--total", type=int, required=True)
    plan.add_argument("--shard-size", type=int, default=20)
    plan.add_argument("--output-dir", type=Path, required=True)
    plan.add_argument("--id-field", default="id")
    plan.add_argument("--run-identity", required=True)
    plan.add_argument("--warmup-json", help="JSON array command executed once before shards")
    plan.add_argument("command", nargs=argparse.REMAINDER, help="Child command; supports {start} {end} {output} {index}")

    warm = sub.add_parser("warm", help="Execute and seal the planned warmup once")
    warm.add_argument("--output-dir", type=Path, required=True)
    warm.add_argument("--timeout-seconds", type=float)

    nxt = sub.add_parser("next", help="Execute exactly one pending shard")
    nxt.add_argument("--output-dir", type=Path, required=True)
    nxt.add_argument("--timeout-seconds", type=float)

    status = sub.add_parser("status", help="Show sealed/pending shard progress")
    status.add_argument("--output-dir", type=Path, required=True)

    merge = sub.add_parser("merge", help="Merge only when every planned shard is valid")
    merge.add_argument("--output-dir", type=Path, required=True)
    merge.add_argument("--aggregate-name", default="aggregate.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command_name == "plan":
        command = list(args.command)
        if command and command[0] == "--":
            command = command[1:]
        if not command:
            raise SystemExit("plan requires a child command after --")
        warmup = json.loads(args.warmup_json) if args.warmup_json else None
        if warmup is not None and (not isinstance(warmup, list) or not all(isinstance(x, str) for x in warmup)):
            raise SystemExit("--warmup-json must be a JSON array of strings")
        manifest = create_manifest(total=args.total, shard_size=args.shard_size, command=command, id_field=args.id_field, warmup_command=warmup, run_identity=args.run_identity)
        path = write_manifest(args.output_dir, manifest)
        print(path)
        return 0
    if args.command_name == "warm":
        changed = run_warmup(args.output_dir, timeout_seconds=args.timeout_seconds)
        print("warmed" if changed else "already-warm")
        return 0
    if args.command_name == "next":
        shard = run_next(args.output_dir, timeout_seconds=args.timeout_seconds)
        if shard is None:
            print("complete")
        else:
            print(f"sealed {shard.key} ({shard.count} rows)")
        return 0
    if args.command_name == "status":
        manifest = load_manifest(args.output_dir)
        pending = pending_shards(args.output_dir, manifest)
        total_shards = len(manifest["shards"])
        complete_shards = total_shards - len(pending)
        result = {
            "schema": manifest["schema"],
            "rows_total": manifest["total"],
            "shards_total": total_shards,
            "shards_complete": complete_shards,
            "shards_pending": len(pending),
            "next": pending[0].key if pending else None,
            "warmup_complete": warmup_complete(args.output_dir, manifest),
        }
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.command_name == "merge":
        path = merge_shards(args.output_dir, aggregate_name=args.aggregate_name)
        print(path)
        return 0
    raise AssertionError(args.command_name)


if __name__ == "__main__":
    raise SystemExit(main())
