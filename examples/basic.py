"""Minimal current Hashmarks repository-intelligence example."""

from pathlib import Path

from hashmarks import CodeMap


workspace = Path(".").resolve()

with CodeMap(workspace) as codemap:
    result = codemap.sync()
    print("generation:", result.generation)

    print("\norientation:")
    print(codemap.orient())

    print("\nrepository-freshness hits:")
    for hit in codemap.find_task("repository freshness", limit=5):
        print(f"{hit.score:8.2f}  {hit.path}")
