from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "host_qualification" / "pi_mcp_host_gate.py"
SPEC = importlib.util.spec_from_file_location("pi_mcp_host_gate", SCRIPT)
assert SPEC and SPEC.loader
pi_gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pi_gate
SPEC.loader.exec_module(pi_gate)


def _start(call_id: str, target: str, args: dict[str, object]) -> dict[str, object]:
    return {
        "type": "tool_execution_start",
        "toolCallId": call_id,
        "toolName": "mcp",
        "args": {"tool": target, "args": args},
    }


def _end(
    call_id: str,
    payload: dict[str, object],
    *,
    is_error: bool = False,
) -> dict[str, object]:
    import json

    return {
        "type": "tool_execution_end",
        "toolCallId": call_id,
        "toolName": "mcp",
        "result": {
            "content": [{"type": "text", "text": json.dumps(payload, sort_keys=True)}]
        },
        "isError": is_error,
    }

def test_pi_event_validation_accepts_exact_proxy_calls() -> None:
    events = [
        _start("a", "hashmarks_repository_context", {"max_areas": 8}),
        _end("a", {"schema": "hashmarks.repository-capsule.v1", "generation": 1}),
        _start("b", "hashmarks_find", {"query": "flare041", "limit": 5}),
        _end(
            "b",
            {
                "schema": "hashmarks.find.v2",
                "results": [{"path": "src/feature.py"}],
            },
        ),
    ]
    result = pi_gate._validate_events(events)
    assert set(result) == {"hashmarks_repository_context", "hashmarks_find"}


def test_pi_event_validation_rejects_schema_only_or_wrong_fixture_result() -> None:
    schema_only = [
        _start("a", "hashmarks_repository_context", {"max_areas": 8}),
        _end("a", {"schema": "hashmarks.repository-capsule.v1", "generation": 1}),
        _start("b", "hashmarks_find", {"query": "flare041", "limit": 5}),
        _end("b", {"schema": "hashmarks.find.v2"}),
    ]
    with pytest.raises(pi_gate.HostGateError, match="src/feature.py"):
        pi_gate._validate_events(schema_only)

    wrong_path = [
        _start("a", "hashmarks_repository_context", {"max_areas": 8}),
        _end("a", {"schema": "hashmarks.repository-capsule.v1", "generation": 1}),
        _start("b", "hashmarks_find", {"query": "flare041", "limit": 5}),
        _end(
            "b",
            {"schema": "hashmarks.find.v2", "results": [{"path": "src/wrong.py"}]},
        ),
    ]
    with pytest.raises(pi_gate.HostGateError, match="src/feature.py"):
        pi_gate._validate_events(wrong_path)

def test_pi_event_validation_binds_fixture_arguments() -> None:
    events = [
        _start("a", "hashmarks_repository_context", {"max_areas": 8}),
        _end("a", {"schema": "hashmarks.repository-capsule.v1", "generation": 1}),
        _start("b", "hashmarks_find", {"query": "wrong", "limit": 5}),
        _end(
            "b",
            {
                "schema": "hashmarks.find.v2",
                "results": [{"path": "src/feature.py"}],
            },
        ),
    ]
    with pytest.raises(pi_gate.HostGateError, match="fixture contract"):
        pi_gate._validate_events(events)

def test_pi_event_validation_rejects_non_mcp_tool() -> None:
    events = [
        {
            "type": "tool_execution_start",
            "toolCallId": "x",
            "toolName": "bash",
            "args": {},
        },
    ]
    with pytest.raises(pi_gate.HostGateError, match="unexpected tool"):
        pi_gate._validate_events(events)

def test_pi_event_validation_rejects_error_and_missing_schema() -> None:
    with pytest.raises(pi_gate.HostGateError, match="reported an error"):
        pi_gate._validate_events(
            [
                _start("a", "hashmarks_repository_context", {"max_areas": 8}),
                _end(
                    "a",
                    {"schema": "hashmarks.repository-capsule.v1", "generation": 1},
                    is_error=True,
                ),
                _start("b", "hashmarks_find", {"query": "flare041", "limit": 5}),
                _end(
                    "b",
                    {
                        "schema": "hashmarks.find.v2",
                        "results": [{"path": "src/feature.py"}],
                    },
                ),
            ]
        )
    with pytest.raises(pi_gate.HostGateError, match="canonical contract validation"):
        pi_gate._validate_events(
            [
                _start("a", "hashmarks_repository_context", {"max_areas": 8}),
                _end("a", {"schema": "wrong.schema", "generation": 1}),
                _start("b", "hashmarks_find", {"query": "flare041", "limit": 5}),
                _end(
                    "b",
                    {
                        "schema": "hashmarks.find.v2",
                        "results": [{"path": "src/feature.py"}],
                    },
                ),
            ]
        )

def test_pi_run_uses_native_model_authority() -> None:
    argv = pi_gate._pi_run_argv("pi", "qualify")
    assert "--model" not in argv
    assert argv == [
        "pi",
        "--mode",
        "json",
        "--no-session",
        "--approve",
        "--no-builtin-tools",
        "--tools",
        "mcp",
        "qualify",
    ]

def test_pi_config_binds_absolute_installed_hashmarks(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    executable = tmp_path / "venv" / "bin" / "hashmarks"
    path = pi_gate._write_pi_config(repo, executable)
    import json

    config = json.loads(path.read_text(encoding="utf-8"))
    entry = config["mcpServers"]["hashmarks"]
    assert entry["command"] == str(executable)
    assert entry["args"] == ["--workspace", str(repo), "mcp"]
