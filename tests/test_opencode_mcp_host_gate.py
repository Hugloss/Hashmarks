from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "host_qualification" / "opencode_mcp_host_gate.py"
SPEC = importlib.util.spec_from_file_location("opencode_mcp_host_gate", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
host_gate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = host_gate
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
            "hashmarks_post_change", {"schema": "hashmarks.task-post-change-delta.v2"}
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
        assert env["PWD"] == str(repo)
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


def test_opencode_run_uses_native_model_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[str] = []

    def fake_run(argv, *, cwd, env=None, timeout=600):
        del cwd, env, timeout
        captured.extend(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(host_gate, "_run", fake_run)
    host_gate._opencode_run(
        "opencode",
        repo=tmp_path,
        prompt="qualify",
        env={},
    )

    assert "--model" not in captured
    assert captured[:5] == [
        "opencode",
        "run",
        "--auto",
        "--dir",
        str(tmp_path),
    ]


def test_selection_scenarios_are_neutral_and_keep_negative_controls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hashmarks.mcp_surface import HashmarksMcpSurface

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    names = {row.name for row in host_gate.SELECTION_SCENARIOS}
    assert names == {
        "unresolved-task",
        "ambiguous-owner",
        "read-only-owner",
        "exact-lookup",
        "orientation",
        "changed-paths",
    }
    forbidden = ("hashmarks", "mcp", "task_evidence", "repository_context")
    assert all(
        not any(word in row.prompt.lower() for word in forbidden)
        for row in host_gate.SELECTION_SCENARIOS
    )
    host_gate._write_selection_fixture(tmp_path)
    assert (
        "from src.checkout.pricing import apply_discount"
        in (tmp_path / "src/checkout/handler.py").read_text()
    )
    assert "def apply_discount" in (tmp_path / "src/legacy/pricing.py").read_text()
    assert len(host_gate._selection_fixture_sources()) == 23
    assert len(host_gate._selection_manifest_identity()) == 64
    assert len(host_gate._selection_fixture_identity()) == 64
    surface = HashmarksMcpSurface(str(tmp_path), state_dir=str(tmp_path / "state"))
    try:
        matches = surface.find("apply_discount")["results"]
        assert (
            len({row["path"] for row in matches if row["name"] == "apply_discount"})
            >= 5
        )
        expected = (
            ("unresolved-task", "src/checkout/pricing.py", "tests/test_checkout.py"),
            ("ambiguous-owner", "src/checkout/pricing.py", "tests/test_checkout.py"),
            ("read-only-owner", "src/checkout/pricing.py", "tests/test_checkout.py"),
        )
        for name, owner, verification in expected:
            scenario = next(
                row for row in host_gate.SELECTION_SCENARIOS if row.name == name
            )
            packet = surface.task_evidence(scenario.prompt)
            assert packet["ownership"]["candidate"]["path"] == owner
            assert packet["verification"]["selected"]["path"] == verification
        ambiguous = surface.task_evidence(host_gate.SELECTION_SCENARIOS[1].prompt)
        assert ambiguous["ownership"]["basis"] == "exact-import-owner"
        assert ambiguous["ownership"]["owner"]["path"] == "src/checkout/pricing.py"
    finally:
        surface.close()


def test_selection_result_keeps_native_calls_and_validates_hashmarks() -> None:
    scenario = host_gate.SELECTION_SCENARIOS[0]
    events = [
        _tool_event("grep", {"matches": 2}),
        _tool_event(
            "hashmarks_task_evidence", {"schema": "hashmarks.task-evidence.v2"}
        ),
        {
            "type": "text",
            "part": {"text": "src/checkout/pricing.py tests/test_checkout.py"},
        },
    ]
    result = host_gate._selection_result(events, scenario)
    assert [row["tool"] for row in result["tool_calls"]] == [
        "grep",
        "hashmarks_task_evidence",
    ]
    assert result["task_evidence_invoked"] is True
    assert all(result["expected_paths_mentioned"].values())
    with pytest.raises(host_gate.HostGateError, match="unexpected schema"):
        host_gate._selection_result(
            [_tool_event("hashmarks_task_evidence", {"unexpected": True})], scenario
        )
    failed = _tool_event("hashmarks_task_evidence", {})
    failed["part"]["state"]["status"] = "error"
    with pytest.raises(host_gate.HostGateError, match="did not complete"):
        host_gate._selection_result([failed], scenario)


def test_selection_error_distinguishes_provider_from_host_failure() -> None:
    provider_error = {
        "type": "error",
        "error": {
            "name": "APIError",
            "data": {"message": "User not found.", "statusCode": 401},
        },
    }
    assert host_gate._selection_error([provider_error]) == (
        "ENVIRONMENT_BLOCKED",
        "User not found.",
    )
    host_error = {
        "type": "error",
        "error": {"name": "ToolError", "data": {"message": "tool failed"}},
    }
    assert host_gate._selection_error([host_error]) == ("FAIL", "tool failed")


def test_selection_receipt_binds_fixture_runner_and_installed_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "hashmarks"
    executable.write_text("entrypoint", encoding="utf-8")
    monkeypatch.setattr(host_gate, "_selection_executable", lambda *_args: executable)
    monkeypatch.setattr(
        host_gate,
        "_opencode_model_catalog",
        lambda *_args, **_kwargs: {"status": "captured", "tools": [{"name": "find"}]},
    )
    monkeypatch.setattr(
        host_gate,
        "_installed_hashmarks_source",
        lambda *_args: {"path": "/installed/mcp_server.py", "sha256": "source-digest"},
    )
    monkeypatch.setattr(
        host_gate,
        "_run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [], 0, "opencode 1.18.34\n", ""
        ),
    )
    receipt = host_gate._selection_diagnostic(
        Namespace(
            opencode="opencode",
            model=None,
            catalog_only=True,
            receipt=str(tmp_path / "receipt.json"),
        ),
        ROOT,
    )
    assert receipt["fixture_sha256"] == host_gate._selection_fixture_identity()
    assert receipt["runner_sha256"] == host_gate._sha256(SCRIPT)
    assert receipt["hashmarks_executable_sha256"] == host_gate._sha256(executable)
    assert receipt["hashmarks_mcp_source"]["sha256"] == "source-digest"
    assert len(receipt["catalog_sha256"]) == 64


def test_selection_trial_keeps_provider_error_unmeasured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        host_gate,
        "_configure_opencode_mcp",
        lambda *_args, **_kwargs: (None, "opencode.json", {}),
    )
    error = {
        "type": "error",
        "error": {
            "name": "APIError",
            "data": {"message": "User not found.", "statusCode": 401},
        },
    }
    monkeypatch.setattr(
        host_gate,
        "_opencode_run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [], 1, json.dumps(error) + "\n", ""
        ),
    )
    result = host_gate._selection_trial(
        Namespace(opencode="opencode", model="provider/model"),
        tmp_path / "hashmarks",
        tmp_path,
        tmp_path / "receipt.json",
        host_gate.SELECTION_SCENARIOS[0],
        0,
    )
    assert result["trial_status"] == "ENVIRONMENT_BLOCKED"
    assert result["semantic_outcome"] == "unavailable"
    assert result["tool_calls"] == []
    assert Path(result["event_log"]).is_file()


