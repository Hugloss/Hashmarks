from __future__ import annotations

from typing import TYPE_CHECKING

from hashmarks.codemap import CodeMap

if TYPE_CHECKING:
    from pathlib import Path


def _write_source_and_test(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "alpha.py").write_text(
        "def alpha():\n    return 1\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_alpha.py").write_text(
        "from src.alpha import alpha\n\n"
        "def test_alpha():\n"
        "    assert alpha() == 1\n",
        encoding="utf-8",
    )


def test_task_entry_point_ambiguity_does_not_turn_truncation_into_unambiguous(
    tmp_path: Path,
) -> None:
    _write_source_and_test(tmp_path)

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        narrow = codemap.task_entry_points("source tests alpha", limit=1, per_role=1)
        complete = codemap.task_entry_points("source tests alpha", limit=20, per_role=1)

    assert len(narrow["canonical"]) == 1
    assert narrow["schema"] == "hashmarks.task-entry-points.v3"
    assert narrow["bounds"]["canonical_completeness"] == "incomplete"
    assert narrow["ambiguity"] == {
        "schema": "hashmarks.entry-point-ambiguity.v3",
        "ambiguous": None,
        "reason": "canonical-retrieval-bound-not-exhausted",
        "completeness": "incomplete",
        "truncation": "truncated",
        "explicit_roles": narrow["ambiguity"]["explicit_roles"],
        "alternatives": narrow["ambiguity"]["alternatives"],
        "resolution": {
            "status": "unknown",
            "reason": "canonical-retrieval-bound-not-exhausted",
        },
        "discrimination_question": None,
        "secret_knowledge_used": False,
    }

    assert complete["bounds"]["canonical_completeness"] == "complete"
    assert complete["ambiguity"]["completeness"] == "complete"
    assert complete["ambiguity"]["truncation"] == "complete"
    assert complete["ambiguity"]["ambiguous"] is True
    assert set(complete["ambiguity"]["explicit_roles"]) == {
        "verification",
        "implementation",
    }
    assert complete["ambiguity"]["resolution"]["status"] == "unresolved"


def test_task_entry_point_unambiguous_requires_exhausted_canonical_retrieval(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "alpha.py").write_text(
        "def alpha():\n    return 1\n",
        encoding="utf-8",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.task_entry_points("source tests alpha", limit=20, per_role=1)

    assert packet["bounds"]["canonical_completeness"] == "complete"
    assert packet["ambiguity"]["completeness"] == "complete"
    assert packet["ambiguity"]["truncation"] == "complete"
    assert packet["ambiguity"]["ambiguous"] is False
    assert packet["ambiguity"]["reason"] == "single-or-no-explicit-role-cue"
    assert packet["ambiguity"]["resolution"] == {"status": "not-required"}
