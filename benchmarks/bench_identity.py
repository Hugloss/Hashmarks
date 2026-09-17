from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
from pathlib import Path

from hashmarks import IdentityEngine, InputManifest


def timed(fn):
    started = time.perf_counter()
    value = fn()
    return value, time.perf_counter() - started


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
    parser.add_argument("--manifest", choices=("directory", "files"), default="directory")
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

        cold, cold_s = timed(lambda: engine.input_root(manifest))
        hot, hot_s = timed(lambda: engine.input_root(manifest))

        engine.merkle.drop_hot_cache()
        warm_scan, warm_scan_s = timed(lambda: engine.input_root(manifest))

        changed = root / paths[len(paths) // 2]
        changed.write_text("changed\n")
        engine.record_changes([changed.relative_to(root)])
        one_edit, one_edit_s = timed(lambda: engine.input_root(manifest))

        batch_paths = paths[: min(100, len(paths))]
        for rel in batch_paths:
            (root / rel).write_text("batch-change\n")
        engine.record_changes(batch_paths)
        batch_edit, batch_edit_s = timed(lambda: engine.input_root(manifest))

        _verified, verify_s = timed(lambda: engine.input_root(manifest, verify=True))
        engine.close()

        fresh = IdentityEngine(root)
        fresh_manifest = (
            fresh.manifest(["src"])
            if args.manifest == "directory"
            else InputManifest(tuple(paths))
        )
        _restart, restart_s = timed(lambda: fresh.input_root(fresh_manifest))
        fresh.close()

        result = {
            "files": args.files,
            "files_per_dir": args.files_per_dir,
            "manifest": args.manifest,
            "seconds": {
                "cold": cold_s,
                "hot_unchanged": hot_s,
                "warm_scan_hot_cache_dropped": warm_scan_s,
                "one_file_edit": one_edit_s,
                "up_to_100_file_edit": batch_edit_s,
                "strong_verify": verify_s,
                "fresh_process_warm_cache": restart_s,
            },
            "identity_checks": {
                "cold_equals_hot": cold == hot,
                "cold_equals_warm_scan": cold == warm_scan,
                "one_edit_changes_identity": one_edit != cold,
                "batch_edit_changes_identity": batch_edit != one_edit,
            },
            "workspace": str(root) if args.keep else None,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
    finally:
        if not args.keep:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
