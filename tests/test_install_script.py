from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _write_asset(directory: Path, payload: bytes) -> tuple[Path, bytes]:
    asset = directory / "hashmarks-linux-x86_64"
    asset.write_bytes(payload)
    asset.chmod(0o755)
    digest = hashlib.sha256(payload).hexdigest()
    (directory / "hashmarks-linux-x86_64.sha256").write_text(
        f"{digest}  hashmarks-linux-x86_64\n",
        encoding="utf-8",
    )
    return asset, payload


def _asset(directory: Path) -> tuple[Path, bytes]:
    return _write_asset(
        directory,
        b"#!/bin/sh\nprintf '%s\\n' 'hashmarks version 9.9.9'\n",
    )


def _environment(tmp_path: Path, source: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(tmp_path / "home")
    env["HASHMARKS_INSTALL_DIR"] = str(tmp_path / "bin")
    env["HASHMARKS_DOWNLOAD_BASE_URL"] = source.as_uri()
    return env


def _working_binary(install_dir: Path) -> tuple[Path, bytes]:
    install_dir.mkdir(parents=True, exist_ok=True)
    installed = install_dir / "hashmarks"
    previous = b"#!/bin/sh\nprintf '%s\\n' 'hashmarks version 1.0.0'\n"
    installed.write_bytes(previous)
    installed.chmod(0o755)
    return installed, previous


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


def test_installer_accepts_v_prefixed_explicit_release_version(tmp_path: Path) -> None:
    source = tmp_path / "release"
    source.mkdir()
    _, payload = _asset(source)

    env = _environment(tmp_path, source)
    env["HASHMARKS_VERSION"] = "v9.9.9"
    subprocess.run(
        ["sh", str(_root() / "install.sh")],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert (tmp_path / "bin" / "hashmarks").read_bytes() == payload


def test_installer_rejects_non_release_version_before_download(tmp_path: Path) -> None:
    source = tmp_path / "release"
    source.mkdir()
    _asset(source)
    env = _environment(tmp_path, source)
    env["HASHMARKS_VERSION"] = "../v9.9.9"

    result = subprocess.run(
        ["sh", str(_root() / "install.sh")],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "invalid release version" in result.stderr
    assert not (tmp_path / "bin" / "hashmarks").exists()


def test_installer_preserves_working_binary_on_requested_version_mismatch(
    tmp_path: Path,
) -> None:
    source = tmp_path / "release"
    source.mkdir()
    _asset(source)

    install_dir = tmp_path / "bin"
    installed, previous = _working_binary(install_dir)

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
        "requested version 1.2.3 but downloaded binary reports 9.9.9" in result.stderr
    )
    assert installed.read_bytes() == previous
    assert list(install_dir.glob(".hashmarks-install.*")) == []


def test_installer_preserves_working_binary_when_candidate_smoke_fails(
    tmp_path: Path,
) -> None:
    source = tmp_path / "release"
    source.mkdir()
    _write_asset(source, b"#!/bin/sh\nexit 23\n")

    install_dir = tmp_path / "bin"
    installed, previous = _working_binary(install_dir)

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


def test_installer_rejects_malformed_latest_version_output_without_replacement(
    tmp_path: Path,
) -> None:
    source = tmp_path / "release"
    source.mkdir()
    _write_asset(
        source,
        b"#!/bin/sh\nprintf '%s\\n' 'hashmarks version 9.9.9' 'unexpected'\n",
    )

    install_dir = tmp_path / "bin"
    installed, previous = _working_binary(install_dir)

    result = subprocess.run(
        ["sh", str(_root() / "install.sh")],
        env=_environment(tmp_path, source),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "invalid release version" in result.stderr
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


def test_installer_rejects_checksum_bound_to_different_asset_name(
    tmp_path: Path,
) -> None:
    source = tmp_path / "release"
    source.mkdir()
    _, payload = _asset(source)
    digest = hashlib.sha256(payload).hexdigest()
    (source / "hashmarks-linux-x86_64.sha256").write_text(
        f"{digest}  another-binary\n",
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
    assert "checksum entry names another-binary" in result.stderr
    assert not (tmp_path / "bin" / "hashmarks").exists()


def test_installer_preserves_working_binary_when_final_replace_fails(
    tmp_path: Path,
) -> None:
    source = tmp_path / "release"
    source.mkdir()
    _asset(source)

    install_dir = tmp_path / "bin"
    installed, previous = _working_binary(install_dir)
    tools = tmp_path / "tools"
    tools.mkdir()
    failing_mv = tools / "mv"
    failing_mv.write_text("#!/bin/sh\nexit 73\n", encoding="utf-8")
    failing_mv.chmod(0o755)

    env = _environment(tmp_path, source)
    env["PATH"] = os.pathsep.join((str(tools), env["PATH"]))
    result = subprocess.run(
        ["sh", str(_root() / "install.sh")],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 73
    assert installed.read_bytes() == previous
    assert list(install_dir.glob(".hashmarks-install.*")) == []


def test_installer_reports_path_shadowing_after_successful_upgrade(
    tmp_path: Path,
) -> None:
    source = tmp_path / "release"
    source.mkdir()
    _, payload = _asset(source)

    shadow_dir = tmp_path / "shadow"
    shadow_dir.mkdir()
    shadow = shadow_dir / "hashmarks"
    shadow.write_text(
        "#!/bin/sh\nprintf '%s\\n' 'hashmarks version 1.0.0'\n",
        encoding="utf-8",
    )
    shadow.chmod(0o755)

    env = _environment(tmp_path, source)
    env["HASHMARKS_VERSION"] = "9.9.9"
    env["PATH"] = os.pathsep.join((str(shadow_dir), env["PATH"]))
    result = subprocess.run(
        ["sh", str(_root() / "install.sh")],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    installed = tmp_path / "bin" / "hashmarks"
    assert installed.read_bytes() == payload
    assert (
        f"Warning: hashmarks on PATH resolves to {shadow}; installed target is {installed}"
        in result.stdout
    )


def test_installer_rejects_directory_at_install_target(tmp_path: Path) -> None:
    source = tmp_path / "release"
    source.mkdir()
    _asset(source)
    target = tmp_path / "bin" / "hashmarks"
    target.mkdir(parents=True)

    result = subprocess.run(
        ["sh", str(_root() / "install.sh")],
        env=_environment(tmp_path, source),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "install target exists but is not a file" in result.stderr
    assert target.is_dir()
