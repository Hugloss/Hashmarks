"""Task-local test directories remain visible beside broad module matches."""

from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records

from hashmarks.codemap import CodeMap
from hashmarks.codemap.task_evidence_initial import (
    decode_initial_collection,
    decode_initial_packet,
)


def _identity(value: object) -> tuple[object, ...] | None:
    if value is None:
        return None
    row = assert_object(value)
    return tuple(
        row.get(key)
        for key in (
            "path",
            "qualname",
            "start_line",
            "end_line",
            "roles",
            "evidence_visibility",
        )
    )


@pytest.mark.parametrize("ambiguous", [False, True])
def test_directory_task_words_keep_a_specific_test_in_bounded_disclosure(
    tmp_path: Path,
    ambiguous: bool,
) -> None:
    (tmp_path / "backend.py").write_text(
        "class Worker:\n    def run(self):\n        warn('attribute is reserved')\n"
    )
    tests = tmp_path / "tests"
    (tests / "processing").mkdir(parents=True)
    (tests / "processing/test_case.py").write_text(
        "from backend import Worker\ndef test_reserved_attribute(): Worker().run()\n"
    )
    (tests / "processing/test_unrelated.py").write_text(
        "def test_reserved_attribute_warning_records(): return None\n"
    )
    if ambiguous:
        (tmp_path / "other.py").write_text((tmp_path / "backend.py").read_text())
        (tests / "test_alternate.py").write_text(
            "from other import Worker\ndef test_other(): Worker().run()\n"
        )
    for i in range(12):
        (tests / f"test_generic_{i}.py").write_text(
            "from backend import Worker\n"
            "def test_reserved_attribute_warning_records(): Worker().run()\n"
        )
    task = "A reserved attribute warning appears while processing records."
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(task)
        packets = [
            codemap.task_evidence(task),
            decode_initial_packet(codemap.task_evidence(task, result_mode="initial")),
        ]
    for packet in packets:
        verification = assert_object(packet["verification"])
        relevance = assert_object(verification["relevance"])
        candidates = relevance["candidates"]
        if "candidates_encoding" in relevance:
            candidates = decode_initial_collection(
                candidates, assert_object(relevance["candidates_encoding"])
            )
        rows = assert_records(candidates)
        assert "tests/processing/test_case.py" in {row["path"] for row in rows}
        for row in rows:
            if row["path"] == "tests/processing/test_unrelated.py":
                assert row["direct_reference"] is False
                assert row["indirect_reference"] is False
                assert row["reference_symbols"] == []
        assert len(rows) <= 8
        assert _identity(verification["selected"]) == _identity(action["verify"])
        assert _identity(assert_object(packet["ownership"])["owner"]) == _identity(
            action["admitted_edit"]
        )
        if ambiguous:
            assert assert_object(packet["ownership"])["owner"] is None
