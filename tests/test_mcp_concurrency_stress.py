import json
from pathlib import Path

from scripts import mcp_concurrency_stress
from scripts.mcp_concurrency_stress import _failure_details, _summary


def _receipt() -> dict[str, object]:
    return {
        "status": "FAIL",
        "totals": {
            "successful_calls": 1439,
            "expected_calls": 1440,
            "errors": 1,
            "building_payloads": 0,
            "generation_regressions": 0,
        },
        "round_results": [
            {
                "round": 2,
                "errors": ["RuntimeError: synthetic race"],
                "process_failures": [],
            }
        ],
    }


def test_stress_failure_summary_surfaces_captured_exception() -> None:
    summary = _summary(_receipt(), Path("dist/mcp-concurrency-stress.json"))

    assert "HASHMARKS MCP CONCURRENCY STRESS: FAIL" in summary
    assert "calls: 1439/1440" in summary
    assert "failure details:" in summary
    assert "- round 2 error: RuntimeError: synthetic race" in summary


def test_stress_failure_details_are_bounded() -> None:
    rounds = [
        {
            "round": 1,
            "errors": [f"error-{index}" for index in range(20)],
            "process_failures": [],
        }
    ]

    assert len(_failure_details(rounds)) == 8


def test_stress_writes_full_receipt_before_reporting_failed_calls(
    monkeypatch, tmp_path: Path
) -> None:
    round_result = {
        "round": 1,
        "status": "FAIL",
        "expected_calls": 1440,
        "successful_calls": 1439,
        "errors": ["RuntimeError: CodeMap generation changed during decision session"],
        "building_payloads": 0,
        "generation_regressions": 0,
        "process_failures": [],
        "workers": [{"worker": 0, "successes": 1439, "errors": ["race"]}],
    }
    monkeypatch.setattr(
        mcp_concurrency_stress, "_run_round", lambda **_kwargs: round_result
    )
    path = tmp_path / "failed-stress.json"

    result = mcp_concurrency_stress.main(
        ["--rounds", "1", "--workers", "18", "--calls", "80", "--receipt", str(path)]
    )

    assert result == 1
    receipt = json.loads(path.read_text(encoding="utf-8"))
    assert receipt["status"] == "FAIL"
    assert receipt["totals"]["successful_calls"] == 1439
    assert receipt["totals"]["expected_calls"] == 1440
    assert receipt["round_results"] == [round_result]
