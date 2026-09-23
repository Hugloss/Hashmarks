from __future__ import annotations

import argparse
import json
import logging
import shutil
import tempfile
import time
from pathlib import Path

from hashmarks import InputManifest
from hashmarks._command_output import log_command_output
from hashmarks.engine import IdentityEngine

logger = logging.getLogger(__name__)


def timed(fn):
    started = time.perf_counter()
    value = fn()
    return value, time.perf_counter() - started


def measure(seconds: dict[str, float], name: str, fn):
    value, seconds[name] = timed(fn)
    return value


def create_repo(root: Path, count: int, files_per_dir: int) -> list[str]:
    src = root / "src"
    src.mkdir(parents=True)
    paths: list[str] = []
    for i in range(count):
        bucket = i // files_per_dir
        directory = src / f"d{bucket:06d}"
        directory.mkdir(exist_ok=True)
        path = directory / f"f{i:07d}.txt"
        path.write_text(f"value={i}\n")
        paths.append(path.relative_to(root).as_posix())
    return paths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", type=int, default=10_000)
    parser.add_argument("--files-per-dir", type=int, default=250)
    parser.add_argument(
        "--manifest", choices=("directory", "files"), default="directory"
    )
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    root = Path(tempfile.mkdtemp(prefix="hashmarks-bench-"))
    try:
        paths = create_repo(root, args.files, args.files_per_dir)
        engine = IdentityEngine(root)
        manifest = (
            engine.manifest(["src"])
            if args.manifest == "directory"
            else InputManifest(tuple(paths))
        )

        seconds: dict[str, float] = {}
        identities = {
            "cold": measure(seconds, "cold", lambda: engine.input_root(manifest)),
            "hot": measure(
                seconds, "hot_unchanged", lambda: engine.input_root(manifest)
            ),
        }

        engine.merkle.drop_hot_cache()
        identities["warm_scan"] = measure(
            seconds,
            "warm_scan_hot_cache_dropped",
            lambda: engine.input_root(manifest),
        )

        changed = root / paths[len(paths) // 2]
        changed.write_text("changed\n")
        engine.record_changes([changed.relative_to(root)])
        identities["one_edit"] = measure(
            seconds, "one_file_edit", lambda: engine.input_root(manifest)
        )

        batch_paths = paths[: min(100, len(paths))]
        for rel in batch_paths:
            (root / rel).write_text("batch-change\n")
        engine.record_changes(batch_paths)
        identities["batch_edit"] = measure(
            seconds, "up_to_100_file_edit", lambda: engine.input_root(manifest)
        )

        measure(
            seconds,
            "strong_verify",
            lambda: engine.input_root(manifest, verify=True),
        )
        engine.close()

        fresh = IdentityEngine(root)
        fresh_manifest = (
            fresh.manifest(["src"])
            if args.manifest == "directory"
            else InputManifest(tuple(paths))
        )
        measure(
            seconds,
            "fresh_process_warm_cache",
            lambda: fresh.input_root(fresh_manifest),
        )
        fresh.close()

        result = {
            "files": args.files,
            "files_per_dir": args.files_per_dir,
            "manifest": args.manifest,
            "seconds": seconds,
            "identity_checks": {
                "cold_equals_hot": identities["cold"] == identities["hot"],
                "cold_equals_warm_scan": identities["cold"] == identities["warm_scan"],
                "one_edit_changes_identity": identities["one_edit"]
                != identities["cold"],
                "batch_edit_changes_identity": identities["batch_edit"]
                != identities["one_edit"],
            },
            "workspace": str(root) if args.keep else None,
        }
        log_command_output(logger, json.dumps(result, indent=2, sort_keys=True))
    finally:
        if not args.keep:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
