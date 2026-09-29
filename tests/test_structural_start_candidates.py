from __future__ import annotations

from pathlib import Path

from hashmarks.codemap import CodeMap
from hashmarks.codemap.model import SearchHit


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


def _graph(start_path: str, *, incomplete: bool = False) -> dict[str, object]:
    owner = "src/owner_b.py" if start_path.endswith("09.py") else "src/owner_a.py"
    selected = None if incomplete and start_path.endswith("09.py") else owner
    return {
        "schema": "hashmarks.ownership-relation-graph.v1",
        "selected": selected,
        "candidates": (
            [{"path": selected, "depth": 1, "corroboration": ["task-locality"]}]
            if selected
            else []
        ),
        "owner_path": (
            [{"from": start_path, "to": selected, "relation": "imports"}]
            if selected
            else []
        ),
        "completeness": "incomplete" if incomplete and selected is None else "complete",
        "search_bound_reasons": (
            ["edge-per-path-limit"] if incomplete and selected is None else []
        ),
        "cycle_count": 0,
        "revisit_count": 0,
    }


def test_ninth_source_start_changes_observed_structural_ambiguity(
    tmp_path: Path, monkeypatch
) -> None:
    task, hits = _fixture(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        monkeypatch.setattr(
            codemap, "find_task", lambda _task, *, limit=20: hits[:limit]
        )
        monkeypatch.setattr(
            codemap,
            "ownership_relation_graph",
            lambda _task, start_path, *, max_depth=2: _graph(start_path),
        )
        first_eight = codemap.task_action_map(task, limit=8, per_role=1)
        all_nine = codemap.task_action_map(task, limit=9, per_role=1)
        wider_display = codemap.task_action_map(task, limit=9, per_role=4)
        packet = codemap.task_decision_packet(task, limit=9, per_role=1)

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
    assert packet["structural_start_summary"]["candidate_count"] == 9


def test_unselected_graph_bound_and_stale_competitor_remain_visible(
    tmp_path: Path, monkeypatch
) -> None:
    task, hits = _fixture(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        monkeypatch.setattr(
            codemap, "find_task", lambda _task, *, limit=20: hits[:limit]
        )
        monkeypatch.setattr(
            codemap,
            "ownership_relation_graph",
            lambda _task, start_path, *, max_depth=2: _graph(
                start_path, incomplete=True
            ),
        )
        bounded = codemap.task_action_map(task, limit=9)
        last = bounded["structural_starts"]["candidates"][-1]
        assert last["status"] == "graph-incomplete"
        assert last["graph_bound_reasons"] == ["edge-per-path-limit"]
        assert (
            bounded["ambiguity"]["reason"] == "structural-start-observation-incomplete"
        )

        monkeypatch.setattr(
            codemap,
            "ownership_relation_graph",
            lambda _task, start_path, *, max_depth=2: _graph(start_path),
        )
        codemap.sync(["src/route_09.py"])
        before = codemap.task_action_map(task, limit=9)
        assert before["structural_starts"]["observed_owners"] == [
            "src/owner_a.py",
            "src/owner_b.py",
        ]
        generation = codemap.store.generation()
        (tmp_path / "src/owner_b.py").unlink()
        after = codemap.task_action_map(task, limit=9)
        after_generation = codemap.store.generation()

    assert after_generation > generation
    assert after["structural_starts"]["observed_owners"] == ["src/owner_a.py"]
    assert after["structural_starts"]["candidates"][-1]["status"] == "stale"
    assert after["ambiguity"]["reason"] == "structural-start-observation-incomplete"
