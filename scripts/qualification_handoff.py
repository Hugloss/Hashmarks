from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from hashmarks._command_output import log_command_output
from hashmarks.qualification_units import (
    native_qualification_handoff,
    validate_native_qualification_repository_binding,
)

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render or validate repository-bound qualification handoff evidence."
    )
    parser.add_argument("--root", default=".")
    parser.add_argument(
        "--validate",
        type=Path,
        help="Validate a retained handoff against this repository.",
    )
    args = parser.parse_args(argv)
    root = Path(args.root)
    if args.validate is not None:
        handoff = json.loads(args.validate.read_bytes())
        value = validate_native_qualification_repository_binding(root, handoff)
        log_command_output(logger, json.dumps(value, indent=2, sort_keys=True))
        return 0 if value["valid"] else 3
    value = native_qualification_handoff(root)
    log_command_output(logger, json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
