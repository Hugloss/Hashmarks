"""CLI command dispatch does not eagerly construct identity/daemon owners."""

from __future__ import annotations

import subprocess
import sys

from hashmarks.client import RepositoryIdentityMode as ClientMode
from hashmarks.identity import RepositoryIdentityMode as FacadeMode


def test_identity_modes_are_a_single_public_contract() -> None:
    assert ClientMode is FacadeMode
    assert [mode.value for mode in ClientMode] == ["auto", "local", "daemon"]


def test_cli_dispatch_import_keeps_identity_engine_and_daemon_lazy() -> None:
    """A real cold Python process must not pre-load unused identity owners."""
    code = (
        "import sys\n"
        "import hashmarks.cli as cli\n"
        "assert 'hashmarks.engine' not in sys.modules\n"
        "assert 'hashmarks.daemon' not in sys.modules\n"
        "try:\n"
        "    cli.main(['--version'])\n"
        "except SystemExit as exit_code:\n"
        "    assert exit_code.code == 0\n"
        "else:\n"
        "    raise AssertionError('expected argparse --version exit')\n"
        "assert 'hashmarks.engine' not in sys.modules\n"
        "assert 'hashmarks.daemon' not in sys.modules\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "hashmarks version" in result.stdout
