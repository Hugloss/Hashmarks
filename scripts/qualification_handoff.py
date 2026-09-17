from __future__ import annotations

import argparse
import json
from pathlib import Path

from hashmarks.qualification_units import native_qualification_handoff


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render native Hashmarks qualification handoff evidence."
    )
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    value = native_qualification_handoff(Path(args.root))
    print(json.dumps(value, indent=2, sort_keys=True))  # noqa: T201 - intentional command output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
