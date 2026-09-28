from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_RELEASE_API = "https://api.github.com/repos/Hugloss/Hashmarks/releases/latest"
_RELEASE_DOWNLOAD = "https://github.com/Hugloss/Hashmarks/releases/download"
_CHECK_INTERVAL_SECONDS = 24 * 60 * 60
_LOCK_STALE_SECONDS = 5 * 60
_MAX_RELEASE_RESPONSE_BYTES = 1024 * 1024
_RELEASE_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_TRUE_VALUES = {"1", "true", "yes", "on"}
_AUTOMATIC_SKIP_COMMANDS = {"daemon", "mcp", "upgrade", "version"}


class ReleaseCheckError(RuntimeError):
    """Latest-release metadata could not be obtained safely."""


class UpgradeDelegationError(RuntimeError):
    """The installation owner could not be delegated to safely."""


@dataclass(frozen=True)
class ReleaseInfo:
    current_version: str
    latest_version: str

    @property
    def update_available(self) -> bool:
        return _version_key(self.latest_version) > _version_key(self.current_version)


@dataclass(frozen=True)
class InstallationOwner:
    kind: str
    label: str
    command: tuple[str, ...] | None


def _version_key(version: str) -> tuple[int, int, int]:
    if not _RELEASE_VERSION.fullmatch(version):
        raise ValueError(f"not a stable Hashmarks release version: {version}")
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


def _strip_tag(tag: str) -> str:
    version = tag[1:] if tag.startswith("v") else tag
    _version_key(version)
    return version


def _request(url: str) -> Request:
    return Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "hashmarks-update-check",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )


def _read_bounded_response(response, *, limit: int) -> bytes:
    payload = response.read(limit + 1)
    if len(payload) > limit:
        raise ReleaseCheckError("release response exceeded the bounded size")
    return payload


