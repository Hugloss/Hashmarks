from __future__ import annotations

from typing import TYPE_CHECKING

from hashmarks.codemap import CodeMap
from hashmarks.codemap.model import SearchHit
from hashmarks.codemap.task_retrieval import _TaskRetrievalResult

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
        "from src.alpha import alpha\n\ndef test_alpha():\n    assert alpha() == 1\n",
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
    assert narrow["schema"] == "hashmarks.task-entry-points.v4"
    assert narrow["bounds"]["canonical_completeness"] == "incomplete"
    canonical_paths = {row["path"] for row in narrow["canonical"]}
    assert {
        row["path"] for row in narrow["ambiguity"]["alternatives"]
    } <= canonical_paths
    assert narrow["ambiguity"] == {
        "schema": "hashmarks.entry-point-ambiguity.v4",
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


def test_internal_task_retrieval_cap_cannot_prove_entry_point_absence(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src"
    source.mkdir()
    for index in range(120):
        (source / f"module_{index:03d}.py").write_text(
            f"def alpha_{index:03d}():\n    return {index}\n", encoding="utf-8"
        )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.task_entry_points("alpha implementation", limit=200)

    assert len(packet["canonical"]) < 120
    assert packet["bounds"]["canonical_completeness"] != "complete"
    assert packet["ambiguity"]["ambiguous"] is None
    assert "probe_limit" not in packet["bounds"]


def test_task_entry_points_reuses_one_retrieval_composition(
    tmp_path: Path, monkeypatch
) -> None:
    _write_source_and_test(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        calls = []
        original = codemap._task_find_sequences

        def tracked(task, limit):
            calls.append((task, limit, codemap.store.generation()))
            return original(task, limit)

        monkeypatch.setattr(codemap, "_task_find_sequences", tracked)
        packet = codemap.task_entry_points("source tests alpha", limit=10)
        cache_keys = [
            key for key in codemap._task_result_cache if key[1] == packet["task"]
        ]

    assert len(calls) == 1
    assert len(cache_keys) == 1
    assert cache_keys[0][2] == 10
    assert len(packet["canonical"]) == 2


def test_stale_cached_task_hit_invalidates_retrieval_completeness(
    tmp_path: Path, monkeypatch
) -> None:
    _write_source_and_test(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        first = codemap.task_entry_points("source tests alpha", limit=20)
        assert first["bounds"]["canonical_completeness"] == "complete"
        monkeypatch.setattr(
            codemap,
            "_indexed_path_current",
            lambda path: path != "tests/test_alpha.py",
        )
        second = codemap.task_entry_points("source tests alpha", limit=20)

    assert second["bounds"]["canonical_completeness"] == "incomplete"
    assert second["bounds"]["canonical_truncation"] == "unknown"
    assert second["ambiguity"]["ambiguous"] is None
    assert "task-stale-cached-hit" in second["bounds"]["bound_reasons"]


def test_query_base_term_limit_invalidates_task_entry_absence(tmp_path: Path) -> None:
    _write_source_and_test(tmp_path)
    terms = "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo"
    (tmp_path / "src" / "alpha.py").write_text(
        f"# {terms}\ndef alpha():\n    return 1\n", encoding="utf-8"
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        task = f"source tests {terms}"
        packet = codemap.task_entry_points(task, limit=20)
        canonical = [hit.as_dict() for hit in codemap.find_task(task, limit=20)]

    assert packet["canonical"] == canonical
    assert "task-query-base-term-limit" in packet["bounds"]["bound_reasons"]
    assert packet["bounds"]["canonical_completeness"] == "incomplete"
    assert packet["ambiguity"]["ambiguous"] is None


def test_query_view_term_limits_invalidate_task_entry_absence(tmp_path: Path) -> None:
    _write_source_and_test(tmp_path)
    (tmp_path / "src" / "alpha.py").write_text(
        "# browser\ndef alpha():\n    return 1\n", encoding="utf-8"
    )
    task = (
        "alpha owner frontend backend plan make generated schedule privacy "
        "observe local release lock dependency browser snapshot retry capacity"
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.task_entry_points(task, limit=20)

    reasons = packet["bounds"]["bound_reasons"]
    assert "task-query-governance-term-limit" in reasons
    assert "task-query-evidence-term-limit" in reasons
    assert packet["ambiguity"]["ambiguous"] is None


def test_omitted_identifier_input_limit_invalidates_task_entry_absence(
    tmp_path: Path,
) -> None:
    _write_source_and_test(tmp_path)
    task = "alpha " + " ".join(f"cue{index:03d}" for index in range(34))

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.task_entry_points(task, limit=20)

    assert "task-omitted-component-input-limit" in packet["bounds"]["bound_reasons"]
    assert packet["bounds"]["canonical_completeness"] == "incomplete"
    assert packet["ambiguity"]["ambiguous"] is None


def test_role_presentation_limit_cannot_hide_competing_anchor(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "anchor_owner.py").write_text(
        "def AnchorOwner():\n    return 1\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "test_unrelated.py").write_text(
        "def test_unrelated():\n    assert True\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "test_anchor_owner.py").write_text(
        "def test_AnchorOwner():\n    assert True\n", encoding="utf-8"
    )
    hits = tuple(
        SearchHit(path=path, score=100.0 - rank, kind="file")
        for rank, path in enumerate(
            (
                "src/anchor_owner.py",
                "tests/test_unrelated.py",
                "tests/test_anchor_owner.py",
            )
        )
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        monkeypatch.setattr(
            codemap,
            "_find_task_evidence_impl",
            lambda task, *, limit=20: _TaskRetrievalResult(hits[:limit], ()),
        )
        task = "change source tests AnchorOwner test_AnchorOwner"
        narrow = codemap.task_entry_points(task, per_role=1)
        wide = codemap.task_entry_points(task, per_role=2)

    assert len(narrow["roles"]["verification"]) == 1
    assert len(wide["roles"]["verification"]) == 2
    assert narrow["ambiguity"]["ambiguous"] is True
    assert wide["ambiguity"]["ambiguous"] is True
    assert narrow["ambiguity"]["resolution"] == wide["ambiguity"]["resolution"]
