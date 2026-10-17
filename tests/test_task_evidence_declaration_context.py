"""Declared context can locate opaque methods without choosing an edit owner."""

from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records

from hashmarks.codemap import CodeMap
from hashmarks.codemap.task_evidence_initial import decode_initial_packet

_TASK = "Deferred loading wrongly retains query criteria after repeated serialization."


def _repository(root: Path) -> Path:
    # Broad file matches must not hide a more coherent declaration match. The
    # relevant words occur separately here, outside the callable declaration.
    for index in range(20):
        (root / f"a_noise_{index:02}.py").write_text(
            "def serialization_criteria(): return None\n"
            "# deferred\n# loading\n# wrongly\n# retains\n# query\n"
            "# criteria\n# after\n# repeated\n# serialization\n"
        )
    source = root / "z_backend.py"
    source.write_text(
        "class DeferredLoader:\n"
        "    def close(self): return None\n"
        "    def process(self, query): return query\n"
    )
    return source


def test_class_and_parameter_words_disclose_an_opaque_method(tmp_path: Path) -> None:
    _repository(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        action = codemap.task_action_map(_TASK)
        packets = [
            codemap.task_evidence(_TASK),
            decode_initial_packet(codemap.task_evidence(_TASK, result_mode="initial")),
        ]
    for packet in packets:
        retrieval = assert_object(packet["retrieval"])
        rows = assert_records(retrieval["results"])
        assert any(
            row.get("path") == "z_backend.py"
            and row.get("symbol") == "DeferredLoader.process"
            and (row.get("start_line"), row.get("end_line")) == (3, 3)
            for row in rows[:3]
        )
        assert retrieval["ownership_authority"] is False
        assert assert_object(packet["ownership"])["owner"] == action["admitted_edit"]
        ambiguity = assert_object(assert_object(packet["ownership"])["ambiguity"])
        assert {
            k: v
            for k, v in ambiguity.items()
            if k not in {"candidates", "alternatives"}
        } == {
            k: v
            for k, v in action["ambiguity"].items()
            if k not in {"candidates", "alternatives"}
        }
        for key in ("candidates", "alternatives"):
            identity = (
                "path",
                "qualname",
                "start_line",
                "end_line",
                "roles",
                "evidence_visibility",
            )
            assert [
                tuple(row.get(field) for field in identity)
                for row in assert_records(ambiguity[key])
            ] == [
                tuple(row.get(field) for field in identity)
                for row in assert_records(action["ambiguity"][key])
            ]
        assert assert_object(packet["verification"])["selected"] == action["verify"]


@pytest.mark.parametrize("invalidity", ["deny", "changed", "deleted"])
def test_context_disclosure_cannot_promote_hidden_or_invalidated_declarations(
    tmp_path: Path, invalidity: str
) -> None:
    source = _repository(tmp_path)
    if invalidity == "deny":
        (tmp_path / ".hashmarks-context.toml").write_text(
            '[[rule]]\npattern = "z_backend.py"\nvisibility = "deny"\n'
        )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        if invalidity == "changed":
            source.write_text("def replacement(): return None\n")
        elif invalidity == "deleted":
            source.unlink()
        packet = codemap.task_evidence(_TASK)
    rows = assert_records(assert_object(packet["retrieval"])["results"])
    assert not any(
        row.get("path") == "z_backend.py"
        and row.get("supplement") == "bounded-declaration-context"
        for row in rows
    )


def test_context_hints_keep_explicit_targets_and_outline_visibility(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "z_backend.py"\nvisibility = "outline"\n'
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packets = [
            codemap.task_evidence(_TASK),
            codemap.task_evidence(
                _TASK + " Inspect a_noise_00.py::serialization_criteria."
            ),
        ]
    rows = assert_records(assert_object(packets[0]["retrieval"])["results"])
    match = next(
        row for row in rows[:3] if row.get("symbol") == "DeferredLoader.process"
    )
    assert match["evidence_visibility"] == "outline"
    explicit = assert_records(assert_object(packets[1]["retrieval"])["results"])
    assert (explicit[0]["path"], explicit[0]["symbol"]) == (
        "a_noise_00.py",
        "serialization_criteria",
    )


def test_sql_prefix_prefilter_cannot_manufacture_identifier_matches(
    tmp_path: Path,
) -> None:
    (tmp_path / "backend.py").write_text(
        "class Transaction:\n    def process(self, adapter): return adapter\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.task_evidence("Transcribing adapter settings fails.")
    rows = assert_records(assert_object(packet["retrieval"])["results"])
    assert not any(
        row.get("supplement") == "bounded-declaration-context" for row in rows
    )


def test_hidden_contexts_cannot_exhaust_the_lookup_bound(tmp_path: Path) -> None:
    (tmp_path / "a_hidden.py").write_text(
        "".join(
            f"class DeferredLoader{index}:\n"
            "    def process(self, query): return query\n"
            for index in range(40)
        )
    )
    (tmp_path / "z_visible.py").write_text(
        "class DeferredLoader:\n    def process(self, query): return query\n"
    )
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "a_hidden.py"\nvisibility = "deny"\n'
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.task_evidence(_TASK)
    rows = assert_records(assert_object(packet["retrieval"])["results"])
    assert any(
        row.get("path") == "z_visible.py"
        and row.get("symbol") == "DeferredLoader.process"
        for row in rows[:3]
    )
    assert not any(row.get("path") == "a_hidden.py" for row in rows)


def test_repeated_task_words_do_not_expand_the_bounded_query(tmp_path: Path) -> None:
    _repository(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.task_evidence(_TASK + " Deferred query." * 40)
    rows = assert_records(assert_object(packet["retrieval"])["results"])
    assert any(row.get("symbol") == "DeferredLoader.process" for row in rows[:3])


def test_explicit_method_and_context_hint_share_one_retrieval_slot(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    task = _TASK + " Inspect z_backend.py::DeferredLoader.process."
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packets = [
            codemap.task_evidence(task),
            decode_initial_packet(codemap.task_evidence(task, result_mode="initial")),
        ]
    for packet in packets:
        rows = assert_records(assert_object(packet["retrieval"])["results"])
        locators = [(row["path"], row.get("symbol")) for row in rows]
        assert locators.count(("z_backend.py", "DeferredLoader.process")) == 1
        assert locators[0] == ("z_backend.py", "DeferredLoader.process")
