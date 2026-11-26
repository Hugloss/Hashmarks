from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records

from hashmarks import CodeMap


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_multiline_imports_and_calls_point_at_each_referenced_name(
    tmp_path: Path, newline: str
) -> None:
    (tmp_path / "service.py").write_text(
        "def first(): return 1\ndef second(): return 2\n"
    )
    lines = [
        "from service import (",
        "    first,",
        "    second as selected,",
        ")",
        "import ast, \\",
        "    json as data",
        "def run():",
        "    def local(): return 1",
        "    return (",
        "        local",
        "    )() + (",
        "        selected",
        "    )()",
    ]
    (tmp_path / "consumer.py").write_bytes((newline.join(lines) + newline).encode())
    with CodeMap(tmp_path) as cm:
        deps = assert_records(cm.relationships.deps("consumer.py")["edges"])
        assert {(r["target"], r["line"]) for r in deps if r["kind"] == "import"} == {
            ("service.first", 2),
            ("service.second", 3),
            ("ast", 5),
            ("json", 6),
        }
        (ref,) = assert_records(cm.relationships.refs("second")["references"])
        assert (ref["target"], ref["line"]) == ("service.second", 3)
        graph = cm.structure.locality("consumer.py::run", max_depth=1)
        assert [
            (r["resolved_symbol_id"], r["line"]) for r in assert_records(graph["edges"])
        ] == [
            ("consumer.py::run.local", 10),
            ("service.py::second", 12),
        ]
        reverse = cm.structure.locality("service.py::second", max_depth=0)
        (node,) = assert_records(reverse["nodes"])
        (caller,) = assert_records(node["exact_callers"])
        assert (caller["path"], caller["source"], caller["line"]) == (
            "consumer.py",
            "run",
            12,
        )


def test_multiline_attribute_witness_and_instance_receiver_match_the_index(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text(
        "def calculate_tax(): return 1\nclass Service:\n    def amount(self): return 1\n"
        "    def run(self):\n        return (\n            self\n            .amount\n        )()\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_amount.py").write_text(
        "import owner as api\ndef test_amount():\n    assert (\n"
        "        api\n        .calculate_tax\n    )() == 1\n"
    )
    with CodeMap(tmp_path) as cm:
        for locator, target, line in (
            ("owner.py::Service.run", "owner.py::Service.amount", 7),
            ("tests/test_amount.py::test_amount", "owner.py::calculate_tax", 5),
        ):
            (edge,) = assert_records(
                cm.structure.locality(locator, max_depth=1)["edges"]
            )
            assert (edge["resolved_symbol_id"], edge["line"]) == (target, line)
        changed = cm.verification.changed_set(["owner.py"])
        assert [t["path"] for t in assert_records(changed["targets"])] == [
            "tests/test_amount.py"
        ]
        task = cm.tasks.evidence("Change calculate_tax in owner.py")
        assert (
            assert_object(task["verification"]["plan"])["test_symbol"] == "test_amount"
        )


def test_relocated_call_keeps_lambda_parameter_shadowing(tmp_path: Path) -> None:
    (tmp_path / "model.py").write_text("def choose(): return 1\n")
    (tmp_path / "consumer.py").write_text(
        "from model import choose\n"
        "def adapter():\n    return lambda choose: (\n        choose\n    )()\n"
    )
    with CodeMap(tmp_path) as cm:
        graph = cm.structure.locality("consumer.py::adapter", max_depth=1)
        (edge,) = assert_records(graph["edges"])
        assert (edge["line"], edge["resolved_symbol_id"]) == (4, None)
        reverse = cm.structure.locality("model.py::choose", max_depth=0)
        assert assert_records(reverse["nodes"])[0]["exact_callers"] == []
