from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "mcp_host_status.py"
SPEC = importlib.util.spec_from_file_location("mcp_host_status", SCRIPT)
assert SPEC and SPEC.loader
status = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = status
SPEC.loader.exec_module(status)


def test_checked_in_project_configs_are_hashmarks_owned() -> None:
    opencode = json.loads((ROOT / "opencode.json").read_text())
    assert status._is_uv_registration(opencode["mcp"]["hashmarks"]["command"])

    shared = json.loads((ROOT / ".mcp.json").read_text())
    entry = shared["mcpServers"]["hashmarks"]
    assert status._is_uv_registration(entry["command"], entry["args"])

    codex = status.tomllib.loads((ROOT / ".codex" / "config.toml").read_text())
    entry = codex["mcp_servers"]["hashmarks"]
    assert status._is_uv_registration(entry["command"], entry["args"])


def test_render_distinguishes_pi_native_mcp_from_adapter() -> None:
    report = {
        "core": {
            "mcp_server_executable": {"status": "PASS", "detail": ""},
            "mcp_sdk": {"status": "PASS", "detail": ""},
            "mcp_tool_catalog": {"status": "PASS", "detail": "5 tools"},
        },
        "opencode": _host(),
        "claude": _host(),
        "codex": _host(),
        "pi": {
            "installed": {"status": "PASS", "detail": "pi 0.1"},
            "native_mcp": {
                "status": "NO",
                "detail": "Pi core intentionally has no native MCP client",
            },
            "mcp_adapter": {"status": "ADAPTER REQUIRED", "detail": ""},
            "project_registration": {"status": "PASS", "detail": ""},
            "registration_source": {"status": "PASS", "detail": ".mcp.json"},
            "registration_ownership": {"status": "HASHMARKS", "detail": ""},
            "global_hashmarks_registration": {
                "status": "NOT REQUIRED",
                "detail": "Hashmarks registration is project-local",
            },
            "discovery": {"status": "NOT CHECKED", "detail": ""},
            "last_successful_mcp_call": {"status": "NOT RECORDED", "detail": ""},
        },
    }
    text = status.render(report)
    assert "Native MCP client" in text
    assert "ADAPTER REQUIRED" in text


def _host() -> dict[str, dict[str, str]]:
    return {
        "installed": {"status": "NOT INSTALLED", "detail": ""},
        "project_registration": {"status": "PASS", "detail": ""},
        "registration_source": {"status": "PASS", "detail": "local"},
        "registration_ownership": {"status": "HASHMARKS", "detail": ""},
        "global_hashmarks_registration": {
            "status": "NOT REQUIRED",
            "detail": "Hashmarks registration is project-local",
        },
        "discovery": {"status": "NOT CHECKED", "detail": ""},
        "last_successful_mcp_call": {"status": "NOT RECORDED", "detail": ""},
    }


def test_codex_discovery_reports_project_trust_required(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / ".codex").mkdir()
    (workspace / ".codex" / "config.toml").write_text(
        '[mcp_servers.hashmarks]\ncommand = "uv"\nargs = ["run", "--frozen", "--no-sync", "hashmarks", "--workspace", ".", "mcp"]\nenabled = true\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        status,
        "_version",
        lambda *args, **kwargs: status.Check("PASS", "codex-cli 0.154.0"),
    )

    def fake_run(argv, *, cwd, timeout=20):
        import subprocess

        assert cwd == workspace
        if "-c" in argv:
            assert 'trust_level="trusted"' in argv[2]
            return subprocess.CompletedProcess(argv, 0, '{"name":"hashmarks"}\n', "")
        return subprocess.CompletedProcess(
            argv, 1, "", "project config disabled until trusted"
        )

    monkeypatch.setattr(status, "_run", fake_run)
    result = status._codex(workspace, "sha256:test:1")
    assert result.discovery.status == "PROJECT TRUST REQUIRED"
    assert "trust the project once" in result.discovery.detail


def test_opencode_discovery_rejects_misleading_failure_text() -> None:
    import subprocess

    result = subprocess.CompletedProcess(
        ["opencode", "mcp", "list"],
        0,
        "hashmarks: FAILED to connect\n",
        "",
    )
    assert status._opencode_discovery_ok(result) is False


def test_opencode_discovery_requires_connected_state() -> None:
    import subprocess

    result = subprocess.CompletedProcess(
        ["opencode", "mcp", "list"],
        0,
        "hashmarks connected\n",
        "",
    )
    assert status._opencode_discovery_ok(result) is True


def test_codex_discovery_requires_structured_server_identity() -> None:
    import subprocess

    misleading = subprocess.CompletedProcess(
        ["codex", "mcp", "get", "hashmarks", "--json"],
        0,
        '{"error":"hashmarks not found"}\n',
        "",
    )
    valid = subprocess.CompletedProcess(
        ["codex", "mcp", "get", "hashmarks", "--json"],
        0,
        '{"name":"hashmarks","enabled":true}\n',
        "",
    )
    assert status._codex_discovery_ok(misleading) is False
    assert status._codex_discovery_ok(valid) is True


