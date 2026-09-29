from __future__ import annotations

from typing import TYPE_CHECKING

from hashmarks.codemap import CodeMap

if TYPE_CHECKING:
    from pathlib import Path

_INDEX_LIMIT = 1024


def _write_plain_owners(tmp_path: Path, *, duplicate: bool = True) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text(
        "def resolve(value):\n    return value\n",
        encoding="utf-8",
    )
    if duplicate:
        (tmp_path / "src" / "b.py").write_text(
            "def resolve(value):\n    return value\n",
            encoding="utf-8",
        )


def _bounded_plain_probe(codemap: CodeMap, monkeypatch) -> None:
    original = codemap._session_exact_symbol_candidates
    actual = list(original(["resolve"], limit=10))
    by_path = {str(row.get("path") or ""): dict(row) for row in actual}
    first = by_path["src/a.py"]
    hidden = by_path["src/b.py"]
    noise = [
        {**first, "path": f"archive/noise_{index:04d}.py"}
        for index in range(_INDEX_LIMIT - 1)
    ]
    probe = [first, *noise, hidden]
    assert len(probe) == _INDEX_LIMIT + 1

    def exact_symbols(names, *, limit):
        normalized = {str(name).lower() for name in names}
        if "resolve" in normalized and limit == _INDEX_LIMIT + 1:
            return probe[:limit]
        return original(names, limit=limit)

    monkeypatch.setattr(codemap, "_session_exact_symbol_candidates", exact_symbols)


def test_bounded_plain_identifier_scan_cannot_hide_duplicate_owner(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_plain_owners(tmp_path)
    task = "Fix resolve behavior"

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        _bounded_plain_probe(codemap, monkeypatch)
        context = codemap._task_action_map_context(task, 1)
        evidence = codemap._task_action_exact_identifier_edit_candidates(
            task, context.rows, context.failed
        )
        action = codemap.task_action_map(task, limit=1, per_role=1)

    assert evidence.candidates == []
    assert evidence.search_complete is False
    assert evidence.bound_reasons == ("plain-ambiguity-symbol-index-limit",)
    assert action["exact_identifier_search"] == {
        "completeness": "incomplete",
        "truncation": "truncated",
        "negative_evidence_admissible": False,
        "uniqueness_admissible": False,
        "bound_reasons": ["plain-ambiguity-symbol-index-limit"],
    }
    assert action["ambiguity"]["ambiguous"] is True
    assert action["ambiguity"]["reason"] == "exact-identifier-search-bounded"
    assert action["owner_basis"] is None
    assert action["ownership_authority"]["owner_resolved"] is False


def test_complete_plain_identifier_scan_can_prove_duplicate_ambiguity(
    tmp_path: Path,
) -> None:
    _write_plain_owners(tmp_path)
    task = "Fix resolve behavior"

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        context = codemap._task_action_map_context(task, 20)
        evidence = codemap._task_action_exact_identifier_edit_candidates(
            task, context.rows, context.failed
        )
        action = codemap.task_action_map(task, limit=20)

    assert {row["path"] for row in evidence.candidates} == {
        "src/a.py",
        "src/b.py",
    }
    assert evidence.search_complete is True
    assert evidence.bound_reasons == ()
    assert action["ambiguity"]["ambiguous"] is True
    assert action["ambiguity"]["reason"] == "multiple-exact-identifier-edit-owners"
    assert action["ownership_authority"]["owner_resolved"] is False


def test_complete_plain_identifier_scan_can_leave_generic_name_unpromoted(
    tmp_path: Path,
) -> None:
    _write_plain_owners(tmp_path, duplicate=False)
    task = "Fix resolve behavior"

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        context = codemap._task_action_map_context(task, 20)
        evidence = codemap._task_action_exact_identifier_edit_candidates(
            task, context.rows, context.failed
        )

    assert evidence.candidates == []
    assert evidence.search_complete is True
    assert evidence.bound_reasons == ()


def test_explicit_identifier_authority_is_independent_of_plain_scan_bound(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_plain_owners(tmp_path)
    (tmp_path / "src" / "owner.py").write_text(
        "def explicit_owner_name(value):\n    return value\n",
        encoding="utf-8",
    )
    original = None

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        original = codemap._session_exact_symbol_candidates
        resolve_rows = list(original(["resolve"], limit=10))
        by_path = {str(row.get("path") or ""): dict(row) for row in resolve_rows}
        first = by_path["src/a.py"]
        hidden = by_path["src/b.py"]
        probe = [
            first,
            *[
                {**first, "path": f"archive/noise_{index:04d}.py"}
                for index in range(_INDEX_LIMIT - 1)
            ],
            hidden,
        ]

        def exact_symbols(names, *, limit):
            normalized = {str(name).lower() for name in names}
            if (
                "resolve" in normalized
                and "explicit_owner_name" in normalized
                and limit == _INDEX_LIMIT + 1
            ):
                return probe[:limit]
            return original(names, limit=limit)

        monkeypatch.setattr(codemap, "_session_exact_symbol_candidates", exact_symbols)
        task = "Refactor explicit_owner_name and resolve behavior"
        action = codemap.task_action_map(task, limit=1, per_role=1)

    assert action["edit"]["path"] == "src/owner.py"
    assert action["owner_basis"] in {"exact-symbol", "unique-exact-symbol"}
    assert action["ownership_authority"]["owner_resolved"] is True
    assert action["exact_identifier_search"]["completeness"] == "complete"
    assert action["exact_identifier_search"]["uniqueness_admissible"] is True
