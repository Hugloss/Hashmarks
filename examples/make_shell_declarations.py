"""Installed-package consumer example using a temporary neutral repository."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from hashmarks.codemap import CodeMap, MakeShellDeclarations


def run_example(workspace: Path) -> dict[str, object]:
    """Create example inputs as a consumer, then observe and compare their syntax."""
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "Makefile").write_text(
        "RUNNER := python\n"
        "TOOL = $(RUNNER)\n"
        "inspect:\n"
        '\tMODE="sample" $(TOOL) -m demo\n',
        encoding="utf-8",
    )
    script = workspace / "demo.sh"
    script.write_text("show() { echo ready; }\nshow\n", encoding="utf-8")
    provider = MakeShellDeclarations(
        make_paths=("Makefile",), shell_paths=("demo.sh", "missing.sh")
    )
    with CodeMap(workspace) as repository:
        repository.index.sync()
        before = repository.declarations.discover([provider])
        # This edit belongs to the example consumer, not the observation provider.
        script.write_text("show() { echo changed; }\nshow\n", encoding="utf-8")
        repository.index.sync(["demo.sh"])
        after = repository.declarations.discover(
            [provider], previous_observation=before
        )
    return {"before": before, "after": after}


def main() -> None:
    with TemporaryDirectory(prefix="hashmarks-make-shell-example-") as directory:
        result = run_example(Path(directory))
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
