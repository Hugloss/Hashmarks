from pathlib import Path

import pytest
from contract_assertions import assert_records

from hashmarks.codemap import CodeMap, python_binding_scope


def test_inheritance_edges_locate_only_direct_named_bases(tmp_path: Path) -> None:
    (tmp_path / "api.py").write_text(
        "import collections as pkg\n"
        "class Payload: pass\n"
        "class Registry: pass\n"
        "class Generated:\n"
        "    class Registry: pass\n"
        "def make_base(value): return Generated\n"
        "class Frame(\n"
        "    pkg.UserList[Payload],\n"
        "    Registry,\n"
        "    make_base('Payload'),\n"
        "    make_base('Payload').Registry,\n"
        "): pass\n"
    )
    with CodeMap(tmp_path) as cm:
        rows = assert_records(cm.relationships.deps("Frame")["edges"])
        assert {(row["kind"], row["target"], row["line"]) for row in rows} == {
            ("inherits", "pkg.UserList", 8),
            ("inherits", "Registry", 9),
        }
        refs = assert_records(cm.relationships.refs("Payload")["references"])
        assert not any(row["kind"] == "inherits" for row in refs)
        calls = assert_records(cm.relationships.refs("make_base")["references"])
        assert {
            (row["source"], row["line"]) for row in calls if row["kind"] == "call"
        } == {(None, 10), (None, 11)}


def test_type_edges_use_written_reference_lines_and_exclude_computed_values(
    tmp_path: Path,
) -> None:
    (tmp_path / "api.py").write_text(
        "from __future__ import annotations\n"
        "from collections.abc import Callable as Fn\n"
        "class Record:\n"
        "    payload: (\n"
        "        Payload\n"
        "    )\n"
        "    def convert(self,\n"
        "        cb: Fn[[\n"
        "            Payload, Payload\n"
        "        ], Result],\n"
        "        value: choose('Decoy'),\n"
        "    ) -> (\n"
        "        list['Wire'] |\n"
        "        make().Decoy\n"
        "    ): ...\n"
        "def dynamic() -> choose('Decoy')['Other']: ...\n"
        "def callback() -> 'Fn[[Payload], Result]': ...\n"
    )
    with CodeMap(tmp_path) as cm:
        edges = assert_records(cm.relationships.deps("Record.convert")["edges"])
        assert {(r["kind"], r["target"], r["line"]) for r in edges} == {
            ("parameter-type", "Fn", 8),
            ("parameter-type", "Payload", 9),
            ("parameter-type", "Result", 10),
            ("parameter-type", "choose", 11),
            ("return-type", "list", 13),
            ("return-type", "Wire", 13),
        }
        (field,) = (
            r
            for r in assert_records(cm.relationships.deps("Record")["edges"])
            if r["source"] == "Record"
        )
        assert (field["kind"], field["target"], field["line"]) == (
            "attribute-type",
            "Payload",
            5,
        )
        assert _type_edges(cm, "dynamic") == set()
        quoted = assert_records(cm.relationships.deps("callback")["edges"])
        assert {(r["target"], r["line"]) for r in quoted} == {
            ("Fn", 17),
            ("Payload", 17),
            ("Result", 17),
        }


def _type_edges(codemap: CodeMap, query: str) -> set[tuple[object, object]]:
    return {
        (row["kind"], row["target"])
        for row in assert_records(codemap.relationships.deps(query)["edges"])
        if row["confidence"] == "annotation" and row["source"] == query
    }


def test_conditional_annotation_references_only_possible_result_arms(
    tmp_path: Path,
) -> None:
    (tmp_path / "api.py").write_text(
        "from __future__ import annotations\n"
        "def result() -> (Input if feature else Output): ...\n"
        "def fixed() -> (Decoy if False else Output): ...\n"
    )
    with CodeMap(tmp_path) as cm:
        assert _type_edges(cm, "result") == {
            ("return-type", "Input"),
            ("return-type", "Output"),
        }
        assert _type_edges(cm, "fixed") == {("return-type", "Output")}


