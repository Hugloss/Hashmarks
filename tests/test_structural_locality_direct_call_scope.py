"""Direct graph edges retain the indexed caller's own lexical scope."""

from pathlib import Path

import pytest
from contract_assertions import assert_records

from hashmarks.codemap import CodeMap
from hashmarks.evidence_presentation import FORMATS, presentation_response


@pytest.mark.parametrize("asynchronous", [False, True])
def test_nested_callback_calls_are_not_direct_calls_of_its_enclosing_function(
    tmp_path: Path, asynchronous: bool
) -> None:
    prefix = "async " if asynchronous else ""
    (tmp_path / "worker.py").write_text(
        "def leaf():\n    return 1\n\n"
        f"{prefix}def owner():\n"
        f"    {prefix}def callback():\n        return leaf()\n"
        "    return callback\n"
    )
    with CodeMap(tmp_path) as codemap:
        outer = codemap.structure.locality("worker.py::owner")
        callback = codemap.structure.locality("worker.py::owner.callback")
        leaf = codemap.structure.locality("worker.py::leaf", max_depth=0)
    assert outer["edges"] == []
    assert {row["symbol_id"] for row in assert_records(outer["nodes"])} == {
        "worker.py::owner"
    }
    assert {
        (row["source_symbol_id"], row["resolved_symbol_id"])
        for row in assert_records(callback["edges"])
    } == {("worker.py::owner.callback", "worker.py::leaf")}
    callers = assert_records(assert_records(leaf["nodes"])[0]["exact_callers"])
    assert {row["source"] for row in callers} == {"owner.callback"}
    for format in FORMATS:
        response = presentation_response("structural_locality", outer, format=format)
        assert response.get("result", response) == outer


def test_calls_in_nested_class_methods_keep_their_actual_caller(tmp_path: Path) -> None:
    (tmp_path / "worker.py").write_text(
        "def leaf():\n    return 1\n\n"
        "def owner():\n    class Worker:\n"
        "        def run(self):\n            return leaf()\n"
        "    return Worker\n"
    )
    with CodeMap(tmp_path) as codemap:
        outer = codemap.structure.locality("worker.py::owner")
        method = codemap.structure.locality("worker.py::owner.Worker.run")
    assert outer["edges"] == []
    assert {
        (row["source_symbol_id"], row["resolved_symbol_id"])
        for row in assert_records(method["edges"])
    } == {("worker.py::owner.Worker.run", "worker.py::leaf")}


def test_direct_call_remains_a_single_segment_without_transitive_shortcut(
    tmp_path: Path,
) -> None:
    (tmp_path / "worker.py").write_text(
        "def leaf():\n    return 1\n\n"
        "def callback():\n    return leaf()\n\n"
        "def owner():\n    return callback()\n"
    )
    with CodeMap(tmp_path) as codemap:
        packet = codemap.structure.locality("worker.py::owner")
    assert {
        (row["source_symbol_id"], row["resolved_symbol_id"])
        for row in assert_records(packet["edges"])
    } == {
        ("worker.py::owner", "worker.py::callback"),
        ("worker.py::callback", "worker.py::leaf"),
    }


def test_nested_calls_do_not_consume_the_enclosing_call_limit(tmp_path: Path) -> None:
    (tmp_path / "worker.py").write_text(
        "def leaf():\n    return 1\n\n"
        "def owner():\n"
        "    def callback():\n        return leaf()\n"
        "    return leaf()\n"
    )
    with CodeMap(tmp_path) as codemap:
        packet = codemap.structure.locality("worker.py::owner", call_limit_per_symbol=1)
    assert [
        (row["source_symbol_id"], row["line"], row["resolved_symbol_id"])
        for row in assert_records(packet["edges"])
    ] == [("worker.py::owner", 7, "worker.py::leaf")]
    assert packet["unresolved_calls"] == []
