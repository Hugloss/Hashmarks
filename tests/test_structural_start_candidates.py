from __future__ import annotations

from pathlib import Path

from contract_assertions import assert_object
from pytest import MonkeyPatch

from hashmarks.codemap import CodeMap
from hashmarks.codemap.model import SearchHit
from hashmarks.codemap.ownership_relation_types import OwnershipRelationGraph


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _fixture(root: Path) -> tuple[str, tuple[SearchHit, ...]]:
    _write(root / "src/__init__.py", "")
    _write(root / "src/owner_a.py", "def owner_a():\n    return 1\n")
    _write(root / "src/owner_b.py", "def owner_b():\n    return 2\n")
    hits = []
    terms = []
    for index in range(1, 10):
        term = f"anchor{index:02d}"
        path = f"src/route_{index:02d}.py"
        _write(root / path, f"def process_{term}():\n    return {index}\n")
        hits.append(
            SearchHit(
                path=path,
                score=float(10 - index),
                kind="symbol",
                name=f"process_{term}",
                qualname=f"process_{term}",
            )
        )
        terms.append(term)
    return "Fix behavior " + " ".join(terms), tuple(hits)


def _graph(
    task: str, start_path: str, *, max_depth: int = 2, incomplete: bool = False
) -> OwnershipRelationGraph:
    owner = "src/owner_b.py" if start_path.endswith("09.py") else "src/owner_a.py"
    selected = None if incomplete and start_path.endswith("09.py") else owner
    complete = not (incomplete and selected is None)
    return {
        "schema": "hashmarks.ownership-relation-graph.v1",
        "task": task,
        "start_path": start_path,
        "max_depth": max_depth,
        "nodes": [],
        "edges": [],
        "selection_reason": "test-fixture",
        "negative_evidence_admissible": complete,
        "uniqueness_admissible": complete,
        "truncation": "complete" if complete else "truncated",
        "bounds": {
            "max_depth": max_depth,
            "edges_per_path": 100,
            "node_symbols": 12,
            "symbols_per_alias": 12,
            "symbol_candidates": 5000,
        },
        "cycle_policy": "bounded-ancestor-cycle-cutoff-plus-revisit-deduplication",
        "relation_authority": "imports-and-calls-are-evidence-not-ownership-truth",
        "secret_knowledge_used": False,
        "selected": selected,
        "candidates": (
            [
                {
                    "path": selected,
                    "depth": 1,
                    "corroboration": ["task-locality"],
                    "relations": ["imports"],
                    "exact_edges": 1,
                    "task_locality_terms": [],
                }
            ]
            if selected
            else []
        ),
        "owner_path": (
            [{"from": start_path, "to": selected, "relation": "imports"}]
            if selected
            else []
        ),
        "completeness": "complete" if complete else "incomplete",
        "search_bound_reasons": ([] if complete else ["edge-per-path-limit"]),
        "cycle_count": 0,
        "revisit_count": 0,
    }


def test_ninth_source_start_changes_observed_structural_ambiguity(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    task, hits = _fixture(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        monkeypatch.setattr(
            codemap.search, "find_task", lambda _task, *, limit=20: hits[:limit]
        )
        monkeypatch.setattr(
            codemap.ownership,
            "relations",
            _graph,
        )
        first_eight = codemap.tasks.action_map(task, limit=8, per_role=1)
        all_nine = codemap.tasks.action_map(task, limit=9, per_role=1)
        wider_display = codemap.tasks.action_map(task, limit=9, per_role=4)
        packet = codemap.tasks.decision_packet(task, limit=9, per_role=1)

    assert first_eight["structural_starts"]["observed_owners"] == ["src/owner_a.py"]
    assert first_eight["structural_starts"]["limit_reached"] is True
    assert first_eight["ownership_authority"]["owner_resolved"] is False
    starts = all_nine["structural_starts"]
    assert [row["start_path"] for row in starts["candidates"]] == [
        hit.path for hit in hits
    ]
    assert starts["observed_owners"] == ["src/owner_a.py", "src/owner_b.py"]
    assert starts["retrieval_completeness"] == "unknown"
    assert all_nine["ambiguity"]["reason"] == "multiple-task-local-structural-owners"
    assert wider_display["structural_starts"] == starts
    assert packet["edit"] is None
    assert assert_object(packet["structural_start_summary"])["candidate_count"] == 9


def test_unselected_graph_bound_and_stale_competitor_remain_visible(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    task, hits = _fixture(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        monkeypatch.setattr(
            codemap.search, "find_task", lambda _task, *, limit=20: hits[:limit]
        )
        monkeypatch.setattr(
            codemap.ownership,
            "relations",
            lambda task, start_path, *, max_depth=2: _graph(
                task, start_path, max_depth=max_depth, incomplete=True
            ),
        )
        bounded = codemap.tasks.action_map(task, limit=9)
        last = bounded["structural_starts"]["candidates"][-1]
        assert last["status"] == "graph-incomplete"
        assert last["graph_bound_reasons"] == ["edge-per-path-limit"]
        assert (
            bounded["ambiguity"]["reason"] == "structural-start-observation-incomplete"
        )

        monkeypatch.setattr(
            codemap.ownership,
            "relations",
            _graph,
        )
        codemap.index.sync(["src/route_09.py"])
        before = codemap.tasks.action_map(task, limit=9)
        assert before["structural_starts"]["observed_owners"] == [
            "src/owner_a.py",
            "src/owner_b.py",
        ]
        generation = codemap.store.generation()
        (tmp_path / "src/owner_b.py").unlink()
        after = codemap.tasks.action_map(task, limit=9)
        after_generation = codemap.store.generation()

    assert after_generation > generation
    assert after["structural_starts"]["observed_owners"] == ["src/owner_a.py"]
    assert after["structural_starts"]["candidates"][-1]["status"] == "stale"
    assert after["ambiguity"]["reason"] == "structural-start-observation-incomplete"
