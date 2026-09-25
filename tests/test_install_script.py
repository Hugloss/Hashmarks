from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _asset(directory: Path) -> tuple[Path, bytes]:
    payload = b"#!/bin/sh\nprintf '%s\\n' '{\"version\": \"test\"}'\n"
    asset = directory / "hashmarks-linux-x86_64"
    asset.write_bytes(payload)
    asset.chmod(0o755)
    digest = hashlib.sha256(payload).hexdigest()
    (directory / "hashmarks-linux-x86_64.sha256").write_text(
        f"{digest}  hashmarks-linux-x86_64\n",
        encoding="utf-8",
    )
    return asset, payload


def _environment(tmp_path: Path, source: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(tmp_path / "home")
    env["HASHMARKS_INSTALL_DIR"] = str(tmp_path / "bin")
    env["HASHMARKS_DOWNLOAD_BASE_URL"] = source.as_uri()
    return env


def test_installer_downloads_verifies_and_installs_release_binary(
    tmp_path: Path,
) -> None:
    source = tmp_path / "release"
    source.mkdir()
    _, payload = _asset(source)

    result = subprocess.run(
        ["sh", str(_root() / "install.sh")],
        env=_environment(tmp_path, source),
        check=True,
        capture_output=True,
        text=True,
    )

    installed = tmp_path / "bin" / "hashmarks"
    assert installed.read_bytes() == payload
    assert os.access(installed, os.X_OK)
    assert "Hashmarks installed:" in result.stdout


def test_installer_rejects_release_binary_with_wrong_checksum(tmp_path: Path) -> None:
    source = tmp_path / "release"
    source.mkdir()
    _asset(source)
    (source / "hashmarks-linux-x86_64.sha256").write_text(
        f"{'0' * 64}  hashmarks-linux-x86_64\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        ["sh", str(_root() / "install.sh")],
        env=_environment(tmp_path, source),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "SHA-256 verification failed" in result.stderr
    assert not (tmp_path / "bin" / "hashmarks").exists()
