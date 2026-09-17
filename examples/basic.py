"""Minimal current Hashmarks repository-intelligence example."""

from pathlib import Path

from hashmarks import CodeMap

workspace = Path(".").resolve()

with CodeMap(workspace) as codemap:
    result = codemap.sync()
    print("generation:", result.generation)  # noqa: T201 - intentional command output

    print("\norientation:")  # noqa: T201 - intentional command output
    print(codemap.orient())  # noqa: T201 - intentional command output

    print("\nrepository-freshness hits:")  # noqa: T201 - intentional command output
    for hit in codemap.find_task("repository freshness", limit=5):
        print(f"{hit.score:8.2f}  {hit.path}")  # noqa: T201 - intentional command output
