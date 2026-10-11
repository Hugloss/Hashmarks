"""Extract caller-selected pinned Git trees for Hashmarks development QA."""

from __future__ import annotations

import argparse
import io
import subprocess
import tarfile
from pathlib import Path

from hashmarks.test_shards import repository_content_identity

from .backend_corpus import SCHEMA, SUITE_PATH
from .common import load_json, write_json
from .run_cases import _validate_case_membership
from .run_heldout import _sources


def materialize_backend(
    *, repositories: dict[str, Path], output_dir: Path, suite_path: Path = SUITE_PATH
) -> dict[str, str]:
    suite = load_json(suite_path, schema=SCHEMA)
    definitions = suite["sources"]
    _validate_case_membership([{"id": name} for name in definitions])
    if set(repositories) != {row["repository"] for row in definitions.values()}:
        raise ValueError(
            "exactly the declared backend repository checkouts are required"
        )
    sources = {}
    for name, definition in definitions.items():
        destination = output_dir / name
        if not destination.exists():
            archive = subprocess.run(
                ["git", "archive", definition["commit"]],
                cwd=repositories[definition["repository"]],
                capture_output=True,
                check=True,
            ).stdout
            destination.mkdir(parents=True)
            with tarfile.open(fileobj=io.BytesIO(archive)) as handle:
                handle.extractall(destination, filter="data")
        if repository_content_identity(destination) != definition["content_identity"]:
            raise ValueError(f"backend archive content identity mismatch: {name}")
        sources[name] = str(destination.resolve())
    write_json(output_dir / "sources.json", sources)
    return sources


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--suite", type=Path, default=SUITE_PATH)
    args = parser.parse_args()
    materialize_backend(
        repositories=_sources(args.repository),
        output_dir=args.output_dir.resolve(),
        suite_path=args.suite.resolve(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
