"""Unresolved task ownership does not hide qualified declaration/test candidates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
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
        codemap.index.sync()
        action = codemap.tasks.action_map(task)
        packet = codemap.tasks.evidence(task)
        initial = read_initial_projection(
            decode_initial_packet(codemap.tasks.evidence(task, result_mode="initial"))
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
        codemap.index.sync()
        codemap.tasks.evidence("Inspect update_metadata behavior")
        path.write_text("def test_different_surface():\n    assert True\n")
        packet = codemap.tasks.evidence("Inspect update_metadata behavior")
    for row in packet["verification"]["relevance"]["candidates"]:
        if row["path"] == "tests/test_original.py" and "test_revision" in row:
            assert row.get("test_revision") == hash_file(path, domain=FILE_DOMAIN).hash


def test_method_subject_and_parent_references_keep_separate_source_bases(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        packet = repository.tasks.evidence("Inspect update_metadata behavior")
    original = assert_object(
        next(
            row
            for row in packet["verification"]["relevance"]["candidates"]
            if row["path"] == "tests/test_original.py"
        )
    )
    bases = assert_records(original.get("source_candidate_basis"))
    assert {"Worker", "Worker.update_metadata"} <= {
        basis["symbol"] for basis in bases if basis["path"] == "alpha.py"
    }
    assert all(basis["ownership_authority"] is False for basis in bases)
    assert original["verification_selection_authority"] is False
    assert original["edit_relationship"] == "unestablished"
    assert packet["ownership"]["owner"] is None


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
        codemap.index.sync()
        packet = codemap.tasks.evidence("Inspect metadata token behavior")
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


def test_file_locator_keeps_qualified_module_test_without_deciding_authority(
    tmp_path: Path,
) -> None:
    (tmp_path / "app.py").write_text(
        '"""Handler registration hooks for multiple paths."""\n'
        "class Dispatcher:\n    def install(self): return 1\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_app.py").write_text(
        "from app import Dispatcher\ndef test_result(): assert Dispatcher().install() == 1\n"
    )
    for n in range(30):
        (tmp_path / f"tests/test_noise_{n}.py").write_text(
            "from app import Dispatcher\ndef test_handler_registration_paths(): assert Dispatcher().install() == 1\n"
        )
    task = "Inspect app.py registration"
    with CodeMap(tmp_path) as repo:
        repo.index.sync()
        action = repo.tasks.action_map(task)
        packet = repo.tasks.evidence(task)
    locator = next(
        row for row in packet["retrieval"]["results"] if row["path"] == "app.py"
    )
    assert not locator.get("symbol")
    relevance = packet["verification"]["relevance"]
    candidate = next(
        row for row in relevance["candidates"] if row["path"] == "tests/test_app.py"
    )
    bases = assert_records(candidate.get("source_candidate_basis"))
    file_basis = next(
        basis
        for basis in bases
        if basis["path"] == "app.py" and basis.get("scope") == "indexed-source-file"
    )
    assert file_basis["symbol"] is None
    assert file_basis["start_line"] is None and file_basis["end_line"] is None
    assert file_basis["direct_reference"] is True
    assert "Dispatcher" in assert_array(file_basis["reference_symbols"])
    assert candidate.get("verification_selection_authority") is False
    assert candidate.get("negative_evidence_admissible") is False
    assert relevance["selection_changed"] is False
    assert packet["ownership"]["owner"] is None
    assert action["edit"] is not None and action["edit"]["path"] == "app.py"
    assert packet["verification"]["selected"] is not None
    assert action["verify"] is not None
    assert packet["verification"]["selected"]["path"] == action["verify"]["path"]


@pytest.mark.parametrize("visibility", ["deny", "outline"])
def test_keyword_candidate_disclosure_respects_source_visibility(
    tmp_path: Path, visibility: str
) -> None:
    _keyword_repository(tmp_path)
    (tmp_path / ".hashmarks-context.toml").write_text(
        f'[[rule]]\npattern = "tests/test_sparse.py"\nvisibility = "{visibility}"\n'
    )
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        packet = repository.tasks.evidence(
            "Payload-codec options are ignored in service.py."
        )
    assert "payload_codec_strict" not in json.dumps(packet)
    assert all(
        row["path"] != "tests/test_sparse.py" or not row.get("task_keyword_syntax")
        for row in packet["verification"]["relevance"]["candidates"]
    )


def test_keyword_candidate_disclosure_drops_changed_snapshot_facts(
    tmp_path: Path,
) -> None:
    _keyword_repository(tmp_path)
    task = "Payload-codec options are ignored in service.py."
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        before = repository.tasks.evidence(task)
        assert "payload_codec_strict" in json.dumps(before)
        (tmp_path / "tests/test_sparse.py").write_text(
            "from service import Encoder\n"
            "def test_result(): Encoder().encode(payload_codec=True)\n"
        )
        after = repository.tasks.evidence(task)
    assert "payload_codec_strict" not in json.dumps(after)
    assert "payload_codec_fields" not in json.dumps(after)


def test_keyword_candidate_disclosure_reports_omitted_names(tmp_path: Path) -> None:
    _keyword_repository(tmp_path)
    arguments = ", ".join(f"payload_codec_option_{n}=True" for n in range(20))
    (tmp_path / "tests/test_sparse.py").write_text(
        "from service import Encoder\n"
        f"def test_result(): Encoder().encode({arguments})\n"
    )
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        packet = repository.tasks.evidence(
            "Payload-codec options are ignored in service.py."
        )
    row = next(
        row
        for row in packet["verification"]["relevance"]["candidates"]
        if row["path"] == "tests/test_sparse.py"
    )
    syntax = assert_object(row.get("task_keyword_syntax"))
    assert len(assert_records(syntax["matches"])) == syntax["returned_bound"] == 16
    assert syntax["observed_keywords"] == 20
    assert syntax["omitted_keywords"] == 4
    assert syntax["negative_evidence_admissible"] is False


def _keyword_repository(root: Path) -> None:
    (root / "service.py").write_text(
        "class Encoder:\n    def encode(self, **options): return options\n"
    )
    (root / "tests").mkdir()
    (root / "tests/test_sparse.py").write_text(
        "from service import Encoder\n"
        "encoder = Encoder()\n"
        "@encoder.encode(payload_codec=True, payload_codec_strict=True, "
        "payload_codec_fields=('x',))\n"
        "def endpoint(): pass\n"
        "def test_result(): assert True\n"
        "from typing import TYPE_CHECKING\n"
        "if False: encoder.encode(payload_codec_dead=True)\n"
        "if TYPE_CHECKING: encoder.encode(payload_codec_type_only=True)\n"
        "encoder.encode(**{'payload_codec_dynamic': True})\n"
        "text = 'payload_codec_string is not a call keyword'\n"
    )
    for n in range(30):
        (root / f"tests/test_payload_codec_options_{n:02}.py").write_text(
            "from service import Encoder\n"
            "def test_payload_codec_options():\n"
            "    Encoder().encode(payload_codec=True)\n"
        )


@pytest.mark.parametrize("mode", ["full", "initial"])
def test_call_keyword_source_facts_survive_competing_test_filenames(
    tmp_path: Path, mode: str
) -> None:
    _keyword_repository(tmp_path)
    task = "Payload-codec options are ignored in service.py."
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        action = repository.tasks.action_map(task)
        packet = (
            repository.tasks.evidence(task)
            if mode == "full"
            else read_initial_projection(
                decode_initial_packet(
                    repository.tasks.evidence(task, result_mode="initial")
                )
            )
        )
    relevance = packet["verification"]["relevance"]
    rows: object = relevance["candidates"]
    if "candidates_encoding" in relevance:
        rows = decode_initial_collection(
            rows, assert_object(relevance["candidates_encoding"])
        )
    candidates = assert_records(rows)
    by_path = {row["path"]: row for row in candidates}
    assert "tests/test_sparse.py" in by_path
    observed = assert_object(by_path["tests/test_sparse.py"].get("task_keyword_syntax"))
    assert {row["name"] for row in assert_records(observed["matches"])} == {
        "payload_codec",
        "payload_codec_strict",
        "payload_codec_fields",
    }
    assert all(row["line"] == 3 for row in assert_records(observed["matches"]))
    assert observed["runtime_binding"] == "not-established"
    assert observed["negative_evidence_admissible"] is False
    assert (
        observed["source_revision"]
        == hash_file(tmp_path / "tests/test_sparse.py", domain=FILE_DOMAIN).hash
    )
    assert packet["ownership"]["owner"] == action["admitted_edit"]
    selected = packet["verification"]["selected"]
    assert selected is not None and action["verify"] is not None
    assert selected["path"] == action["verify"]["path"]
    assert relevance["selection_changed"] is False


def test_keyword_syntax_does_not_prove_a_reference_to_another_owner(
    tmp_path: Path,
) -> None:
    for path in ("service.py", "other.py"):
        (tmp_path / path).write_text(
            "class Encoder:\n    def encode(self, **options): return options\n"
        )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_actual.py").write_text(
        "from service import Encoder\n"
        "def test_result(): Encoder().encode(payload_codec=True)\n"
    )
    (tmp_path / "tests/test_other.py").write_text(
        "from other import Encoder\n"
        "def test_result():\n"
        "    Encoder().encode(payload_codec=True, payload_codec_strict=True, "
        "payload_codec_fields=True)\n"
    )
    task = "Payload-codec options are ignored in service.py."
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        action = repository.tasks.action_map(task)
        packet = repository.tasks.evidence(task)
    candidate = next(
        row
        for row in packet["verification"]["relevance"]["candidates"]
        if row["path"] == "tests/test_other.py"
    )
    assert assert_object(candidate.get("task_keyword_syntax"))["observed_keywords"] == 3
    assert all(
        basis["direct_reference"] is False
        for basis in assert_records(candidate.get("source_candidate_basis"))
        if basis["path"] == "service.py"
    )
    assert candidate.get("verification_selection_authority") is False
    assert packet["ownership"]["owner"] == action["admitted_edit"]
    assert packet["verification"]["selected"] == action["verify"]
