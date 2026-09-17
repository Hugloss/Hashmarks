import json
from pathlib import Path

import pytest

from scripts.agent_evaluation.generate_hard_agent_corpus import CATEGORIES, generate


def test_generator_keeps_public_answer_blind_and_secret_external(tmp_path: Path):
    repo = tmp_path / "worker"
    public = tmp_path / "authority" / "public.json"
    secret = tmp_path / "authority" / "secret.json"
    manifest = generate(repo, public, secret, cases_per_category=2)
    pub = json.loads(public.read_text())
    sec = json.loads(secret.read_text())
    assert manifest["tasks"] == 2 * len(CATEGORIES)
    assert all(set(row) == {"id", "query"} for row in pub["tasks"])
    assert all("expected_edit_path" in row for row in sec["tasks"])
    assert not list(repo.rglob("*secret*"))
    assert not (repo / "benchmarks" / "agent_tasks.json").exists()


def test_generator_covers_every_hardness_category(tmp_path: Path):
    repo = tmp_path / "worker"
    public = tmp_path / "public.json"
    secret = tmp_path / "secret.json"
    generate(repo, public, secret, cases_per_category=1)
    categories = {row["category"] for row in json.loads(secret.read_text())["tasks"]}
    assert categories == set(CATEGORIES)


def test_generator_is_deterministic(tmp_path: Path):
    a = tmp_path / "a"; b = tmp_path / "b"
    pa = tmp_path / "pa.json"; sa = tmp_path / "sa.json"
    pb = tmp_path / "pb.json"; sb = tmp_path / "sb.json"
    ma = generate(a, pa, sa, cases_per_category=1)
    mb = generate(b, pb, sb, cases_per_category=1)
    assert pa.read_bytes() == pb.read_bytes()
    assert sa.read_bytes() == sb.read_bytes()
    assert ma["public_identity"] == mb["public_identity"]
    assert ma["secret_identity"] == mb["secret_identity"]


def test_generator_refuses_secret_inside_worker_repo(tmp_path: Path):
    repo = tmp_path / "worker"
    with pytest.raises(ValueError):
        generate(repo, tmp_path / "public.json", repo / "secret.json", cases_per_category=1)
