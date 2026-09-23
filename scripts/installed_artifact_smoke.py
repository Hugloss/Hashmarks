"""Smoke-test an installed Hashmarks artifact from an isolated interpreter.

Run this with ``python -I`` from a clean environment containing only the built
artifact. The source checkout must not be able to satisfy Hashmarks imports.
"""

from __future__ import annotations

import importlib.resources
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import hashmarks
from hashmarks import CodeMap, File, RepositoryIdentity
from hashmarks._command_output import log_command_output

logger = logging.getLogger(__name__)

REQUIRED_PUBLIC = {
    "CodeMap",
    "Digest",
    "RepositoryIdentity",
    "Snapshot",
    "File",
    "Directory",
    "Glob",
}

FORBIDDEN_BOUNDARY_DEBT = {
    "ActionCache",
    "ActionResult",
    "AgentWorkSession",
    "ExecutionCache",
    "PassPromotion",
    "StepIdentity",
    "WorkUnit",
}


def _check_public_surface() -> None:
    exported = set(hashmarks.__all__)
    missing = REQUIRED_PUBLIC - exported
    if missing:
        raise RuntimeError(f"installed public API is missing: {sorted(missing)}")
    leaked = FORBIDDEN_BOUNDARY_DEBT & exported
    if leaked:
        raise RuntimeError(
            f"removed boundary debt leaked into public API: {sorted(leaked)}"
        )
    for name in REQUIRED_PUBLIC:
        getattr(hashmarks, name)
    if not importlib.resources.files("hashmarks").joinpath("py.typed").is_file():
        raise RuntimeError("installed package is missing py.typed")


def _check_repository_intelligence() -> None:
    with tempfile.TemporaryDirectory(prefix="hashmarks-artifact-smoke-") as raw:
        root = Path(raw)
        (root / "sample.py").write_text(
            "def answer() -> int:\n    return 42\n",
            encoding="utf-8",
        )
        with RepositoryIdentity(root, mode="local") as identity:
            snapshot = identity.snapshot(File("sample.py"))
            if not snapshot.hash:
                raise RuntimeError(
                    "installed RepositoryIdentity produced an empty hash"
                )
        with CodeMap(root) as codemap:
            result = codemap.sync()
            if result.discovered < 1:
                raise RuntimeError(
                    "installed CodeMap did not discover the smoke repository"
                )
            hits = codemap.find_task("answer", limit=5)
            if not any(hit.path == "sample.py" for hit in hits):
                raise RuntimeError("installed CodeMap did not retrieve sample.py")


def _console_script() -> Path:
    directory = Path(sys.executable).parent
    names = ("hashmarks.exe", "hashmarks") if os.name == "nt" else ("hashmarks",)
    for name in names:
        candidate = directory / name
        if candidate.is_file():
            return candidate
    raise RuntimeError(
        f"installed hashmarks console script not found beside {sys.executable}"
    )


def _run_cli(*args: str) -> dict[str, object]:
    completed = subprocess.run(
        [str(_console_script()), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError(
            f"installed CLI did not return a JSON object for: {' '.join(args)}"
        )
    return payload


def _check_cli() -> None:
    version = _run_cli("version")
    if version.get("version") != hashmarks.__version__:
        raise RuntimeError("installed CLI and package versions disagree")

    with tempfile.TemporaryDirectory(prefix="hashmarks-cli-smoke-") as raw:
        root = Path(raw)
        (root / "sample.py").write_text(
            "def answer() -> int:\n    return 42\n",
            encoding="utf-8",
        )
        doctor = _run_cli("--workspace", str(root), "doctor", "--mode", "local")
        if doctor.get("workspace") != str(root.resolve()):
            raise RuntimeError(
                "installed doctor did not bind to the requested workspace"
            )

        sync = _run_cli("--workspace", str(root), "map", "sync")
        if (
            sync.get("schema") != "hashmarks.codemap.v1"
            or sync.get("build_state") != "COMPLETE"
        ):
            raise RuntimeError("installed map sync returned an unexpected contract")

        orientation = _run_cli("--workspace", str(root), "orient")
        if orientation.get("schema") != "hashmarks.repository-capsule.v1":
            raise RuntimeError("installed orient returned an unexpected schema")

        found = _run_cli("--workspace", str(root), "find", "answer")
        hits = found.get("hits")
        if (
            found.get("schema") != "hashmarks.find.v1"
            or not isinstance(hits, list)
            or not any(
                isinstance(row, dict) and row.get("path") == "sample.py" for row in hits
            )
        ):
            raise RuntimeError("installed find did not retrieve sample.py")


def main() -> int:
    _check_public_surface()
    _check_repository_intelligence()
    _check_cli()
    log_command_output(logger, f"installed Hashmarks {hashmarks.__version__}: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
