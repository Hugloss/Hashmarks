from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from hashmarks import Identity


def timed(fn):
    started = time.perf_counter()
    value = fn()
    return value, time.perf_counter() - started


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark an existing repository without generating files")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--input", action="append", required=True)
    parser.add_argument("--mode", choices=("auto", "local", "daemon"), default="auto")
    parser.add_argument("--hot-requests", type=int, default=20)
    args = parser.parse_args()

    with Identity(Path(args.workspace), mode=args.mode) as identity:
        first, first_s = timed(lambda: identity.snapshot(*args.input))
        hot = []
        last = first
        for _ in range(args.hot_requests):
            last, elapsed = timed(lambda: identity.snapshot(*args.input))
            hot.append(elapsed)
        result = {
            "workspace": str(identity.workspace),
            "inputs": args.input,
            "requested_mode": args.mode,
            "active_mode": last.mode,
            "seconds": {
                "first": first_s,
                "hot_min": min(hot),
                "hot_avg": sum(hot) / len(hot),
            },
            "identity_checks": {"hot_equals_first": last.hash == first.hash},
        }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
