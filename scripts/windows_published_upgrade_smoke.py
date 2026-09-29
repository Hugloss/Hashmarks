"""Exercise a published Windows CLI upgrade through its real interactive handoff."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.request import Request, urlopen

if TYPE_CHECKING:
    from winpty import PtyProcess

_TAG = re.compile(r"^v([0-9]+)\.([0-9]+)\.([0-9]+)$")
_WINDOWS_ASSET = "hashmarks-windows-x86_64.exe"


def _request(url: str, *, token: str | None = None) -> Request:
    headers = {"User-Agent": "hashmarks-published-upgrade-smoke"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return Request(url, headers=headers)


def _read_url(url: str, *, token: str | None = None) -> bytes:
    with urlopen(_request(url, token=token), timeout=30) as response:
        return response.read()


def _version(tag: str) -> tuple[int, int, int]:
    match = _TAG.fullmatch(tag)
    if match is None:
        raise ValueError(f"invalid stable release tag: {tag!r}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _eligible_windows_release(
    release: object, current: tuple[int, int, int]
) -> tuple[tuple[int, int, int], str] | None:
    if (
        not isinstance(release, dict)
        or release.get("draft")
        or release.get("prerelease")
    ):
        return None
    tag = release.get("tag_name")
    if not isinstance(tag, str) or _TAG.fullmatch(tag) is None:
        return None
    version = _version(tag)
    assets = release.get("assets")
    if not isinstance(assets, list) or version >= current:
        return None
    names = {item.get("name") for item in assets if isinstance(item, dict)}
    if {_WINDOWS_ASSET, "install.ps1", "SHA256SUMS.txt"} <= names:
        return version, tag
    return None


def _previous_windows_release(repository: str, current_tag: str) -> str | None:
    current = _version(current_tag)
    token = os.environ.get("GH_TOKEN")
    candidates: list[tuple[tuple[int, int, int], str]] = []
    page = 1
    while True:
        url = f"https://api.github.com/repos/{repository}/releases?per_page=100&page={page}"
        releases = json.loads(_read_url(url, token=token))
        if not isinstance(releases, list):
            raise ValueError("GitHub releases response is not a list")
        if not releases:
            break
        for release in releases:
            candidate = _eligible_windows_release(release, current)
            if candidate is not None:
                candidates.append(candidate)
        if len(releases) < 100:
            break
        page += 1
    return max(candidates)[1] if candidates else None


def _verified_installer(repository: str, tag: str, root: Path) -> Path:
    base = f"https://github.com/{repository}/releases/download/{tag}"
    installer = root / "prior-install.ps1"
    installer.write_bytes(_read_url(f"{base}/install.ps1"))
    sums = _read_url(f"{base}/SHA256SUMS.txt").decode("utf-8")
    matches = re.findall(r"(?m)^([0-9a-fA-F]{64})  install\.ps1$", sums)
    if len(matches) != 1:
        raise ValueError("previous release does not bind install.ps1 exactly once")
    if hashlib.sha256(installer.read_bytes()).hexdigest() != matches[0].lower():
        raise ValueError("previous release installer checksum mismatch")
    return installer


def _install_previous(installer: Path, tag: str, root: Path) -> Path:
    install_dir = root / "prior-bin"
    env = os.environ.copy()
    env["HASHMARKS_VERSION"] = tag.removeprefix("v")
    env["HASHMARKS_INSTALL_DIR"] = str(install_dir)
    env["HASHMARKS_SKIP_PATH_UPDATE"] = "1"
    subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(installer)],
        env=env,
        check=True,
    )
    target = install_dir / "hashmarks.exe"
    reported = subprocess.check_output([target, "--version"], text=True).strip()
    if reported != f"hashmarks version {tag.removeprefix('v')}":
        raise ValueError(f"previous Windows installation reports {reported!r}")
    return target


def _read_terminal(process: PtyProcess, output: queue.Queue[str | None]) -> None:
    try:
        while True:
            chunk = process.read(1024)
            if not chunk:
                break
            output.put(chunk)
    except EOFError:
        pass
    finally:
        output.put(None)


def _await_upgrade_choice(
    process: PtyProcess, output: queue.Queue[str | None], deadline: float
) -> str:
    transcript = ""
    selected = False
    while time.monotonic() < deadline:
        try:
            chunk = output.get(timeout=min(5, max(0.1, deadline - time.monotonic())))
        except queue.Empty:
            continue
        if chunk is None:
            break
        transcript += chunk
        if not selected and "Select [1/2]:" in transcript:
            process.write("1\r\n")
            selected = True
    if not selected:
        raise ValueError(f"Windows upgrade never offered consent: {transcript[-2000:]}")
    if process.isalive():
        raise TimeoutError(f"Windows upgrade did not exit: {transcript[-2000:]}")
    if "Delegating update to the Hashmarks standalone installer." not in transcript:
        raise ValueError(f"Windows CLI did not hand off: {transcript[-2000:]}")
    return transcript


def _await_installed_bytes(
    target: Path, expected_version: str, expected_hash: str, deadline: float
) -> None:
    while time.monotonic() < deadline:
        try:
            reported = subprocess.check_output(
                [target, "--version"], text=True, stderr=subprocess.DEVNULL
            ).strip()
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
        except (OSError, subprocess.CalledProcessError):
            reported, digest = "", ""
        if (
            reported == f"hashmarks version {expected_version}"
            and digest == expected_hash
        ):
            return
        time.sleep(0.5)
    raise TimeoutError("Windows upgrade did not install expected published bytes")


def _interactive_upgrade(
    target: Path, *, expected_version: str, expected_hash: str
) -> None:
    from winpty import PtyProcess

    env = os.environ.copy()
    env.pop("GH_TOKEN", None)
    env.pop("HASHMARKS_DOWNLOAD_BASE_URL", None)
    env["HASHMARKS_SKIP_PATH_UPDATE"] = "1"
    process = PtyProcess.spawn([str(target), "upgrade"], env=env)
    output: queue.Queue[str | None] = queue.Queue()
    threading.Thread(target=_read_terminal, args=(process, output), daemon=True).start()
    deadline = time.monotonic() + 180
    try:
        _await_upgrade_choice(process, output, deadline)
        # Windows execv can end the CLI before its PowerShell replacement finishes.
        _await_installed_bytes(target, expected_version, expected_hash, deadline)
    finally:
        if process.isalive():
            process.terminate(force=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    current_version = ".".join(map(str, _version(args.tag)))
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository) is None:
        raise ValueError("invalid GitHub repository")
    prior = _previous_windows_release(args.repository, args.tag)
    if prior is None:
        sys.stdout.write(
            "Windows interactive upgrade smoke: SKIP (no earlier Windows release)\n"
        )
        return 0
    args.root.mkdir(parents=True, exist_ok=True)
    installer = _verified_installer(args.repository, prior, args.root)
    target = _install_previous(installer, prior, args.root)
    current_binary = args.root / "bin" / "hashmarks.exe"
    expected_hash = hashlib.sha256(current_binary.read_bytes()).hexdigest()
    _interactive_upgrade(
        target, expected_version=current_version, expected_hash=expected_hash
    )
    sys.stdout.write(
        f"Windows interactive upgrade smoke: PASS ({prior} -> {args.tag})\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
