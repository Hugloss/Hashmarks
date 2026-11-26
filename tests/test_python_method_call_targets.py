from pathlib import Path

from contract_assertions import assert_records

from hashmarks import CodeMap


def test_decorated_member_call_qualifies_the_target_descriptor(tmp_path: Path) -> None:
    (tmp_path / "model.py").write_text(
        "from builtins import property as getter, staticmethod as sm, classmethod as cm\n"
        "def callback(*args): pass\n"
        "def replace(method): return callback\n"
        "class Base:\n"
        "    def chosen(self): pass\n"
        "class Model(Base):\n"
        "    @getter\n    def chosen(self): return callback\n"
        "    @replace\n    def transformed(self): pass\n"
        "    @sm\n    def direct_static(): pass\n"
        "    @cm\n    def direct_class(cls): pass\n"
        "    def direct(self): pass\n"
        "class Consumer(Model):\n"
        "    def dispatch(self):\n"
        "        return self.chosen(), self.transformed(), self.direct_static(), self.direct_class(), self.direct()\n"
        "    @cm\n    def inspect(cls): return cls.chosen()\n"
        "def local(): return Model.chosen(), Model.transformed(), Model.direct_static()\n"
    )
    (tmp_path / "use.py").write_text(
        "from model import Model as Imported\n"
        "def dispatch(): return Imported.chosen(), Imported.transformed(), Imported.direct_static()\n"
    )
    with CodeMap(tmp_path) as codemap:
        for caller, receiver, resolved in (
            (
                "model.py::Consumer.dispatch",
                "self",
                {"direct", "direct_static", "direct_class"},
            ),
            ("model.py::Consumer.inspect", "cls", set()),
            ("model.py::local", "Model", {"direct_static"}),
            ("use.py::dispatch", "Imported", {"direct_static"}),
        ):
            packet = codemap.structure.locality(caller, max_depth=1)
            uncertain = {"chosen"} if receiver == "cls" else {"chosen", "transformed"}
            expected: dict[str, str | None] = {
                f"{receiver}.{name}": None for name in uncertain
            }
            expected.update(
                {f"{receiver}.{name}": f"model.py::Model.{name}" for name in resolved}
            )
            assert {
                row["target_text"]: row["resolved_symbol_id"]
                for row in assert_records(packet["edges"])
            } == expected
            assert {
                row["target_text"] for row in assert_records(packet["unresolved_calls"])
            } == {f"{receiver}.{name}" for name in uncertain}
        for name in ("Model.chosen", "Model.transformed", "Base.chosen", "callback"):
            reverse = codemap.structure.locality("model.py::" + name, max_depth=0)
            assert assert_records(reverse["nodes"])[0]["exact_callers"] == []
        positive = codemap.structure.locality(
            "model.py::Model.direct_static", max_depth=0
        )
        node = assert_records(positive["nodes"])[0]
        assert {row["source"] for row in assert_records(node["exact_callers"])} == {
            "Consumer.dispatch",
            "dispatch",
            "local",
        }


def test_method_target_refreshes_when_its_descriptor_changes(tmp_path: Path) -> None:
    model = tmp_path / "model.py"
    source = (
        "from builtins import staticmethod as bind\n"
        "def callback(): pass\n"
        "class Worker:\n"
        "    @bind\n    def entry(*args): return callback\n"
        "    def run(self): return self.entry()\n"
    )
    model.write_text(source)
    with CodeMap(tmp_path) as codemap:
        before = codemap.structure.locality("model.py::Worker.entry", max_depth=0)
        model.write_text(source.replace("import staticmethod", "import property"))
        after = codemap.structure.locality("model.py::Worker.entry", max_depth=0)
    assert assert_records(before["nodes"])[0]["exact_caller_count"] == 1
    assert assert_records(after["nodes"])[0]["exact_caller_count"] == 0


def test_shadowed_and_stacked_staticmethod_targets_remain_unresolved(
    tmp_path: Path,
) -> None:
    (tmp_path / "model.py").write_text(
        "from builtins import staticmethod as real_static\n"
        "def callback(*args): pass\n"
        "def staticmethod(fn): return callback\n"
        "class Worker:\n"
        "    @staticmethod\n    def shadowed(): pass\n"
        "    @real_static\n    @staticmethod\n    def stacked(): pass\n"
        "    def run(self): return self.shadowed(), self.stacked()\n"
    )
    with CodeMap(tmp_path) as codemap:
        packet = codemap.structure.locality("model.py::Worker.run", max_depth=1)
        assert {
            (row["target_text"], row["resolved_symbol_id"])
            for row in assert_records(packet["unresolved_calls"])
        } == {("self.shadowed", None), ("self.stacked", None)}
