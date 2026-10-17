"""Unresolved task ownership does not hide qualified declaration/test candidates."""

from __future__ import annotations

from pathlib import Path

from contract_assertions import assert_array, assert_object, assert_records

from hashmarks.codemap import CodeMap
from hashmarks.codemap.task_evidence_contract import (
    read_initial_projection,
    read_task_candidate,
)
from hashmarks.codemap.task_evidence_initial import (
    decode_initial_collection,
    decode_initial_packet,
)
from hashmarks.digest import FILE_DOMAIN, hash_file


def _repository(root: Path) -> None:
    for name in ("alpha", "beta"):
        (root / f"{name}.py").write_text(
            "class Worker:\n    def update_metadata(self):\n        return False\n"
        )
    (root / "tests").mkdir()
    (root / "tests/test_original.py").write_text(
        "from alpha import Worker as Actual\ndef test_original_response():\n    assert Actual().update_metadata() is False\n"
    )
    (root / "tests/test_alternate.py").write_text(
        "from beta import Worker as Other\ndef test_alternate_response():\n    assert Other().update_metadata() is False\n"
    )


def test_candidate_disclosure_preserves_ambiguity_and_verification_selection(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    task = "Inspect update_metadata behavior"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(task)
        packet = codemap.task_evidence(task)
        initial = read_initial_projection(
            decode_initial_packet(codemap.task_evidence(task, result_mode="initial"))
        )
    assert packet["ownership"]["owner"] is None
    assert packet["ownership"]["ambiguity"]["ambiguous"] is True
    for observed in (packet, initial):
        relevance = observed["verification"]["relevance"]
        candidate_rows: object = relevance["candidates"]
        if "candidates_encoding" in relevance:
            candidate_rows = decode_initial_collection(
                candidate_rows, assert_object(relevance["candidates_encoding"])
            )
        candidates = [read_task_candidate(row) for row in assert_array(candidate_rows)]
        by_path = {row["path"]: row for row in candidates}
        assert {"tests/test_original.py", "tests/test_alternate.py"} <= by_path.keys()
        for path, source in (
            ("tests/test_original.py", "alpha.py"),
            ("tests/test_alternate.py", "beta.py"),
        ):
            row = by_path[path]
            assert (
                row.get("test_revision")
                == hash_file(tmp_path / path, domain=FILE_DOMAIN).hash
            )
            assert row.get("verification_selection_authority") is False
            assert row.get("negative_evidence_admissible") is False
            assert row.get("edit_relationship") == "unestablished"
            assert any(
                basis["path"] == source
                and basis["symbol"] == "Worker"
                and basis["ownership_authority"] is False
                for basis in assert_records(row.get("source_candidate_basis"))
            )
        assert relevance["selection_changed"] is False
        assert observed["verification"]["selected"] is not None
        assert action["verify"] is not None
        assert observed["verification"]["selected"]["path"] == action["verify"]["path"]
        assert "candidate_disclosure" in relevance
        assert (
            relevance["candidate_disclosure"]["negative_evidence_admissible"] is False
        )


def test_candidate_disclosure_never_promotes_stale_test_revision(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    path = tmp_path / "tests/test_original.py"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        codemap.task_evidence("Inspect update_metadata behavior")
        path.write_text("def test_different_surface():\n    assert True\n")
        packet = codemap.task_evidence("Inspect update_metadata behavior")
    for row in packet["verification"]["relevance"]["candidates"]:
        if row["path"] == "tests/test_original.py" and "test_revision" in row:
            assert row.get("test_revision") == hash_file(path, domain=FILE_DOMAIN).hash


def test_source_identifier_scout_keeps_late_test_body_without_claiming_reference(
    tmp_path: Path,
) -> None:
    for name in ("alpha", "beta"):
        (tmp_path / f"{name}.py").write_text(
            "class MetadataTokenPolicy:\n    def reset(self):\n        return None\n"
        )
    (tmp_path / "tests").mkdir()
    (tmp_path / "bridge.py").write_text(
        "from alpha import MetadataTokenPolicy\ndef helper():\n    return MetadataTokenPolicy()\n"
    )
    (tmp_path / "tests/test_neutral.py").write_text(
        "".join(
            f"def test_unrelated_{index}():\n    assert True\n" for index in range(80)
        )
        + "def test_final_result():\n    assert 'metadata token'\n"
    )
    for index in range(10):
        (tmp_path / f"tests/test_noise_{index}.py").write_text(
            "from bridge import helper\ndef test_result():\n    helper()\n    assert 'metadata'\n"
        )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.task_evidence("Inspect metadata token behavior")
    assert packet["ownership"]["owner"] is None
    candidate = next(
        row
        for row in packet["verification"]["relevance"]["candidates"]
        if row["path"] == "tests/test_neutral.py"
    )
    term_matches = candidate.get("subject_term_matches")
    assert isinstance(term_matches, int)
    assert term_matches >= 2
    assert "direct_reference" in candidate
    assert candidate["direct_reference"] is False
    assert candidate.get("verification_selection_authority") is False
    assert candidate.get("edit_relationship") == "unestablished"