@pytest.mark.parametrize(
    ("imports", "form"),
    [
        ("import typing as t", "t.Callable"),
        ("import collections.abc", "collections.abc.Callable"),
        ("from collections import abc", "abc.Callable"),
    ],
)
def test_callable_parameter_list_has_type_slots_but_an_ordinary_list_value_does_not(
    tmp_path: Path, imports: str, form: str
) -> None:
    (tmp_path / "api.py").write_text(
        f"from __future__ import annotations\n{imports}\n"
        f"def callback() -> {form}[[Input], Output]: ...\n"
        "def settings() -> Box[['Decoy']]: ...\n"
    )
    with CodeMap(tmp_path) as cm:
        assert _type_edges(cm, "callback") == {
            ("return-type", name) for name in (form, "Input", "Output")
        }
        assert _type_edges(cm, "settings") == {("return-type", "Box")}


def test_deps_emit_types_from_typing_argument_positions(tmp_path: Path) -> None:
    (tmp_path / "api.py").write_text(
        "import typing as t\n"
        "from typing_extensions import Annotated as A, Literal as L\n"
        "Decorated = t.Annotated\n"
        "class Payload: pass\n"
        "class Decoy: pass\n"
        "class Service:\n"
        '    mode: t.Literal["Decoy", Decoy.option]\n'
        "    def parse(self, value: L['Decoy']) -> A[list['Payload'], 'Decoy', Decoy.option]: ...\n"
        """    def forward(self) -> "Decorated[tuple['Payload', L['Decoy']], Decoy]": ...\n"""
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        assert _type_edges(codemap, "Service") == {("attribute-type", "t.Literal")}
        assert _type_edges(codemap, "Service.parse") == {
            ("parameter-type", "L"),
            ("return-type", "A"),
            ("return-type", "list"),
            ("return-type", "Payload"),
        }
        assert _type_edges(codemap, "Service.forward") == {
            ("return-type", target) for target in ("Decorated", "tuple", "Payload", "L")
        }


def test_annotation_form_identity_uses_the_source_scope(tmp_path: Path) -> None:
    (tmp_path / "api.py").write_text(
        "from typing import Annotated\n"
        "from .custom import Literal as CustomLiteral\n"
        "class Payload: pass\n"
        "class Model:\n"
        "    class Annotated: pass\n"
        "    def parse(self, value: CustomLiteral['Payload']) -> Annotated['Payload']: ...\n"
        "def outer(Annotated):\n"
        "    def inner() -> Annotated['Uncertain']: ...\n"
        "def original() -> Annotated['Payload', 'Decoy']: ...\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        assert _type_edges(codemap, "Model.parse") == {
            ("parameter-type", "CustomLiteral"),
            ("parameter-type", "Payload"),
            ("return-type", "Annotated"),
            ("return-type", "Payload"),
        }
        assert _type_edges(codemap, "outer.inner") == {("return-type", "Annotated")}
        assert _type_edges(codemap, "original") == {
            ("return-type", "Annotated"),
            ("return-type", "Payload"),
        }


def test_source_local_typing_spelling_stays_syntactic(tmp_path: Path) -> None:
    (tmp_path / "api.py").write_text(
        "import typing as t\n"
        "def read(value: t.Literal['Token']) -> t.Annotated['Payload', 'Tag']: ...\n"
    )
    (tmp_path / "typing.py").write_text(
        "Literal = custom_literal\nAnnotated = custom_metadata\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        assert _type_edges(codemap, "read") == {
            ("parameter-type", "t.Literal"),
            ("return-type", "t.Annotated"),
            ("return-type", "Payload"),
        }


def test_bound_binding_scope_cannot_promote_values_to_types(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(python_binding_scope, "MAX_BINDING_NODES", 5)
    (tmp_path / "api.py").write_text(
        "from typing import Literal as Mode, Annotated as Mark\n"
        "def bounded(flag: Mode['Decoy'], plain: list['Payload']) -> Mark['Payload', 'Tag']: ...\n"
    )
    with CodeMap(tmp_path, artifact_db=tmp_path / ".artifacts.sqlite3") as codemap:
        codemap.index.sync()
        assert _type_edges(codemap, "bounded") == {
            ("parameter-type", "Mode"),
            ("parameter-type", "list"),
            ("parameter-type", "Payload"),
            ("return-type", "Mark"),
        }