def test_old_unbound_host_receipt_is_stale(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "dist").mkdir()
    registration = workspace / "opencode.json"
    registration.write_text("{}\n", encoding="utf-8")
    (workspace / "dist" / "opencode-mcp-host-gate.json").write_text(
        json.dumps(
            {
                "schema": "hashmarks.opencode-mcp-host-gate.v1",
                "status": "PASS",
                "completed_at": "2020-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    result = status._latest_receipt_call(
        workspace,
        "opencode",
        installed=status.Check("PASS", "opencode v2.0.4"),
        registration_path=registration,
        candidate_identity="sha256:current:1",
    )
    assert result.status == "STALE"
    assert "identity" in result.detail


def test_host_receipt_is_bound_to_registration_host_and_completion(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "repo"
    receipt_dir = workspace / "dist"
    receipt_dir.mkdir(parents=True)
    registration = workspace / "opencode.json"
    registration.write_text("{}\n", encoding="utf-8")
    receipt_path = receipt_dir / "opencode-mcp-host-gate.json"
    base = {
        "schema": "hashmarks.opencode-mcp-host-gate.v1",
        "status": "PASS",
        "source_repository_identity": "sha256:current:1",
        "source_project_registration": {
            "path": "opencode.json",
            "sha256": status._sha256(registration),
        },
        "host": {"name": "opencode", "version": "opencode v2.0.4"},
        "completed_at": "2026-09-23T12:00:00Z",
    }

    def check(payload: dict) -> status.Check:
        receipt_path.write_text(json.dumps(payload), encoding="utf-8")
        return status._latest_receipt_call(
            workspace,
            "opencode",
            installed=status.Check("PASS", "opencode v2.0.4"),
            registration_path=registration,
            candidate_identity="sha256:current:1",
        )

    assert check(base) == status.Check("PASS", "2026-09-23T12:00:00Z")
    mutations = [
        ({**base, "schema": "old"}, "schema"),
        ({**base, "source_project_registration": None}, "registration binding"),
        (
            {
                **base,
                "source_project_registration": {
                    "path": "elsewhere.json",
                    "sha256": status._sha256(registration),
                },
            },
            "registration changed",
        ),
        (
            {
                **base,
                "source_project_registration": {
                    "path": "opencode.json",
                    "sha256": "wrong",
                },
            },
            "bytes changed",
        ),
        ({**base, "host": None}, "host-version binding"),
        (
            {**base, "host": {"name": "opencode", "version": "old"}},
            "version changed",
        ),
        ({**base, "completed_at": ""}, "completion timestamp"),
    ]
    for payload, detail in mutations:
        result = check(payload)
        assert result.status == "STALE"
        assert detail in result.detail


def test_host_receipt_rejects_registration_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    (workspace / "dist").mkdir(parents=True)
    registration = tmp_path / "outside.json"
    registration.write_text("{}\n", encoding="utf-8")
    (workspace / "dist" / "opencode-mcp-host-gate.json").write_text(
        json.dumps(
            {
                "schema": "hashmarks.opencode-mcp-host-gate.v1",
                "status": "PASS",
                "source_repository_identity": "sha256:current:1",
                "source_project_registration": {},
            }
        ),
        encoding="utf-8",
    )

    result = status._latest_receipt_call(
        workspace,
        "opencode",
        installed=status.Check("PASS", "opencode v2.0.4"),
        registration_path=registration,
        candidate_identity="sha256:current:1",
    )
    assert result == status.Check("STALE", "registration path is outside workspace")


def test_codex_discovery_reports_direct_success_and_hard_failure(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = tmp_path / "repo"
    config = workspace / ".codex" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text(
        '[mcp_servers.hashmarks]\ncommand = "uv"\n'
        'args = ["run", "--frozen", "--no-sync", "hashmarks", "--workspace", ".", "mcp"]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        status,
        "_version",
        lambda *args, **kwargs: status.Check("PASS", "codex-cli 0.154.0"),
    )
    calls = []

    def direct_success(argv, *, cwd, timeout=20):
        import subprocess

        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, '{"name":"hashmarks"}\n', "")

    monkeypatch.setattr(status, "_run", direct_success)
    assert status._codex(workspace, "sha256:test:1").discovery == status.Check("PASS")
    assert len(calls) == 1

    def hard_failure(argv, *, cwd, timeout=20):
        import subprocess

        message = "project disabled" if "-c" not in argv else "still unavailable"
        return subprocess.CompletedProcess(argv, 1, "", message)

    monkeypatch.setattr(status, "_run", hard_failure)
    assert status._codex(workspace, "sha256:test:1").discovery == status.Check(
        "FAIL", "project disabled"
    )
