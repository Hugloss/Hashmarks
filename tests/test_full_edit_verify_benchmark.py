from pathlib import Path

from scripts.agent_evaluation import full_edit_verify_benchmark as benchmark


def test_run_lane_measures_first_edit_and_controlled_recovery(
    tmp_path: Path, monkeypatch
) -> None:
    base = tmp_path / "base"
    base.mkdir()
    (base / "owner.py").write_text("mode = 'old'\n", encoding="utf-8")
    (base / "wrong.py").write_text("mode = 'old'\n", encoding="utf-8")
    tasks = [
        {"id": "recover", "query": "recover owner"},
        {"id": "direct", "query": "edit owner"},
    ]
    packets = {
        "recover": {"edit": {"path": "wrong.py"}},
        "direct": {"edit": {"path": "owner.py"}},
    }
    secret = {
        task["id"]: {
            "expected_edit_path": "owner.py",
            "expected_verify_path": "tests/test_owner.py",
            "category": task["id"],
        }
        for task in tasks
    }
    monkeypatch.setattr(benchmark, "packet_all", lambda *_args: (packets, 4.0))

    def verify(repo: Path, _verify_path: str) -> tuple[bool, float]:
        return "mode = 'new'" in (repo / "owner.py").read_text(), 2.0

    monkeypatch.setattr(benchmark, "verify", verify)
    work = tmp_path / "work"

    result = benchmark.run_lane(tmp_path, base, tasks, secret, work)

    assert result["tasks"] == 2
    assert result["first_edit_correct"] == 1
    assert result["first_verification_passed"] == 1
    assert result["verified_solutions"] == 2
    assert result["verification_attempts"] == 3
    assert result["recovery_attempts"] == 1
    assert result["packet_ms_per_task"] == 2.0
    assert (work / "owner.py").read_text() == "mode = 'old'\n"
    assert (work / "wrong.py").read_text() == "mode = 'old'\n"
