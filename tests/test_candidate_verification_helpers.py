"""Fixture-module references are candidate evidence, without selection authority."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from contract_assertions import assert_array, assert_object, assert_records

from hashmarks.codemap import CodeMap
from hashmarks.codemap.task_evidence_contract import read_initial_projection
from hashmarks.codemap.task_evidence_initial import (
    decode_initial_collection,
    decode_initial_packet,
)
from hashmarks.digest import FILE_DOMAIN, hash_file

if TYPE_CHECKING:
    from pathlib import Path


_TASK = "Inspect RepositoryBase.update in service.py"


def _repository(tmp_path: Path) -> None:
    (tmp_path / "service.py").write_text(
        "class RepositoryBase:\n    def update(self): return 1\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/models.py").write_text(
        "from service import RepositoryBase\n"
        "class FixtureRepository(RepositoryBase): pass\n"
        "def persist_request(repository): return repository.update()\n"
    )
    (tmp_path / "tests/test_zzz_flow.py").write_text(
        "from tests.models import persist_request\n"
        "def test_flow(repository): assert persist_request(repository) == 1\n"
    )
    for i in range(12):
        (tmp_path / f"tests/test_noise_{i:02}.py").write_text(
            "# RepositoryBase declaration update service\n"
            f"def test_noise_{i}(): assert True\n"
        )


def test_source_candidate_follows_fixture_module_to_the_importing_test(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(_TASK)
        packet = codemap.task_evidence(_TASK)
        initial = read_initial_projection(
            decode_initial_packet(codemap.task_evidence(_TASK, result_mode="initial"))
        )
    revision = hash_file(tmp_path / "tests/models.py", domain=FILE_DOMAIN).hash
    for observed in (packet, initial):
        relevance = observed["verification"]["relevance"]
        rows: object = relevance["candidates"]
        if "candidates_encoding" in relevance:
            rows = decode_initial_collection(
                rows, assert_object(relevance["candidates_encoding"])
            )
        candidate = next(
            row
            for row in assert_records(rows)
            if row["path"] == "tests/test_zzz_flow.py"
        )
        assert candidate.get("verification_selection_authority") is False
        assert candidate.get("edit_relationship") == "unestablished"
        assert candidate.get("negative_evidence_admissible") is False
        assert any(
            "tests/models.py" in assert_array(basis.get("indirect_via_paths"))
            and assert_object(basis.get("test_module_revisions"))
            == {"tests/models.py": revision}
            for basis in assert_records(candidate.get("source_candidate_basis"))
        )
        selected = observed["verification"]["selected"]
        assert selected is not None and action["verify"] is not None
        assert selected["path"] == action["verify"]["path"]
        assert observed["ownership"]["owner"] is None
    assert packet["ownership"]["owner"] == action["admitted_edit"]


@pytest.mark.parametrize("invalidity", ["hidden", "stale", "different-owner"])
def test_fixture_module_cannot_supply_an_unqualified_reference(
    tmp_path: Path, invalidity: str
) -> None:
    _repository(tmp_path)
    helper = tmp_path / "tests/models.py"
    if invalidity == "hidden":
        (tmp_path / ".hashmarks-context.toml").write_text(
            '[[rule]]\npattern = "tests/models.py"\nvisibility = "deny"\n'
        )
    if invalidity == "different-owner":
        (tmp_path / "alternative.py").write_text(
            "class RepositoryBase:\n    def update(self): return 2\n"
        )
        helper.write_text(
            helper.read_text().replace("from service", "from alternative")
        )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        if invalidity == "stale":
            codemap.task_evidence(_TASK)
            helper.write_text("def persist_request(repository): return None\n")
        action = codemap.task_action_map(_TASK)
        packet = codemap.task_evidence(_TASK)
    for candidate in packet["verification"]["relevance"]["candidates"]:
        for basis in assert_records(candidate.get("source_candidate_basis", [])):
            if basis["path"] == "service.py":
                assert "tests/models.py" not in assert_array(
                    basis.get("indirect_via_paths")
                )
    assert packet["verification"]["selected"] == action["verify"]
    assert packet["ownership"]["owner"] == action["admitted_edit"]
