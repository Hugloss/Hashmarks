from __future__ import annotations

from types import SimpleNamespace

from hashmarks.codemap.providers import TreeSitterRangeProvider


class FakeNode:
    def __init__(
        self,
        node_type: str,
        *,
        position: tuple[int, int, int, int] = (0, 0, 0, 0),
        children: tuple[FakeNode, ...] = (),
        fields: dict[str, FakeNode] | None = None,
        broken_field: str | None = None,
    ) -> None:
        start, end, start_line, end_line = position
        self.type = node_type
        self.start_byte = start
        self.end_byte = end
        self.start_point = (start_line, 0)
        self.end_point = (end_line, 0)
        self.children = children
        self.named_children = children
        self.fields = fields or {}
        self.broken_field = broken_field

    def child_by_field_name(self, field: str) -> FakeNode | None:
        if field == self.broken_field:
            raise ValueError("broken field")
        return self.fields.get(field)


def test_range_provider_name_lookup_handles_declarators_and_fallback() -> None:
    identifier = FakeNode("identifier")
    wrapper = FakeNode("declarator", children=(identifier,))
    direct = FakeNode("class_definition", fields={"name": identifier})
    nested = FakeNode(
        "function_definition",
        fields={"declarator": wrapper},
        broken_field="name",
    )
    fallback = FakeNode("function_definition", children=(identifier,))
    assert TreeSitterRangeProvider._name_node(direct) is identifier
    assert TreeSitterRangeProvider._name_node(nested) is identifier
    assert TreeSitterRangeProvider._name_node(fallback) is identifier
    assert TreeSitterRangeProvider._name_node(FakeNode("unknown")) is None
    assert (
        TreeSitterRangeProvider._name_node(
            SimpleNamespace(children=(FakeNode("comment"), identifier))
        )
        is identifier
    )


def test_range_provider_collects_nested_symbols_from_one_parser_tree() -> None:
    source = "class Alpha {\n  function work() {}\n}\n"
    alpha_start = source.index("Alpha")
    work_start = source.index("work")
    method_start = source.index("function")
    method_end = source.index("}", method_start) + 1
    alpha = FakeNode("identifier", position=(alpha_start, alpha_start + 5, 0, 0))
    work = FakeNode("identifier", position=(work_start, work_start + 4, 0, 0))
    method = FakeNode(
        "method_definition",
        position=(method_start, method_end, 1, 1),
        children=(work,),
        fields={"name": work},
    )
    klass = FakeNode(
        "class_definition",
        position=(0, len(source) - 1, 0, 2),
        children=(alpha, method),
        fields={"name": alpha},
    )
    root = FakeNode("module", children=(klass,))
    parser = SimpleNamespace(parse=lambda data: SimpleNamespace(root_node=root))
    provider = TreeSitterRangeProvider(lambda language: parser, version="fixture")

    symbols = provider._collect(source, "javascript")
    assert [
        (symbol.qualname, symbol.kind, symbol.start_line, symbol.end_line)
        for symbol in symbols
    ] == [
        ("Alpha", "class", 1, 3),
        ("Alpha.work", "method", 2, 2),
    ]
    assert symbols[0].signature == "class Alpha"
    assert symbols[1].signature == "function work()"


def test_range_provider_ignores_unnamed_nodes_and_bounds_long_headers() -> None:
    long_name = "symbol" + "x" * 405
    source = f"function {long_name}(\n  value\n) {{}}\n"
    name_start = source.index(long_name)
    identifier = FakeNode(
        "identifier", position=(name_start, name_start + len(long_name), 0, 0)
    )
    unnamed = FakeNode("class_definition")
    blank = FakeNode(
        "function_definition",
        fields={"name": FakeNode("identifier", position=(0, 0, 0, 0))},
    )
    function = FakeNode(
        "function_definition",
        position=(0, len(source) - 1, 0, 2),
        fields={"name": identifier},
    )
    root = FakeNode("module", children=(unnamed, blank, function))
    parser = SimpleNamespace(parse=lambda data: SimpleNamespace(root_node=root))
    provider = TreeSitterRangeProvider(lambda language: parser)

    symbols = provider._collect(source, "javascript")
    assert len(symbols) == 1
    assert symbols[0].name == long_name
    assert symbols[0].signature.endswith("...")
    assert len(symbols[0].signature) == 400
    assert "\n" not in symbols[0].signature
