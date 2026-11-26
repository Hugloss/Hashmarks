from pathlib import Path

import pytest
from contract_assertions import assert_records

from hashmarks.codemap import CodeMap, python_binding_scope


def _type_edges(codemap: CodeMap, query: str) -> set[tuple[object, object]]:
    return {
        (row["kind"], row["target"])
        for row in assert_records(codemap.relationships.deps(query)["edges"])
        if row["confidence"] == "annotation" and row["source"] == query
    }


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
