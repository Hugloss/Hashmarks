from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
import time
from pathlib import Path

from hashmarks._command_output import log_command_output

from ._version import __version__
from .client import (
    DaemonCompatibilityError,
    DaemonUnavailableError,
    IdentityClient,
    StateDirectoryError,
    prepare_default_state_dir,
)
from .daemon import IdentityDaemon
from .errors import UserFacingError
from .identity import RepositoryIdentity, RepositoryIdentityMode
from .paths import canonical_host_path
from .release_update import (
    ReleaseCheckError,
    ReleaseInfo,
    StandaloneUpgradeError,
    automatic_check_allowed,
    delegate_standalone_upgrade,
    fetch_latest_release,
    periodic_release_check,
    standalone_upgrade_command,
)

logger = logging.getLogger(__name__)


def _version(args) -> int:
    del args
    _print({"version": __version__})
    return 0


def _workspace(value: str) -> Path:
    return canonical_host_path(value)


def _client(args) -> IdentityClient:
    return IdentityClient(
        args.workspace, state_dir=args.state_dir, timeout=args.timeout
    )


def _print(value) -> None:
    log_command_output(logger, json.dumps(value, indent=2, sort_keys=True))


def _text(*values: object, file=None) -> None:
    for value in values:
        log_command_output(logger, value, file=file)


def _interactive_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _render_release(release: ReleaseInfo, *, announce: bool) -> None:
    if announce:
        _text("A newer Hashmarks version is available.", "")
    _text(
        f"Hashmarks {release.current_version}",
        f"Latest: {release.latest_version}",
    )


def _render_external_upgrade_guidance(latest_version: str) -> None:
    tag = f"v{latest_version}"
    _text(
        "",
        "This installation is managed outside Hashmarks.",
        "Use the native mechanism that installed or owns this Hashmarks installation.",
        "Hashmarks does not detect, validate, or certify that package-manager state.",
        "",
        "Exact GitHub release (wheel and source distribution):",
        f"    https://github.com/Hugloss/Hashmarks/releases/tag/{tag}",
        "",
        "No changes were made.",
    )


def _render_standalone_upgrade(
    release: ReleaseInfo,
    command: str,
    *,
    announce: bool,
) -> None:
    _render_release(release, announce=announce)
    _text(
        "",
        "This installation uses the Hashmarks standalone installer.",
        "",
        "Native upgrade command:",
        "",
        f"    {command}",
    )


def _prompt_upgrade() -> bool:
    _text("", "[1] Upgrade now", "[2] Skip for now")
    return input("Select [1/2]: ").strip() == "1"


def _delegate_selected_standalone_upgrade(command: str) -> None:
    _text(
        "",
        "Delegating update to the Hashmarks standalone installer.",
        "Hashmarks exits before the installer mutates the installation.",
        "Restart Hashmarks after the upgrade completes.",
    )
    delegate_standalone_upgrade(command)


def _upgrade(args) -> int:
    del args
    release = fetch_latest_release(__version__, timeout=5.0)
    if not release.update_available:
        if release.current_version == release.latest_version:
            _text(f"Hashmarks {release.current_version} is up to date.")
        else:
            _text(
                f"Hashmarks {release.current_version} is newer than the latest "
                f"stable release {release.latest_version}.",
                "No changes were made.",
            )
        return 0

    command = standalone_upgrade_command(release.latest_version)
    if command is None:
        _render_release(release, announce=False)
        _render_external_upgrade_guidance(release.latest_version)
        return 0

    _render_standalone_upgrade(release, command, announce=False)
    if not _interactive_terminal():
        _text("", "No changes were made.")
        return 0
    if not _prompt_upgrade():
        _text("Upgrade skipped.")
        return 0
    _delegate_selected_standalone_upgrade(command)
    return 0


def _maybe_offer_periodic_upgrade() -> None:
    interactive = _interactive_terminal()
    if not automatic_check_allowed(interactive=interactive):
        return
    release = periodic_release_check(
        __version__,
        interactive=interactive,
    )
    if release is None:
        return
    upgrade_command = standalone_upgrade_command(release.latest_version)
    if upgrade_command is None:
        _render_release(release, announce=True)
        _render_external_upgrade_guidance(release.latest_version)
        return

    _render_standalone_upgrade(release, upgrade_command, announce=True)
    if not _prompt_upgrade():
        _text("Upgrade skipped for now.")
        return
    _delegate_selected_standalone_upgrade(upgrade_command)


def _daemon_serve_command(workspace: Path, state: Path) -> list[str]:
    command = [sys.executable]
    if not getattr(sys, "frozen", False):
        command.extend(["-m", "hashmarks.cli"])
    command.extend(
        [
            "--workspace",
            str(workspace),
            "--state-dir",
            str(state),
            "daemon",
            "serve",
        ]
    )
    return command


