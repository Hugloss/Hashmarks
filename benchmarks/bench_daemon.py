from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import threading
import time
from pathlib import Path

from hashmarks.client import IdentityClient
from hashmarks.daemon import IdentityDaemon
from hashmarks.inputs import InputManifest


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
    parser.add_argument("--hot-requests", type=int, default=50)
    parser.add_argument(
        "--manifest", choices=("directory", "files"), default="directory"
    )
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    root = Path(tempfile.mkdtemp(prefix="hashmarks-daemon-bench-"))
    try:
        paths = create_repo(root, args.files, args.files_per_dir)
        state = root / ".hashmarks"
        socket_path = state / "identity.sock"
        daemon = IdentityDaemon(root, state_dir=state, socket_path=socket_path)
        thread = threading.Thread(target=daemon.serve_forever, daemon=True)
        thread.start()

        deadline = time.monotonic() + 60.0
        while not socket_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        if not socket_path.exists():
            raise RuntimeError("daemon did not start")

        client = IdentityClient(root, socket_path=socket_path, timeout=60.0)
        manifest_registration_s = 0.0
        if args.manifest == "files":
            manifest = InputManifest(tuple(paths))
            handle, manifest_registration_s = timed(
                lambda: client.register_manifest(manifest)
            )

            def request_root():
                return client.input_root_manifest(handle)
        else:

            def request_root():
                return client.input_root(["src"])

        cold, cold_s = timed(request_root)

        hot_times: list[float] = []
        last = cold
        for _ in range(args.hot_requests):
            last, elapsed = timed(request_root)
            hot_times.append(elapsed)

        changed = root / paths[len(paths) // 2]
        changed.write_text("changed\n")
        # The real filesystem watcher daemon will observe this asynchronously. Wait until
        # its tracker leaves CLEAN, bounded so benchmark failures are explicit.
        deadline = time.monotonic() + 2.0
        while (
            daemon.engine.changes.snapshot().state.value == "clean"
            and time.monotonic() < deadline
        ):
            time.sleep(0.001)
        edited, edit_s = timed(request_root)

        status = client.status()
        client.stop()
        thread.join(timeout=5.0)

        result = {
            "files": args.files,
            "files_per_dir": args.files_per_dir,
            "manifest": args.manifest,
            "seconds": {
                "manifest_registration": manifest_registration_s,
                "first_daemon_identity": cold_s,
                "hot_ipc_min": min(hot_times),
                "hot_ipc_avg": sum(hot_times) / len(hot_times),
                "one_file_edit": edit_s,
            },
            "identity_checks": {
                "hot_equals_cold": last["hash"] == cold["hash"],
                "edit_changes_identity": edited["hash"] != cold["hash"],
            },
            "daemon_status": status,
            "workspace": str(root) if args.keep else None,
        }
        print(json.dumps(result, indent=2, sort_keys=True))  # noqa: T201 - intentional command output
    finally:
        if not args.keep:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
