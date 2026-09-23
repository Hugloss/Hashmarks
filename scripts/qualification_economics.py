from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from hashmarks._command_output import log_command_output
from hashmarks.qualification_economics import qualification_classification_economics

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render Hashmarks qualification-classification economics."
    )
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    value = qualification_classification_economics(Path(args.root))
    log_command_output(logger, json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
