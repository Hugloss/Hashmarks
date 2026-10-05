from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "host_qualification" / "claude_mcp_host_gate.py"
SPEC = importlib.util.spec_from_file_location("claude_mcp_host_gate", SCRIPT)
assert SPEC and SPEC.loader
claude_gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = claude_gate
SPEC.loader.exec_module(claude_gate)


def _events() -> list[dict[str, object]]:
    return [
        {
            "type": "system",
            "subtype": "init",
            "mcp_servers": [{"name": "hashmarks", "status": "connected"}],
            "tools": list(claude_gate.EXPECTED),
        },
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "a",
                        "name": "mcp__hashmarks__repository_context",
                        "input": {"max_areas": 8},
                    }
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "a",
                        "content": '{"schema":"hashmarks.repository-capsule.v1","generation":1}',
                    }
                ]
            },
        },
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "b",
                        "name": "mcp__hashmarks__find",
                        "input": {"query": "flare041", "limit": 5},
                    }
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "b",
                        "content": '{"schema":"hashmarks.find.v2","results":[{"path":"src/feature.py"}]}',
                    }
                ]
            },
        },
    ]

def test_claude_event_validation_requires_connected_model_visible_tools_and_results() -> (
    None
):
    result = claude_gate._validate_events(_events())
    assert set(result) == set(claude_gate.EXPECTED)


def test_claude_event_validation_rejects_schema_token_without_semantic_result() -> None:
    events = _events()
    result_event = events[-1]
    assert isinstance(result_event, dict)
    message = result_event["message"]
    assert isinstance(message, dict)
    content = message["content"]
    assert isinstance(content, list)
    block = content[0]
    assert isinstance(block, dict)

    block["content"] = "Hashmarks schema hashmarks.find.v2 was observed but no result exists."
    with pytest.raises(claude_gate.HostGateError, match="exact JSON object"):
        claude_gate._validate_events(events)

    block["content"] = '{"schema":"hashmarks.find.v2","results":[]}'
    with pytest.raises(claude_gate.HostGateError, match="src/feature.py"):
        claude_gate._validate_events(events)

def test_claude_event_validation_binds_fixture_arguments() -> None:
    events = _events()
    use_event = events[3]
    assert isinstance(use_event, dict)
    message = use_event["message"]
    assert isinstance(message, dict)
    content = message["content"]
    assert isinstance(content, list)
    block = content[0]
    assert isinstance(block, dict)
    block["input"] = {"query": "wrong", "limit": 5}

    with pytest.raises(claude_gate.HostGateError, match="fixture contract"):
        claude_gate._validate_events(events)

def test_claude_connected_but_tools_not_model_visible_is_environment_blocked() -> None:
    events = _events()
    init = events[0]
    assert isinstance(init, dict)
    init["tools"] = []
    with pytest.raises(
        claude_gate.HostGateEnvironmentBlocked, match="model-visible catalog"
    ):
        claude_gate._validate_events(events)

def test_claude_event_validation_rejects_builtin_tool() -> None:
    events = _events()
    events.append(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "x", "name": "Bash", "input": {}}
                ]
            },
        }
    )
    with pytest.raises(claude_gate.HostGateError, match="unexpected tool"):
        claude_gate._validate_events(events)

def test_claude_config_binds_absolute_installed_hashmarks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    executable = tmp_path / "venv" / "bin" / "hashmarks"
    path = claude_gate._write_claude_config(repo, executable)
    import json

    config = json.loads(path.read_text(encoding="utf-8"))
    entry = config["mcpServers"]["hashmarks"]
    assert entry["command"] == str(executable)
    assert entry["args"] == ["--workspace", str(repo), "mcp"]
