from pathlib import Path

import pytest
from contract_assertions import assert_records

from hashmarks.codemap import CodeMap


@pytest.mark.parametrize("prefix", ["", "async "])
def test_direct_nested_helper_qualifies_despite_same_name_crowding(
    tmp_path: Path, prefix: str
) -> None:
    (tmp_path / "decoys.py").write_text(
        "".join(f"class C{i}:\n    def helper(self): pass\n" for i in range(70))
    )
    (tmp_path / "worker.py").write_text(
        "def helper(): return 1\n"
        f"{prefix}def outer():\n    {prefix}def helper(): return 2\n"
        + ("    return await helper()\n" if prefix else "    return helper()\n")
    )
    with CodeMap(tmp_path) as codemap:
        packet = codemap.structure.locality("worker.py::outer", max_depth=1)
        assert [
            (row["source_symbol_id"], row["resolved_symbol_id"])
            for row in assert_records(packet["edges"])
        ] == [("worker.py::outer", "worker.py::outer.helper")]
        for owner, expected in (
            ("outer.helper", ["outer"]),
            ("helper", []),
            ("decoys.py::C0.helper", []),
        ):
            symbol = owner if "::" in owner else "worker.py::" + owner
            node = assert_records(
                codemap.structure.locality(symbol, max_depth=0)["nodes"]
            )[0]
            assert [
                row["source"] for row in assert_records(node["exact_callers"])
            ] == expected


@pytest.mark.parametrize(
    ("header", "body"),
    [
        ("", "    helper()\n    def helper(): pass\n"),
        ("", "    def helper(): pass\n    helper = unknown\n    helper()\n"),
        ("", "    def helper(): pass\n    del helper\n    helper()\n"),
        ("", "    @wrapper\n    def helper(): pass\n    helper()\n"),
        ("", "    if cond:\n        def helper(): pass\n    helper()\n"),
        ("", "    def helper(): pass\n    def helper(): pass\n    helper()\n"),
        ("helper", "    helper()\n"),
        (
            "",
            "    def helper(): pass\n    return helper(), (lambda helper: helper())(arg)\n",
        ),
    ],
)
def test_local_binding_gaps_do_not_fall_back_to_a_module_function(
    tmp_path: Path, header: str, body: str
) -> None:
    (tmp_path / "worker.py").write_text(
        f"def helper(): pass\ndef outer({header}):\n" + body
    )
    with CodeMap(tmp_path) as codemap:
        packet = codemap.structure.locality("worker.py::outer", max_depth=1)
        calls = [
            row
            for row in assert_records(packet["edges"])
            if row["target_text"] == "helper"
        ]
        assert calls and all(row["resolved_symbol_id"] is None for row in calls)
        reverse = codemap.structure.locality("worker.py::helper", max_depth=0)
        assert assert_records(reverse["nodes"])[0]["exact_callers"] == []
        if not header:
            nested = codemap.structure.locality("worker.py::outer.helper", max_depth=0)
            assert assert_records(nested["nodes"])[0]["exact_callers"] == []


def test_outline_visibility_does_not_qualify_a_nested_call(tmp_path: Path) -> None:
    (tmp_path / ".hashmarks-context.toml").write_text(
        "[[rule]]\npattern='worker.py'\nvisibility='outline'\n"
    )
    (tmp_path / "worker.py").write_text(
        "def outer():\n    def helper(): pass\n    return helper()\n"
    )
    with CodeMap(tmp_path) as codemap:
        packet = codemap.structure.locality("worker.py::outer", max_depth=1)
        assert all(
            row["resolved_symbol_id"] is None for row in assert_records(packet["edges"])
        )
        reverse = codemap.structure.locality("worker.py::outer.helper", max_depth=0)
        assert assert_records(reverse["nodes"])[0]["exact_callers"] == []


def test_editing_helper_binding_refreshes_both_caller_projections(
    tmp_path: Path,
) -> None:
    worker = tmp_path / "worker.py"
    source = "def outer():\n    def helper(): pass\n    return helper()\n"
    worker.write_text(source)
    with CodeMap(tmp_path) as codemap:
        first = codemap.structure.locality("worker.py::outer")
        assert (
            assert_records(first["edges"])[0]["resolved_symbol_id"]
            == "worker.py::outer.helper"
        )
        worker.write_text(
            source.replace("    def helper", "    @modifier\n    def helper")
        )
        after = codemap.structure.locality("worker.py::outer")
        reverse = codemap.structure.locality("worker.py::outer.helper", max_depth=0)
    assert assert_records(after["edges"])[0]["resolved_symbol_id"] is None
    assert assert_records(reverse["nodes"])[0]["exact_callers"] == []
