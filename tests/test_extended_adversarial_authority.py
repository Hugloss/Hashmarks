from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from hashmarks.codemap import CodeMap
from scripts.agent_evaluation.generate_hard_agent_corpus import generate


def _hard_repo(root: Path, *, cases_per_category: int = 4):
    repo = root / "repo"
    public = root / "public.json"
    secret = root / "secret.json"
    generate(repo, public, secret, cases_per_category=cases_per_category)
    tasks = json.loads(public.read_text(encoding="utf-8"))["tasks"]
    return repo, tasks


def test_cross_task_previous_evidence_never_launders_authority(tmp_path: Path) -> None:
    repo, tasks = _hard_repo(tmp_path)
    with CodeMap(repo) as codemap:
        codemap.sync()
        starts = [codemap.task_evidence(row["query"]) for row in tasks]
        assert all(start["status"].startswith("safe-") for start in starts)
        for index, row in enumerate(tasks):
            foreign = starts[(index + 1) % len(starts)]
            changed = [foreign["edit"]]
            with pytest.raises(ValueError, match="task-mismatch"):
                codemap.task_post_change_delta(row["query"], changed, previous_evidence=foreign)


def test_context_identity_mutation_matrix_fails_closed(tmp_path: Path) -> None:
    repo, tasks = _hard_repo(tmp_path)
    with CodeMap(repo) as codemap:
        codemap.sync()
        for row in tasks:
            start = codemap.task_evidence(row["query"])
            tampered = copy.deepcopy(start)
            tampered["provenance"]["context_identity"] = "sha256:" + "0" * 64
            with pytest.raises(ValueError, match="context-identity-mismatch"):
                codemap.task_post_change_delta(row["query"], [start["edit"]], previous_evidence=tampered)


def test_selected_verification_mutation_is_never_safe_fresh_across_hard_corpus(tmp_path: Path) -> None:
    repo, tasks = _hard_repo(tmp_path)
    with CodeMap(repo) as codemap:
        codemap.sync()
        for row in tasks:
            start = codemap.task_evidence(row["query"])
            verify_path = repo / start["verify_path"]
            original = verify_path.read_text(encoding="utf-8")
            verify_path.write_text(original + "\n# adversarial verification mutation\n", encoding="utf-8")
            stale = codemap.task_evidence(row["query"])
            assert stale["status"] == "safe-stale"
            assert stale["provenance"]["freshness"] == "stale"
            assert stale["provenance"]["freshness_reason"] == "verification-changed-since-selection"
            verify_path.write_text(original, encoding="utf-8")


@pytest.mark.parametrize("fanout", [1, 3, 10, 30, 100])
@pytest.mark.parametrize("limit", [1, 2, 5, 20])
def test_bounded_fanout_never_claims_exhaustive(tmp_path: Path, fanout: int, limit: int) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "core.py").write_text("def shared(): return 1\n", encoding="utf-8")
    for index in range(fanout):
        (tmp_path / "src" / f"consumer_{index}.py").write_text(
            "from src.core import shared\ndef consume(): return shared()\n", encoding="utf-8"
        )
    (tmp_path / "tests" / "test_core.py").write_text(
        "from src.core import shared\ndef test_shared(): assert shared() == 1\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        impact = codemap.task_change_impact(
            "change shared implementation", ["src/core.py"],
            impact_limit_per_surface=limit, max_depth=3,
        )
    implementations = impact["surfaces"]["implementation"]
    assert len(implementations) <= limit
    assert impact["bounds"]["per_surface"] == limit
    assert impact["completeness"] == "not-claimed"
    if fanout > limit:
        assert len(implementations) == limit
