from pathlib import Path

from contract_assertions import assert_records

from hashmarks import CodeMap


def test_replacing_a_class_withdraws_calls_through_its_published_name(
    tmp_path: Path,
) -> None:
    module = tmp_path / "model.py"
    source = (
        "class Replacement:\n"
        "    @staticmethod\n    def work(): return 'replacement'\n"
        "def replace(cls): return Replacement\n"
        "def independent(): return 1\n"
        "@replace\nclass Service:\n"
        "    @staticmethod\n    def work(): return 'original'\n"
        "    def own(self): return 'base'\n"
        "    def inside(self): return self.work(), independent()\n"
        "class LocalSub(Service):\n    def inside(self): return self.work()\n"
        "def local(): return Service(), Service.work()\n"
    )
    module.write_text(source)
    (tmp_path / "facade.py").write_text("from model import Service as Published\n")
    (tmp_path / "consumer.py").write_text(
        "from facade import Published as Imported\n"
        "import model\n"
        "def direct(): return Imported(), Imported.work(), model.Service()\n"
        "class Child(Imported):\n"
        "    def inherited(self): return self.work()\n"
        "    @classmethod\n    def on_class(cls): return cls.work()\n"
        "    def own(self): pass\n"
        "    def keep(self): return self.own()\n"
    )
    with CodeMap(tmp_path) as codemap:
        for decorated in (True, False):
            if not decorated:
                module.write_text(source.replace("@replace\n", ""))
            class_id = None if decorated else "model.py::Service"
            method_id = None if decorated else "model.py::Service.work"
            expected = {
                "model.py::local": {"Service": class_id, "Service.work": method_id},
                "consumer.py::direct": {
                    "Imported": class_id,
                    "Imported.work": method_id,
                    "model.Service": class_id,
                },
                "model.py::Service.inside": {
                    "self.work": method_id,
                    "independent": "model.py::independent",
                },
                "model.py::LocalSub.inside": {"self.work": method_id},
                "consumer.py::Child.inherited": {"self.work": method_id},
                "consumer.py::Child.on_class": {"cls.work": method_id},
                "consumer.py::Child.keep": {"self.own": "consumer.py::Child.own"},
            }
            for caller, targets in expected.items():
                packet = codemap.structure.locality(caller, max_depth=1)
                assert {
                    row["target_text"]: row["resolved_symbol_id"]
                    for row in assert_records(packet["edges"])
                } == targets
                assert {
                    row["target_text"]
                    for row in assert_records(packet["unresolved_calls"])
                } == {name for name, target in targets.items() if target is None}
            for name, caller_names in (
                ("Service", {"local", "direct"}),
                (
                    "Service.work",
                    {
                        "local",
                        "direct",
                        "Service.inside",
                        "LocalSub.inside",
                        "Child.inherited",
                        "Child.on_class",
                    },
                ),
                ("Replacement.work", set()),
                ("Service.own", set()),
            ):
                result = codemap.structure.locality("model.py::" + name, max_depth=0)
                node = assert_records(result["nodes"])[0]
                assert {
                    row["source"] for row in assert_records(node["exact_callers"])
                } == (set() if decorated else caller_names)
            assert (
                codemap.source.read("model.py::Service.work")["content"]
                == "    def work(): return 'original'"
            )
            imports = assert_records(codemap.relationships.deps("facade.py")["edges"])
            assert any(
                row["kind"] == "import" and row["target"] == "model.Service"
                for row in imports
            )


def test_nested_class_calls_require_every_published_class_component(
    tmp_path: Path,
) -> None:
    (tmp_path / "scope.py").write_text(
        "def replace(cls): return object\n"
        "class Outer:\n"
        "    @replace\n    class Wrapped:\n"
        "        class Leaf:\n            @staticmethod\n            def run(): pass\n"
        "    class Plain:\n        @staticmethod\n        def run(): pass\n"
        "def select():\n"
        "    return Outer.Wrapped(), Outer.Wrapped.Leaf(), Outer.Wrapped.Leaf.run(), Outer.Plain.run()\n"
    )
    with CodeMap(tmp_path) as codemap:
        packet = codemap.structure.locality("scope.py::select", max_depth=1)
    assert {
        row["target_text"]: row["resolved_symbol_id"]
        for row in assert_records(packet["edges"])
    } == {
        "Outer.Wrapped": None,
        "Outer.Wrapped.Leaf": None,
        "Outer.Wrapped.Leaf.run": None,
        "Outer.Plain.run": "scope.py::Outer.Plain.run",
    }
