from __future__ import annotations

import json
from pathlib import Path

from hashmarks.codemap import CodeMap

ROOT = Path(__file__).resolve().parents[1]
RETAINED = ROOT / "benchmarks/agent_evaluation/retained/challenge/base"


def _cases():
    for corpus in sorted((RETAINED / "corpora").glob("*.json")):
        payload = json.loads(corpus.read_text(encoding="utf-8"))
        repo = RETAINED / "repos" / corpus.stem
        for task in payload["tasks"]:
            yield repo, task


def test_retained_real_repositories_preserve_expected_top_file() -> None:
    misses: list[str] = []
    checked = 0
    for repo, task in _cases():
        with CodeMap(repo) as codemap:
            codemap.sync()
            results = codemap.search(task["query"], limit=5)
        checked += 1
        paths = [str(row["path"]) for row in results]
        if not any(expected in paths for expected in task["expected_files"]):
            misses.append(f"{task['id']}: expected={task['expected_files']} got={paths}")
    assert checked >= 18
    assert not misses, "\n".join(misses)


def test_retained_real_repositories_keep_search_deterministic_across_rebuild() -> None:
    repo = RETAINED / "repos/python-orders"
    query = "OrderService submit_order implementation"
    with CodeMap(repo) as codemap:
        codemap.sync()
        first = [
            (row["path"], row.get("name"), row.get("kind"))
            for row in codemap.search(query, limit=8)
        ]
        codemap.sync(force=True)
        rebuilt = [
            (row["path"], row.get("name"), row.get("kind"))
            for row in codemap.search(query, limit=8)
        ]
    assert first == rebuilt


def test_retained_real_repository_irrelevant_query_terms_do_not_erase_owner_file() -> None:
    repo = RETAINED / "repos/python-orders"
    with CodeMap(repo) as codemap:
        codemap.sync()
        baseline = codemap.search("OrderService submit_order implementation", limit=8)
        mutated = codemap.search(
            "OrderService submit_order implementation unrelated_observation_marker",
            limit=8,
        )
    baseline_paths = [str(row["path"]) for row in baseline]
    mutated_paths = [str(row["path"]) for row in mutated]
    assert "src/orders/service.py" in baseline_paths
    assert "src/orders/service.py" in mutated_paths
