from pathlib import Path

import pytest
from contract_assertions import assert_records, assert_text

from hashmarks import CodeMap
from hashmarks.codemap.python_ast import estimate_tokens


def test_python_outline_discloses_long_signature_once_with_its_exact_occurrence(
    tmp_path: Path,
) -> None:
    default = "界" * 1000
    (tmp_path / "codec.py").write_text(
        "class Codec:\n"
        "    def encode(self, value: str): ...\n"
        f"    def encode(self, value='{default}'):\n        return value\n"
    )
    (tmp_path / "small.py").write_text("def short(value): return value\n")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        packet = codemap.source.outline("codec.py")
        rows = assert_records(packet["symbols"])
        assert [row["qualname"] for row in rows] == [
            "Codec",
            "Codec.encode",
            "Codec.encode@L3",
        ]
        assert rows[1]["signature"] == "def encode(self, value: str): ..."
        truncated = rows[2]
        preview = assert_text(truncated["signature_preview"])
        assert (
            truncated["signature_truncated"] is True and truncated["signature"] is None
        )
        assert 0 < len(preview.encode()) <= 512
        assert packet["outline_signature_previews"] == 1
        outline = assert_text(packet["outline"])
        assert preview not in outline and "/symbols/2/signature_preview" in outline
        assert assert_text(rows[1]["signature"]) in outline
        assert packet["outline_tokens"] == estimate_tokens(outline)
        assert packet["full_tokens"] == estimate_tokens(
            (tmp_path / "codec.py").read_text()
        )
        indexed = codemap.store.symbol_at("codec.py", "Codec.encode@L3")
        assert indexed is not None
        assert default in assert_text(indexed["signature"])
        assert truncated["signature_tokens"] == estimate_tokens(
            assert_text(indexed["signature"])
        )
        body = codemap.source.read(f"{truncated['path']}::{truncated['qualname']}")
        assert body["lines"] == [3, 4] and default in assert_text(body["content"])
        small = codemap.source.outline("small.py")
    assert small["outline"] == "def short(value)  [1-1]"
    assert "outline_signature_previews" not in small
    assert "signature_truncated" not in assert_records(small["symbols"])[0]


