from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from contract_assertions import assert_array, assert_object, assert_records, assert_text

from hashmarks.codemap import CodeMap
from scripts.agent_evaluation.metrics_fresh_multi_repo import materialize_fixture


def _cases(root: Path) -> Iterator[tuple[Path, dict[str, object]]]:
    for _name, repo, corpus in materialize_fixture(root):
        payload = assert_object(json.loads(corpus.read_text(encoding="utf-8")))
        for task in assert_records(payload["tasks"]):
            yield repo, task


def test_canonical_fixture_preserves_expected_top_file(tmp_path: Path) -> None:
    misses: list[str] = []
    checked = 0
    for repo, task in _cases(tmp_path / "fixture"):
        with CodeMap(repo) as codemap:
            codemap.index.sync()
            results = codemap.search.find(assert_text(task["query"]), limit=5)
        checked += 1
        paths = [str(row.path) for row in results]
        expected_files = [
            assert_text(path) for path in assert_array(task["expected_files"])
        ]
        if not any(expected in paths for expected in expected_files):
            misses.append(
                f"{task['id']}: expected={task['expected_files']} got={paths}"
            )
    assert checked >= 18
    assert not misses, "\n".join(misses)


def test_canonical_fixture_keeps_search_deterministic_across_rebuild(
    tmp_path: Path,
) -> None:
    repos = {
        name: repo for name, repo, _corpus in materialize_fixture(tmp_path / "fixture")
    }
    repo = repos["python-orders"]
    query = "OrderService submit_order implementation"
    with CodeMap(repo) as codemap:
        codemap.index.sync()
        first = [
            (row.path, row.name, row.kind)
            for row in codemap.search.find(query, limit=8)
        ]
    with CodeMap(repo) as rebuilt_map:
        rebuilt_map.index.sync()
        rebuilt = [
            (row.path, row.name, row.kind)
            for row in rebuilt_map.search.find(query, limit=8)
        ]
    assert first == rebuilt


def test_canonical_fixture_irrelevant_query_terms_do_not_erase_owner_file(
    tmp_path: Path,
) -> None:
    repos = {
        name: repo for name, repo, _corpus in materialize_fixture(tmp_path / "fixture")
    }
    repo = repos["python-orders"]
    with CodeMap(repo) as codemap:
        codemap.index.sync()
        baseline = codemap.search.find(
            "OrderService submit_order implementation", limit=8
        )
        mutated = codemap.search.find(
            "OrderService submit_order implementation unrelated_observation_marker",
            limit=8,
        )
    baseline_paths = [str(row.path) for row in baseline]
    mutated_paths = [str(row.path) for row in mutated]
    assert "src/orders/service.py" in baseline_paths
    assert "src/orders/service.py" in mutated_paths