def _daemon_start(args) -> int:
    client = _client(args)
    try:
        status = client.status()
    except DaemonUnavailableError:
        pass
    except DaemonCompatibilityError as exc:
        raise SystemExit(
            f"an incompatible identity daemon is already present at {client.socket_path}: {exc}; "
            "stop/terminate the old daemon before starting this version"
        ) from exc
    else:
        _print({"already_running": True, **status})
        return 0

    workspace = canonical_host_path(args.workspace)
    state = (
        prepare_default_state_dir(workspace)
        if args.state_dir is None
        else canonical_host_path(args.state_dir)
    )
    state.mkdir(parents=True, exist_ok=True)
    log_path = state / "identity-daemon.log"
    log = log_path.open("ab", buffering=0)
    cmd = _daemon_serve_command(workspace, state)
    subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
        start_new_session=True,
        close_fds=True,
    )
    log.close()
    deadline = time.monotonic() + args.start_timeout
    while time.monotonic() < deadline:
        try:
            status = client.status()
        except (DaemonUnavailableError, DaemonCompatibilityError):
            time.sleep(0.05)
            continue
        _print({"started": True, "log": str(log_path), **status})
        return 0
    raise SystemExit(f"daemon did not become ready; see {log_path}")


def _daemon_serve(args) -> int:
    daemon = IdentityDaemon(args.workspace, state_dir=args.state_dir)
    daemon.serve_forever()
    return 0


def _daemon_status(args) -> int:
    value = _client(args).status()
    _print(value)
    return 0


def _daemon_stop(args) -> int:
    value = _client(args).stop()
    _print(value)
    return 0


def _snapshot(args) -> int:
    with RepositoryIdentity(
        args.workspace,
        state_dir=args.state_dir,
        mode=args.mode,
        timeout=args.timeout,
    ) as identity:
        snapshot = identity.snapshot(*args.input, verify=args.verify)
    _print(snapshot.as_dict())
    return 0


def _stats(args) -> int:
    with RepositoryIdentity(
        args.workspace,
        state_dir=args.state_dir,
        mode=args.mode,
        timeout=args.timeout,
    ) as identity:
        value = identity.stats()
    _print(value)
    return 0


def _doctor(args) -> int:
    with RepositoryIdentity(
        args.workspace,
        state_dir=args.state_dir,
        mode=args.mode,
        timeout=args.timeout,
    ) as identity:
        _print(identity.doctor())
    return 0


def _mcp(args) -> int:
    from .mcp_server import run_stdio

    run_stdio(args.workspace, state_dir=args.state_dir)
    return 0


def _installed_hashmarks_executable() -> Path:
    if getattr(sys, "frozen", False):
        return canonical_host_path(sys.executable)
    resolved = shutil.which("hashmarks")
    if resolved is None:
        raise UserFacingError(
            "hashmarks executable is not on PATH; install the standalone binary first"
        )
    return canonical_host_path(resolved)


