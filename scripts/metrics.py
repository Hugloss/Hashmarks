from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
import tomllib
from pathlib import Path

from hashmarks import RepositoryIdentity
from hashmarks.codemap import CodeMap

SCHEMA = "fastidentity.metrics.v1"


def _run_json(argv: list[str], *, cwd: Path) -> dict:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        env=os.environ.copy(),
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"metrics command failed ({completed.returncode}): {' '.join(argv)}\n{completed.stderr.strip()}"
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"metrics command did not return JSON: {' '.join(argv)}\n{completed.stdout[-2000:]}"
        ) from exc


def _timed(fn):
    started = time.perf_counter()
    value = fn()
    return value, time.perf_counter() - started


def _repo_inputs(root: Path) -> list[str]:
    candidates = ["hashmarks", "tests", "pyproject.toml", "uv.lock"]
    return [value for value in candidates if (root / value).exists()]







def _codemap_probe(root: Path) -> dict:
    with CodeMap(root) as codemap:
        first, first_s = _timed(codemap.sync)
        second, second_s = _timed(codemap.sync)
        hits, find_s = _timed(lambda: codemap.find("Identity impact", limit=10))
        pack, context_s = _timed(lambda: codemap.context("Identity impact", token_budget=1200, limit=10))
        stats = codemap.status()
    return {
        "seconds": {
            "sync": first_s,
            "hot_sync": second_s,
            "find": find_s,
            "context": context_s,
        },
        "parsed": first.parsed_artifacts,
        "hot_parsed": second.parsed_artifacts,
        "files": stats["files"],
        "symbols": stats["symbols"],
        "edges": stats["edges"],
        "find_hits": len(hits),
        "context_tokens": pack.estimated_tokens,
        "context_confidence": pack.confidence,
        "context_abstained": pack.abstained,
    }


def _uv_version(root: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["uv", "--version"],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout.strip() or None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect a reproducible Hashmarks development baseline"
    )
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--files", type=int, default=10_000)
    parser.add_argument("--files-per-dir", type=int, default=250)
    parser.add_argument("--hot-requests", type=int, default=20)
    parser.add_argument("--skip-daemon", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()

    root = Path(args.workspace).resolve()
    python = sys.executable
    repo_inputs = _repo_inputs(root)
    generated_at = time.time()
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))

    repo_cmd = [python, "benchmarks/bench_repo.py", "--workspace", str(root), "--mode", "local"]
    for value in repo_inputs:
        repo_cmd.extend(["--input", value])
    repo_cmd.extend(["--hot-requests", str(args.hot_requests)])

    result: dict[str, object] = {
        "schema": SCHEMA,
        "generated_at_unix": generated_at,
        "project": {"name": project["project"]["name"], "version": project["project"]["version"]},
        "environment": {
            "python": sys.version.split()[0],
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "uv": _uv_version(root),
        },
        "parameters": {
            "files": args.files,
            "files_per_dir": args.files_per_dir,
            "hot_requests": args.hot_requests,
            "daemon": not args.skip_daemon,
        },
        "repository": _run_json(repo_cmd, cwd=root) if repo_inputs else None,
        "identity": {
            "directory": _run_json(
                [
                    python,
                    "benchmarks/bench_identity.py",
                    "--files",
                    str(args.files),
                    "--files-per-dir",
                    str(args.files_per_dir),
                    "--manifest",
                    "directory",
                ],
                cwd=root,
            ),
            "files": _run_json(
                [
                    python,
                    "benchmarks/bench_identity.py",
                    "--files",
                    str(args.files),
                    "--files-per-dir",
                    str(args.files_per_dir),
                    "--manifest",
                    "files",
                ],
                cwd=root,
            ),
        },
        "codemap": _codemap_probe(root),
    }

    if not args.skip_daemon:
        result["daemon"] = {
            "directory": _run_json(
                [
                    python,
                    "benchmarks/bench_daemon.py",
                    "--files",
                    str(args.files),
                    "--files-per-dir",
                    str(args.files_per_dir),
                    "--hot-requests",
                    str(args.hot_requests),
                    "--manifest",
                    "directory",
                ],
                cwd=root,
            ),
            "files": _run_json(
                [
                    python,
                    "benchmarks/bench_daemon.py",
                    "--files",
                    str(args.files),
                    "--files-per-dir",
                    str(args.files_per_dir),
                    "--hot-requests",
                    str(args.hot_requests),
                    "--manifest",
                    "files",
                ],
                cwd=root,
            ),
        }

    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = root / output
    else:
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(generated_at))
        output = root / ".hashmarks" / "metrics" / f"baseline-{stamp}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    output.write_text(payload, encoding="utf-8")
    if args.output is None:
        latest = output.parent / "latest.json"
        latest.write_text(payload, encoding="utf-8")

    print(json.dumps({"ok": True, "output": str(output), "metrics": result}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
