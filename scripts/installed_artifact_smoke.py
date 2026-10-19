"""Smoke-test an installed Hashmarks artifact from an isolated interpreter.

Run this with ``python -I`` from a clean environment containing only the built
artifact. The source checkout must not be able to satisfy Hashmarks imports.
"""

from __future__ import annotations

import base64
import importlib.resources
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import hashmarks
from hashmarks import CodeMap, File, RepositoryIdentity, validate_native_consumer_bundle
from hashmarks._command_output import log_command_output
from hashmarks.codemap import MakeShellDeclarations, PythonUvManifestDeclarations
from hashmarks.operation_contract import operation_schema

logger = logging.getLogger(__name__)

REQUIRED_PUBLIC = {
    "CodeMap",
    "Digest",
    "RepositoryIdentity",
    "Snapshot",
    "InputObservation",
    "InputMember",
    "InputCounts",
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
        (root / "Makefile").write_text("check:\n\tuv run pytest\n", encoding="utf-8")
        (root / "consumer.ts").write_text(
            "const client = transport; client.send();\n", encoding="utf-8"
        )
        (root / "pyproject.toml").write_text(
            '[project]\nname = "example"\nversion = "1"\n'
            '[project.scripts]\nexample = "sample:answer"\n',
            encoding="utf-8",
        )
        with RepositoryIdentity(root, mode="local") as identity:
            snapshot = identity.snapshot(File("sample.py"))
            if not snapshot.hash:
                raise RuntimeError(
                    "installed RepositoryIdentity produced an empty hash"
                )
            observation = identity.observe_inputs(File("sample.py"))
            if (
                observation.snapshot.digest != snapshot.digest
                or observation.counts.file_count != 1
            ):
                raise RuntimeError(
                    "installed input observation disagrees with canonical identity"
                )
        with CodeMap(root) as codemap:
            result = codemap.index.sync()
            if result.discovered < 1:
                raise RuntimeError(
                    "installed CodeMap did not discover the smoke repository"
                )
            hits = codemap.search.find_task("answer", limit=5)
            if not any(hit.path == "sample.py" for hit in hits):
                raise RuntimeError("installed CodeMap did not retrieve sample.py")
            _check_source_receipt(codemap)
            _check_ecmascript_source(codemap)
            _check_declaration_providers(codemap)
            _check_membership_handoff(codemap)


def _check_source_receipt(codemap: CodeMap) -> None:
    receipt = codemap.source.range_receipt("sample.py", start_byte=0, end_byte=3)
    content = receipt.get("content")
    if (
        not isinstance(content, dict)
        or base64.b64decode(str(content.get("data")), validate=True) != b"def"
    ):
        raise RuntimeError("installed source receipt did not preserve exact bytes")


def _check_ecmascript_source(codemap: CodeMap) -> None:
    packet = codemap.source.ecmascript("consumer.ts", limit=2)
    facts = packet.get("facts")
    if (
        packet.get("schema") != operation_schema("source_ecmascript")
        or packet.get("semantic_resolution") != "not-performed"
        or packet.get("negative_evidence") != "not-admissible"
        or not isinstance(facts, list)
    ):
        raise RuntimeError("installed ECMAScript source contract is malformed")
    if packet.get("availability") == "observed" and not facts:
        raise RuntimeError("installed native ECMAScript syntax lost authored facts")


def _check_declaration_providers(codemap: CodeMap) -> None:
    observation = codemap.declarations.discover(
        [
            MakeShellDeclarations(make_paths=("Makefile",)),
            PythonUvManifestDeclarations(paths=("pyproject.toml",)),
        ]
    )
    declarations = observation.get("declarations")
    if not isinstance(declarations, dict) or not declarations.get("groups"):
        raise RuntimeError("installed first-party providers returned no declarations")


def _check_membership_handoff(codemap: CodeMap) -> None:
    member, _ = codemap.source.member("sample.py")
    report: dict[str, object] = {
        "schema": "hashmarks.verification-membership-report.v1",
        "selection_kind": "caller-selected",
        "producer": {"name": "installed-consumer-example", "version": "1"},
        "provenance": {"source": "explicit-caller-selection"},
        "scope": {"paths": ["sample.py"]},
        "status": "succeeded",
        "completeness": "complete",
        "truncation": "complete",
        "members": [{"path": "sample.py"}],
        "inputs": [{"path": "sample.py", "member_revision": member["member_revision"]}],
    }
    for members in ([{"path": "sample.py"}], []):
        report["members"] = members
        observed = codemap.verification.observe_membership(report)
        validated = validate_native_consumer_bundle(observed)
        if not validated["valid"]:
            raise RuntimeError(
                f"installed membership handoff failed: {validated['reasons']}"
            )


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
        _check_observation_cli(root)
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
        results = found.get("results")
        if (
            found.get("schema") != operation_schema("find")
            or not isinstance(results, list)
            or not any(
                isinstance(row, dict) and row.get("path") == "sample.py"
                for row in results
            )
        ):
            raise RuntimeError("installed find did not retrieve sample.py")


def _check_observation_cli(root: Path) -> None:
    observation = _run_cli(
        "--workspace",
        str(root),
        "observe-inputs",
        "--mode",
        "local",
        "--input",
        "sample.py",
    )
    counts = observation.get("counts")
    if not isinstance(counts, dict) or counts.get("file_count") != 1:
        raise RuntimeError("installed input CLI lost its selected inventory")
    receipt = _run_cli(
        "--workspace",
        str(root),
        "source-observation",
        "sample.py",
        "--result-mode",
        "range",
        "--start-byte",
        "0",
        "--end-byte",
        "3",
    )
    content = receipt.get("content")
    if (
        not isinstance(content, dict)
        or base64.b64decode(str(content.get("data")), validate=True) != b"def"
    ):
        raise RuntimeError("installed range CLI lost original bytes")


def main() -> int:
    _check_public_surface()
    _check_repository_intelligence()
    _check_cli()
    log_command_output(logger, f"installed Hashmarks {hashmarks.__version__}: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
