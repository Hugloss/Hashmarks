"""Prove that Windows standalone delegation really replaces the caller process."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from hashmarks.release_update import delegate_standalone_upgrade


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", type=Path)
    args = parser.parse_args()
    if args.child is not None:
        destination = str(args.child).replace("'", "''")
        delegate_standalone_upgrade(
            f"Set-Content -LiteralPath '{destination}' -Value 'handoff-complete'"
        )
        raise RuntimeError(
            "Windows delegation returned instead of replacing the process"
        )

    with tempfile.TemporaryDirectory(prefix="hashmarks-windows-handoff-") as folder:
        marker = Path(folder) / "handoff.txt"
        subprocess.run(
            [sys.executable, __file__, "--child", str(marker)],
            check=True,
            timeout=30,
        )
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        if marker.read_text(encoding="utf-8").strip() != "handoff-complete":
            raise RuntimeError("Windows standalone handoff did not run PowerShell")
    sys.stdout.write("Hashmarks Windows process handoff: PASS\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
