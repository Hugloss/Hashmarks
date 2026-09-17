from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "host_qualification" / "opencode_mcp_host_gate.py"
SPEC = importlib.util.spec_from_file_location("opencode_mcp_host_gate", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
host_gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(host_gate)


def _tool_event(
    tool: str, output: dict[str, object], *, session: str = "ses_123"
) -> dict[str, object]:
    return {
        "type": "tool_use",
        "sessionID": session,
        "part": {
            "type": "tool",
            "tool": tool,
            "state": {
                "status": "completed",
                "input": {},
                "output": json.dumps(output, sort_keys=True),
            },
        },
    }


def test_parse_jsonl_and_session_id_accept_current_opencode_event_shape() -> None:
    text = (
        json.dumps(_tool_event("hashmarks_find", {"schema": "hashmarks.mcp-find.v1"}))
        + "\n"
    )
    events = host_gate._parse_jsonl(text)
    assert host_gate._session_id(events) == "ses_123"
    assert host_gate._tool_events(events)[0]["tool"] == "hashmarks_find"


def test_parse_jsonl_rejects_non_json_stdout() -> None:
    with pytest.raises(host_gate.HostGateError, match="non-JSON stdout"):
        host_gate._parse_jsonl("not-json\n")


def test_completed_tool_set_rejects_missing_unexpected_and_duplicate_calls() -> None:
    expected = {"hashmarks_find"}
    with pytest.raises(host_gate.HostGateError, match="required tools"):
        host_gate._assert_completed_tool_set([], expected)

    unexpected = [_tool_event("shell", {"schema": "x"})]
    with pytest.raises(host_gate.HostGateError, match="unexpected tools"):
        host_gate._assert_completed_tool_set(unexpected, expected)

    duplicate = [
        _tool_event("hashmarks_find", {"schema": "hashmarks.mcp-find.v1"}),
        _tool_event("hashmarks_find", {"schema": "hashmarks.mcp-find.v1"}),
    ]
    with pytest.raises(host_gate.HostGateError, match="more than once"):
        host_gate._assert_completed_tool_set(duplicate, expected)


def test_completed_tool_set_rejects_hashmarks_tool_from_wrong_phase() -> None:
    events = [
        _tool_event("hashmarks_find", {"schema": "hashmarks.mcp-find.v1"}),
        _tool_event(
            "hashmarks_post_change", {"schema": "hashmarks.task-post-change-delta.v1"}
        ),
    ]
    with pytest.raises(host_gate.HostGateError, match="outside this phase"):
        host_gate._assert_completed_tool_set(events, {"hashmarks_find"})


def test_tool_payload_requires_schema_and_rejects_building_state() -> None:
    part = host_gate._tool_events(
        [
            _tool_event(
                "hashmarks_find",
                {"schema": "hashmarks.mcp-find.v1", "status": "complete"},
            )
        ]
    )[0]
    assert (
        host_gate._tool_payload(part, "hashmarks.mcp-find.v1")["status"] == "complete"
    )

    building = host_gate._tool_events(
        [
            _tool_event(
                "hashmarks_find",
                {"schema": "hashmarks.mcp-find.v1", "status": "BUILDING"},
            )
        ]
    )[0]
    with pytest.raises(host_gate.HostGateError, match="BUILDING"):
        host_gate._tool_payload(building, "hashmarks.mcp-find.v1")


def test_opencode_project_config_is_real_repo_local_minimal_registration(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    fake_hashmarks = tmp_path / "venv" / "bin" / "hashmarks"
    path = host_gate._write_opencode_project_config(repo, fake_hashmarks)
    assert path == repo / "opencode.json"
    config = json.loads(path.read_text())
    assert config["$schema"] == "https://opencode.ai/config.json"
    assert config["mcp"]["hashmarks"] == {
        "type": "local",
        "command": [str(fake_hashmarks), "--workspace", str(repo), "mcp"],
        "enabled": True,
    }


def test_configure_opencode_mcp_uses_natural_project_config_discovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    fake_hashmarks = tmp_path / "venv" / "bin" / "hashmarks"
    monkeypatch.setenv("OPENCODE_CONFIG", "/tmp/foreign.json")
    monkeypatch.setenv("OPENCODE_CONFIG_CONTENT", '{"mcp":{}}')

    def fake_run(argv, *, cwd, env=None, timeout=600):
        del timeout
        assert argv == ["opencode", "mcp", "list"]
        assert cwd == repo
        assert env is not None
        assert "OPENCODE_CONFIG" not in env
        assert "OPENCODE_CONFIG_CONTENT" not in env
        config_path = repo / "opencode.json"
        config = json.loads(config_path.read_text())
        assert "hashmarks" in config["mcp"]
        import subprocess

        return subprocess.CompletedProcess(argv, 0, "hashmarks connected\n", "")

    monkeypatch.setattr(host_gate, "_run", fake_run)
    result, config_path, env = host_gate._configure_opencode_mcp(
        "opencode", repo=repo, hashmarks=fake_hashmarks
    )
    assert "connected" in result.stdout
    assert config_path == "opencode.json"
    assert "OPENCODE_CONFIG" not in env
    assert "OPENCODE_CONFIG_CONTENT" not in env


def test_configure_opencode_mcp_fails_when_real_project_registration_is_not_loaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    fake_hashmarks = tmp_path / "venv" / "bin" / "hashmarks"

    def fake_run(argv, *, cwd, env=None, timeout=600):
        del argv, cwd, env, timeout
        import subprocess

        return subprocess.CompletedProcess(
            ["opencode", "mcp", "list"], 0, "No MCP servers configured\n", ""
        )

    monkeypatch.setattr(host_gate, "_run", fake_run)
    with pytest.raises(
        host_gate.HostGateError, match="repo-local Hashmarks MCP registration"
    ):
        host_gate._configure_opencode_mcp(
            "opencode", repo=repo, hashmarks=fake_hashmarks
        )


def test_configure_opencode_mcp_rejects_misleading_failed_connected_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    fake_hashmarks = tmp_path / "venv" / "bin" / "hashmarks"

    def fake_run(argv, *, cwd, env=None, timeout=600):
        del cwd, env, timeout
        import subprocess

        return subprocess.CompletedProcess(argv, 0, "hashmarks FAILED to connect\n", "")

    monkeypatch.setattr(host_gate, "_run", fake_run)
    with pytest.raises(
        host_gate.HostGateError, match="repo-local Hashmarks MCP registration"
    ):
        host_gate._configure_opencode_mcp(
            "opencode", repo=repo, hashmarks=fake_hashmarks
        )


def test_opencode_version_gate_accepts_stable_v1_and_v2() -> None:
    assert host_gate._opencode_version("opencode 1.18.31") == (1, 18)
    assert host_gate._opencode_version("2.0.4") == (2, 0)
    with pytest.raises(host_gate.HostGateError, match="1.18 or newer"):
        host_gate._opencode_version("opencode 1.17.9")
