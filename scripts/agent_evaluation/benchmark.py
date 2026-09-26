from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "benchmarks" / "benchmark.toml"


def _load(path: Path, profile: str) -> tuple[list[str], dict[str, str]]:
    data = tomllib.loads(path.read_text())
    profiles = data.get("profile", {})
    if profile not in profiles:
        available = ", ".join(sorted(profiles))
        raise SystemExit(f"unknown benchmark profile {profile!r}; choose: {available}")
    row = profiles[profile]
    module = row.get("module")
    args = row.get("args", [])
    env = row.get("env", {})
    if not isinstance(module, str) or not module:
        raise SystemExit(f"profile {profile!r} requires a module")
    if not isinstance(args, list) or not all(isinstance(x, str) for x in args):
        raise SystemExit(f"profile {profile!r} args must be strings")
    if not isinstance(env, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in env.items()
    ):
        raise SystemExit(f"profile {profile!r} env must be string pairs")
    return [sys.executable, "-m", module, *args], env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a checked-in Hashmarks benchmark profile."
    )
    parser.add_argument("profile", nargs="?", default="local")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(\n        "--show", action="store_true", help="print the resolved command only"\n    )
    ns = parser.parse_args(argv)
    command, profile_env = _load(ns.config, ns.profile)
    if ns.show:
        sys.stdout.write(" ".join(command) + "\\n")
        return 0
    env = dict(os.environ)
    env.update(profile_env)
    return subprocess.run(command, cwd=ROOT, env=env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