def test_catalog_rows_selects_actual_tool_bearing_model_request() -> None:
    rows = host_gate._catalog_rows(
        [
            {"messages": []},
            {
                "tools": [
                    {
                        "function": {
                            "name": "hashmarks_task_evidence",
                            "description": "task",
                            "parameters": {"required": ["task"]},
                        }
                    }
                ]
            },
        ]
    )
    assert rows == [
        {
            "name": "hashmarks_task_evidence",
            "description": "task",
            "parameters": {"required": ["task"]},
        }
    ]


def test_main_resolves_repository_root_for_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roots = []

    def fake_diagnostic(args, project_root):
        roots.append(project_root)
        return {
            "schema": "hashmarks.opencode-selection-diagnostic.v1",
            "status": "CATALOG_ONLY",
        }

    monkeypatch.setattr(host_gate, "_selection_diagnostic", fake_diagnostic)
    receipt = tmp_path / "receipt.json"
    assert (
        host_gate.main(
            ["--selection-diagnostic", "--catalog-only", "--receipt", str(receipt)]
        )
        == 0
    )
    assert roots == [ROOT]
    assert json.loads(receipt.read_text())["status"] == "CATALOG_ONLY"


def test_selection_stops_after_model_environment_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    def fake_trial(*args):
        calls.append(args)
        return {"trial_status": "ENVIRONMENT_BLOCKED"}

    monkeypatch.setattr(host_gate, "_selection_trial", fake_trial)
    status, rows = host_gate._selection_trials(
        Namespace(opencode="opencode", model="provider/model", repeats=2),
        tmp_path / "hashmarks",
        tmp_path,
        tmp_path / "receipt.json",
    )
    assert status == "ENVIRONMENT_BLOCKED"
    assert len(calls) == len(rows) == 1


