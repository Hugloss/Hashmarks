from __future__ import annotations

from typing import TYPE_CHECKING

from hashmarks.codemap import CodeMap
from hashmarks.codemap.ownership_graph import (
    OwnershipGraphMixin,
    _OwnershipGraphState,
)

if TYPE_CHECKING:
    from pathlib import Path


def _state() -> _OwnershipGraphState:
    return _OwnershipGraphState(
        start="tests/test_start.py",
        task_terms={"target"},
        nodes={},
        edges=[],
        candidates={},
        parents={},
        seen={"tests/test_start.py"},
    )


def _ranked_delegation() -> list[dict[str, object]]:
    return [
        {
            "path": "src/owner.py",
            "depth": 3,
            "corroborated": True,
            "task_locality_terms": ["target", "owner"],
            "relations": ["calls"],
            "exact_edges": 0,
        },
        {
            "path": "src/facade.py",
            "depth": 2,
            "corroborated": True,
            "task_locality_terms": ["target"],
            "relations": ["imports"],
            "exact_edges": 1,
        },
    ]


def _delegation_edge() -> dict[str, object]:
    return {
        "from": "src/facade.py",
        "to": "src/owner.py",
        "relation": "calls",
        "depth": 3,
        "resolution": "import-constrained-symbol",
        "cycle": False,
        "revisited": False,
    }


def test_edge_bound_cannot_become_structural_owner_absence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src/start.py").write_text(
        "def start():\n    return 1\n",
        encoding="utf-8",
    )
    probed_edges = [{"kind": "other"} for _ in range(101)]

    with CodeMap(tmp_path) as codemap:
        codemap.sync()

        def edges_many(paths, *, limit_per_path):
            assert paths == ["src/start.py"]
            assert limit_per_path == 101
            return {"src/start.py": probed_edges[:limit_per_path]}

        monkeypatch.setattr(codemap, "_session_edges_for_paths_many", edges_many)
        graph = codemap.ownership_relation_graph(
            "change target behavior",
            "src/start.py",
            max_depth=3,
        )

    assert graph["selected"] is None
    assert graph["selection_reason"] == "unresolved-search-incomplete"
    assert graph["completeness"] == "incomplete"
    assert graph["truncation"] == "truncated"
    assert graph["negative_evidence_admissible"] is False
    assert graph["uniqueness_admissible"] is False
    assert graph["search_bound_reasons"] == ["edge-per-path-limit"]
    assert len(graph["edges"]) == 0


def test_symbol_candidate_bound_is_observed_before_ownership_filtering(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state = _state()
    expandable = [("src/start.py", 0, ("src/start.py",))]
    edge_map = {
        "src/start.py": [
            {
                "kind": "call",
                "target_short": "target",
            }
        ]
    }
    symbols = [
        {
            "path": f"src/candidate_{index}.py",
            "name": "target",
            "qualname": "target",
        }
        for index in range(13)
    ]

    with CodeMap(tmp_path) as codemap:

        def exact_symbols(names, *, limit):
            assert names == ["target"]
            assert limit == 13
            return symbols[:limit]

        monkeypatch.setattr(codemap, "_session_exact_symbol_candidates", exact_symbols)
        symbol_map = codemap._ownership_symbol_map(state, expandable, edge_map)

    assert len(symbol_map["target"]) == 12
    assert state.search_bound_reasons == {"symbol-candidate-limit"}


def test_incomplete_ownership_graph_cannot_manufacture_unique_delegation() -> None:
    state = _state()
    state.edges.append(_delegation_edge())
    state.search_bound_reasons.add("edge-per-path-limit")

    selected, reason = OwnershipGraphMixin._select_ownership_candidate(
        state,
        _ranked_delegation(),
        3,
    )

    assert selected is not None
    assert selected["path"] == "src/facade.py"
    assert reason == "bounded-two-hop-corroboration-search-incomplete"


def test_complete_ownership_graph_can_still_select_unique_delegation() -> None:
    state = _state()
    state.edges.append(_delegation_edge())

    selected, reason = OwnershipGraphMixin._select_ownership_candidate(
        state,
        _ranked_delegation(),
        3,
    )

    assert selected is not None
    assert selected["path"] == "src/owner.py"
    assert reason == "unique-task-local-delegation-continuation"
