"""Observe a native uv-selected distribution without importing its implementation."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records, assert_text

from hashmarks.adapters import uv_lock_dependency_observation
from hashmarks.codemap import CodeMap

_BUILD_BACKEND = """import csv
import io
import tomllib
import zipfile
from pathlib import Path

def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    stem = f"sample_distribution-{version}"
    info = stem + ".dist-info/"
    members = {
        "observed_runtime/__init__.py": "raise RuntimeError('must never be imported')\\n",
        info + "METADATA": f"Metadata-Version: 2.4\\nName: sample-distribution\\nVersion: {version}\\n",
        info + "WHEEL": "Wheel-Version: 1.0\\nGenerator: native-test\\nRoot-Is-Purelib: true\\nTag: py3-none-any\\n",
        info + "top_level.txt": "observed_runtime\\n",
    }
    record = io.StringIO()
    csv.writer(record).writerows((name, "", "") for name in [*members, info + "RECORD"])
    members[info + "RECORD"] = record.getvalue()
    filename = stem + "-py3-none-any.whl"
    with zipfile.ZipFile(Path(wheel_directory) / filename, "w") as wheel:
        for name, content in members.items():
            wheel.writestr(name, content)
    return filename
"""

_COLLECT_METADATA = """import base64
import importlib.metadata
import json
import sys
from pathlib import Path

distribution = importlib.metadata.distribution("sample-distribution")
members = distribution.files or ()
result = {}
for name in ("METADATA", "RECORD"):
    member = next(p for p in members if p.name == name and p.parent.name.endswith(".dist-info"))
    result[name] = base64.b64encode(Path(distribution.locate_file(member)).read_bytes()).decode("ascii")
Path(sys.argv[1]).write_text(json.dumps(result), encoding="utf-8")
"""


def _fixture_project(root: Path) -> Path:
    provider = root / "vendor" / "provider"
    provider.mkdir(parents=True)
    (provider / "build_backend.py").write_text(_BUILD_BACKEND, encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "sample-app"\nversion = "0.1.0"\n'
        'requires-python = ">=3.11"\ndependencies = ["sample-distribution"]\n'
        "[tool.uv]\npackage = false\n[tool.uv.sources]\n"
        'sample-distribution = {path = "vendor/provider"}\n',
        encoding="utf-8",
    )
    (root / "consumer.py").write_text("import observed_runtime\n", encoding="utf-8")
    (root / "test_consumer.py").write_text("import consumer\n", encoding="utf-8")
    return provider


def _native_capture(
    root: Path, scratch: Path, provider: Path, version: str
) -> tuple[bytes, dict[str, object]]:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("native uv is unavailable")
    (provider / "pyproject.toml").write_text(
        '[build-system]\nrequires = []\nbuild-backend = "build_backend"\n'
        'backend-path = ["."]\n[project]\nname = "sample-distribution"\n'
        f'version = "{version}"\nrequires-python = ">=3.11"\n',
        encoding="utf-8",
    )
    environment = scratch / "environment"
    env = {
        **os.environ,
        "UV_PROJECT_ENVIRONMENT": str(environment),
        "UV_CACHE_DIR": str(scratch / "uv-cache"),
        "UV_PYTHON_DOWNLOADS": "never",
    }
    commands = [
        [uv, "lock", "--offline", "--python", sys.executable],
        [uv, "sync", "--offline", "--frozen", "--python", sys.executable],
    ]
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    transport = scratch / f"metadata-{version}.json"
    commands.append([str(python), "-I", "-c", _COLLECT_METADATA, str(transport)])
    with (scratch / f"native-{version}.log").open("wb") as log:
        for command in commands:
            subprocess.run(
                command,
                cwd=root,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=60,
            )
    metadata = assert_object(json.loads(transport.read_text(encoding="utf-8")))
    lock = (root / "uv.lock").read_bytes()
    raw = uv_lock_dependency_observation(lock=lock)
    selected = next(
        row
        for row in assert_records(raw["selections"])
        if row["component_id"] == "sample-distribution"
    )
    return lock, {
        "node_id": selected["node_id"],
        "metadata": base64.b64decode(assert_text(metadata["METADATA"])),
        "record": base64.b64decode(assert_text(metadata["RECORD"])),
    }


def test_native_uv_metadata_survives_version_change_without_consumer_closure(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    provider = _fixture_project(root)
    previous: dict[str, object] | None = None
    previous_node: str | None = None
    for version in ("1.0.0", "2.0.0"):
        lock, metadata = _native_capture(root, tmp_path, provider, version)
        raw = uv_lock_dependency_observation(
            lock=lock, distribution_metadata=[metadata]
        )
        with CodeMap(root, state_dir=tmp_path / "state") as codemap:
            codemap.index.sync()
            observed = codemap.dependencies.observe(raw)
            consumers = codemap.dependencies.consumers(
                observed,
                source_paths=["consumer.py"],
                node_ids=[assert_text(metadata["node_id"])],
            )
            rows = assert_records(consumers["consumers"])
            assert len(rows) == 1
            assert rows[0]["import_target"] == "observed_runtime"
            assert rows[0]["import_claim_authority"] == "source-observed-static-import"
            assert assert_object(rows[0]["source_member"])["state"] == "known-present"
            assert (
                assert_object(consumers["consumer_scope"])["negative_evidence"]
                == "not-admissible"
            )
            assert consumers["producer_authority"] == "caller-claimed"
            assert consumers["execution_authority"] == "external"
            downstream = assert_records(consumers["downstream_relationships"])
            assert len(downstream) == 1
            assert downstream[0]["source_path"] == "consumer.py"
            assert assert_object(downstream[0]["relationships"])["tests"] == [
                "test_consumer.py"
            ]
            assert all(
                row["completeness"] == "incomplete"
                for row in assert_records(observed["module_ownership"])
            )
            if previous is not None:
                delta = codemap.dependencies.delta(previous, observed)
                assert (
                    len(assert_records(delta["component_selection_transitions"])) == 1
                )
                assert (
                    previous["observation_identity"] != observed["observation_identity"]
                )
                assert previous_node is not None
                with pytest.raises(ValueError, match="binding|generation|stale"):
                    codemap.dependencies.consumers(
                        previous,
                        source_paths=["consumer.py"],
                        node_ids=[previous_node],
                    )
            previous = observed
            previous_node = assert_text(metadata["node_id"])
