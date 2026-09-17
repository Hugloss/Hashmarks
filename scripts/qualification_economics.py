from __future__ import annotations

import argparse
import json
from pathlib import Path

from hashmarks.qualification_economics import qualification_classification_economics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render Hashmarks qualification-classification economics."
    )
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    value = qualification_classification_economics(Path(args.root))
    print(json.dumps(value, indent=2, sort_keys=True))  # noqa: T201 - intentional command output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
