from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable

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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", type=int, default=10_000)
    parser.add_argument("--files-per-dir", type=int, default=250)
    parser.add_argument("--hot-requests", type=int, default=50)
    parser.add_argument(
        "--manifest", choices=("directory", "files"), default="directory"
    )
    parser.add_argument("--keep", action="store_true")
    return parser


def _start_daemon(
    root: Path,
) -> tuple[IdentityDaemon, threading.Thread, IdentityClient]:
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
    return daemon, thread, IdentityClient(root, socket_path=socket_path, timeout=60.0)


def _identity_request(
    client: IdentityClient, paths: list[str], manifest_mode: str
) -> tuple[Callable[[], dict], float]:
    if manifest_mode == "files":
        handle, registration_s = timed(
            lambda: client.register_manifest(InputManifest(tuple(paths)))
        )
        return lambda: client.input_root_manifest(handle), registration_s
    return lambda: client.input_root(["src"]), 0.0


def _measure_identities(
    root: Path,
    paths: list[str],
    daemon: IdentityDaemon,
    request_root: Callable[[], dict],
    hot_requests: int,
) -> dict:
    cold, cold_s = timed(request_root)
    hot_times: list[float] = []
    last = cold
    for _ in range(hot_requests):
        last, elapsed = timed(request_root)
        hot_times.append(elapsed)

    (root / paths[len(paths) // 2]).write_text("changed\n")
    # The filesystem watcher observes this asynchronously. The bounded wait makes
    # benchmark failures explicit without treating the wait as product authority.
    deadline = time.monotonic() + 2.0
    while (
        daemon.engine.changes.snapshot().state.value == "clean"
        and time.monotonic() < deadline
    ):
        time.sleep(0.001)
    edited, edit_s = timed(request_root)
    return {
        "cold": cold,
        "cold_s": cold_s,
        "hot_times": hot_times,
        "last": last,
        "edited": edited,
        "edit_s": edit_s,
    }


def _result(args, root: Path, measurements: dict, registration_s: float, status: dict):
    hot_times = measurements["hot_times"]
    return {
        "files": args.files,
        "files_per_dir": args.files_per_dir,
        "manifest": args.manifest,
        "seconds": {
            "manifest_registration": registration_s,
            "first_daemon_identity": measurements["cold_s"],
            "hot_ipc_min": min(hot_times),
            "hot_ipc_avg": sum(hot_times) / len(hot_times),
            "one_file_edit": measurements["edit_s"],
        },
        "identity_checks": {
            "hot_equals_cold": measurements["last"]["hash"]
            == measurements["cold"]["hash"],
            "edit_changes_identity": measurements["edited"]["hash"]
            != measurements["cold"]["hash"],
        },
        "daemon_status": status,
        "workspace": str(root) if args.keep else None,
    }


def main() -> None:
    args = _parser().parse_args()

    root = Path(tempfile.mkdtemp(prefix="hashmarks-daemon-bench-"))
    try:
        paths = create_repo(root, args.files, args.files_per_dir)
        daemon, thread, client = _start_daemon(root)
        request_root, registration_s = _identity_request(client, paths, args.manifest)
        measurements = _measure_identities(
            root, paths, daemon, request_root, args.hot_requests
        )
        status = client.status()
        client.stop()
        thread.join(timeout=5.0)
        result = _result(args, root, measurements, registration_s, status)
        print(json.dumps(result, indent=2, sort_keys=True))  # noqa: T201 - intentional command output
    finally:
        if not args.keep:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
