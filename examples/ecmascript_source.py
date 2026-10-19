"""Installed-package consumer example of bounded native source syntax facts."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from hashmarks import CodeMap


def run_example(workspace: Path) -> dict[str, object]:
    """Write a neutral consumer fixture, then observe its own source bytes."""
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "consumer.ts").write_text(
        'import { gateway as client } from "./gateway";\n'
        "const transport = client;\n"
        "const { send: transmit } = transport;\n"
        "transport.send(payload);\n"
        "transmit(payload);\n"
        "transport[method](payload);\n",
        encoding="utf-8",
    )
    with CodeMap(workspace) as repository:
        repository.index.sync()
        # A missing imported implementation does not block local syntax facts.
        # Without the optional syntax provider this returns explicit unknowns.
        return repository.source.ecmascript("consumer.ts")


def main() -> None:
    with TemporaryDirectory(prefix="hashmarks-ecmascript-example-") as directory:
        result = run_example(Path(directory))
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
