from __future__ import annotations

import sys
from pathlib import Path

from hashmarks.cli import _daemon_serve_command


def test_frozen_cli_reenters_daemon_without_python_module_switch(
    monkeypatch,
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    command = _daemon_serve_command(Path("/repo"), Path("/state"))

    assert command == [
        sys.executable,
        "--workspace",
        "/repo",
        "--state-dir",
        "/state",
        "daemon",
        "serve",
    ]
