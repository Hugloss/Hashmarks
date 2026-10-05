from __future__ import annotations

from scripts import standalone_build


def test_standalone_build_owns_packager_version_and_exact_argv() -> None:
    python = "/candidate/.venv/bin/python"

    assert standalone_build._packager_install_command(python) == (
        "uv",
        "pip",
        "install",
        "--python",
        python,
        "pyinstaller==6.22.3",
    )
    assert standalone_build._build_command(python) == (
        python,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--onefile",
        "--name",
        "hashmarks",
        "--collect-all",
        "hashmarks",
        "scripts/hashmarks_entrypoint.py",
    )
