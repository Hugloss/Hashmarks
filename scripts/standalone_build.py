"""Build the canonical Hashmarks standalone executable."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYINSTALLER_REQUIREMENT = "pyinstaller==6.22.3"
PYINSTALLER_ARGS = (
    "--clean",
    "--noconfirm",
    "--onefile",
    "--name",
    "hashmarks",
    "--collect-all",
    "hashmarks",
    "scripts/hashmarks_entrypoint.py",
)


def _packager_install_command(python: str) -> tuple[str, ...]:
    return (
        "uv",
        "pip",
        "install",
        "--python",
        python,
        PYINSTALLER_REQUIREMENT,
    )


def _build_command(python: str) -> tuple[str, ...]:
    return (
        python,
        "-m",
        "PyInstaller",
        *PYINSTALLER_ARGS,
    )


def main() -> int:
    python = sys.executable
    subprocess.run(
        _packager_install_command(python),
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        _build_command(python),
        cwd=ROOT,
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
