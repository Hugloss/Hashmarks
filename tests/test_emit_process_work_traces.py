from __future__ import annotations

import json
from pathlib import Path

from scripts.agent_evaluation import emit_process_work_traces as M


def test_emitter_freezes_answer_blind_not_run_work_trace(tmp_path: Path) -> None:
    repo = tmp_path / "repo"; (repo / "src").mkdir(parents=True); (repo / "tests").mkdir()
    (repo / "src" / "a.py").write_text("class A:\n    pass\n")
    (repo / "tests" / "test_a.py").write_text("from src.a import A\n")
    public = tmp_path / "public.json"; secret = tmp_path / "secret.json"; traces = tmp_path / "traces"
    public.write_text(json.dumps({"tasks": [{"id": "a", "query": "A implementation test"}]}))
    secret.write_text(json.dumps({"tasks": [{"id": "a", "expected_files": ["src/a.py"]}]}))
    paths = M.emit(repo, public, secret, traces)
    trace = json.loads(paths[0].read_text())
    assert trace["schema"] == "hashmarks.agent-work-trace.v1"
    assert next(event for event in trace["events"] if event["kind"] == "verification")["outcome"] == "not-run"
