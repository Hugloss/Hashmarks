from pathlib import Path

from contract_assertions import assert_records

from hashmarks.codemap import CodeMap


def test_overload_call_and_types_belong_to_the_authored_occurrence(
    tmp_path: Path,
) -> None:
    (tmp_path / "codec.py").write_text(
        "from typing import overload\n"
        "def helper(): return 1\n"
        "class Codec:\n"
        "    @overload\n    def encode(self, value: str) -> str: ...\n"
        "    def encode(self, value: int) -> int: return helper()\n"
        "def invoke(codec): return codec.encode(1)\n"
    )
    state = tmp_path / ".state"
    for _ in range(2):
        with CodeMap(tmp_path, state_dir=state) as codemap:
            stub = codemap.structure.locality("codec.py::Codec.encode")
            implementation = codemap.structure.locality("codec.py::Codec.encode@L6")
            reverse = codemap.structure.locality("codec.py::helper", max_depth=0)
            dynamic = codemap.structure.locality("codec.py::invoke")
            deps = codemap.relationships.deps("codec.py")
        assert stub["edges"] == []
        assert [
            (row["source_symbol_id"], row["resolved_symbol_id"])
            for row in assert_records(implementation["edges"])
        ] == [("codec.py::Codec.encode@L6", "codec.py::helper")]
        assert [
            row["source"]
            for row in assert_records(
                assert_records(reverse["nodes"])[0]["exact_callers"]
            )
        ] == ["Codec.encode@L6"]
        assert assert_records(dynamic["edges"])[0]["resolved_symbol_id"] is None
        assert {
            (row["source"], row["kind"], row["target"])
            for row in assert_records(deps["edges"])
            if row["kind"] in {"parameter-type", "return-type"}
        } == {
            (occurrence, kind, annotation)
            for occurrence, annotation in (
                ("Codec.encode", "str"),
                ("Codec.encode@L6", "int"),
            )
            for kind in ("parameter-type", "return-type")
        }


def test_occurrence_does_not_resolve_a_shadowed_or_repeated_callee(
    tmp_path: Path,
) -> None:
    (tmp_path / "other.py").write_text("def emit(): ...\ndef emit(): return 1\n")
    (tmp_path / "api.py").write_text(
        "from other import emit\n"
        "def leaf(): pass\n"
        "def publish(): ...\n"
        "def publish(leaf):\n    leaf()\n    emit()\n"
    )
    with CodeMap(tmp_path) as codemap:
        result = codemap.structure.locality("api.py::publish@L4", max_depth=1)
        assert {
            (row["target_text"], row["resolved_symbol_id"])
            for row in assert_records(result["edges"])
        } == {("leaf", None), ("emit", None)}
        for key in ("api.py::leaf", "other.py::emit", "other.py::emit@L2"):
            reverse = codemap.structure.locality(key, max_depth=0)
            assert assert_records(reverse["nodes"])[0]["exact_callers"] == []


def test_redefined_parent_owns_nested_definition_headers(tmp_path: Path) -> None:
    (tmp_path / "api.py").write_text(
        "def default(): return 1\n"
        "def leaf(): return 2\n"
        "def factory(): ...\n"
        "def factory():\n"
        "    def nested(x=default()): return leaf()\n"
        "    return nested\n"
    )
    with CodeMap(tmp_path) as codemap:
        for source, target in (
            ("factory", None),
            ("factory@L4", "default"),
            ("factory.nested", "leaf"),
        ):
            packet = codemap.structure.locality("api.py::" + source, max_depth=1)
            assert [row["target_text"] for row in assert_records(packet["edges"])] == (
                [target] if target else []
            )


def test_method_occurrence_qualifies_its_own_receiver_only(tmp_path: Path) -> None:
    (tmp_path / "api.py").write_text(
        "class Codec:\n"
        "    def helper(self): pass\n"
        "    def encode(self): ...\n"
        "    def encode(self): return self.helper()\n"
        "    def run(self): return self.encode()\n"
    )
    with CodeMap(tmp_path) as codemap:
        implementation = codemap.structure.locality(
            "api.py::Codec.encode@L4", max_depth=1
        )
        through_name = codemap.structure.locality("api.py::Codec.run", max_depth=1)
    assert [
        row["resolved_symbol_id"] for row in assert_records(implementation["edges"])
    ] == ["api.py::Codec.helper"]
    assert assert_records(through_name["edges"])[0]["resolved_symbol_id"] is None
