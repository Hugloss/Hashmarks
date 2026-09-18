import ast

from hashmarks.codemap.python_exports import static_string_names


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
