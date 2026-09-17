"""Observe canonical input identity with the local Linux/WSL watcher."""

import time
from pathlib import Path

from hashmarks import Directory, File, RepositoryIdentity

workspace = Path(".").resolve()

with RepositoryIdentity(workspace, mode="local", local_observer="watcher") as identity:
    manifest = identity.manifest([Directory("hashmarks"), File("pyproject.toml")])

    try:
        while True:
            snapshot = identity.snapshot_manifest(manifest)
            print(snapshot.hash)  # noqa: T201 - intentional command output
            time.sleep(1)
    except KeyboardInterrupt:
        pass
