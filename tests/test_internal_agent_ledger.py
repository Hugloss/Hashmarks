import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.agent_evaluation import grade_internal_agent_runs as grader
from scripts.agent_evaluation import internal_agent_ledger as ledger


def _invoke(monkeypatch: pytest.MonkeyPatch, state: Path, *args: str) -> None:
    monkeypatch.setattr(sys, "argv", ["ledger", "--state", str(state), *args])
    ledger.main()


def test_ledger_native_lifecycle_records_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "owner.py"
    source.write_text("answer = 'old'\n", encoding="utf-8")
    state = tmp_path / "state.json"
    output = tmp_path / "sealed.json"

    _invoke(
        monkeypatch,
        state,
        "init",
        "--task-id",
        "task-1",
        "--lane",
        "native",
        "--repo",
        str(repo),
        "--query",
        "change answer",
    )
    _invoke(monkeypatch, state, "search", "--pattern", "answer")
    _invoke(monkeypatch, state, "read", "--path", "owner.py")
    _invoke(
        monkeypatch,
        state,
        "edit",
        "--path",
        "owner.py",
        "--old",
        "old",
        "--new",
        "new",
    )
    _invoke(
        monkeypatch,
        state,
        "finalize",
        "--selected-edit",
        "owner.py",
        "--verified",
        "true",
        "--output",
        str(output),
    )

    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["sealed"] is True
    assert result["metrics"]["tool_calls"] == 3
    assert result["metrics"]["search_calls"] == 1
    assert result["metrics"]["read_calls"] == 1
    assert source.read_text(encoding="utf-8") == "answer = 'new'\n"
    assert result["identity"] in capsys.readouterr().out


def test_ledger_search_uses_python_when_rg_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "owner.py").write_text("answer = 42\n", encoding="utf-8")
    state = tmp_path / "state.json"
    _invoke(
        monkeypatch,
        state,
        "init",
        "--task-id",
        "task-1",
        "--lane",
        "native",
        "--repo",
        str(repo),
        "--query",
        "answer",
    )
    monkeypatch.setattr(ledger.shutil, "which", lambda _name: None)

    _invoke(monkeypatch, state, "search", "--pattern", "answer")

    assert capsys.readouterr().out == "owner.py:1:answer = 42\n"
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["events"][-1]["provider"] == "python"


def test_ledger_rg_and_python_search_normalize_to_same_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "owner.py").write_text("answer = 42\n", encoding="utf-8")

    monkeypatch.setattr(ledger.shutil, "which", lambda _name: None)
    python_output, python_provider = ledger._search_output(repo, "answer")

    monkeypatch.setattr(
        ledger.shutil, "which", lambda name: "/fake/rg" if name == "rg" else None
    )
    monkeypatch.setattr(
        ledger.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(
            argv,
            0,
            stdout="./owner.py:1:answer = 42\n",
            stderr="",
        ),
    )
    rg_output, rg_provider = ledger._search_output(repo, "answer")

    assert python_output == rg_output == "owner.py:1:answer = 42\n"
    assert (python_provider, rg_provider) == ("python", "rg")


def test_ledger_packet_and_verification_capture_subprocess_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    state = tmp_path / "state.json"
    _invoke(
        monkeypatch,
        state,
        "init",
        "--task-id",
        "task-1",
        "--lane",
        "hashmarks",
        "--repo",
        str(repo),
        "--query",
        "find owner",
    )

    def fake_run(argv, **kwargs):
        if "-c" in argv:
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps(
                    {
                        "wall_ms": 1.5,
                        "packet": {
                            "identity": {"decision_generation": "sha256:packet"},
                            "edit": {"path": "owner.py"},
                        },
                    }
                ),
                stderr="",
            )
        return subprocess.CompletedProcess(argv, 0, stdout="passed\n", stderr="")

    monkeypatch.setattr(ledger.subprocess, "run", fake_run)
    _invoke(
        monkeypatch,
        state,
        "packet",
        "--source",
        str(tmp_path),
        "--budget",
        "128",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["ledger", "--state", str(state), "verify", "--path", "test_owner.py"],
    )
    with pytest.raises(SystemExit, match="0"):
        ledger.main()

    saved = json.loads(state.read_text(encoding="utf-8"))
    assert [event["kind"] for event in saved["events"]] == [
        "task_received",
        "hashmarks_packet",
        "verification",
    ]
    assert saved["events"][-1]["passed"] is True


def test_ledger_cli_rejects_oracle_secret_argument(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state.json"
    secret = tmp_path / "secret.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ledger",
            "--state",
            str(state),
            "--secret",
            str(secret),
            "init",
            "--task-id",
            "task-1",
            "--lane",
            "native",
            "--repo",
            str(tmp_path),
            "--query",
            "find owner",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        ledger.main()

    assert exc_info.value.code == 2
    assert not state.exists()


def test_grader_rejects_unsealed_trace_then_joins_secret_for_sealed_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    trace_path = runs / "task-1.json"
    secret_path = tmp_path / "secret.json"
    output = tmp_path / "graded.json"

    trace = {
        "sealed": False,
        "task_id": "task-1",
        "lane": "native",
        "identity": "sha256:trace",
        "events": [
            {
                "kind": "final_result",
                "selected_edit": "owner.py",
                "verified": True,
            }
        ],
        "metrics": {
            "tool_calls": 1,
            "search_calls": 0,
            "read_calls": 0,
            "repository_read_bytes": 0,
            "hashmarks_visible_bytes": 0,
            "verification_attempts": 1,
            "failed_verifications": 0,
            "wall_ms": 1.0,
        },
    }
    trace_path.write_text(json.dumps(trace), encoding="utf-8")
    secret_path.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": "task-1",
                        "category": "ownership",
                        "expected_edit_path": "owner.py",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "grade",
            "--runs",
            str(runs),
            "--secret",
            str(secret_path),
            "--output",
            str(output),
        ],
    )

    with pytest.raises(AssertionError):
        grader.main()
    assert not output.exists()

    trace["sealed"] = True
    trace_path.write_text(json.dumps(trace), encoding="utf-8")
    grader.main()

    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["protocol"]["secret_join_after_trace_seal"] is True
    assert result["rows"][0]["edit_correct"] is True
