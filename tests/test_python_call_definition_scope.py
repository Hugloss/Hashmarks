"""Definition expressions retain their surrounding lexical call scope."""

from pathlib import Path

import pytest
from contract_assertions import assert_records

from hashmarks.codemap import CodeMap


@pytest.mark.parametrize("asynchronous", [False, True])
def test_function_header_calls_belong_to_definition_scope(
    tmp_path: Path, asynchronous: bool
) -> None:
    prefix = "async " if asynchronous else ""
    (tmp_path / "worker.py").write_text(
        "def leaf():\n    return 1\n\n"
        "def owner():\n"
        "    @leaf()\n"
        f"    {prefix}def callback(value=leaf()):\n"
        "        return leaf()\n"
        "    return callback\n"
    )
    with CodeMap(tmp_path) as codemap:
        outer = codemap.structure.locality("worker.py::owner")
        callback = codemap.structure.locality("worker.py::owner.callback")
        leaf = codemap.structure.locality("worker.py::leaf", max_depth=0)
    assert {
        (row["line"], row["resolved_symbol_id"])
        for row in assert_records(outer["edges"])
        if row["source_symbol_id"] == "worker.py::owner"
    } == {(5, "worker.py::leaf"), (6, "worker.py::leaf")}
    assert {
        (row["line"], row["resolved_symbol_id"])
        for row in assert_records(callback["edges"])
        if row["source_symbol_id"] == "worker.py::owner.callback"
    } == {(7, "worker.py::leaf")}
    assert {
        row["source"]
        for row in assert_records(assert_records(leaf["nodes"])[0]["exact_callers"])
    } == {"owner", "owner.callback"}


def test_class_header_calls_belong_to_definition_scope(tmp_path: Path) -> None:
    (tmp_path / "worker.py").write_text(
        "def leaf():\n    return object\n\n"
        "def owner():\n"
        "    @leaf()\n"
        "    class Worker(leaf()):\n"
        "        value = leaf()\n"
        "    return Worker\n"
    )
    with CodeMap(tmp_path) as codemap:
        outer = codemap.structure.locality("worker.py::owner")
        worker = codemap.structure.locality("worker.py::owner.Worker")
    assert {
        row["line"]
        for row in assert_records(outer["edges"])
        if row["source_symbol_id"] == "worker.py::owner"
    } == {5, 6}
    assert {
        row["line"]
        for row in assert_records(worker["edges"])
        if row["source_symbol_id"] == "worker.py::owner.Worker"
    } == {7}
