from __future__ import annotations

from typing import TYPE_CHECKING

from hashmarks.codemap import CodeMap
from hashmarks.codemap.model import SearchHit

if TYPE_CHECKING:
    from pathlib import Path

_INDEX_LIMIT = 1024


def _write_duplicate_owners(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    for name in ("a", "b"):
        (tmp_path / "src" / f"{name}.py").write_text(
            "def collision_owner(value):\n    return value\n",
            encoding="utf-8",
        )
    (tmp_path / "tests" / "test_surface.py").write_text(
        "def test_surface():\n    assert True\n",
        encoding="utf-8",
    )


def _canonical_test_hit() -> SearchHit:
    return SearchHit(
        path="tests/test_surface.py",
        score=100.0,
        kind="symbol",
        name="test_surface",
        qualname="test_surface",
        start_line=1,
        end_line=2,
    )


def _install_bounded_exact_index(
    codemap: CodeMap, monkeypatch, *, visible: bool
) -> None:
    original = codemap._session_exact_symbol_candidates
    actual = list(original(["collision_owner"], limit=10))
    by_path = {str(row.get("path") or ""): dict(row) for row in actual}
    first = by_path["src/a.py"]
    hidden = by_path["src/b.py"]
    stale = [
        {**first, "path": f"archive/noise_{index:04d}.py"}
        for index in range(_INDEX_LIMIT - int(visible))
    ]
    probe = ([first] if visible else []) + stale + [hidden]
    assert len(probe) == _INDEX_LIMIT + 1

    def exact_symbols(names, *, limit):
        normalized = {str(name).lower() for name in names}
        if "collision_owner" in normalized and limit == _INDEX_LIMIT + 1:
            return probe[:limit]
        return original(names, limit=limit)

    monkeypatch.setattr(codemap, "_session_exact_symbol_candidates", exact_symbols)
    monkeypatch.setattr(
        codemap,
        "find_task",
        lambda _task, *, limit=20: (_canonical_test_hit(),)[:limit],
    )


def test_exact_symbol_bound_cannot_manufacture_unique_owner(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_duplicate_owners(tmp_path)

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        _install_bounded_exact_index(codemap, monkeypatch, visible=True)
        task = "Refactor collision_owner without changing behavior"
        context = codemap._task_action_map_context(task, 1)
        evidence = codemap._task_action_exact_identifier_edit_candidates(
            task, context.rows, context.failed
        )
        action = codemap.task_action_map(task, limit=1, per_role=1)

    assert [row["path"] for row in evidence.candidates] == ["src/a.py"]
    assert evidence.search_complete is False
    assert evidence.bound_reasons == ("plain-exact-symbol-index-limit",)
    assert action["owner_basis"] is None
    assert action["ambiguity"]["ambiguous"] is True
    assert action["ambiguity"]["reason"] == "exact-identifier-search-bounded"
    assert action["ownership_authority"]["owner_resolved"] is False
    assert action["exact_identifier_search"] == {
        "completeness": "incomplete",
        "truncation": "truncated",
        "negative_evidence_admissible": False,
        "uniqueness_admissible": False,
        "bound_reasons": ["plain-exact-symbol-index-limit"],
    }


def test_exact_symbol_bound_cannot_become_no_exact_owner_then_structural_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_duplicate_owners(tmp_path)
    (tmp_path / "tests" / "test_surface.py").write_text(
        "from src.a import collision_owner\n\n"
        "def test_surface():\n"
        "    assert collision_owner('x') == 'x'\n",
        encoding="utf-8",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        _install_bounded_exact_index(codemap, monkeypatch, visible=False)
        task = "Refactor collision_owner without changing behavior"
        context = codemap._task_action_map_context(task, 1)
        evidence = codemap._task_action_exact_identifier_edit_candidates(
            task, context.rows, context.failed
        )
        action = codemap.task_action_map(task, limit=1, per_role=1)

    assert evidence.candidates == []
    assert evidence.search_complete is False
    assert evidence.bound_reasons == ("plain-exact-symbol-index-limit",)
    assert action["owner_basis"] is None
    assert action["ownership_resolution"] is None
    assert action["ambiguity"]["ambiguous"] is True
    assert action["ambiguity"]["reason"] == "exact-identifier-search-bounded"
    assert action["ownership_authority"]["owner_resolved"] is False
    assert action["exact_identifier_search"]["negative_evidence_admissible"] is False


def test_complete_exact_symbol_search_can_still_resolve_unique_owner(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "a.py").write_text(
        "def collision_owner(value):\n    return value\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_surface.py").write_text(
        "def test_surface():\n    assert True\n",
        encoding="utf-8",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "Refactor collision_owner without changing behavior",
            limit=1,
            per_role=1,
        )

    assert action["edit"]["path"] == "src/a.py"
    assert action["owner_basis"] in {"exact-symbol", "unique-exact-symbol"}
    assert action["ambiguity"]["ambiguous"] is False
    assert action["ownership_authority"]["owner_resolved"] is True
    assert action["exact_identifier_search"] == {
        "completeness": "complete",
        "truncation": "complete",
        "negative_evidence_admissible": True,
        "uniqueness_admissible": True,
        "bound_reasons": [],
    }


def test_literal_path_remains_independent_authority_when_symbol_index_is_bounded(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_duplicate_owners(tmp_path)

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        _install_bounded_exact_index(codemap, monkeypatch, visible=True)
        action = codemap.task_action_map(
            "Change src/a.py collision_owner behavior",
            limit=1,
            per_role=1,
        )

    assert action["edit"]["path"] == "src/a.py"
    assert action["owner_basis"] == "literal-path"
    assert action["ambiguity"]["ambiguous"] is False
    assert action["ownership_authority"]["owner_resolved"] is True
    assert action["ownership_authority"]["proof_scope"] == (
        "repository-global-path-identity"
    )
    assert action["exact_identifier_search"]["completeness"] == "incomplete"
    assert action["exact_identifier_search"]["uniqueness_admissible"] is False
