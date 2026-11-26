from pathlib import Path

from contract_assertions import assert_records

from hashmarks.codemap import CodeMap


def _callers(codemap: CodeMap, target: str) -> set[object]:
    packet = codemap.structure.locality(target, max_depth=0)
    node = assert_records(packet["nodes"])[0]
    return {row["source"] for row in assert_records(node["exact_callers"])}


def test_later_base_rebinding_cannot_qualify_inherited_callers(tmp_path: Path) -> None:
    source = tmp_path / "api.py"
    source.write_text(
        "from external import Foreign as Base\n"
        "class Known:\n    def persist(self): pass\n"
        "class Early(Base, Known):\n"
        "    def run(self):\n        self.save()\n        self.persist()\n"
        "class Base:\n    def save(self): pass\n"
        "class Late(Base, Known):\n"
        "    def run(self):\n        self.save()\n        self.persist()\n"
    )
    with CodeMap(tmp_path) as codemap:
        early = codemap.structure.locality("api.py::Early.run", max_depth=1)
        assert {
            (row["target_text"], row["resolved_symbol_id"])
            for row in assert_records(early["unresolved_calls"])
        } == {("self.save", None), ("self.persist", None)}
        late = codemap.structure.locality("api.py::Late.run", max_depth=1)
        assert {row["resolved_symbol_id"] for row in assert_records(late["edges"])} == {
            "api.py::Known.persist",
            "api.py::Base.save",
        }
        for owner in ("Known.persist", "Base.save"):
            assert _callers(codemap, f"api.py::{owner}") == {"Late.run"}


def test_nested_class_header_uses_the_enclosing_namespace(tmp_path: Path) -> None:
    (tmp_path / "api.py").write_text(
        "class Base:\n    def save(self): pass\n"
        "class Outer:\n"
        "    class Base:\n        def save(self): pass\n"
        "    class Worker(Base):\n        def run(self): return self.save()\n"
    )
    with CodeMap(tmp_path) as codemap:
        target = "api.py::Outer.Base.save"
        packet = codemap.structure.locality("api.py::Outer.Worker.run", max_depth=1)
        assert [
            row["resolved_symbol_id"] for row in assert_records(packet["edges"])
        ] == [target]
        assert _callers(codemap, target) == {"Outer.Worker.run"}
        assert _callers(codemap, "api.py::Base.save") == set()


def test_diamond_through_renamed_import_reaches_one_declared_base(
    tmp_path: Path,
) -> None:
    (tmp_path / "store.py").write_text("class Storage:\n    def save(self): pass\n")
    (tmp_path / "public.py").write_text("from store import Storage as Base\n")
    (tmp_path / "api.py").write_text(
        "from public import Base\n"
        "class Left(Base): pass\nclass Right(Base): pass\n"
        "class Worker(Left, Right):\n    def run(self): return self.save()\n"
    )
    with CodeMap(tmp_path) as codemap:
        owner = "store.py::Storage.save"
        packet = codemap.structure.locality("api.py::Worker.run", max_depth=1)
        assert [
            row["resolved_symbol_id"] for row in assert_records(packet["edges"])
        ] == [owner]
        assert _callers(codemap, owner) == {"Worker.run"}
