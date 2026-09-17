from __future__ import annotations

from scripts.mcp_concurrency_stress import _run_round


def test_mcp_multi_process_readers_remain_fail_closed_during_live_mutation() -> None:
    """OSS regression: independent MCP-style processes may share one changing workspace.

    Keep this deliberately smaller than the release stress so `make test` remains suitable
    for normal contributors. The heavier release gate remains `make mcp-concurrency-stress`.
    """

    result = _run_round(
        round_number=1,
        workers=4,
        calls=16,
        writes=10,
        extra_files=24,
    )

    assert result["status"] == "PASS", result
    assert result["successful_calls"] == result["expected_calls"] == 64
    assert result["errors"] == []
    assert result["building_payloads"] == 0
    assert result["generation_regressions"] == 0
    assert result["process_failures"] == []
