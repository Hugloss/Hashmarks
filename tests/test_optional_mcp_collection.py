"""Optional SDK annotations cannot prevent collection of native CLI tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent


def test_native_transport_collects_without_optional_mcp(tmp_path: Path) -> None:
    script = dedent("""\
        import sys

        class MissingMcp:
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "mcp" or fullname.startswith("mcp."):
                    raise ModuleNotFoundError("optional SDK unavailable", name=fullname)

        sys.meta_path.insert(0, MissingMcp())
        import pytest
        raise SystemExit(pytest.main([
            "--collect-only", "-q", "tests/test_native_evidence_transport.py",
            "-o", "cache_dir=" + sys.argv[1],
        ]))
    """)
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "pytest-cache")],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "test_native_scip_cli_change_roundtrips_exact_packets" in result.stdout