def _fetch_json(url: str, *, timeout: float, limit: int) -> object:
    try:
        with urlopen(_request(url), timeout=timeout) as response:
            payload = _read_bounded_response(response, limit=limit)
        return json.loads(payload)
    except (
        HTTPError,
        URLError,
        TimeoutError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ReleaseCheckError("could not read Hashmarks release metadata") from exc


def fetch_latest_release(
    current_version: str,
    *,
    timeout: float = 1.0,
) -> ReleaseInfo:
    try:
        _version_key(current_version)
    except ValueError as exc:
        raise ReleaseCheckError("current Hashmarks version is not a stable release") from exc
    payload = _fetch_json(
        _RELEASE_API,
        timeout=timeout,
        limit=_MAX_RELEASE_RESPONSE_BYTES,
    )
    if not isinstance(payload, dict):
        raise ReleaseCheckError("latest release metadata is not a JSON object")
    if payload.get("draft") is True or payload.get("prerelease") is True:
        raise ReleaseCheckError("latest release metadata is not a stable release")
    tag = payload.get("tag_name")
    if not isinstance(tag, str):
        raise ReleaseCheckError("latest release metadata has no release tag")
    try:
        latest = _strip_tag(tag)
    except ValueError as exc:
        raise ReleaseCheckError("latest release tag is not a stable version") from exc
    return ReleaseInfo(current_version=current_version, latest_version=latest)


def _cache_path(environ: Mapping[str, str] = os.environ) -> Path:
    if os.name == "nt":
        root = environ.get("LOCALAPPDATA")
        if root:
            return Path(root) / "Hashmarks" / "update-check.json"
    root = environ.get("XDG_CACHE_HOME")
    if root:
        return Path(root) / "hashmarks" / "update-check.json"
    return Path.home() / ".cache" / "hashmarks" / "update-check.json"


def _cache_is_fresh(path: Path, *, now: float) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        checked_at = float(payload["checked_at"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return False
    age = now - checked_at
    return 0 <= age < _CHECK_INTERVAL_SECONDS


def _write_cache(path: Path, *, now: float, latest_version: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    payload = {"checked_at": now, "latest_version": latest_version}
    try:
        temporary.write_text(
            json.dumps(payload, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _remove_stale_lock(path: Path, *, now: float) -> None:
    try:
        stale = now - path.stat().st_mtime >= _LOCK_STALE_SECONDS
    except OSError:
        return
    if not stale:
        return
    try:
        path.unlink()
    except OSError:
        pass


@contextmanager
def _periodic_check_lock(cache: Path, *, now: float) -> Iterator[bool]:
    lock = cache.with_name(f"{cache.name}.lock")
    try:
        lock.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        yield False
        return
    _remove_stale_lock(lock, now=now)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except OSError:
        yield False
        return
    try:
        os.write(fd, f"{os.getpid()}\n".encode())
        os.close(fd)
        fd = -1
        yield True
    finally:
        if fd >= 0:
            os.close(fd)
        try:
            lock.unlink()
        except OSError:
            pass


def _truthy(value: str | None) -> bool:
    return value is not None and value.strip().lower() in _TRUE_VALUES


def automatic_check_allowed(
    *,
    command: str,
    interactive: bool,
    environ: Mapping[str, str] = os.environ,
) -> bool:
    if command in _AUTOMATIC_SKIP_COMMANDS or not interactive:
        return False
    if _truthy(environ.get("HASHMARKS_NO_UPDATE_CHECK")):
        return False
    return not (_truthy(environ.get("CI")) or _truthy(environ.get("GITHUB_ACTIONS")))


def periodic_release_check(
    current_version: str,
    *,
    command: str,
    interactive: bool,
    environ: Mapping[str, str] = os.environ,
    now: float | None = None,
    timeout: float = 1.0,
) -> ReleaseInfo | None:
    if not automatic_check_allowed(
        command=command,
        interactive=interactive,
        environ=environ,
    ):
        return None
    checked_at = time.time() if now is None else now
    cache = _cache_path(environ)
    if _cache_is_fresh(cache, now=checked_at):
        return None
    with _periodic_check_lock(cache, now=checked_at) as acquired:
        if not acquired or _cache_is_fresh(cache, now=checked_at):
            return None
        try:
            release = fetch_latest_release(current_version, timeout=timeout)
        except ReleaseCheckError:
            release = None
        try:
            _write_cache(
                cache,
                now=checked_at,
                latest_version=None if release is None else release.latest_version,
            )
        except OSError:
            pass
    if release is None or not release.update_available:
        return None
    return release


def detect_installation_owner() -> InstallationOwner:
    if getattr(sys, "frozen", False):
        return InstallationOwner("standalone", "Hashmarks standalone installer", None)
    prefix = str(Path(sys.prefix).resolve()).replace("\\", "/").casefold()
    if "/uv/tools/hashmarks" in prefix:
        return InstallationOwner("uv", "uv", ("uv", "tool", "upgrade", "hashmarks"))
    if "/pipx/venvs/hashmarks" in prefix:
        return InstallationOwner("pipx", "pipx", ("pipx", "upgrade", "hashmarks"))
    if sys.prefix != sys.base_prefix:
        return InstallationOwner("environment", "the current Python environment", None)
    return InstallationOwner("unknown", "an unknown installation owner", None)


def manual_upgrade_command(owner: InstallationOwner, latest_version: str) -> str | None:
    _version_key(latest_version)
    if owner.command is not None:
        return " ".join(owner.command)
    tag = f"v{latest_version}"
    if owner.kind == "standalone" and os.name == "nt":
        url = f"{_RELEASE_DOWNLOAD}/{tag}/install.ps1"
        return (
            f"$env:HASHMARKS_VERSION='{latest_version}'; "
            f"Invoke-RestMethod {url} | Invoke-Expression"
        )
    if owner.kind == "standalone":
        url = f"{_RELEASE_DOWNLOAD}/{tag}/install.sh"
        return f"curl -fsSL {url} | HASHMARKS_VERSION={latest_version} sh"
    return None


def _standalone_exec_target(latest_version: str) -> tuple[str, tuple[str, ...]]:
    owner = InstallationOwner("standalone", "Hashmarks standalone installer", None)
    command = manual_upgrade_command(owner, latest_version)
    if command is None:
        raise UpgradeDelegationError("standalone upgrade command is unavailable")
    if os.name == "nt":
        executable = shutil.which("pwsh") or shutil.which("powershell")
        if executable is None:
            raise UpgradeDelegationError("PowerShell is required for the installer")
        return executable, (
            executable,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            command,
        )
    executable = shutil.which("sh")
    if executable is None:
        raise UpgradeDelegationError("sh is required for the installer")
    if shutil.which("curl") is None:
        raise UpgradeDelegationError("curl is required for the installer")
    return executable, (executable, "-c", command)


def can_delegate_upgrade(owner: InstallationOwner) -> bool:
    if owner.kind == "standalone":
        if os.name == "nt":
            return bool(shutil.which("pwsh") or shutil.which("powershell"))
        return shutil.which("sh") is not None and shutil.which("curl") is not None
    return owner.command is not None and shutil.which(owner.command[0]) is not None


def _exec_owner(
    executable: str,
    argv: tuple[str, ...],
    environment: Mapping[str, str],
) -> None:
    try:
        os.execve(executable, list(argv), dict(environment))
    except OSError as exc:
        raise UpgradeDelegationError(
            f"could not start native installation owner: {Path(executable).name}"
        ) from exc


def delegate_upgrade(
    owner: InstallationOwner,
    latest_version: str,
) -> None:
    _version_key(latest_version)
    environment = os.environ.copy()
    environment["HASHMARKS_VERSION"] = latest_version
    if owner.kind == "standalone":
        executable, argv = _standalone_exec_target(latest_version)
        _exec_owner(executable, argv, environment)
        return
    if owner.command is None:
        raise UpgradeDelegationError("Hashmarks cannot mutate this installation")
    executable = shutil.which(owner.command[0])
    if executable is None:
        raise UpgradeDelegationError(
            f"{owner.command[0]} is not on PATH; run the printed command manually"
        )
    argv = (executable, *owner.command[1:])
    _exec_owner(executable, argv, environment)
