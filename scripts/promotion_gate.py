from __future__ import annotations

import argparse
import json
from pathlib import Path

from hashmarks.promotion_receipt import promotion_manifest


def _load_mapping(path: str, *, label: str) -> dict[str, object]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _load_optional_mapping(path: str | None, *, label: str) -> dict[str, object] | None:
    if path is None:
        return None
    return _load_mapping(path, label=label)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate Hashmarks promotion evidence binding. A successful result does not "
            "authorize release; release authority remains external."
        )
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--receipt")
    parser.add_argument("--qualification-handoff", required=True)
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    handoff = _load_mapping(args.qualification_handoff, label="qualification handoff")
    receipt = _load_optional_mapping(args.receipt, label="promotion receipt")
    manifest = promotion_manifest(
        root,
        native_qualification_handoff=handoff,
        native_ruff_receipt=receipt,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))  # noqa: T201 - intentional command output
    return 0 if manifest["manifest_valid"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
