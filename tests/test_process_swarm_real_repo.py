from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.agent_evaluation.process_swarm_real_repo_v2 import (
    STRATEGIES,
    SwarmRunConfig,
    run,
    worker,
)


def _fixture(root: Path) -> tuple[Path, Path, Path]:
    repo = root / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src" / "feature.py").write_text(
        "def flare041(value: int) -> int:\n    return value + 1\n",
        encoding="utf-8",
    )
    (repo / "tests" / "test_feature.py").write_text(
        "from src.feature import flare041\n\n"
        "def test_flare041():\n    assert flare041(1) == 2\n",
        encoding="utf-8",
    )
    public = root / "public.json"
    public.write_text(
        json.dumps({"tasks": [{"id": "flare", "query": "change flare041"}]}),
        encoding="utf-8",
    )
    secret = root / "secret.json"
    secret.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": "flare",
                        "expected_files": ["src/feature.py"],
                        "expected_symbols": ["flare041"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return repo, public, secret


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_process_swarm_worker_records_each_strategy(
    tmp_path: Path, strategy: str
) -> None:
    repo, _public, _secret = _fixture(tmp_path)
    trace = worker(
        str(repo),
        {"id": "flare", "query": "change flare041"},
        strategy,
        20,
        str(tmp_path / "traces"),
    )

    assert trace["schema"] == "hashmarks.process-swarm-trace.v2"
    assert trace["strategy"] == strategy
    assert trace["top_candidates"]
    assert trace["events"]
    assert Path(trace["trace_file"]).is_file()


def test_process_swarm_run_freezes_workers_before_hidden_grading(
    tmp_path: Path,
) -> None:
    repo, public, secret = _fixture(tmp_path)
    output = tmp_path / "result.json"

    result = run(
        SwarmRunConfig(
            repo=repo,
            public_path=public,
            secret_path=secret,
            output=output,
            trace_dir=tmp_path / "traces",
            workers=1,
            limit=20,
        )
    )

    assert result["schema"] == "hashmarks.process-swarm-real-repo.v2"
    assert result["summary"]["tasks"] == 1
    assert result["summary"]["workers_launched"] == len(STRATEGIES)
    assert set(result["summary"]["strategies"]) == set(STRATEGIES)
    assert len(result["results"]) == len(STRATEGIES)
    assert all(row["expected_files"] == ["src/feature.py"] for row in result["results"])
    assert result["protocol_identity"]
    assert output.is_file()


def test_process_swarm_run_rejects_hidden_fields_in_public_tasks(
    tmp_path: Path,
) -> None:
    repo, public, secret = _fixture(tmp_path)
    payload = json.loads(public.read_text(encoding="utf-8"))
    payload["tasks"][0]["expected_files"] = ["src/feature.py"]
    public.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="only id/query"):
        run(
            SwarmRunConfig(
                repo=repo,
                public_path=public,
                secret_path=secret,
                output=tmp_path / "result.json",
                trace_dir=tmp_path / "traces",
                workers=1,
                limit=20,
            )
        )
