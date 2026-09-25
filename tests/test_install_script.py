from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _asset(directory: Path) -> tuple[Path, bytes]:
    payload = b"#!/bin/sh\nprintf '%s\\n' 'hashmarks version 9.9.9'\n"
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

    env = _environment(tmp_path, source)
    env["HASHMARKS_VERSION"] = "9.9.9"
    result = subprocess.run(
        ["sh", str(_root() / "install.sh")],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    installed = tmp_path / "bin" / "hashmarks"
    assert installed.read_bytes() == payload
    assert os.access(installed, os.X_OK)
    assert "Hashmarks installed:" in result.stdout
    assert list((tmp_path / "bin").glob(".hashmarks-install.*")) == []


def test_installer_preserves_working_binary_on_requested_version_mismatch(
    tmp_path: Path,
) -> None:
    source = tmp_path / "release"
    source.mkdir()
    _asset(source)

    install_dir = tmp_path / "bin"
    install_dir.mkdir()
    installed = install_dir / "hashmarks"
    previous = b"#!/bin/sh\nprintf '%s\\n' 'hashmarks version 1.0.0'\n"
    installed.write_bytes(previous)
    installed.chmod(0o755)

    env = _environment(tmp_path, source)
    env["HASHMARKS_VERSION"] = "1.2.3"
    result = subprocess.run(
        ["sh", str(_root() / "install.sh")],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert (
        "requested version 1.2.3 but downloaded binary reports 9.9.9"
        in result.stderr
    )
    assert installed.read_bytes() == previous
    assert list(install_dir.glob(".hashmarks-install.*")) == []


def test_installer_preserves_working_binary_when_candidate_smoke_fails(
    tmp_path: Path,
) -> None:
    source = tmp_path / "release"
    source.mkdir()
    payload = b"#!/bin/sh\nexit 23\n"
    asset = source / "hashmarks-linux-x86_64"
    asset.write_bytes(payload)
    asset.chmod(0o755)
    digest = hashlib.sha256(payload).hexdigest()
    (source / "hashmarks-linux-x86_64.sha256").write_text(
        f"{digest}  hashmarks-linux-x86_64\n",
        encoding="utf-8",
    )

    install_dir = tmp_path / "bin"
    install_dir.mkdir()
    installed = install_dir / "hashmarks"
    previous = b"#!/bin/sh\nexit 0\n"
    installed.write_bytes(previous)
    installed.chmod(0o755)

    result = subprocess.run(
        ["sh", str(_root() / "install.sh")],
        env=_environment(tmp_path, source),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "downloaded binary failed version smoke test" in result.stderr
    assert installed.read_bytes() == previous
    assert list(install_dir.glob(".hashmarks-install.*")) == []


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
