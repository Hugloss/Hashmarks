from pathlib import Path

from scripts.agent_evaluation.generate_hard_agent_corpus import generate
from scripts.agent_evaluation.score_hard_agent_decisions import run


def test_replay_freezes_before_grading_and_reports_all_categories(tmp_path: Path):
    repo = tmp_path / "repo"
    public = tmp_path / "public.json"
    secret = tmp_path / "secret.json"
    out = tmp_path / "out.json"
    manifest = generate(repo, public, secret, cases_per_category=1)
    result = run(repo, public, secret, out, token_budget=512)
    assert result["summary"]["tasks"] == manifest["tasks"]
    assert result["protocol"]["trace_freeze_before_grading"] is True
    assert result["protocol"]["secret_outside_worker_repo"] is True
    assert len(result["categories"]) == 6
    assert all("expected_edit_path" not in row for row in result["results"])


def test_task_specific_symbol_anchor_beats_sibling_contract_noise(tmp_path: Path):
    repo = tmp_path / "repo"
    public = tmp_path / "public.json"
    secret = tmp_path / "secret.json"
    out = tmp_path / "out.json"
    from scripts.agent_evaluation.generate_full_edit_corpus import (
        generate as generate_full,
    )

    generate_full(tmp_path / "repos", public, secret, cases_per_category=2)
    import json
    import shutil

    public_payload = json.loads(public.read_text())
    secret_payload = json.loads(secret.read_text())
    combined = repo
    combined.mkdir()
    (combined / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths=['tests','checks']\n"
    )
    for task in public_payload["tasks"]:
        src = tmp_path / "repos" / task["id"]
        for top in ("src", "tests", "checks", "frontend"):
            if (src / top).exists():
                shutil.copytree(src / top, combined / top, dirs_exist_ok=True)
    from hashmarks.codemap import CodeMap

    with CodeMap(combined) as codemap:
        codemap.sync()
        task = public_payload["tasks"][1]
        packet = codemap.task_decision_packet(task["query"], token_budget=512)
    truth = {r["id"]: r for r in secret_payload["tasks"]}[task["id"]]
    assert packet["edit"]["path"] == truth["expected_edit_path"]


def test_explicit_policy_uses_task_namespace_not_sibling_policy(tmp_path: Path):
    import json
    import shutil

    from scripts.agent_evaluation.generate_full_edit_corpus import (
        generate as generate_full,
    )

    public = tmp_path / "public.json"
    secret = tmp_path / "secret.json"
    roots = tmp_path / "repos"
    repo = tmp_path / "combined"
    generate_full(roots, public, secret, cases_per_category=2)
    pub = json.loads(public.read_text())
    sec = json.loads(secret.read_text())
    truth = {r["id"]: r for r in sec["tasks"]}
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths=['tests','checks']\n"
    )
    for task in pub["tasks"]:
        src = roots / task["id"]
        for top in ("src", "tests", "checks", "frontend"):
            if (src / top).exists():
                shutil.copytree(src / top, repo / top, dirs_exist_ok=True)
    task = next(t for t in pub["tasks"] if t["id"] == "edit-009")
    from hashmarks.codemap import CodeMap

    with CodeMap(repo) as codemap:
        codemap.sync()
        packet = codemap.task_decision_packet(task["query"], token_budget=512)
    assert packet["edit"]["path"] == truth[task["id"]]["expected_edit_path"]
