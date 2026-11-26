from pathlib import Path

import pytest
from contract_assertions import assert_records

from hashmarks import CodeMap


@pytest.mark.parametrize(
    ("initializer", "shadowed"),
    [
        ("instance.work = replacement", {"work"}),
        ("alias = instance\n        setattr(alias, 'work', replacement)", {"work"}),
        ("setattr(instance, field, replacement)", {"work", "keep"}),
        ("other.work = replacement", set()),
        ("def deferred(): instance.work = replacement", set()),
    ],
)
def test_instance_calls_consume_writes_on_the_initializer_parameter(
    tmp_path: Path, initializer: str, shadowed: set[str]
) -> None:
    path = tmp_path / "worker.py"
    source = (
        "def replacement(): return 2\n"
        "class Worker:\n"
        f"    def __init__(instance, /, other, field):\n        {initializer}\n"
        "    def work(self): return 1\n    def keep(self): return 3\n"
        "    def run(self): return self.work(), self.keep()\n"
        "    @classmethod\n    def via_cls(cls, obj): return cls.work(obj)\n"
        "def via_class(obj): return Worker.work(obj)\n"
    )
    path.write_text(source)
    with CodeMap(tmp_path) as codemap:
        for replaced in (True, False):
            if not replaced:
                path.write_text(source.replace(initializer, "pass"))
            forward = codemap.structure.locality("worker.py::Worker.run", max_depth=1)
            assert {
                row["target_text"]: row["resolved_symbol_id"]
                for row in assert_records(forward["edges"])
            } == {
                f"self.{name}": None
                if replaced and name in shadowed
                else f"worker.py::Worker.{name}"
                for name in ("work", "keep")
            }
            reverse = codemap.structure.locality("worker.py::Worker.work", max_depth=0)
            callers = assert_records(
                assert_records(reverse["nodes"])[0]["exact_callers"]
            )
            expected = {"Worker.via_cls", "via_class"}
            if not replaced or "work" not in shadowed:
                expected.add("Worker.run")
            assert {row["source"] for row in callers} == expected
            unused = codemap.structure.locality("worker.py::replacement", max_depth=0)
            assert assert_records(unused["nodes"])[0]["exact_callers"] == []


def test_inherited_initializer_can_shadow_a_subclass_override(tmp_path: Path) -> None:
    (tmp_path / "base.py").write_text(
        "class Base:\n    def __init__(self): self.work = lambda: 2\n"
        "    def work(self): return 1\n"
        "    def keep(self): return 3\n"
    )
    (tmp_path / "child.py").write_text(
        "from base import Base as Parent\n"
        "class Override(Parent):\n    def work(self): return 3\n"
        "    def run(self): return self.work()\n"
        "class Independent(Parent):\n    def __init__(self): pass\n"
        "    def run(self): return self.work()\n"
        "class Delegate(Parent):\n    def __init__(self): super().__init__()\n"
        "    def run(self): return self.work(), self.keep()\n"
        "class Shadowed(Parent):\n    def __init__(self, super): super().__init__()\n"
        "    def run(self): return self.work()\n"
    )
    with CodeMap(tmp_path) as codemap:
        override = codemap.structure.locality("child.py::Override.run", max_depth=1)
        independent = codemap.structure.locality(
            "child.py::Independent.run", max_depth=1
        )
        assert [
            row["resolved_symbol_id"]
            for row in assert_records(override["unresolved_calls"])
        ] == [None]
        assert [
            row["resolved_symbol_id"] for row in assert_records(independent["edges"])
        ] == ["base.py::Base.work"]
        delegated = codemap.structure.locality("child.py::Delegate.run", max_depth=1)
        assert {
            row["target_text"]: row["resolved_symbol_id"]
            for row in assert_records(delegated["edges"])
        } == {"self.work": None, "self.keep": "base.py::Base.keep"}
        shadowed = codemap.structure.locality("child.py::Shadowed.run", max_depth=1)
        assert (
            assert_records(shadowed["edges"])[0]["resolved_symbol_id"]
            == "base.py::Base.work"
        )
        reverse = codemap.structure.locality("child.py::Override.work", max_depth=0)
        assert assert_records(reverse["nodes"])[0]["exact_callers"] == []


def test_competing_initializers_preserve_an_observed_instance_write(
    tmp_path: Path,
) -> None:
    (tmp_path / "worker.py").write_text(
        "class Writes:\n    def __init__(self): self.work = lambda: 2\n"
        "class Other:\n    def __init__(self): pass\n"
        "class Worker(Writes, Other):\n"
        "    def work(self): return 1\n    def run(self): return self.work()\n"
    )
    with CodeMap(tmp_path) as codemap:
        packet = codemap.structure.locality("worker.py::Worker.run", max_depth=1)
        assert [
            row["resolved_symbol_id"]
            for row in assert_records(packet["unresolved_calls"])
        ] == [None]
        reverse = codemap.structure.locality("worker.py::Worker.work", max_depth=0)
        assert assert_records(reverse["nodes"])[0]["exact_callers"] == []
