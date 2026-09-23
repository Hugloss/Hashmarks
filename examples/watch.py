"""Observe canonical input identity with the local Linux/WSL watcher."""

import logging
import time
from pathlib import Path

from hashmarks import Directory, File, RepositoryIdentity
from hashmarks._command_output import log_command_output

logger = logging.getLogger(__name__)

workspace = Path(".").resolve()

with RepositoryIdentity(workspace, mode="local", local_observer="watcher") as identity:
    manifest = identity.manifest([Directory("hashmarks"), File("pyproject.toml")])

    try:
        while True:
            snapshot = identity.snapshot_manifest(manifest)
            log_command_output(logger, snapshot.hash)
            time.sleep(1)
    except KeyboardInterrupt:
        pass