def test_selection_timeout_keeps_partial_event_log_as_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        host_gate,
        "_configure_opencode_mcp",
        lambda *_args, **_kwargs: (None, "opencode.json", {}),
    )

    def timed_out(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(
            ["opencode", "run"], 120, output=b'{"type":"text"}\n'
        )

    monkeypatch.setattr(host_gate, "_opencode_run", timed_out)
    result = host_gate._selection_trial(
        Namespace(opencode="opencode", model="provider/model"),
        tmp_path / "hashmarks",
        tmp_path,
        tmp_path / "receipt.json",
        host_gate.SELECTION_SCENARIOS[0],
        0,
    )
    assert result["semantic_outcome"] == "incomplete"
    assert result["trial_status"] == "INCOMPLETE"
    assert result["host_error"] == "OpenCode model call timed out"
    assert Path(result["event_log"]).read_text() == '{"type":"text"}\n'


def test_main_retains_environment_blocked_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        host_gate,
        "_selection_diagnostic",
        lambda *_args: {
            "schema": "hashmarks.opencode-selection-diagnostic.v1",
            "status": "ENVIRONMENT_BLOCKED",
            "results": [],
        },
    )
    receipt = tmp_path / "blocked.json"
    assert host_gate.main(["--selection-diagnostic", "--receipt", str(receipt)]) == 2
    assert json.loads(receipt.read_text())["status"] == "ENVIRONMENT_BLOCKED"


@pytest.mark.parametrize("status", ["FAIL", "INCOMPLETE"])
def test_main_does_not_accept_failed_or_incomplete_selection(
    status: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        host_gate,
        "_selection_diagnostic",
        lambda *_args: {
            "schema": "hashmarks.opencode-selection-diagnostic.v1",
            "status": status,
        },
    )
    receipt = tmp_path / "failed.json"
    assert host_gate.main(["--selection-diagnostic", "--receipt", str(receipt)]) == 1
    assert json.loads(receipt.read_text())["status"] == status


