from pathlib import Path

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