def test_python_signature_previews_bound_source_and_exact_lookup(
    tmp_path: Path,
) -> None:
    default = "界" * 3000
    (tmp_path / "codec.py").write_text(
        f"def encode_record(value='{default}'):\n    return value\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        source = codemap.source.read("codec.py::encode_record", token_budget=16)
        hit = assert_records(
            codemap.search.packet("encode_record", limit=1)["results"]
        )[0]
        full = codemap.source.read("codec.py::encode_record", token_budget=4000)
    assert source["too_large"] and "content" not in source
    for row, bound in ((source, 64), (hit, 512)):
        assert row["signature"] is None and row["signature_truncated"] is True
        preview = assert_text(row["signature_preview"])
        assert 0 < len(preview.encode()) <= bound
        assert assert_text(full["content"]).startswith(preview)
        assert row["lines"] == [1, 2]
    assert default in assert_text(full["content"])


def test_overload_occurrences_remain_addressable_and_show_stub_syntax(
    tmp_path: Path,
) -> None:
    (tmp_path / "codec.py").write_text(
        "from typing import overload\n"
        "class Codec:\n"
        "    @overload\n"
        "    def f(self, value: str) -> str: ...\n"
        "    @overload\n"
        "    def f(self, value: int) -> int: ...\n"
        "    def f(self, value):\n        return value\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        lookup = codemap.search.packet("Codec.f")
        source = codemap.source.read("codec.py::Codec.f")
        matches = assert_records(source["matches"])
        assert not source["matches_truncated"]
        assert source["lines"] == [4, 4]
        assert [row["lines"] for row in matches] == [[4, 4], [6, 6], [7, 8]]
        assert [assert_text(row["signature"]).endswith(": ...") for row in matches] == [
            True,
            True,
            False,
        ]
        assert lookup["observed_exact_match_count"] == 3
        assert lookup["uniqueness_evidence"] == "not-applicable"
        assert codemap.source.read("Codec.f")["ambiguous"] is True
        body = codemap.source.read(assert_text(matches[-1]["symbol_id"]))
        assert body["lines"] == [7, 8] and "return value" in assert_text(
            body["content"]
        )
        assert "matches" not in body


def test_repeated_declaration_preview_reports_omissions(tmp_path: Path) -> None:
    (tmp_path / "codec.pyi").write_text("def encode_record(): ...\n" * 22)
    with CodeMap(tmp_path) as codemap:
        source = codemap.source.read("codec.pyi::encode_record", token_budget=16)
        assert source["matches_truncated"] is True
        choices = assert_records(source["matches"])
        assert len(choices) == 20
        assert (
            sum(
                len(assert_text(choice["signature_preview"]).encode())
                for choice in [source, *choices]
            )
            <= 64
        )
        assert codemap.source.read("codec.pyi::encode_record@L22")["lines"] == [22, 22]


@pytest.mark.parametrize("budget", [16, 32, 128])
def test_qualified_source_signature_budget_includes_primary_and_choices(
    tmp_path: Path, budget: int
) -> None:
    names = ["界" * 600 + str(index) for index in range(4)]
    (tmp_path / "codec.pyi").write_text(
        "".join(f"def encode(x='{value}'): ...\n" for value in names)
    )
    with CodeMap(tmp_path) as repository:
        source = repository.source.read("codec.pyi::encode", token_budget=budget)
        broad = repository.source.read("codec.pyi::encode", token_budget=4000)
    assert source["too_large"] is True and "content" not in source
    assert broad["too_large"] is False and names[0] in assert_text(broad["content"])
    matches = assert_records(source["matches"])
    broad_matches = assert_records(broad["matches"])
    assert len(matches) == 4 and source["matches_truncated"] is False
    assert source["symbol_id"] == matches[0]["symbol_id"]
    sizes = []
    for row, reference in zip([source, *matches], [broad, *broad_matches], strict=True):
        assert (row["symbol_id"], row["lines"]) == (
            reference["symbol_id"],
            reference["lines"],
        )
        assert row["signature"] is None and row["signature_truncated"] is True
        preview = assert_text(row["signature_preview"])
        assert preview and assert_text(reference["signature_preview"]).startswith(
            preview
        )
        sizes.append(len(preview.encode()))
    assert sum(sizes) <= 4 * budget
    assert sizes[0] >= sizes[1]


def test_qualified_source_keeps_exact_signatures_that_fit_together(
    tmp_path: Path,
) -> None:
    (tmp_path / "codec.py").write_text(
        "def encode(data: EncodingParameterDefinition): ...\ndef encode(): ...\n"
    )
    with CodeMap(tmp_path) as repository:
        result = repository.source.read("codec.py::encode", token_budget=32)
    rows = [result, *assert_records(result["matches"])]
    assert [row["signature"] for row in rows] == [
        "def encode(data: EncodingParameterDefinition): ...",
        "def encode(data: EncodingParameterDefinition): ...",
        "def encode(): ...",
    ]
    assert all("signature_truncated" not in row for row in rows)


def test_symbol_metadata_and_dependency_candidates_bound_overload_signatures(
    tmp_path: Path,
) -> None:
    choices = ", ".join(repr(f"field_{i:04}") for i in range(512))
    (tmp_path / "codec.py").write_text(
        "from typing import overload, Literal\nclass Codec:\n"
        "    @overload\n"
        f"    def encode(self, value: Literal[{choices}]) -> bytes: ...\n"
        "    def encode(self, value): return str(value).encode()\n"
        "def driver(codec): return codec.encode('field_0002')\n"
    )
    with CodeMap(tmp_path) as codemap:
        result = codemap.source.symbol("Codec.encode")
        assert not result["matches_truncated"]
        matches = assert_records(result["matches"])
        assert [row["qualname"] for row in matches] == [
            "Codec.encode",
            "Codec.encode@L5",
        ]
        assert matches[1]["signature"] == "def encode(self, value)"
        calls = [
            row
            for row in assert_records(
                codemap.relationships.deps("Codec.encode")["edges"]
            )
            if row["kind"] == "call"
        ]
        assert calls and all(row["source"] == matches[1]["qualname"] for row in calls)
        candidates = assert_records(
            assert_records(codemap.relationships.deps("driver")["edges"])[0][
                "resolved_symbols"
            ]
        )
        for row in (matches[0], candidates[0]):
            assert row["signature"] is None and row["signature_truncated"] is True
            assert len(assert_text(row["signature_preview"]).encode()) <= 512
        assert "field_0511" in assert_text(
            codemap.source.read("codec.py::Codec.encode", token_budget=4000)["content"]
        )


def test_denied_python_names_do_not_consume_visible_lookup_or_relationship_slots(
    tmp_path: Path,
) -> None:
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern="a_hidden.py"\nvisibility="deny"\n'
    )
    (tmp_path / "a_hidden.py").write_text(
        "def secret(): pass\n"
        + "def helper(): pass\n" * 9
        + "def target(): helper(); helper()\n" * 51
    )
    (tmp_path / "z_visible.py").write_text(
        "def helper(): pass\ndef target(): helper()\n"
    )
    with CodeMap(tmp_path) as codemap:
        symbols = codemap.source.symbol("target")
        assert not symbols["matches_truncated"]
        assert [row["path"] for row in assert_records(symbols["matches"])] == [
            "z_visible.py"
        ]
        dep = codemap.relationships.deps("target")
        assert not dep["matches_truncated"]
        (edge,) = assert_records(dep["edges"])
        (helper,) = assert_records(edge["resolved_symbols"])
        assert (edge["path"], helper["path"]) == ("z_visible.py", "z_visible.py")
        refs = codemap.relationships.refs("helper")
        assert not refs["references_truncated"]
        (only,) = assert_records(refs["references"])
        assert only["path"] == "z_visible.py"
        for denied in ("a_hidden.py", "secret"):
            with pytest.raises(PermissionError):
                codemap.relationships.deps(denied)
        with pytest.raises(PermissionError):
            codemap.source.symbol("secret")
        with pytest.raises(KeyError):
            codemap.source.symbol("missing")


@pytest.mark.parametrize("count", [50, 51])
def test_symbol_and_dependency_limits_count_visible_occurrences(
    tmp_path: Path, count: int
) -> None:
    (tmp_path / "scope.py").write_text(
        "def helper(): pass\n" * 9 + "def target(): helper(); helper()\n" * count
    )
    with CodeMap(tmp_path) as codemap:
        symbol = codemap.source.symbol("target")
        deps = codemap.relationships.deps("target")
        refs = codemap.relationships.refs("helper")
    assert len(assert_records(symbol["matches"])) == 50
    assert len(assert_records(refs["references"])) == 100
    assert (
        refs["references_truncated"]
        == symbol["matches_truncated"]
        == deps["matches_truncated"]
        == (count > 50)
    )
    edge = assert_records(deps["edges"])[0]
    assert edge["resolved_symbols_truncated"] is True
    assert len(assert_records(edge["resolved_symbols"])) == 8
