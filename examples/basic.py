"""Minimal current Hashmarks repository-intelligence example."""

import logging
from pathlib import Path

from hashmarks import CodeMap
from hashmarks._command_output import log_command_output

logger = logging.getLogger(__name__)

workspace = Path(".").resolve()

with CodeMap(workspace) as codemap:
    result = codemap.sync()
    log_command_output(logger, "generation:", result.generation)

    log_command_output(logger, "\norientation:")
    log_command_output(logger, codemap.orient())

    log_command_output(logger, "\nrepository-freshness hits:")
    for hit in codemap.find_task("repository freshness", limit=5):
        log_command_output(logger, f"{hit.score:8.2f}  {hit.path}")
