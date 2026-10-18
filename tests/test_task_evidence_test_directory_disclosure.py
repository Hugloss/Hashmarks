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


def test_problem_named_test_is_not_buried_by_generic_protocol_helpers(
    tmp_path: Path,
) -> None:
    source = tmp_path / "app/protocols"
    source.mkdir(parents=True)
    (source / "scope.py").write_text(
        "class Boundary:\n    async def __aexit__(self, *args):\n        return None\n"
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    for index in range(12):
        (tests / f"test_helpers_{index}.py").write_text(
            "class BoundaryHelper:\n"
            "    async def __aexit__(self, *args): return None\n"
            "    def test_boundary_scope(self): assert True\n"
        )
    target = "tests/test_cancellation.py"
    (tmp_path / target).write_text("def test_cancellation(): assert True\n")
    task = "Inspect cancellation when Boundary.__aexit__ receives exit. Source: app/protocols/scope.py"
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        action = codemap.tasks.action_map(task)
        packets = [
            codemap.tasks.evidence(task),
            decode_initial_packet(codemap.tasks.evidence(task, result_mode="initial")),
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
        matching = [row for row in rows if row["path"] == target]
        assert matching and len(rows) <= 8
        candidate = matching[0]
        assert candidate["direct_reference"] is False
        assert candidate["indirect_reference"] is False
        assert candidate["verification_selection_authority"] is False
        assert candidate["edit_relationship"] == "unestablished"
        assert candidate["negative_evidence_admissible"] is False
        assert _identity(verification["selected"]) == _identity(action["verify"])
        assert _identity(assert_object(packet["ownership"])["owner"]) == _identity(
            action["admitted_edit"]
        )


def test_broad_candidate_pool_cannot_erase_other_observed_source_namespaces(
    tmp_path: Path,
) -> None:
    for package, name in (("alpha", "Alpha"), ("beta", "Beta"), ("zulu", "Zulu")):
        source = tmp_path / "app" / package
        source.mkdir(parents=True)
        (source / "__init__.py").write_text("")
        (source / "owner.py").write_text(
            f"class {name}:\n    def process(self):\n        return None\n"
        )
        tests = tmp_path / "tests" / package
        tests.mkdir(parents=True)
        for index in range(12):
            (tests / f"test_{index}.py").write_text(
                f"from app.{package}.owner import {name}\n"
                f"def test_process_records(): {name}().process()\n"
            )
    task = "Inspect Alpha.process, Beta.process and Zulu.process for record processing."
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        action = codemap.tasks.action_map(task)
        packets = [
            codemap.tasks.evidence(task),
            decode_initial_packet(codemap.tasks.evidence(task, result_mode="initial")),
        ]
    for packet in packets:
        relevance = assert_object(assert_object(packet["verification"])["relevance"])
        candidates = relevance["candidates"]
        if "candidates_encoding" in relevance:
            candidates = decode_initial_collection(
                candidates, assert_object(relevance["candidates_encoding"])
            )
        paths = {str(row["path"]) for row in assert_records(candidates)}
        assert {path.split("/")[1] for path in paths} == {"alpha", "beta", "zulu"}
        assert len(paths) <= 8
        assert _identity(assert_object(packet["verification"])["selected"]) == (
            _identity(action["verify"])
        )
        assert _identity(assert_object(packet["ownership"])["owner"]) == _identity(
            action["admitted_edit"]
        )


def test_task_directory_words_cannot_displace_source_namespace_locality(
    tmp_path: Path,
) -> None:
    source = tmp_path / "app/processing"
    source.mkdir(parents=True)
    (tmp_path / "app/__init__.py").write_text("")
    (source / "__init__.py").write_text("")
    (source / "backend.py").write_text(
        "class Worker:\n    def run(self):\n        warn('reserved attribute')\n"
    )
    tests = tmp_path / "tests"
    (tests / "processing").mkdir(parents=True)
    (tests / "sql").mkdir()
    (tests / "processing/test_case.py").write_text(
        "from app.processing.backend import Worker\n"
        "def test_reserved_attribute(): Worker().run()\n"
    )
    for i in range(12):
        (tests / f"sql/test_generic_{i}.py").write_text(
            "from app.processing.backend import Worker\n"
            "def test_reserved_attribute_warning(): Worker().run()\n"
        )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        with codemap.reads.session():
            rows = codemap.tasks._task_evidence_candidate_verifiers(
                "A reserved attribute warning breaks SQL queries.",
                {
                    "path": "app/processing/backend.py",
                    "symbol": "Worker.run",
                    "start_line": 2,
                    "end_line": 3,
                },
            )
    assert "tests/processing/test_case.py" in {row["path"] for row in rows}


def test_source_declaration_words_retain_tests_when_task_uses_other_word_forms(
    tmp_path: Path,
) -> None:
    (tmp_path / "backend.py").write_text(
        "class Builder:\n    def assemble_bundles(self):\n"
        "        raise TypeError('bundle assembly fails')\n"
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    target = "tests/test_a_target.py"
    (tmp_path / target).write_text(
        "from backend import Builder\n"
        "def test_assemble_bundles(): Builder().assemble_bundles()\n"
    )
    for index in range(12):
        (tests / f"test_generic_{index}.py").write_text(
            "from backend import Builder\n"
            "def test_assembly_bundle_type_error(): Builder().assemble_bundles()\n"
            "def test_assemble(): Builder().assemble_bundles()\n"
            "def test_bundles(): Builder().assemble_bundles()\n"
        )
    task = "Assembly of a bundle fails with TypeError."
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        action = codemap.tasks.action_map(task)
        packets = [
            codemap.tasks.evidence(task),
            decode_initial_packet(codemap.tasks.evidence(task, result_mode="initial")),
        ]
    for packet in packets:
        verification = assert_object(packet["verification"])
        relevance = assert_object(verification["relevance"])
        candidates = relevance["candidates"]
        if "candidates_encoding" in relevance:
            candidates = decode_initial_collection(
                candidates, assert_object(relevance["candidates_encoding"])
            )
        assert target in {row["path"] for row in assert_records(candidates)}
        assert _identity(verification["selected"]) == _identity(action["verify"])
        assert _identity(assert_object(packet["ownership"])["owner"]) == _identity(
            action["admitted_edit"]
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
        codemap.index.sync()
        action = codemap.tasks.action_map(task)
        packets = [
            codemap.tasks.evidence(task),
            decode_initial_packet(codemap.tasks.evidence(task, result_mode="initial")),
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


@pytest.mark.parametrize("tied_competitors", [False, True])
def test_module_wide_keyword_union_cannot_hide_a_specific_test_declaration(
    tmp_path: Path,
    tied_competitors: bool,
) -> None:
    source = tmp_path / "app/engine"
    source.mkdir(parents=True)
    (tmp_path / "app/__init__.py").write_text("")
    (source / "__init__.py").write_text("")
    (source / "adapter.py").write_text(
        "class Worker:\n    def run(self):\n        warn('reserved attribute warning record placement')\n"
    )
    tests = tmp_path / "tests/engine"
    tests.mkdir(parents=True)
    (tests / "test_a_target.py").write_text(
        "from app.engine.adapter import Worker\n"
        "def test_reserved_attribute_warning_record_placement(): Worker().run()\n"
    )
    for i in range(12):
        declarations = (
            "def test_reserved_attribute_warning_record_placement_one(): Worker().run()\n"
            "def test_reserved_attribute_warning_record_placement_two(): Worker().run()\n"
            if tied_competitors
            else "def test_reserved_breaks(): Worker().run()\n"
            "def test_attribute_produces(): Worker().run()\n"
            "def test_warning_handler_failures(): Worker().run()\n"
            "def test_record_placement(): Worker().run()\n"
        )
        (tests / f"test_large_{i}.py").write_text(
            "from app.engine.adapter import Worker\n" + declarations
        )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        with codemap.reads.session():
            rows = codemap.tasks._task_evidence_candidate_verifiers(
                "A reserved attribute warning breaks record placement and produces handler failures.",
                {
                    "path": "app/engine/adapter.py",
                    "symbol": "Worker.run",
                    "start_line": 2,
                    "end_line": 3,
                },
            )
    assert "tests/engine/test_a_target.py" in {row["path"] for row in rows}
