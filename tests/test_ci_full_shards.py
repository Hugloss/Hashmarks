"""Exact full-suite membership must be proven before GitHub matrix execution."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import ci_full_shards as handoff


@pytest.fixture
def native_repository(tmp_path: Path) -> Path:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_a.py").write_text(
        "def test_standard():\n    assert True\n", encoding="utf-8"
    )
    (tests / "test_b.py").write_text(
        "def test_sensitive():\n    assert True\ndef test_other():\n    assert True\n",
        encoding="utf-8",
    )
    (tests / "test_c.py").write_text(
        "def test_harness():\n    assert True\n", encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "tests"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=ci@example.test",
            "commit",
            "-qm",
            "native test membership",
        ],
        check=True,
    )
    return tmp_path


@pytest.fixture
def collected() -> list[str]:
    return [
        "tests/test_a.py::test_standard[one]",
        "tests/test_a.py::test_standard[two]",
        "tests/test_b.py::test_sensitive",
        "tests/test_b.py::test_other",
        "tests/test_c.py::test_harness",
    ]


def test_native_parity_includes_params_and_isolates_process_sensitive_nodes(
    native_repository: Path, collected: list[str]
) -> None:
    isolated = ("tests/test_b.py::test_sensitive",)
    plan = handoff._build_plan(
        native_repository, collected, isolated=isolated, shard_count=2
    )
    assert plan == handoff._build_plan(
        native_repository, collected, isolated=isolated, shard_count=2
    )
    assert plan["native_test_count"] == 5
    shards = plan["shards"]
    members = [node for row in shards for node in row["native_nodeids"]]
    assert sorted(members) == sorted(collected)
    normal = [selector for row in shards for selector in row["normal_args"]]
    singleton = [node for row in shards for node in row["isolated_nodeids"]]
    assert singleton == ["tests/test_b.py::test_sensitive"]
    assert "tests/test_b.py" not in normal
    assert "tests/test_b.py::test_other" in normal
    assert "tests/test_a.py" in normal
    assert plan["plan_identity"].startswith("sha256:")
    assert plan["execution_authority"] == "external-native-pytest"


def test_missing_isolation_and_duplicates_fail_closed(
    native_repository: Path, collected: list[str]
) -> None:
    with pytest.raises(ValueError, match="process-sensitive"):
        handoff._build_plan(
            native_repository, collected, isolated=("tests/test_missing.py::test_gone",)
        )
    with pytest.raises(ValueError, match="duplicate"):
        handoff._build_plan(
            native_repository, [*collected, collected[0]], isolated=(), shard_count=2
        )


@pytest.mark.parametrize(
    "nodeid",
    [
        "../outside/test_escape.py::test_escape",
        "tests/../test_a.py::test_standard",
        "tests/test_ghost.py::test_missing",
        "tests/conftest.py::test_unexpected",
    ],
)
def test_unadmitted_native_members_fail_closed(
    native_repository: Path, nodeid: str
) -> None:
    with pytest.raises(ValueError):
        handoff._build_plan(native_repository, [nodeid], isolated=(), shard_count=1)


def test_rechecked_native_membership_rejects_drift(
    native_repository: Path,
    collected: list[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan = handoff._build_plan(native_repository, collected, isolated=(), shard_count=2)
    manifest = tmp_path / "plan.json"
    manifest.write_text(json.dumps(plan), encoding="utf-8")
    monkeypatch.setattr(handoff, "_native_collection", lambda: collected)
    assert (
        handoff._bound_plan(native_repository, manifest, shard_count=2, isolated=())
        == plan
    )
    monkeypatch.setattr(handoff, "_native_collection", lambda: collected[:-1])
    with pytest.raises(ValueError, match="differs"):
        handoff._bound_plan(native_repository, manifest, shard_count=2, isolated=())


def test_execution_collection_rejects_missing_and_unplanned_items() -> None:
    expected = ["tests/test_a.py::test_one", "tests/test_b.py::test_two"]
    handoff._assert_executed_collection(expected, expected[::-1])
    with pytest.raises(pytest.UsageError, match="differs"):
        handoff._assert_executed_collection(expected, expected[:1])
    with pytest.raises(pytest.UsageError, match="differs"):
        handoff._assert_executed_collection(expected[:1], expected)


def test_expected_worker_membership_requires_valid_nul(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HASHMARKS_CI_EXPECTED_NUL", raising=False)
    monkeypatch.delenv("HASHMARKS_CI_EXPECTED_NODEID", raising=False)
    with pytest.raises(pytest.UsageError, match="requires one"):
        handoff._expected_execution_membership()
    path = tmp_path / "expected.nul"
    monkeypatch.setenv("HASHMARKS_CI_EXPECTED_NUL", str(path))
    path.write_bytes(b"tests/test_a.py::test_one")
    with pytest.raises(pytest.UsageError, match="NUL-delimited"):
        handoff._expected_execution_membership()
    handoff._nul(["tests/test_a.py::test_one"], path)
    assert handoff._expected_execution_membership() == [
        "tests/test_a.py::test_one"
    ]
    handoff._nul(["tests/test_a.py::test_one"] * 2, path)
    with pytest.raises(pytest.UsageError, match="duplicated"):
        handoff._expected_execution_membership()


def test_actual_pytest_plugin_enforces_collected_membership(
    native_repository: Path, tmp_path: Path
) -> None:
    """Exercise the actual -p pytest process and reject a mismatched expectation."""
    root = Path(__file__).resolve().parents[1]
    expected = tmp_path / "expected.nul"
    handoff._nul(["tests/test_a.py::test_standard"], expected)
    environment = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join((str(root), os.environ.get("PYTHONPATH", ""))),
        "HASHMARKS_CI_EXPECTED_NUL": str(expected),
    }
    args = [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "scripts.ci_full_shards",
        "-q",
        "tests/test_a.py",
    ]
    qualified = subprocess.run(
        args,
        cwd=native_repository,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert qualified.returncode == 0, qualified.stdout + qualified.stderr
    handoff._nul(["tests/test_a.py::test_unplanned"], expected)
    rejected = subprocess.run(
        args,
        cwd=native_repository,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert rejected.returncode != 0
    assert "differs" in rejected.stdout + rejected.stderr


def test_class_parametrization_keeps_full_isolated_function_name() -> None:
    nodeid = "tests/test_a.py::TestCases[variant]::test_run[one]"
    assert handoff._test_function(nodeid) == "tests/test_a.py::TestCases::test_run"


def test_nul_argv_preserves_exact_nodeids(tmp_path: Path) -> None:
    destination = tmp_path / "argv.nul"
    args = ["tests/test_a.py", "tests/test_b.py::test_sensitive"]
    handoff._nul(args, destination)
    assert destination.read_bytes() == b"".join(
        value.encode() + b"\0" for value in args
    )
