from __future__ import annotations

from typing import TYPE_CHECKING

from hashmarks.codemap import CodeMap

if TYPE_CHECKING:
    from pathlib import Path

_DIRECT_REF_LIMIT = 1024


def _write_owner(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "owner.py").write_text(
        "def target():\n    return 1\n",
        encoding="utf-8",
    )


def _ref(path: str) -> dict[str, object]:
    return {
        "path": path,
        "line": 1,
        "kind": "call",
        "target": "target",
        "target_short": "target",
        "evidence_visibility": "source",
    }


def test_bounded_reference_search_cannot_report_no_verification_candidate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_owner(tmp_path)
    refs = [_ref(f"src/noise_{index}.py") for index in range(_DIRECT_REF_LIMIT + 1)]

    with CodeMap(tmp_path) as codemap:
        codemap.sync()

        def refs_many(targets, *, limit_per_target):
            targets = list(targets)
            if limit_per_target == _DIRECT_REF_LIMIT + 1:
                assert targets == ["target"]
                return {"target": refs[:limit_per_target]}
            assert limit_per_target == 257
            return {symbol: [] for symbol in targets}

        monkeypatch.setattr(codemap, "_session_refs_many", refs_many)
        monkeypatch.setattr(
            codemap.store,
            "refs_matching_target_suffix",
            lambda _short, _suffix, *, limit: [],
        )
        monkeypatch.setattr(
            codemap.store,
            "symbols_for_paths_many",
            lambda _paths, *, limit_per_path: {},
        )

        packet = codemap._verification_relevance(
            "target",
            edit={"path": "src/owner.py", "name": "target"},
            current_verify=None,
            rows=[],
        )

    assert packet["selected"] is None
    assert packet["selection_reason"] == "verification-candidate-search-bounded"
    assert packet["completeness"] == "incomplete"
    assert packet["truncation"] == "truncated"
    assert packet["negative_evidence_admissible"] is False
    assert "direct-reverse-ref-limit" in packet["search_bound_reasons"]


def test_bounded_reference_search_cannot_manufacture_unique_verifier(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_owner(tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_owner.py").write_text(
        "from src.owner import target\n\n"
        "def test_target():\n"
        "    assert target() == 1\n",
        encoding="utf-8",
    )
    refs = [_ref("tests/test_owner.py")]
    refs.extend(_ref(f"src/noise_{index}.py") for index in range(_DIRECT_REF_LIMIT))

    with CodeMap(tmp_path) as codemap:
        codemap.sync()

        def refs_many(targets, *, limit_per_target):
            targets = list(targets)
            if limit_per_target == _DIRECT_REF_LIMIT + 1:
                assert targets == ["target"]
                return {"target": refs[:limit_per_target]}
            return {symbol: [] for symbol in targets}

        monkeypatch.setattr(codemap, "_session_refs_many", refs_many)
        monkeypatch.setattr(
            codemap.store,
            "refs_matching_target_suffix",
            lambda _short, _suffix, *, limit: [],
        )

        packet = codemap._verification_relevance(
            "target",
            edit={"path": "src/owner.py", "name": "target"},
            current_verify=None,
            rows=[],
        )

    assert packet["selected"]["path"] == "tests/test_owner.py"
    assert (
        packet["selected"]["selection_reason"] == "best-bounded-verification-evidence"
    )
    assert packet["completeness"] == "incomplete"
    assert packet["negative_evidence_admissible"] is False
    assert "direct-reverse-ref-limit" in packet["search_bound_reasons"]


def test_exhausted_verification_search_can_still_authorize_absence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_owner(tmp_path)

    with CodeMap(tmp_path) as codemap:
        codemap.sync()

        def refs_many(targets, *, limit_per_target):
            return {symbol: [] for symbol in targets}

        monkeypatch.setattr(codemap, "_session_refs_many", refs_many)
        monkeypatch.setattr(
            codemap.store,
            "refs_matching_target_suffix",
            lambda _short, _suffix, *, limit: [],
        )

        packet = codemap._verification_relevance(
            "target",
            edit={"path": "src/owner.py", "name": "target"},
            current_verify=None,
            rows=[],
        )

    assert packet["selected"] is None
    assert packet["selection_reason"] == "no-verification-candidate"
    assert packet["completeness"] == "complete"
    assert packet["truncation"] == "complete"
    assert packet["negative_evidence_admissible"] is True
    assert packet["search_bound_reasons"] == []
