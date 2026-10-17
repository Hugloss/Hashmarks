"""External native behavior proof, independently correlated with source facts."""

from __future__ import annotations

import json
import os
import platform
import select
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from contract_assertions import assert_array, assert_object, assert_records

from hashmarks.codemap import CodeMap

_SOURCE = """import os
import sys
from threading import Lock

def cleanup(root):
    name = 'child'
    parent_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    lock = Lock()
    with lock:
        checked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        print(checked.st_ino, flush=True)
        sys.stdin.buffer.read(1)
        os.rmdir(name, dir_fd=parent_fd)
    os.close(parent_fd)

if __name__ == '__main__':
    cleanup(sys.argv[1])
"""


@pytest.mark.skipif(
    sys.platform != "linux",
    reason="requires native Linux descriptor-relative directory operations",
)
def test_native_child_replacement_is_separate_from_source_evidence(
    tmp_path: Path, record_property: Callable[[str, object], None]
) -> None:
    namespace = tmp_path / "namespace"
    namespace.mkdir()
    child = namespace / "child"
    child.mkdir()
    original = child.stat()
    fixture = tmp_path / "cleanup.py"
    fixture.write_text(_SOURCE, encoding="utf-8")
    _replace_after_check(fixture, namespace, original.st_ino)
    assert not child.exists()
    assert (namespace / "retained").stat().st_ino == original.st_ino
    record_property("kernel", platform.release())
    record_property("python_version", platform.python_version())
    filesystem = os.statvfs(namespace)
    record_property("filesystem_id", filesystem.f_fsid)
    record_property("filesystem_block_size", filesystem.f_bsize)
    record_property(
        "environment", "wsl2" if "microsoft" in platform.release().lower() else "linux"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        evidence = codemap.repository_findings(["cleanup.py"])["resource_lifecycle"]
        assert isinstance(evidence, dict)
        observations = assert_records(evidence["observations"])
        assert observations
        observation = observations[0]
        assert observation["runtime_identity"] == "unverified"
        anchor = assert_object(observation["use"])
        assert anchor["guards"]
        correlated = codemap.correlate_evidence(
            [
                {
                    "bundle_id": "native-child-replacement",
                    "producer": {"kind": "external-pytest-fixture"},
                    "completeness": "complete",
                    "truncation": "complete",
                    "anchors": [
                        {
                            "anchor_id": "deletion",
                            "path": "cleanup.py",
                            "line": assert_array(anchor["lines"])[0],
                            "member_revision": anchor["member_revision"],
                            "metadata": {
                                "observed_removed": "replacement",
                                "kernel": platform.release(),
                            },
                        }
                    ],
                }
            ]
        )
    assert correlated["causation"] == "not-inferred"
    assert correlated["storage"] == "request-scoped-not-persisted"
    assert 'runtime_identity": "proven' not in json.dumps(observation)


def _replace_after_check(fixture: Path, namespace: Path, original_inode: int) -> None:
    with subprocess.Popen(
        [sys.executable, str(fixture), str(namespace)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        assert process.stdin is not None and process.stdout is not None
        try:
            ready, _, _ = select.select([process.stdout], [], [], 10)
            assert ready, "fixture did not reach the explicitly signalled check"
            assert int(process.stdout.readline()) == original_inode
            child = namespace / "child"
            child.rename(namespace / "retained")
            child.mkdir()
            assert child.stat().st_ino != original_inode
            process.stdin.write("x")
            process.stdin.flush()
            _, stderr = process.communicate(timeout=10)
            assert process.returncode == 0, stderr
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
