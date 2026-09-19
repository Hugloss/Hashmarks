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
