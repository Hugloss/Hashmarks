from pathlib import Path

import pytest
from contract_assertions import assert_records

from hashmarks.codemap import CodeMap


def test_method_receiver_requires_a_qualified_descriptor(tmp_path: Path) -> None:
    (tmp_path / "worker.py").write_text(
        "from builtins import classmethod as cm, staticmethod as sm\n"
        "import builtins as b\n"
        "method = classmethod\n"
        "class Custom:\n"
        "    def classmethod(fn): return staticmethod(fn)\n"
        "class Worker:\n"
        "    def helper(self): pass\n"
        "    def ordinary(self): return self.helper()\n"
        "    @classmethod\n    def bare(cls): return cls.helper()\n"
        "    @cm\n    def imported(cls): return cls.helper()\n"
        "    @b.classmethod\n    def qualified(cls): return cls.helper()\n"
        "    @method\n    def assigned(cls): return cls.helper()\n"
        "    @b.property\n    def getter(self): return self.helper()\n"
        "    @Custom.classmethod\n    def disguised(cls): return cls.helper()\n"
        "    @sm\n    def static(self): return self.helper()\n"
        "    @wrap\n    def custom(self): return self.helper()\n"
        "    @wrap\n    @cm\n    def stacked(cls): return cls.helper()\n"
        "class Shadow:\n"
        "    classmethod = sm\n"
        "    @classmethod\n    def disguised(cls): return cls.helper()\n"
        "    def helper(self): pass\n"
    )
    exact = {"ordinary", "bare", "imported", "qualified", "assigned", "getter"}
    with CodeMap(tmp_path) as codemap:
        for method in sorted(exact | {"disguised", "static", "custom", "stacked"}):
            packet = codemap.structure.locality(
                f"worker.py::Worker.{method}", max_depth=1
            )
            calls = assert_records(packet["edges"])
            assert [row["resolved_symbol_id"] for row in calls] == [
                "worker.py::Worker.helper" if method in exact else None
            ]
        for name in ("Worker", "Shadow"):
            reverse = codemap.structure.locality(
                f"worker.py::{name}.helper", max_depth=0
            )
            node = assert_records(reverse["nodes"])[0]
            callers = {row["source"] for row in assert_records(node["exact_callers"])}
            assert callers == (
                {f"Worker.{method}" for method in exact} if name == "Worker" else set()
            )


def test_mutated_builtin_descriptor_cannot_prove_a_receiver(tmp_path: Path) -> None:
    (tmp_path / "worker.py").write_text(
        "import builtins as b\n"
        "setattr(b, 'classmethod', b.staticmethod)\n"
        "class Worker:\n"
        "    def helper(self): pass\n"
        "    @classmethod\n    def bare(cls): return cls.helper()\n"
        "    @b.classmethod\n    def qualified(cls): return cls.helper()\n"
    )
    with CodeMap(tmp_path) as codemap:
        for method in ("bare", "qualified"):
            packet = codemap.structure.locality(f"worker.py::Worker.{method}")
            assert [
                row["resolved_symbol_id"] for row in assert_records(packet["edges"])
            ] == [None]
        reverse = codemap.structure.locality("worker.py::Worker.helper", max_depth=0)
        assert assert_records(reverse["nodes"])[0]["exact_callers"] == []


def test_refreshed_decorator_does_not_reuse_a_previous_receiver(tmp_path: Path) -> None:
    worker = tmp_path / "worker.py"
    source = (
        "from builtins import classmethod as wrap\n"
        "class Worker:\n"
        "    def helper(self): pass\n"
        "    @wrap\n    def method(cls): return cls.helper()\n"
    )
    worker.write_text(source)
    with CodeMap(tmp_path) as codemap:
        first = codemap.structure.locality("worker.py::Worker.helper", max_depth=0)
        worker.write_text(source.replace("import classmethod", "import staticmethod"))
        second = codemap.structure.locality("worker.py::Worker.helper", max_depth=0)
    assert assert_records(first["nodes"])[0]["exact_caller_count"] == 1
    assert assert_records(second["nodes"])[0]["exact_caller_count"] == 0


@pytest.mark.parametrize(
    ("receiver", "write"),
    [
        ("self", "self.step = replacement"),
        ("self", "alias = self\n        alias.step = replacement"),
        ("self", "del self.step"),
        ("cls", "setattr(cls, 'step', replacement)"),
        ("cls", "setattr(cls, field, replacement)"),
    ],
)
def test_receiver_member_write_is_not_an_exact_class_caller(
    tmp_path: Path, receiver: str, write: str
) -> None:
    decorator = "    @classmethod\n" if receiver == "cls" else ""
    (tmp_path / "worker.py").write_text(
        "class Worker:\n"
        "    def step(self): pass\n"
        f"{decorator}    def changed({receiver}, replacement, field):\n"
        f"        {write}\n        return {receiver}.step()\n"
        f"{decorator}    def unaffected({receiver}, other):\n"
        f"        {receiver}.other = other\n        return {receiver}.step()\n"
    )
    target = "worker.py::Worker.step"
    with CodeMap(tmp_path) as codemap:
        changed = codemap.structure.locality("worker.py::Worker.changed", max_depth=1)
        uses = [
            row
            for row in assert_records(changed["unresolved_calls"])
            if row["target_text"] == f"{receiver}.step"
        ]
        assert [row["resolved_symbol_id"] for row in uses] == [None]
        control = codemap.structure.locality(
            "worker.py::Worker.unaffected", max_depth=1
        )
        assert [
            row["resolved_symbol_id"] for row in assert_records(control["edges"])
        ] == [target]
        reverse = codemap.structure.locality(target, max_depth=0)
        callers = assert_records(assert_records(reverse["nodes"])[0]["exact_callers"])
        assert [row["source"] for row in callers] == ["Worker.unaffected"]
