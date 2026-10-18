"""Real CLI disclosure reuses canonical member and source-line observations."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from hashmarks.digest import FILE_DOMAIN, hash_file
from scripts.repository_evaluation.backend_transport import capture_cli


def test_cli_source_lines_follow_current_revision_in_every_format(
    tmp_path: Path,
) -> None:
    root, state = tmp_path / "repo", tmp_path / "state"
    root.mkdir()
    path = root / "service.py"
    case = {
        "operation": "source_observation",
        "inputs": {
            "paths": ["service.py"],
            "result_mode": "member",
            "context_lines": {"lines": [2], "radius": 1},
        },
    }
    identities = []
    for value in (1, 2):
        path.write_text(f"def process():\n    return {value}\n")
        revision = hash_file(path, domain=FILE_DOMAIN).hash
        for capture in capture_cli(root, state, case):
            response = capture["response"]
            packet = response.get("result", response)
            assert packet["member"]["state"] == "known-present"
            assert packet["member"]["member_revision"] == revision
            assert packet["requested_lines"] == [2]
            assert packet["line_coverage"] == "complete"
            assert packet["line_anchors"][0]["line"] == 2
            assert packet["line_anchors"][0]["member_revision"] == revision
            identities.append(packet["observation_identity"])
    assert len(set(identities[:4])) == len(set(identities[4:])) == 1
    assert identities[0] != identities[4]


def test_invalid_source_line_fails_before_creating_index_state(tmp_path: Path) -> None:
    root, state = tmp_path / "repo", tmp_path / "state"
    root.mkdir()
    (root / "service.py").write_text("def process():\n    return 1\n")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hashmarks.cli",
            "--workspace",
            str(root),
            "--state-dir",
            str(state),
            "source-observation",
            "service.py",
            "--line",
            "0",
        ],
        env={**os.environ, "HASHMARKS_NO_UPDATE_CHECK": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "positive integers" in result.stderr
    assert not state.exists()