def test_host_gate_runs_both_protocol_phases_and_binds_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "opencode.json").write_text("{}\n", encoding="utf-8")
    receipt_path = tmp_path / "receipts" / "gate.json"
    args = Namespace(
        opencode="opencode",
        uv="uv",
        python="3.14",
        receipt=str(receipt_path),
    )
    monkeypatch.setattr(host_gate.shutil, "which", lambda _name: "/bin/opencode")

    def fake_run(argv, *, cwd, env=None, timeout=600):
        del cwd, env, timeout
        if argv == ["opencode", "--version"]:
            return subprocess.CompletedProcess(argv, 0, "opencode 2.0.4\n", "")
        if argv[:2] == ["uv", "build"]:
            build_dir = Path(argv[argv.index("--out-dir") + 1])
            (build_dir / "hashmarks-1.0.0-py3-none-any.whl").write_bytes(b"wheel")
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(host_gate, "_run", fake_run)
    monkeypatch.setattr(
        host_gate,
        "_package_versions",
        lambda _python: {"hashmarks": "1.0.0", "mcp": "1.0"},
    )
    monkeypatch.setattr(
        host_gate,
        "_installed_mcp_contract",
        lambda *_args, **_kwargs: {
            "schema": "hashmarks.mcp-contract.v1",
            "contract_identity": "sha256:" + "a" * 64,
            "server_version": "1.0.0",
            "tools": list(host_gate.MCP_WORKFLOW_HOST_QUALIFICATION_TOOLS),
        },
    )
    registration_env = {"QUALIFICATION": "opencode"}
    monkeypatch.setattr(
        host_gate,
        "_configure_opencode_mcp",
        lambda *args, **kwargs: (
            subprocess.CompletedProcess([], 0, "hashmarks connected\n", ""),
            "opencode.json",
            registration_env,
        ),
    )
    phase1_events = [
        _tool_event(
            "hashmarks_repository_context",
            {"schema": "hashmarks.repository-capsule.v1", "generation": 1},
        ),
        _tool_event(
            "hashmarks_find",
            {
                "schema": "hashmarks.mcp-find.v1",
                "results": [{"path": host_gate.CHANGED_PATH}],
            },
        ),
        _tool_event(
            "hashmarks_task_evidence",
            {
                "schema": "hashmarks.task-evidence.v2",
                "ownership": {
                    "status": "resolved",
                    "owner": {"path": host_gate.CHANGED_PATH},
                },
                "evidence_receipt": {
                    "codemap_generation": 1,
                    "evidence_identity": "sha256:evidence",
                },
            },
        ),
        _tool_event(
            "hashmarks_change_impact",
            {"schema": "hashmarks.task-change-impact.v1"},
        ),
    ]
    phase2_events = [
        _tool_event(
            "hashmarks_post_change",
            {
                "schema": "hashmarks.task-post-change-delta.v2",
                "status": "changed",
                "generation_before": 1,
                "generation_after": 2,
                "invalidated": [host_gate.CHANGED_PATH],
                "path_changes": [{"path": host_gate.CHANGED_PATH, "state": "changed"}],
            },
        ),
        _tool_event(
            "hashmarks_repository_context",
            {"schema": "hashmarks.repository-capsule.v1", "generation": 2},
        ),
    ]
    calls = []

    def fake_opencode_run(opencode, *, repo, prompt, env, session_id=None):
        del opencode, repo, prompt
        calls.append((env, session_id))
        events = phase1_events if session_id is None else phase2_events
        return subprocess.CompletedProcess(
            [], 0, "\n".join(json.dumps(event) for event in events) + "\n", ""
        )

    monkeypatch.setattr(host_gate, "_opencode_run", fake_opencode_run)

    receipt = host_gate._host_gate(args, project)

    assert receipt["status"] == "PASS"
    assert receipt["host"] == {"name": "opencode", "version": "opencode 2.0.4"}
    assert receipt["model_authority"] == "opencode-native-config"
    assert receipt["mcp_contract"]["schema"] == "hashmarks.mcp-contract.v1"
    assert receipt["mcp_contract"]["server_version"] == "1.0.0"
    assert "model" not in receipt
    assert receipt["phase1"]["generation"] == 1
    assert receipt["phase2"]["generation_after"] == 2
    assert calls == [(registration_env, None), (registration_env, "ses_123")]
    assert Path(receipt["logs"]["phase1"]["path"]).is_file()
    assert Path(receipt["logs"]["phase2"]["path"]).is_file()
