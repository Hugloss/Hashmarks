import copy
import json
from pathlib import Path

import pytest

from scripts.agent_evaluation import normalize_agent_trace as normalizer


def _raw() -> dict:
    tool_map = {"search": "repository_search", "ignore": None}
    return {
        "schema": normalizer.RAW_SCHEMA,
        "runner_identity": "runner:test:v1",
        "task_id": "task-1",
        "task_revision": "v1",
        "repository_identity": "sha256:repo",
        "mode": "baseline",
        "run_id": "run-1",
        "model_identity": "model-x",
        "model_config_identity": "sha256:model",
        "normalization_policy_schema": normalizer.POLICY_SCHEMA,
        "normalization_policy_identity": normalizer.normalization_policy_identity(
            tool_map
        ),
        "tool_map": tool_map,
        "events": [
            {
                "sequence": 0,
                "tool": "search",
                "query": "owner",
                "path": "./src/owner.py",
                "paths": ["src/owner.py"],
                "returned_paths": ["tests/test_owner.py"],
                "evidence_paths": ["src/owner.py"],
                "bytes": 12,
                "estimated_tokens": 3,
                "model_input_tokens": 5,
                "started_at_ns": 10,
                "finished_at_ns": 20,
                "fallback": False,
            },
            {"sequence": 1, "tool": "ignore"},
        ],
    }


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_normalize_validates_and_projects_all_event_fields(tmp_path: Path) -> None:
    path = tmp_path / "raw.json"
    _write(path, _raw())

    trace = normalizer.normalize(path)

    assert trace["events"] == [
        {
            "kind": "repository_search",
            "runner_sequence": 0,
            "runner_tool": "search",
            "query": "owner",
            "path": "src/owner.py",
            "paths": ["src/owner.py"],
            "returned_paths": ["tests/test_owner.py"],
            "evidence_paths": ["src/owner.py"],
            "bytes": 12,
            "estimated_tokens": 3,
            "model_input_tokens": 5,
            "started_at_ns": 10,
            "finished_at_ns": 20,
            "fallback": False,
        }
    ]
    assert trace["normalization"] == {
        "schema": normalizer.POLICY_SCHEMA,
        "raw_events": 2,
        "navigation_events": 1,
        "explicitly_ignored_events": 1,
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.update(mode="unknown"), "mode must be"),
        (
            lambda value: value.update(normalization_policy_identity="sha256:wrong"),
            "identity mismatch",
        ),
        (
            lambda value: value["events"][0].update(tool="undeclared"),
            "not explicitly declared",
        ),
        (
            lambda value: value["events"][1].update(sequence=0),
            "strictly increasing",
        ),
        (
            lambda value: value["events"][0].update(finished_at_ns=9),
            "must be >=",
        ),
        (
            lambda value: value["events"][0].update(bytes=-1),
            "non-negative integer",
        ),
    ],
)
def test_normalize_rejects_invalid_authority_and_event_values(
    tmp_path: Path, mutation, message: str
) -> None:
    value = copy.deepcopy(_raw())
    mutation(value)
    path = tmp_path / "raw.json"
    _write(path, value)

    with pytest.raises(ValueError, match=message):
        normalizer.normalize(path)
