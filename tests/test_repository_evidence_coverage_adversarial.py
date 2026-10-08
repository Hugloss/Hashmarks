from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from hashmarks.client import RepositoryObservation
from hashmarks.codemap.engine import CodeMap
from hashmarks.observation import ObservationState


def _bindings() -> list[dict[str, object]]:
    return [
        {
            "binding_id": "shared:first",
            "evidence": [
                {"path": "shared.py", "start_line": 1, "end_line": 1},
            ],
        },
        {
            "binding_id": "shared:second",
            "evidence": [
                {"path": "shared.py", "start_line": 2, "end_line": 2},
            ],
        },
        {
            "binding_id": "other",
            "evidence": [
                {"path": "other.py", "start_line": 1, "end_line": 1},
            ],
        },
    ]


def _changed_shared_member(
    codemap: CodeMap,
    root: Path,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    before = codemap.repository_evidence_bindings(
        _bindings(),
        include_relationships=False,
    )
    (root / "shared.py").write_text("ONE\ntwo\n", encoding="utf-8")
    codemap.sync(["shared.py"])
    after = codemap.repository_evidence_bindings(
        _bindings(),
        include_relationships=False,
    )
    delta = codemap.repository_evidence_binding_delta(before, after)
    return before, after, delta


def _assert_binding_local_precision(coverage: dict[str, object]) -> None:
    assert coverage["classification"] == {
        "changed_inside_bound_evidence": ["shared.py"],
        "changed_elsewhere_in_bound_member": [],
        "bound_members_added": [],
        "bound_members_removed": [],
        "bound_member_observation_state_changed": [],
        "bound_locator_changed": [],
        "bound_member_precision_unknown": [],
        "declared_dependencies_changed": [],
        "outside_declared_bindings": [],
        "outside_declared_bindings_candidates": ["outside.py"],
    }
    assert coverage["precision"] == {
        "bound_range": "known",
        "reason": "binding-delta-supplied",
    }
    assert coverage["coverage"]["state"] == "incomplete"
    assert coverage["coverage"]["outside_classification"] == "unknown"
    assert coverage["binding_impacts"] == [
        {
            "binding_id": "shared:first",
            "reasons": [
                "bound-member-changed",
                "bound-range-content-changed",
            ],
        },
        {
            "binding_id": "shared:second",
            "reasons": ["bound-member-changed"],
        },
    ]


def test_incomplete_change_set_keeps_exact_precision_binding_local(
    tmp_path: Path,
) -> None:
    (tmp_path / "shared.py").write_text("one\ntwo\n", encoding="utf-8")
    (tmp_path / "other.py").write_text("other\n", encoding="utf-8")
    (tmp_path / "outside.py").write_text("outside\n", encoding="utf-8")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before, after, delta = _changed_shared_member(codemap, tmp_path)
        coverage = codemap.repository_evidence_coverage(
            after,
            changed_paths=["shared.py", "outside.py"],
            change_set_complete=False,
            binding_delta=delta,
            binding_delta_before=before,
        )

    _assert_binding_local_precision(coverage)
    assert coverage["coverage"]["source"] == "caller-asserted"


def test_incomplete_repository_observation_keeps_same_precision_split(
    tmp_path: Path,
) -> None:
    (tmp_path / "shared.py").write_text("one\ntwo\n", encoding="utf-8")
    (tmp_path / "other.py").write_text("other\n", encoding="utf-8")
    (tmp_path / "outside.py").write_text("outside\n", encoding="utf-8")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before, after, delta = _changed_shared_member(codemap, tmp_path)
        observation = RepositoryObservation(
            state=ObservationState.DIRTY,
            generation=17,
            dirty_paths=("shared.py", "outside.py"),
            paths_complete=False,
            dirty_path_count=2,
        )
        coverage = codemap.repository_evidence_coverage(
            after,
            repository_observation=observation,
            binding_delta=delta,
            binding_delta_before=before,
        )

    _assert_binding_local_precision(coverage)
    assert coverage["coverage"]["source"] == "repository-observer"
    assert coverage["change_set"] == {
        "source": "repository-observer",
        "state": "dirty",
        "generation": 17,
        "paths_complete": False,
        "dirty_path_count": 2,
    }


def test_coverage_prepares_each_binding_scope_once(tmp_path: Path) -> None:
    (tmp_path / "shared.py").write_text("one\ntwo\n", encoding="utf-8")
    (tmp_path / "other.py").write_text("other\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        bindings = codemap.repository_evidence_bindings(
            _bindings(), include_relationships=False
        )
        with (
            patch.object(CodeMap, "_binding_rows", wraps=CodeMap._binding_rows) as rows,
            patch.object(
                CodeMap, "_binding_paths", wraps=CodeMap._binding_paths
            ) as paths,
        ):
            coverage = codemap.repository_evidence_coverage(
                bindings,
                changed_paths=["shared.py", "outside.py"],
                change_set_complete=False,
            )

    assert rows.call_count == 1
    assert paths.call_count == len(_bindings())
    assert coverage["precision"]["bound_range"] == "unknown"
    assert coverage["classification"]["outside_declared_bindings"] == []
    assert coverage["classification"]["outside_declared_bindings_candidates"] == [
        "outside.py"
    ]
    assert coverage["binding_impacts"] == [
        {"binding_id": "shared:first", "reasons": ["bound-member-precision-unknown"]},
        {"binding_id": "shared:second", "reasons": ["bound-member-precision-unknown"]},
    ]
