from __future__ import annotations

import json
from pathlib import Path

import pytest


_MODULE = __import__("scripts.agent_evaluation.agent_runner_journal", fromlist=["*"])


def _load():
    return _MODULE

def _init(module, journal: Path) -> None:
    module.init_journal(
        journal,
        runner_identity="runner:oh-goon:v1", task_id="t1", task_revision="v1",
        repository_identity="sha256:repo", mode="baseline", run_id="run-1",
        model_identity="model-x", model_config_identity="sha256:model",
        tool_map={"search": "repository_search", "read": "file_read", "edit": None},
    )


def test_journal_records_out_of_order_files_and_finalizes_in_sequence(tmp_path: Path) -> None:
    module = _load(); journal = tmp_path / "journal"; _init(module, journal)
    module.record_event(journal, {"sequence": 2, "tool": "read", "path": "src/a.py", "estimated_tokens": 20})
    module.record_event(journal, {"sequence": 0, "tool": "search", "query": "a", "returned_paths": ["src/a.py"], "estimated_tokens": 5})
    module.record_event(journal, {"sequence": 1, "tool": "edit", "path": "src/a.py"})
    raw = tmp_path / "raw.json"; normalized = tmp_path / "trace.json"
    payload = module.finalize_journal(journal, raw, normalized_output=normalized)
    assert [event["sequence"] for event in payload["events"]] == [0, 1, 2]
    trace = json.loads(normalized.read_text())
    assert trace["schema"] == "hashmarks.agent-trace.v2"
    assert [event["kind"] for event in trace["events"]] == ["repository_search", "file_read"]
    assert trace["normalization"]["explicitly_ignored_events"] == 1


def test_duplicate_sequence_fails_without_overwriting_first_event(tmp_path: Path) -> None:
    module = _load(); journal = tmp_path / "journal"; _init(module, journal)
    module.record_event(journal, {"sequence": 0, "tool": "search", "query": "first"})
    with pytest.raises(ValueError, match="already exists"):
        module.record_event(journal, {"sequence": 0, "tool": "search", "query": "second"})
    event = json.loads((journal / "events" / "00000000000000000000.json").read_text())
    assert event["query"] == "first"


def test_undeclared_tool_and_path_escape_fail_before_recording(tmp_path: Path) -> None:
    module = _load(); journal = tmp_path / "journal"; _init(module, journal)
    with pytest.raises(ValueError, match="not explicitly declared"):
        module.record_event(journal, {"sequence": 0, "tool": "mystery"})
    with pytest.raises(ValueError, match="repository-relative"):
        module.record_event(journal, {"sequence": 1, "tool": "read", "path": "../secret"})
    assert list((journal / "events").glob("*.json")) == []


def test_journal_init_is_create_only(tmp_path: Path) -> None:
    module = _load(); journal = tmp_path / "journal"; _init(module, journal)
    with pytest.raises(ValueError, match="already exists"):
        _init(module, journal)


def test_finalize_rejects_sequence_gap(tmp_path: Path) -> None:
    module = _load(); journal = tmp_path / "journal"; _init(module, journal)
    module.record_event(journal, {"sequence": 0, "tool": "search", "query": "x"})
    module.record_event(journal, {"sequence": 2, "tool": "read", "path": "src/a.py"})
    with pytest.raises(ValueError, match="sequence gap"):
        module.finalize_journal(journal, tmp_path / "raw.json")
