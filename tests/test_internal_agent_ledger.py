import json
import subprocess
import sys
from pathlib import Path

import pytest

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


def test_ledger_search_uses_grep_when_rg_is_unavailable(
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
    real_which = ledger.shutil.which
    monkeypatch.setattr(
        ledger.shutil,
        "which",
        lambda name: None if name == "rg" else real_which(name),
    )

    _invoke(monkeypatch, state, "search", "--pattern", "answer")

    assert "owner.py:1:answer = 42" in capsys.readouterr().out


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
