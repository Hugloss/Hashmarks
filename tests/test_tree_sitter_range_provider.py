from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from hashmarks.codemap import CodeMap, providers
from hashmarks.codemap.parsers import artifact_key_for
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


@dataclass
class FakeTree:
    root_node: FakeNode


@dataclass
class FakeParser:
    root: FakeNode

    def parse(self, source: bytes) -> FakeTree:
        return FakeTree(self.root)


def test_native_binding_change_invalidates_range_artifact_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("tree_sitter_language_pack")
    versions = {
        "tree-sitter-language-pack": "grammar-fixture",
        "tree-sitter": "binding-before",
    }
    monkeypatch.setattr(providers.metadata, "version", lambda name: versions[name])
    before = TreeSitterRangeProvider.auto()
    versions["tree-sitter"] = "binding-after"
    after = TreeSitterRangeProvider.auto()
    assert before.available and after.available
    assert before.version == after.version
    assert artifact_key_for(
        "same-source", "typescript", range_provider=before
    ) != artifact_key_for(
        "same-source",
        "typescript",
        range_provider=after,
    )


@pytest.mark.parametrize("missing", ["tree-sitter-language-pack", "tree-sitter"])
def test_unqualified_native_versions_keep_range_enrichment_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
) -> None:
    pytest.importorskip("tree_sitter_language_pack")

    def version(name: str) -> str:
        if name == missing:
            raise providers.metadata.PackageNotFoundError(name)
        return "present"

    monkeypatch.setattr(providers.metadata, "version", version)
    provider = TreeSitterRangeProvider.auto()
    assert provider.available is False
    assert provider.signature("typescript") is None
    assert "metadata unavailable" in (provider.status().detail or "")


def test_reopen_refreshes_ranges_after_native_binding_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    language_pack = pytest.importorskip("tree_sitter_language_pack")
    source = "class Request {\n  value() {}\n}\n"
    identifier = FakeNode("type_identifier", position=(6, 13, 0, 0))
    declaration = FakeNode(
        "class_declaration",
        position=(0, len(source) - 1, 0, 0),
        children=(identifier,),
        fields={"name": identifier},
    )
    parser = FakeParser(FakeNode("program", children=(declaration,)))
    monkeypatch.setattr(language_pack, "get_parser", lambda name: parser)
    real_version = providers.metadata.version
    versions = {"tree-sitter-language-pack": "same-grammar", "tree-sitter": "before"}

    def version(name: str) -> str:
        return versions[name] if name in versions else real_version(name)

    monkeypatch.setattr(providers.metadata, "version", version)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "request.ts").write_text(source)
    with CodeMap(
        repo, state_dir=tmp_path / "state", artifact_db=tmp_path / "artifacts.db"
    ) as codemap:
        codemap.sync()
        before = codemap.outline("request.ts")
        symbols = before["symbols"]
        assert isinstance(symbols, list)
        assert symbols[0]["end_line"] == 1
    versions["tree-sitter"] = "after"
    declaration.end_point = (2, 0)
    with CodeMap(
        repo, state_dir=tmp_path / "state", artifact_db=tmp_path / "artifacts.db"
    ) as codemap:
        after = codemap.outline("request.ts")
        assert after["file_digest"] == before["file_digest"]
        symbols = after["symbols"]
        assert isinstance(symbols, list)
        assert symbols[0]["end_line"] == 3


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
            FakeNode("function_definition", children=(FakeNode("comment"), identifier))
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
    parser = FakeParser(root)
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
    parser = FakeParser(root)
    provider = TreeSitterRangeProvider(lambda language: parser)

    symbols = provider._collect(source, "javascript")
    assert len(symbols) == 1
    assert symbols[0].name == long_name
    assert symbols[0].signature.endswith("...")
    assert len(symbols[0].signature) == 400
    assert "\n" not in symbols[0].signature
