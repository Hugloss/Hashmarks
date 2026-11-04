"""Unresolved authored names retain provenance without runtime identity."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from hashmarks import CodeMap
from hashmarks.codemap.python_bindings import python_bindings
from hashmarks.python_ast_cache import parse_python_ast


def _rows(source: str) -> list[dict[str, object]]:
    raw = source.encode()
    return python_bindings(parse_python_ast(raw), raw, 1_000)[0]


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _call(rows: list[dict[str, object]], spelling: str) -> dict[str, object]:
    return next(
        row
        for row in rows
        if row["kind"] == "call-site"
        and _mapping(row["expression"])["text"] == spelling
    )


@pytest.mark.parametrize("origin", ["unprovided_loader", "__import__"])
def test_unresolved_alias_origin_is_independent_of_runtime_target(origin: str) -> None:
    source = f'alias = {origin}\nforwarded = alias\nforwarded("pkg")\n'
    call = _call(_rows(source), "forwarded")
    assert call["target"] is None
    assert call["qualification"] == "unknown"
    assert call["reasons"] == ["unresolved-lexical-name"]
    assert call["runtime_target"] == "not-established"
    symbolic = _mapping(call["symbolic_reference"])
    assert symbolic["qualification"] == "qualified"
    assert symbolic["runtime_identity"] == "not-established"
    assert symbolic["conditions"] == []
    assert symbolic["properties"] == []
    root = _mapping(symbolic["root"])
    assert root["kind"] == "unresolved-name"
    assert root["name"] == origin
    assert _mapping(root["scope"])["kind"] == "module"
    span = _mapping(root["range"])
    assert (
        source.encode()[
            cast(int, span["start_byte"]) : cast(int, span["end_byte"])
        ].decode()
        == origin
    )
    assert len(cast(list[object], symbolic["supporting_ranges"])) >= 3


def test_parameter_shadow_is_not_rewritten_as_an_unresolved_outer_name() -> None:
    call = _call(
        _rows('def invoke(__import__):\n    alias = __import__\n    alias("pkg")\n'),
        "alias",
    )
    assert call["target"] is None
    symbolic = _mapping(call["symbolic_reference"])
    assert _mapping(symbolic["root"])["kind"] == "parameter"
    assert _mapping(_mapping(symbolic["root"])["scope"])["name"] == "invoke"


@pytest.mark.parametrize(
    "source",
    [
        'alias = __import__\n__import__ = replacement\nalias("pkg")\n',
        'from somewhere import *\nalias = __import__\nalias("pkg")\n',
        'alias = __import__\nif condition:\n    alias = replacement\nalias("pkg")\n',
        'locals()["__import__"] = replacement\nalias = __import__\nalias("pkg")\n',
    ],
)
def test_unqualified_namespace_or_binding_cannot_claim_unique_alias_origin(
    source: str,
) -> None:
    call = _call(_rows(source), "alias")
    assert call["qualification"] == "unknown"
    assert call["target"] is None
    assert call["symbolic_reference"] is None


def test_unresolved_defaults_and_helper_inputs_remain_separate_conditions() -> None:
    rows = _rows(
        'def invoke(factory=__import__):\n    factory("pkg")\ninvoke(__import__)\n'
    )
    factory_call = _call(rows, "factory")
    assert factory_call["qualification"] == "unknown"
    assert factory_call["target"] is None
    assert (
        _mapping(_mapping(factory_call["symbolic_reference"])["root"])["kind"]
        == "parameter"
    )
    relations = {
        str(row["kind"]): row
        for row in rows
        if row["kind"] in {"default-binding", "argument-binding"}
    }
    assert set(relations) == {"default-binding", "argument-binding"}
    for row in relations.values():
        assert row["qualification"] == "unknown"
        assert row["target"] is None
        assert row["runtime_target"] == "not-established"
        symbolic = _mapping(row["symbolic_reference"])
        assert symbolic["qualification"] == "conditional"
        assert _mapping(symbolic["root"])["kind"] == "unresolved-name"
        assert _mapping(symbolic["root"])["name"] == "__import__"
    assert relations["default-binding"]["conditions"] == ["default-is-used"]
    assert "external-callers-not-observed" in cast(
        list[str], relations["argument-binding"]["conditions"]
    )


def test_public_observation_binds_unresolved_origin_to_exact_member(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.py"
    source.write_text('alias = __import__\nalias("pkg")\n')
    with CodeMap(tmp_path, state_dir=tmp_path / "state") as native:
        packet = native.source.bindings("source.py")
        assert packet["availability"] == "observed"
        call = _call(cast(list[dict[str, object]], packet["facts"]), "alias")
        assert (
            _mapping(_mapping(call["symbolic_reference"])["root"])["kind"]
            == "unresolved-name"
        )
        assert call["evidence_identity"]
        assert _mapping(packet["member"])["member_revision"]
        assert packet["observation_identity"]
        assert packet["negative_evidence"] == "not-admissible"
        assert _mapping(packet["semantic_coverage"])["state"] == "incomplete"
