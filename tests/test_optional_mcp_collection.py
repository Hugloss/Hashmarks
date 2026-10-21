"""Native SDK coverage is required; constrained diagnostics remain capability-aware."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent
from xml.etree import ElementTree as ET


def _without_mcp(
    tmp_path: Path, *arguments: str, constrained: bool = False
) -> subprocess.CompletedProcess[str]:
    script = dedent("""\
        import importlib.util
        import sys

        class MissingMcp:
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "mcp" or fullname.startswith("mcp."):
                    raise ModuleNotFoundError("optional SDK unavailable", name=fullname)

        sys.meta_path.insert(0, MissingMcp())
        original_find_spec = importlib.util.find_spec
        def find_spec(name, *args, **kwargs):
            if name == "mcp" or name.startswith("mcp."):
                return None
            return original_find_spec(name, *args, **kwargs)
        importlib.util.find_spec = find_spec
        import pytest
        raise SystemExit(pytest.main([
            "-o", "cache_dir=" + sys.argv[1],
            *sys.argv[2:],
        ]))
    """)
    return subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "pytest-cache"), *arguments],
        cwd=Path(__file__).resolve().parents[1],
        env={
            **os.environ,
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "HASHMARKS_CONSTRAINED_HOST": "1" if constrained else "0",
        },
        capture_output=True,
        text=True,
        check=False,
    )


def test_native_transport_collects_without_optional_mcp(tmp_path: Path) -> None:
    result = _without_mcp(
        tmp_path, "--collect-only", "-q", "tests/test_native_evidence_transport.py"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "test_native_scip_cli_change_roundtrips_exact_packets" in result.stdout


def test_normal_host_without_sdk_rejects_incomplete_qualification(
    tmp_path: Path,
) -> None:
    result = _without_mcp(
        tmp_path,
        "-q",
        "tests/test_repository_observation_cli.py::test_official_mcp_matches_json_cli_observation_contract",
    )
    assert result.returncode == 4, result.stdout + result.stderr
    assert "MCP SDK is required" in result.stderr
    assert "make init" in result.stderr
    assert "skipped" not in result.stdout


def test_normal_host_without_sdk_can_run_cli_only_cases(tmp_path: Path) -> None:
    result = _without_mcp(
        tmp_path,
        "-q",
        "-m",
        "not host_mcp_sdk",
        "tests/test_function_boundary_arguments.py::test_public_transports_preserve_literal_arguments_and_unknown_binding",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout


def test_constrained_host_without_sdk_skips_mcp_and_keeps_cli_cases(
    tmp_path: Path,
) -> None:
    report = tmp_path / "sdk-absence.xml"
    result = _without_mcp(
        tmp_path,
        "-q",
        "tests/test_backend_declaration_transport.py::test_official_mcp_selected_declarations_keep_bindings_in_every_format",
        "tests/test_backend_declaration_transport.py::test_public_transports_reject_invalidated_source_before_refresh",
        "tests/test_function_boundary_arguments.py::test_public_transports_preserve_literal_arguments_and_unknown_binding",
        "tests/test_repository_observation_cli.py::test_official_mcp_matches_json_cli_observation_contract",
        f"--junitxml={report}",
        constrained=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    cases = list(ET.parse(report).getroot().iter("testcase"))
    cli = [case for case in cases if case.get("name", "").endswith("[cli]")]
    sdk = [case for case in cases if case not in cli]
    assert len(cli) == 2
    assert all(not list(case) for case in cli)
    assert len(sdk) == 4
    assert all(
        (skipped := case.find("skipped")) is not None
        and "host_mcp_sdk" in skipped.get("message", "")
        for case in sdk
    )
