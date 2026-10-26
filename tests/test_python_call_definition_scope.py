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


@pytest.mark.parametrize(
    ("declaration", "result_expression"),
    [
        ("def build(value=build()):\n    return value\n", "7"),
        ("@build()\ndef build():\n    return 1\n", "lambda function: function"),
        ("class build(build()):\n    pass\n", "object"),
    ],
)
def test_definition_header_cannot_call_the_binding_it_has_not_published(
    tmp_path: Path, declaration: str, result_expression: str
) -> None:
    (tmp_path / "provider.py").write_text(f"def build(): return {result_expression}\n")
    (tmp_path / "consumer.py").write_text("from provider import build\n" + declaration)
    with CodeMap(tmp_path) as codemap:
        declared = codemap.structure.locality("consumer.py::build", max_depth=0)
        imported = codemap.structure.locality("provider.py::build", max_depth=0)
    for packet in (declared, imported):
        node = assert_records(packet["nodes"])[0]
        assert node["exact_callers"] == []
        assert any(
            row["path"] == "consumer.py" and row["source"] is None
            for row in assert_records(node["unresolved_caller_candidates"])
        )


@pytest.mark.parametrize("argument", ["value", "build"])
def test_unrelated_definition_and_parameter_names_preserve_header_imports(
    tmp_path: Path, argument: str
) -> None:
    (tmp_path / "provider.py").write_text("def build(): return 1\n")
    (tmp_path / "consumer.py").write_text(
        f"from provider import build\ndef wrapper({argument}=build()):\n"
        f"    return {argument}\n"
    )
    with CodeMap(tmp_path) as codemap:
        packet = codemap.structure.locality("provider.py::build", max_depth=0)
    node = assert_records(packet["nodes"])[0]
    assert {
        (row["path"], row["source"]) for row in assert_records(node["exact_callers"])
    } == {("consumer.py", None)}


def test_function_body_recursion_retains_the_published_definition(
    tmp_path: Path,
) -> None:
    (tmp_path / "provider.py").write_text("def build(value): return value\n")
    (tmp_path / "consumer.py").write_text(
        "from provider import build\ndef build(value):\n"
        "    return build(value - 1) if value else 0\n"
    )
    with CodeMap(tmp_path) as codemap:
        packet = codemap.structure.locality("consumer.py::build")
    call = next(
        row for row in assert_records(packet["edges"]) if row["target_text"] == "build"
    )
    assert call["resolved_symbol_id"] == "consumer.py::build"
