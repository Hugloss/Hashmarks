"""Direct graph edges retain the indexed caller's own lexical scope."""

from pathlib import Path

import pytest
from contract_assertions import assert_records

from hashmarks.codemap import CodeMap
from hashmarks.evidence_presentation import FORMATS, presentation_response


def test_callable_kinds_and_bare_target_follow_their_lexical_scope(
    tmp_path: Path,
) -> None:
    (tmp_path / "worker.py").write_text(
        "def normalize(x): return x\n"
        "def dispatch(x): return normalize(x)\n"
        "def factory():\n"
        "    def normalize(x): return x + 1\n"
        "    class Preview:\n"
        "        async def normalize(self):\n"
        "            async def inner(): pass\n"
        "            return inner\n"
        "    return Preview\n"
    )
    with CodeMap(tmp_path) as codemap:
        outline = codemap.source.outline("worker.py")
        kinds = {
            row["qualname"]: row["kind"] for row in assert_records(outline["symbols"])
        }
        assert (
            kinds["factory.normalize"]
            == kinds["factory.Preview.normalize.inner"]
            == "function"
        )
        assert kinds["factory.Preview.normalize"] == "method"
        exact = assert_records(codemap.search.packet("factory.normalize")["results"])
        assert (
            next(row["kind"] for row in exact if row["qualname"] == "factory.normalize")
            == "function"
        )
        calls = assert_records(
            codemap.structure.locality("worker.py::dispatch")["edges"]
        )
        assert [row["resolved_symbol_id"] for row in calls] == ["worker.py::normalize"]
        for callee, expected in (
            ("normalize", ["dispatch"]),
            ("factory.normalize", []),
            ("factory.Preview.normalize", []),
        ):
            node = assert_records(
                codemap.structure.locality(f"worker.py::{callee}", max_depth=0)["nodes"]
            )[0]
            assert [
                row["source"] for row in assert_records(node["exact_callers"])
            ] == expected


@pytest.mark.parametrize(
    ("declaration", "call", "target"),
    [
        ("def process(): pass", "process()", "consumer.py::process"),
        ("from provider import process as run", "run()", "provider.py::process"),
        ("from provider import Job", "Job.process()", "provider.py::Job.process"),
        ("import provider as lib", "lib.process()", "provider.py::process"),
    ],
)
def test_module_call_requires_a_preceding_binding(
    tmp_path: Path, declaration: str, call: str, target: str
) -> None:
    (tmp_path / "provider.py").write_text(
        "def process(): pass\nclass Job:\n    @staticmethod\n    def process(): pass\n"
    )
    consumer = tmp_path / "consumer.py"
    consumer.write_text(f"value = {call}\n{declaration}\n")
    with CodeMap(tmp_path) as codemap:
        before = assert_records(
            codemap.structure.locality(target, max_depth=0)["nodes"]
        )[0]
        assert before["exact_callers"] == []
        assert [
            row["line"]
            for row in assert_records(before["unresolved_caller_candidates"])
        ] == [1]
        consumer.write_text(f"{declaration}\nvalue = {call}\n")
        after = assert_records(
            codemap.structure.locality(target, max_depth=0)["nodes"]
        )[0]
        assert [
            (row["path"], row["line"]) for row in assert_records(after["exact_callers"])
        ] == [("consumer.py", 2)]


def test_same_line_from_import_cannot_establish_call_order(tmp_path: Path) -> None:
    (tmp_path / "provider.py").write_text("def process(): pass\n")
    (tmp_path / "consumer.py").write_text("from provider import process; process()\n")
    with CodeMap(tmp_path) as codemap:
        node = assert_records(
            codemap.structure.locality("provider.py::process", max_depth=0)["nodes"]
        )[0]
    assert node["exact_callers"] == []
    assert [
        row["line"] for row in assert_records(node["unresolved_caller_candidates"])
    ] == [1]


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
