from __future__ import annotations

from typing import TYPE_CHECKING

from hashmarks import CodeMap
from hashmarks.codemap.evidence_verification import _VerificationRelevanceState

if TYPE_CHECKING:
    from pathlib import Path


def test_verification_reference_strength_preserves_syntactic_fallback(
    tmp_path: Path,
) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_bad.py").write_text(
        "from pkg import target\ndef broken(:\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        assert codemap._verification_reference_strength(
            "tests/test_bad.py", ["target"]
        ) == {"syntactic_reference": True, "reference_strength": "syntactic"}
        assert codemap._verification_reference_strength("tests/test_bad.py", []) == {
            "syntactic_reference": False,
            "reference_strength": "none",
        }


def test_exact_verification_import_requires_resolved_owner_path(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "owner.py").write_text("def widget(): return 1\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_owner.py").write_text(
        "from pkg.owner import widget\n", encoding="utf-8"
    )
    state = _VerificationRelevanceState(
        current_path="pkg/owner.py",
        edit_path="pkg/owner.py",
        generic_parts=set(),
        edit_parts=set(),
        task_terms=set(),
        canonical_rank={},
        candidate_paths=set(),
        refs_by_path={},
        indirect_refs_by_path={},
        indirect_via_paths={},
        source_ref_paths=set(),
        unresolved_import_identity_paths=set(),
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        paths, available = codemap._verification_exact_import_paths(
            state,
            [
                {
                    "kind": "import",
                    "path": "tests/test_owner.py",
                    "target": "pkg.owner",
                },
                {
                    "kind": "import",
                    "path": "tests/test_owner.py",
                    "target": "pkg.missing",
                },
            ],
        )
    assert paths == {"tests/test_owner.py"}
    assert available is True


def test_verification_locality_replaces_unrelated_canonical_without_reference_proof() -> None:
    selected = {
        "path": "backend/tests/unit/repository_tooling/test_test_batch_receipts.py",
        "direct_reference": False,
        "indirect_reference": False,
        "namespace_overlap": 0,
        "task_anchor_count": 3,
        "canonical_rank": 7,
        "runner_available": True,
    }
    local = {
        "path": "backend/tests/unit/integrations/test_fleet_plan_attempt_authority.py",
        "direct_reference": False,
        "indirect_reference": False,
        "namespace_overlap": 1,
        "task_anchor_count": 5,
        "canonical_rank": 10,
        "runner_available": True,
    }

    chosen, reason = CodeMap._verification_select_candidate(
        [local, selected], selected["path"]
    )

    assert chosen is local
    assert reason == "stronger-namespace-task-locality"


def test_verification_locality_never_overrides_reference_evidence() -> None:
    selected = {
        "path": "tests/test_exact_owner.py",
        "direct_reference": True,
        "indirect_reference": False,
        "namespace_overlap": 0,
        "task_anchor_count": 1,
        "canonical_rank": 9,
        "runner_available": True,
    }
    local = {
        "path": "pkg/tests/test_local_words.py",
        "direct_reference": False,
        "indirect_reference": False,
        "namespace_overlap": 2,
        "task_anchor_count": 6,
        "canonical_rank": 1,
        "runner_available": True,
    }

    chosen, reason = CodeMap._verification_select_candidate(
        [local, selected], selected["path"]
    )

    assert chosen is selected
    assert reason == "canonical-verification"
