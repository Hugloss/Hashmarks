from pathlib import Path

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
