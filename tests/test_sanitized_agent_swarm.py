from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from scripts.agent_evaluation import sanitized_agent_swarm as MODULE

if TYPE_CHECKING:
    from pathlib import Path


def test_sanitized_swarm_rejects_answer_key_inside_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "benchmarks").mkdir(parents=True)
    (repo / "benchmarks" / "agent_tasks.json").write_text('{"tasks": []}\n')
    public = tmp_path / "public.json"
    secret = tmp_path / "secret.json"
    public.write_text(json.dumps({"tasks": [{"id": "a", "query": "x"}]}))
    secret.write_text(json.dumps({"tasks": [{"id": "a", "expected_files": []}]}))
    with pytest.raises(RuntimeError, match="answer key"):
        MODULE._guard(repo, public, secret)


def test_sanitized_swarm_rejects_hidden_public_fields(tmp_path: Path) -> None:
    public = tmp_path / "public.json"
    public.write_text(
        json.dumps({"tasks": [{"id": "a", "query": "x", "expected_files": ["x.py"]}]})
    )
    with pytest.raises(ValueError, match="exactly id/query"):
        MODULE._load_public(public)
