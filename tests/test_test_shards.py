from __future__ import annotations

from pathlib import Path

import pytest

from hashmarks.python_ast_cache import ast_cache_info, clear_ast_cache
from hashmarks.test_shards import ISOLATED_NODEIDS, plan, select


def _write(root: Path, name: str, body: str) -> None:
    tests = root / "tests"
    tests.mkdir(exist_ok=True)
    (tests / name).write_text(body, encoding="utf-8")


def test_plan_is_deterministic_complete_and_non_overlapping(tmp_path: Path) -> None:
    _write(tmp_path, "test_a.py", "def test_one(): pass\ndef test_two(): pass\n")
    _write(
        tmp_path,
        "test_b.py",
        "class TestGroup:\n def test_three(self): pass\n\ndef helper(): pass\n",
    )
    first = plan(tmp_path, 2)
    second = plan(tmp_path, 2)
    assert first == second
    nodes = [n for row in first["shards"] for n in row["nodeids"]]
    assert sorted(nodes) == [
        "tests/test_a.py::test_one",
        "tests/test_a.py::test_two",
        "tests/test_b.py::TestGroup::test_three",
    ]
    assert len(nodes) == len(set(nodes))
    assert first["plan_identity"].startswith("sha256:")


def test_selector_returns_only_requested_shard(tmp_path: Path) -> None:
    _write(tmp_path, "test_a.py", "\n".join(f"def test_{i}(): pass" for i in range(5)))
    chosen = select(tmp_path, 2, 1)
    assert chosen
    assert all(v.startswith("tests/test_a.py::test_") for v in chosen)


def test_selector_rejects_invalid_shard(tmp_path: Path) -> None:
    _write(tmp_path, "test_a.py", "def test_a(): pass\n")
    with pytest.raises(ValueError, match="shard_index"):
        select(tmp_path, 2, 2)


def test_process_sensitive_nodes_are_isolated(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_codemap_watcher.py").write_text(
        "def test_codemap_watcher_keeps_map_hot_without_identity_daemon(): pass\n"
        "def test_other(): pass\n",
        encoding="utf-8",
    )
    payload = plan(tmp_path, 2)
    isolated = [row for row in payload["shards"] if row["isolated_process"]]
    assert len(isolated) == 1
    assert isolated[0]["nodeids"] == [
        "tests/test_codemap_watcher.py::test_codemap_watcher_keeps_map_hot_without_identity_daemon"
    ]


def test_real_repository_isolated_nodes_have_exact_singleton_membership() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = plan(root, 64)
    shards = payload["shards"]
    membership = [nodeid for shard in shards for nodeid in shard["nodeids"]]
    assert len(membership) == len(set(membership)) == payload["test_node_count"]
    assert all(
        len(shard["nodeids"]) == 1 for shard in shards if shard["isolated_process"]
    )
    assert {
        shard["nodeids"][0] for shard in shards if shard["isolated_process"]
    } == set(ISOLATED_NODEIDS)


def test_selector_rejects_more_shards_than_test_nodes(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_one.py").write_text("def test_one(): pass\n", encoding="utf-8")
    with pytest.raises(ValueError, match="test node count"):
        plan(tmp_path, 2)


def test_expensive_benchmark_nodes_are_always_singleton_shards(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_agent_metrics_suite.py").write_text(
        "\n".join(
            [
                "def test_blind_worker_ab_is_reproducible_and_scores_both_workers(): pass",
                "def test_worker_behavior_ab_is_answer_blind_and_reproducible(): pass",
                "def test_worker_inspection_ab_recovers_ambiguity_without_hidden_answers(): pass",
                "def test_worker_multistep_ab_improves_edit_safety_and_preserves_verification(): pass",
                "def test_worker_failed_verification_ab_recovers_without_hidden_answers(): pass",
                "def test_ordinary_metrics_contract(): pass",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    payload = plan(tmp_path, 6)
    isolated = [row for row in payload["shards"] if row["isolated_process"]]
    assert len(isolated) == 5
    assert all(len(row["nodeids"]) == 1 for row in isolated)
    isolated_nodes = {row["nodeids"][0] for row in isolated}
    assert (
        "tests/test_agent_metrics_suite.py::test_ordinary_metrics_contract"
        not in isolated_nodes
    )


def test_expensive_benchmark_nodes_never_mix_with_ordinary_nodes(
    tmp_path: Path,
) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_agent_metrics_suite.py").write_text(
        "def test_blind_worker_ab_is_reproducible_and_scores_both_workers(): pass\n"
        "def test_worker_behavior_ab_is_answer_blind_and_reproducible(): pass\n"
        "def test_ordinary_a(): pass\n"
        "def test_ordinary_b(): pass\n",
        encoding="utf-8",
    )
    payload = plan(tmp_path, 3)
    for row in payload["shards"]:
        if row["isolated_process"]:
            assert len(row["nodeids"]) == 1
        else:
            assert all(
                "blind_worker_ab" not in node and "worker_behavior_ab" not in node
                for node in row["nodeids"]
            )


def test_plan_fails_closed_when_shard_count_cannot_preserve_singleton_isolation(
    tmp_path: Path,
) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_agent_metrics_suite.py").write_text(
        "def test_blind_worker_ab_is_reproducible_and_scores_both_workers(): pass\n"
        "def test_worker_behavior_ab_is_answer_blind_and_reproducible(): pass\n"
        "def test_ordinary(): pass\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="leave at least one non-isolated shard"):
        plan(tmp_path, 2)


def test_repeated_planning_reuses_cached_test_asts(tmp_path: Path) -> None:
    _write(tmp_path, "test_cache.py", "def test_one(): pass\ndef test_two(): pass\n")
    clear_ast_cache()
    before = ast_cache_info()
    first = plan(tmp_path, 1)
    middle = ast_cache_info()
    second = plan(tmp_path, 1)
    after = ast_cache_info()
    assert first == second
    assert middle.misses == before.misses + 1
    assert after.hits >= middle.hits + 1
