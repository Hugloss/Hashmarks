from pathlib import Path

import pytest
from contract_assertions import assert_records

from hashmarks import CodeMap


@pytest.mark.parametrize(
    ("write", "keep_exact"),
    [
        ("Service.work = replacement", True),
        ("alias = Service\nsetattr(alias, 'work', replacement)", True),
        ("del Service.work", True),
        ("setattr(Service, field, replacement)", False),
    ],
)
def test_class_member_writes_withdraw_local_imported_and_inherited_callers(
    tmp_path: Path, write: str, keep_exact: bool
) -> None:
    owner = tmp_path / "model.py"
    source = (
        "field = ''.join(('wo', 'rk'))\n"
        "def replacement(): return 2\n"
        "class Service:\n    @staticmethod\n    def work(): return 1\n"
        "    @staticmethod\n    def keep(): return 3\n"
        "class Child(Service):\n    def inherited(self): return self.work()\n"
        "def direct(): return Service.work(), Service.keep()\n"
        "def unrelated(Service): Service.work = replacement\n"
    )
    (tmp_path / "consumer.py").write_text(
        "from model import Service as Alias\ndef use(): return Alias.work(), Alias.keep()\n"
    )
    owner.write_text(source + write + "\n")
    with CodeMap(tmp_path) as codemap:
        for mutated in (True, False):
            if not mutated:
                owner.write_text(source)
            for key in (
                "model.py::direct",
                "consumer.py::use",
                "model.py::Child.inherited",
            ):
                packet = codemap.structure.locality(key, max_depth=1)
                expected = {"work": None if mutated else "model.py::Service.work"}
                if not key.endswith("::Child.inherited"):
                    expected["keep"] = (
                        "model.py::Service.keep" if not mutated or keep_exact else None
                    )
                assert {
                    str(row["target_text"]).rsplit(".", 1)[-1]: row[
                        "resolved_symbol_id"
                    ]
                    for row in assert_records(packet["edges"])
                } == expected
            reverse = codemap.structure.locality("model.py::Service.work", max_depth=0)
            callers = assert_records(
                assert_records(reverse["nodes"])[0]["exact_callers"]
            )
            assert {row["source"] for row in callers} == (
                set() if mutated else {"direct", "use", "Child.inherited"}
            )
            replacement = codemap.structure.locality(
                "model.py::replacement", max_depth=0
            )
            assert assert_records(replacement["nodes"])[0]["exact_callers"] == []
            assert (
                codemap.source.read("model.py::Service.work")["content"]
                == "    def work(): return 1"
            )


def test_relative_import_member_write_qualifies_aliases_and_subclasses(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "owner.py").write_text(
        "class Service:\n    @staticmethod\n    def work(): pass\n"
        "    @staticmethod\n    def keep(): pass\n"
    )
    (package / "consumer.py").write_text(
        "from .owner import Service as Write\nfrom .owner import Service as Read\n"
        "Write.work = lambda: 2\n"
        "def use(): return Read.work(), Read.keep()\n"
        "class Child(Read):\n    def inherited(self): return self.work(), self.keep()\n"
        "class Override(Read):\n    def work(self): pass\n    def own(self): return self.work()\n"
    )
    with CodeMap(tmp_path) as codemap:
        for caller in ("use", "Child.inherited"):
            packet = codemap.structure.locality(
                "pkg/consumer.py::" + caller, max_depth=1
            )
            assert {
                row["resolved_symbol_id"] for row in assert_records(packet["edges"])
            } == {None, "pkg/owner.py::Service.keep"}
        own = codemap.structure.locality("pkg/consumer.py::Override.own", max_depth=1)
        assert (
            assert_records(own["edges"])[0]["resolved_symbol_id"]
            == "pkg/consumer.py::Override.work"
        )
        reverse = codemap.structure.locality("pkg/owner.py::Service.work", max_depth=0)
        assert assert_records(reverse["nodes"])[0]["exact_callers"] == []
