from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "host_qualification" / "codex_mcp_host_gate.py"
SPEC = importlib.util.spec_from_file_location("codex_mcp_host_gate", SCRIPT)
assert SPEC and SPEC.loader
codex_gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = codex_gate
SPEC.loader.exec_module(codex_gate)


def _event(tool: str, schema: str, *, status: str = "completed") -> dict[str, object]:
    payload: dict[str, object]
    if tool == "find":
        payload = {"schema": schema, "results": [{"path": "src/feature.py"}]}
    else:
        payload = {"schema": schema, "generation": 1}
    return {
        "type": "item.completed",
        "item": {
            "type": "mcp_tool_call",
            "server": "hashmarks",
            "tool": tool,
            "status": status,
            "result": {"structured_content": payload},
        },
    }


def test_codex_event_validation_accepts_exact_two_hashmarks_calls() -> None:
    result = codex_gate._validate_events(
        [
            _event("repository_context", "hashmarks.repository-capsule.v1"),
            _event("find", "hashmarks.mcp-find.v1"),
        ]
    )
    assert set(result) == {"repository_context", "find"}


def test_codex_event_validation_rejects_built_in_tool_use() -> None:
    events = [
        {
            "type": "item.completed",
            "item": {"type": "command_execution", "status": "completed"},
        },
        _event("repository_context", "hashmarks.repository-capsule.v1"),
        _event("find", "hashmarks.mcp-find.v1"),
    ]
    with pytest.raises(codex_gate.HostGateError, match="forbidden built-in"):
        codex_gate._validate_events(events)


def test_codex_event_validation_rejects_failed_or_wrong_schema() -> None:
    with pytest.raises(codex_gate.HostGateError, match="did not complete"):
        codex_gate._validate_events(
            [
                _event(
                    "repository_context",
                    "hashmarks.repository-capsule.v1",
                    status="failed",
                ),
                _event("find", "hashmarks.mcp-find.v1"),
            ]
        )
    with pytest.raises(codex_gate.HostGateError, match="unexpected schema"):
        codex_gate._validate_events(
            [
                _event("repository_context", "wrong.schema"),
                _event("find", "hashmarks.mcp-find.v1"),
            ]
        )


def test_codex_config_binds_absolute_installed_hashmarks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    executable = tmp_path / "venv" / "bin" / "hashmarks"
    path = codex_gate._write_codex_config(repo, executable)
    data = codex_gate.json.loads(
        "{}"
    )  # prove json module remains ordinary before TOML read
    assert data == {}
    import tomllib

    config = tomllib.loads(path.read_text(encoding="utf-8"))
    entry = config["mcp_servers"]["hashmarks"]
    assert entry["command"] == str(executable)
    assert entry["args"] == ["--workspace", str(repo), "mcp"]
    assert entry["enabled"] is True


def test_codex_headless_approval_block_detection_is_narrow() -> None:
    assert codex_gate._looks_like_headless_mcp_approval_block(
        "mcp: hashmarks/find failed: user cancelled MCP tool call"
    )
    assert not codex_gate._looks_like_headless_mcp_approval_block(
        "model authentication failed"
    )
