"""Partial evaluator output remains observable when an external run times out."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts.agent_evaluation.codex_agent_economics import (
    CodexRunConfig,
    _run_one,
    _usage_from_jsonl,
)
from scripts.agent_evaluation.codex_selective_scout_economics import _run_scout


@pytest.mark.parametrize("runner", ["main", "scout"])
@pytest.mark.parametrize(
    "output_case",
    [
        (
            b'{"partial":"caf\xc3\xa9"}\n',
            b"partial \xff",
            '{"partial":"caf\u00e9"}\n',
            "partial \ufffd\nTIMEOUT",
        ),
        ('{"partial":"text"}\n', "stderr", '{"partial":"text"}\n', "stderr\nTIMEOUT"),
        (None, None, "", "\nTIMEOUT"),
    ],
)
def test_timeout_retains_output_and_its_exact_persisted_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    runner: str,
    output_case: tuple[str | bytes | None, str | bytes | None, str, str],
) -> None:
    stdout, stderr, expected_out, expected_error = output_case

    def timeout(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired("fixture", 1, output=stdout, stderr=stderr)

    monkeypatch.setattr(subprocess, "run", timeout)
    config = CodexRunConfig("unused", None, None, "read-only", tmp_path / "bridge", 1)
    task = {"id": "one", "query": "observe the repository"}
    run_dir = tmp_path / "run"
    result = (
        _run_one(config, "native", task, tmp_path, run_dir)
        if runner == "main"
        else _run_scout(config, task, tmp_path, {}, run_dir)
    )

    assert result["returncode"] == 124
    assert result["final"] is None
    assert (run_dir / "events.jsonl").read_bytes() == expected_out.encode("utf-8")
    assert (run_dir / "stderr.txt").read_bytes() == expected_error.encode("utf-8")
    assert (
        result["events_sha256"]
        == "sha256:"
        + hashlib.sha256((run_dir / "events.jsonl").read_bytes()).hexdigest()
    )
    assert (
        result["stderr_sha256"]
        == "sha256:" + hashlib.sha256((run_dir / "stderr.txt").read_bytes()).hexdigest()
    )


@pytest.mark.parametrize("value", [None, True, False, -1, 1.0, "12"])
def test_partial_usage_does_not_promote_invalid_counters(value: object) -> None:
    usage = _usage_from_jsonl(json.dumps({"usage": {"input_tokens": value}}))
    assert usage["input_tokens"] is None
    assert usage["total_tokens"] is None


def test_partial_usage_retains_known_counters_without_inventing_totals() -> None:
    usage = _usage_from_jsonl('{"usage":{"input_tokens":0,"output_tokens":7}}')
    assert usage["input_tokens"] == 0
    assert usage["output_tokens"] == 7
    assert usage["total_tokens"] is None
