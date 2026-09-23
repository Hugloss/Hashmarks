from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from hashmarks._command_output import log_command_output

logger = logging.getLogger(__name__)


def _load(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if value.get("schema") != "fastidentity.metrics.v1":
        raise SystemExit(
            f"unsupported metrics schema in {path!r}: {value.get('schema')!r}"
        )
    return value


def _seconds(value: Any, prefix: tuple[str, ...] = ()) -> dict[str, float]:
    out: dict[str, float] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            next_prefix = (*prefix, str(key))
            if key == "seconds" and isinstance(child, dict):
                for name, number in child.items():
                    if isinstance(number, (int, float)) and not isinstance(
                        number, bool
                    ):
                        out[".".join((*next_prefix, str(name)))] = float(number)
            else:
                out.update(_seconds(child, next_prefix))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare two Hashmarks metric baselines"
    )
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--current", default=".hashmarks/metrics/latest.json")
    args = parser.parse_args()

    baseline = _load(args.baseline)
    current = _load(args.current)
    old = _seconds(baseline)
    new = _seconds(current)
    rows = []
    for key in sorted(old.keys() & new.keys()):
        before = old[key]
        after = new[key]
        delta = after - before
        percent = None if before == 0 else (delta / before) * 100.0
        rows.append(
            {
                "metric": key,
                "baseline_seconds": before,
                "current_seconds": after,
                "delta_seconds": delta,
                "delta_percent": percent,
                "faster": after < before,
            }
        )
    log_command_output(
        logger,
        json.dumps(
            {
                "schema": "fastidentity.metrics-comparison.v1",
                "baseline": str(Path(args.baseline)),
                "current": str(Path(args.current)),
                "metrics": rows,
            },
            indent=2,
            sort_keys=True,
        ),
    )


if __name__ == "__main__":
    main()
