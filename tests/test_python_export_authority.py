import ast

import pytest

from hashmarks.codemap.python_exports import (
    python_export_binding,
    python_export_bindings,
    python_export_is_declaration,
    static_string_names,
)


def _value(source: str) -> ast.expr:
    node = ast.parse(source).body[0]
    assert isinstance(node, ast.Assign)
    return node.value


def test_static_string_names_accepts_literal_collections() -> None:
    assert static_string_names(_value("names = ['Public', 'Other']")) == [
        "Public",
        "Other",
    ]
    assert static_string_names(_value("names = ('Public',)")) == ["Public"]
    assert static_string_names(_value("names = {'Public'}")) == ["Public"]


def test_static_string_names_rejects_runtime_or_mixed_values() -> None:
    assert static_string_names(_value("names = exported_names")) is None
    assert static_string_names(_value("names = ['Public', dynamic_name]")) is None
    assert static_string_names(None) is None


@pytest.mark.parametrize(
    ("source", "kind", "targets", "declared"),
    [
        ("def Public(): pass", "local", [], True),
        ("class Public: pass", "local", [], True),
        ("def other():\n    Public = 1", "unknown", [], False),
        ("def other(value=(Public := 1)): pass", "ambiguous", [], False),
        ("other = lambda: (Public := 1)", "unknown", [], False),
        ("other = lambda value=(Public := 1): value", "ambiguous", [], False),
        ("other = [Public for Public in items]", "unknown", [], False),
        (
            "other = [item for item in items if (Public := item)]",
            "ambiguous",
            [],
            False,
        ),
        ("class Other(metaclass=(Public := factory)): pass", "ambiguous", [], False),
        (
            "from .first import Public\nfrom .second import Public",
            "ambiguous",
            [".first.Public", ".second.Public"],
            False,
        ),
        ("if TYPE_CHECKING:\n    from .first import Public", "ambiguous", [], False),
        ("try:\n    call()\nexcept Error as Public:\n    pass", "ambiguous", [], False),
        (
            "match value:\n    case {'key': item, **Public}: pass",
            "ambiguous",
            [],
            False,
        ),
        ("def Public(): pass\nPublic: object", "local", [], True),
        ("def Public(): pass\nPublic: object = 1", "local", [], False),
        (
            "class Public: pass\nfrom .impl import Internal as Public",
            "reexport",
            [".impl.Internal"],
            False,
        ),
        ("from .impl import *", "star", [".impl.Public"], False),
    ],
)
def test_snapshot_binding_artifact_preserves_scope_and_order(
    source: str,
    kind: str,
    targets: list[str],
    declared: bool,
) -> None:
    tree = ast.parse(source)
    indexed = python_export_bindings("/repo/module.py", (1, 2, 3, 4, 5), tree)
    observed = indexed.binding("Public")
    assert (observed.kind, list(observed.targets)) == (kind, targets)
    assert (observed.declaration is not None) is declared
    assert python_export_binding(tree, "Public") == (kind, targets)
    assert python_export_is_declaration(tree, "Public") is declared


def test_source_only_binding_observes_mutated_input_and_new_snapshot() -> None:
    tree = ast.parse("class Public: pass")
    assert python_export_is_declaration(tree, "Public") is True
    declaration = tree.body[0]
    assert isinstance(declaration, ast.ClassDef)
    declaration.name = "Other"
    assert python_export_binding(tree, "Public") == ("unknown", [])
    first = python_export_bindings(
        "/repo/module.py", (1, 2, 3, 4, 5), ast.parse("from .left import Public")
    )
    second = python_export_bindings(
        "/repo/module.py", (1, 2, 3, 4, 5), ast.parse("from .right import Public")
    )
    assert first.binding("Public").targets == (".left.Public",)
    assert second.binding("Public").targets == (".right.Public",)
