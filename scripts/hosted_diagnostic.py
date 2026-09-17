from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "hashmarks.hosted-diagnostic.v1"
MANDATORY_MARKER = "not certification and not host_dns and not slow and not scale"


def _package_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _console_script() -> str | None:
    name = "hashmarks.exe" if os.name == "nt" else "hashmarks"
    candidate = Path(sys.executable).with_name(name)
    if candidate.is_file():
        return str(candidate)
    return None


def capabilities() -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "mode": "HOSTED-DIAGNOSTIC",
        "authoritative": False,
        "python": sys.version.split()[0],
        "interpreter": sys.executable,
        "pytest": _package_version("pytest"),
        "mcp_sdk": importlib.util.find_spec("mcp") is not None,
        "hashmarks_console_script": _console_script(),
        "git": shutil.which("git"),
        "uv": shutil.which("uv"),
        "platform": sys.platform,
        # External DNS/network is intentionally unavailable to the diagnostic test
        # contract even when the host happens to provide it. Tests that require it
        # must opt into host_dns and are never part of constrained-host evidence.
        "external_dns": False,
    }


def marker_expression(extra: str = "") -> str:
    extra = extra.strip()
    if not extra:
        return MANDATORY_MARKER
    return f"({MANDATORY_MARKER}) and ({extra})"


def _selected_nodes(shards: int, shard: int) -> tuple[str, ...]:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from hashmarks.test_shards import select

    return select(ROOT, shards, shard)


def _run_shard(shards: int, shard: int, *, extra_marker: str) -> int:
    nodes = _selected_nodes(shards, shard)
    if not nodes:
        print(f"--- HOSTED DIAGNOSTIC SHARD {shard + 1}/{shards}: EMPTY ---")
        return 0
    env = os.environ.copy()
    env["HASHMARKS_CONSTRAINED_HOST"] = "1"
    # Hosted runners often inject unrelated pytest plugins. Hashmarks has no pytest
    # plugin dependency, so diagnostic evidence deliberately disables host autoload.
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-m",
        marker_expression(extra_marker),
        *nodes,
    ]
    print(f"--- HOSTED DIAGNOSTIC SHARD {shard + 1}/{shards}: {len(nodes)} selected nodes ---", flush=True)
    code = subprocess.run(command, cwd=ROOT, env=env, check=False).returncode
    if code == 5:
        # Deterministic membership can legitimately contain only tests excluded by
        # the mandatory constrained-host marker policy (for example scale tests).
        print(f"--- HOSTED DIAGNOSTIC SHARD {shard + 1}/{shards}: POLICY-EXCLUDED ---")
        return 0
    return code


def _validate_range(shards: int, start: int, limit: int | None) -> tuple[int, int]:
    if shards < 1:
        raise ValueError("shards must be >= 1")
    if start < 0 or start >= shards:
        raise ValueError(f"start shard must be between 0 and {shards - 1}")
    if limit is not None and limit < 1:
        raise ValueError("limit must be >= 1")
    stop = shards if limit is None else min(shards, start + limit)
    return start, stop


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capability-aware constrained-host pytest runner")
    parser.add_argument("--shards", type=int, default=64)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--extra-marker", default="")
    parser.add_argument("--capabilities", action="store_true")
    args = parser.parse_args(argv)

    inventory = capabilities()
    if args.capabilities:
        print(json.dumps(inventory, indent=2, sort_keys=True))
        return 0
    if inventory["pytest"] is None:
        print("HASHMARKS HOSTED DIAGNOSTIC: ENVIRONMENT-BLOCKED (pytest unavailable)", file=sys.stderr)
        return 2

    try:
        start, stop = _validate_range(args.shards, args.start, args.limit)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(inventory, sort_keys=True))
    print(f"mandatory-marker={MANDATORY_MARKER}")
    if args.extra_marker.strip():
        print(f"extra-marker={args.extra_marker.strip()}")
    print(f"shards={args.shards} range={start}..{stop - 1}")

    for shard in range(start, stop):
        code = _run_shard(args.shards, shard, extra_marker=args.extra_marker)
        if code != 0:
            print(
                f"HASHMARKS HOSTED DIAGNOSTIC: FAIL (shard {shard}; reproduce with "
                f"HASHMARKS_CONSTRAINED_HOST=1 make test-diagnostic-shard DIAGNOSTIC_SHARD={shard})",
                file=sys.stderr,
            )
            return code

    if start == 0 and stop == args.shards:
        scope = "complete constrained-host selection"
    else:
        scope = f"bounded shard range {start}..{stop - 1}"
    print(f"HASHMARKS HOSTED DIAGNOSTIC: HOSTED-DIAGNOSTIC-PASSED ({scope})")
    print("This is diagnostic evidence only and is never native release/certification authority.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
