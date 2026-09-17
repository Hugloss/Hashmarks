from __future__ import annotations

import sys
from pathlib import Path


def windows_mounted_wsl_path(path: Path) -> bool:
    """Return whether *path* uses WSL's conventional Windows-drive mount surface."""
    resolved = path.resolve()
    parts = resolved.parts
    return len(parts) >= 3 and parts[0] == "/" and parts[1] == "mnt" and len(parts[2]) == 1 and parts[2].isalpha()


def main() -> int:
    root = Path.cwd()
    if windows_mounted_wsl_path(root):
        print(
            "qualification-performance-warning: repository is under /mnt/<drive>; "
            "correctness results remain valid, but performance/economics timings are not "
            "comparable to native Linux filesystem baselines. Prefer /home/... for profiling.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