def _opencode_effective_hashmarks_command(
    opencode: str,
) -> tuple[list[str] | None, str | None]:
    result = subprocess.run(
        [opencode, "debug", "config"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None, f"opencode debug config exited {result.returncode}"
    try:
        config = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None, "opencode debug config did not return JSON"
    if not isinstance(config, dict):
        return None, "opencode debug config did not return an object"
    mcp = config.get("mcp")
    if not isinstance(mcp, dict):
        return None, "effective OpenCode config has no MCP object"
    servers = mcp.get("servers")
    entries = servers if isinstance(servers, dict) else mcp
    hashmarks = entries.get("hashmarks") if isinstance(entries, dict) else None
    if not isinstance(hashmarks, dict):
        return None, "effective OpenCode config has no hashmarks MCP server"
    command = hashmarks.get("command")
    if not (
        isinstance(command, list)
        and command
        and all(isinstance(value, str) and value for value in command)
    ):
        return None, "effective OpenCode hashmarks MCP command is not inspectable"
    return list(command), None


def _effective_command_uses_installed_hashmarks(
    command: list[str],
    executable: Path,
) -> bool:
    if command[1:] != ["--workspace", ".", "mcp"]:
        return False
    configured = command[0]
    resolved = (
        shutil.which(configured)
        if "/" not in configured and "\\" not in configured
        else configured
    )
    if resolved is None:
        return False
    try:
        return canonical_host_path(resolved).samefile(executable)
    except OSError:
        return False


def _install(args) -> int:
    if not args.opencode:
        raise UserFacingError("choose a host to register, for example --opencode")
    opencode = shutil.which("opencode")
    if opencode is None:
        raise UserFacingError("opencode executable is not on PATH")
    executable = _installed_hashmarks_executable()
    command = [
        opencode,
        "mcp",
        "add",
        "hashmarks",
        "--",
        str(executable),
        "--workspace",
        ".",
        "mcp",
    ]
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise UserFacingError(
            f"OpenCode rejected Hashmarks MCP registration (exit {result.returncode})"
        )
    effective_command, diagnostic = _opencode_effective_hashmarks_command(opencode)
    payload = {
        "host": "opencode",
        "registered": True,
        "hashmarks": str(executable),
        "workspace": ".",
    }
    if effective_command is None:
        payload["effective_registration"] = "unverified"
        payload["diagnostic"] = diagnostic
    elif _effective_command_uses_installed_hashmarks(
        effective_command,
        executable,
    ):
        payload["effective_registration"] = "active"
    else:
        payload["effective_registration"] = "shadowed"
        payload["effective_command"] = effective_command
        payload["warning"] = (
            "OpenCode's effective project configuration shadows the installed "
            "Hashmarks registration; Hashmarks did not modify project configuration."
        )
    _print(payload)
    return 0


def _add_mode_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--mode",
        choices=tuple(mode.value for mode in RepositoryIdentityMode),
        default=RepositoryIdentityMode.AUTO.value,
        help="auto uses a running daemon and safely falls back to local identity",
    )


def _add_common_arguments(
    parser: argparse.ArgumentParser, *, inherited: bool = False
) -> None:
    default = argparse.SUPPRESS if inherited else "."
    parser.add_argument("--workspace", default=default)
    parser.add_argument(
        "--state-dir",
        default=argparse.SUPPRESS if inherited else None,
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=argparse.SUPPRESS if inherited else 30.0,
    )


def _add_daemon_cli(sub) -> None:
    version = sub.add_parser("version")
    version.set_defaults(func=_version, automatic_update_check=False)

    daemon = sub.add_parser("daemon")
    daemon.set_defaults(automatic_update_check=False)
    daemon_sub = daemon.add_subparsers(dest="daemon_command", required=True)
    start = daemon_sub.add_parser("start")
    _add_common_arguments(start, inherited=True)
    start.add_argument("--start-timeout", type=float, default=60.0)
    start.set_defaults(func=_daemon_start)
    serve = daemon_sub.add_parser("serve")
    _add_common_arguments(serve, inherited=True)
    serve.set_defaults(func=_daemon_serve)
    status = daemon_sub.add_parser("status")
    _add_common_arguments(status, inherited=True)
    status.set_defaults(func=_daemon_status)
    stop = daemon_sub.add_parser("stop")
    _add_common_arguments(stop, inherited=True)
    stop.set_defaults(func=_daemon_stop)


def _add_identity_cli(sub) -> None:
    snapshot = sub.add_parser("snapshot")
    _add_common_arguments(snapshot, inherited=True)
    _add_mode_argument(snapshot)
    snapshot.add_argument("--input", action="append", required=True)
    snapshot.add_argument("--verify", action="store_true")
    snapshot.set_defaults(func=_snapshot, automatic_update_check=True)

    stats = sub.add_parser("stats")
    _add_common_arguments(stats, inherited=True)
    _add_mode_argument(stats)
    stats.set_defaults(func=_stats, automatic_update_check=True)

    doctor = sub.add_parser("doctor")
    _add_common_arguments(doctor, inherited=True)
    _add_mode_argument(doctor)
    doctor.set_defaults(func=_doctor, automatic_update_check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hashmarks")
    parser.add_argument(
        "--version",
        action="version",
        version=f"hashmarks version {__version__}",
    )
    _add_common_arguments(parser)
    parser.set_defaults(automatic_update_check=False)
    sub = parser.add_subparsers(dest="command", required=True)
    _add_daemon_cli(sub)
    _add_identity_cli(sub)
    mcp = sub.add_parser(
        "mcp", help="serve this workspace as a local read-only MCP stdio server"
    )
    _add_common_arguments(mcp, inherited=True)
    mcp.set_defaults(func=_mcp, automatic_update_check=False)
    install = sub.add_parser(
        "install", help="register the installed Hashmarks executable with agent hosts"
    )
    install.add_argument("--opencode", action="store_true")
    install.set_defaults(func=_install, automatic_update_check=True)
    upgrade = sub.add_parser(
        "upgrade",
        help="check the latest release and explicitly hand standalone installs to the existing installer",
    )
    upgrade.set_defaults(func=_upgrade, automatic_update_check=False)
    from .repository_cli import add_repository_cli

    add_repository_cli(sub, add_common_arguments=_add_common_arguments)
    args = parser.parse_args(argv)
    try:
        if args.automatic_update_check:
            _maybe_offer_periodic_upgrade()
        args.workspace = _workspace(args.workspace)
        if args.state_dir is not None:
            state = Path(args.state_dir)
            if not state.is_absolute():
                state = args.workspace / state
            args.state_dir = canonical_host_path(state)
        return int(args.func(args))
    except (
        UserFacingError,
        DaemonUnavailableError,
        DaemonCompatibilityError,
        StateDirectoryError,
        ReleaseCheckError,
        StandaloneUpgradeError,
    ) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    raise SystemExit(main())
