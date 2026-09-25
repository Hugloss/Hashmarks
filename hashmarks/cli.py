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
    default_state_dir,
)
from .daemon import IdentityDaemon
from .errors import UserFacingError
from .identity import RepositoryIdentity, RepositoryIdentityMode
from .paths import canonical_host_path

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
        default_state_dir(workspace)
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
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as exc:
        raise UserFacingError(
            f"OpenCode rejected Hashmarks MCP registration (exit {exc.returncode})"
        ) from exc
    _print(
        {
            "host": "opencode",
            "registered": True,
            "hashmarks": str(executable),
            "workspace": ".",
        }
    )
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
    version.set_defaults(func=_version)

    daemon = sub.add_parser("daemon")
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
    snapshot.set_defaults(func=_snapshot)

    stats = sub.add_parser("stats")
    _add_common_arguments(stats, inherited=True)
    _add_mode_argument(stats)
    stats.set_defaults(func=_stats)

    doctor = sub.add_parser("doctor")
    _add_common_arguments(doctor, inherited=True)
    _add_mode_argument(doctor)
    doctor.set_defaults(func=_doctor)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hashmarks")
    parser.add_argument(
        "--version",
        action="version",
        version=f"hashmarks version {__version__}",
    )
    _add_common_arguments(parser)
    sub = parser.add_subparsers(dest="command", required=True)
    _add_daemon_cli(sub)
    _add_identity_cli(sub)
    mcp = sub.add_parser(
        "mcp", help="serve this workspace as a local read-only MCP stdio server"
    )
    _add_common_arguments(mcp, inherited=True)
    mcp.set_defaults(func=_mcp)
    install = sub.add_parser(
        "install", help="register the installed Hashmarks executable with agent hosts"
    )
    install.add_argument("--opencode", action="store_true")
    install.set_defaults(func=_install)
    from .repository_cli import add_repository_cli

    add_repository_cli(sub, add_common_arguments=_add_common_arguments)
    args = parser.parse_args(argv)
    try:
        args.workspace = _workspace(args.workspace)
        if args.state_dir is not None:
            state = Path(args.state_dir)
            if not state.is_absolute():
                state = args.workspace / state
            args.state_dir = canonical_host_path(state)
        return int(args.func(args))
    except (UserFacingError, DaemonUnavailableError, DaemonCompatibilityError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    raise SystemExit(main())
