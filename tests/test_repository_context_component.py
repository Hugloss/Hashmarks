"""Disclosure and cache ownership work without constructing the facade."""

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from test_repository_index_component import index as index
from test_repository_relationships_component import _relationships

from hashmarks.codemap.context_cache import ContextCache
from hashmarks.codemap.find_engine import RepositorySearch
from hashmarks.codemap.indexing_lifecycle import RepositoryIndex
from hashmarks.codemap.model import ContextDisclosure
from hashmarks.codemap.python_ast import estimate_tokens
from hashmarks.codemap.repository_context import RepositoryContext


@pytest.fixture
def context(index: RepositoryIndex) -> Iterator[RepositoryContext]:
    relationships = _relationships(index)
    search = RepositorySearch(relationships.native)
    cache = ContextCache(index.workspace.parent / "context-cache")
    try:
        yield RepositoryContext(relationships.source, search, relationships, cache)
    finally:
        cache.close()


def test_context_limits_python_orientation_and_keeps_full_explicit_source(
    context: RepositoryContext,
) -> None:
    opening = "def encode_record(value='"
    default = "A" * (511 - len(opening)) + "界" * 800
    definition = f"{opening}{default}'):\n    return value"
    (context.workspace / "codec.py").write_text(
        definition + "\n\ndef decode_record(value): return value\n", encoding="utf-8"
    )
    (context.workspace / "worker.py").write_text(
        "from codec import encode_record\ndef dispatch(value): return encode_record(value)\n"
    )
    context.source.index.sync()
    bounded = context.build(
        "encode_record", token_budget=128, disclosure=ContextDisclosure.OUTLINE
    )
    item = next(item for item in bounded.items if item.symbol == "encode_record")
    assert item.path == "codec.py" and item.representation == "signature-preview"
    assert item.content == definition.encode()[:512].decode("utf-8", errors="ignore")
    assert item.estimated_tokens == estimate_tokens(item.content)
    assert (
        bounded.estimated_tokens
        == sum(i.estimated_tokens for i in bounded.items)
        <= 128
    )
    warm = context.build(
        "encode_record", token_budget=128, disclosure=ContextDisclosure.OUTLINE
    )
    assert warm.cache_hit and warm.items == bounded.items
    evidence = context.build("dispatch", disclosure=ContextDisclosure.EVIDENCE)
    dependency = next(i for i in evidence.items if i.symbol == "encode_record")
    assert (dependency.path, dependency.representation, dependency.content) == (
        item.path,
        item.representation,
        item.content,
    )
    assert (
        next(i for i in evidence.items if i.symbol == "dispatch").representation
        == "signature"
    )
    file_pack = context.build("codec.py")
    outline = next(
        i
        for i in file_pack.items
        if i.path == "codec.py" and i.representation == "outline"
    )
    assert (
        f"encode_record [signature preview] {item.content}…  [1-2]" in outline.content
    )
    assert (
        "def decode_record(value)" in outline.content
        and "/symbols/" not in outline.content
    )
    assert outline.estimated_tokens == estimate_tokens(outline.content)
    full = context.build("encode_record", disclosure=ContextDisclosure.SOURCE)
    source = next(i for i in full.items if i.symbol == "encode_record")
    assert source.representation == "source-range" and source.content == definition


@pytest.mark.parametrize("source_bytes", [480, 511])
def test_source_replaces_preview_when_normalized_signature_costs_as_much_as_body(
    context: RepositoryContext, source_bytes: int
) -> None:
    # ast.unparse inserts spaces after argument commas, unlike the authored definition.
    arguments = ",".join(f"a{i}" for i in range(108))
    definition = f"def format_record({arguments}): return a0 #".ljust(source_bytes, "x")
    (context.workspace / "codec.py").write_text(definition + "\n")
    outline = context.build(
        "format_record", disclosure=ContextDisclosure.OUTLINE, token_budget=128
    )
    preview = next(item for item in outline.items if item.symbol == "format_record")
    assert (
        preview.representation == "signature-preview"
        and preview.estimated_tokens == 128
    )
    packet = context.build(
        "format_record", disclosure=ContextDisclosure.SOURCE, token_budget=128
    )
    item = next(item for item in packet.items if item.symbol == "format_record")
    assert item.representation == "source-range" and item.content == definition
    assert (
        packet.estimated_tokens
        == item.estimated_tokens
        == estimate_tokens(definition)
        <= 128
    )


def test_standalone_context_preserves_unknown_identity_and_reobserves_source(
    context: RepositoryContext,
) -> None:
    path = context.workspace / "owner.py"
    path.write_text("def owner():\n    return 'original'\n")
    context.source.index.sync()
    first = context.build("owner", disclosure=ContextDisclosure.SOURCE)
    assert first.items
    assert first.identity_generation is None
    assert first.stale is None
    assert first.cache_hit is False
    assert any("original" in item.content for item in first.items)

    path.write_text("def owner():\n    return 'replacement'\n")
    context.source.index.sync()
    second = context.build("owner", disclosure=ContextDisclosure.SOURCE)
    assert second.generation > first.generation
    assert any("replacement" in item.content for item in second.items)
    assert all("original" not in item.content for item in second.items)


def test_standalone_context_uses_search_only_to_nominate_instruction_paths(
    context: RepositoryContext,
) -> None:
    (context.workspace / "AGENTS.md").write_text("repository instructions\n")
    (context.workspace / "owner.py").write_text("def owner(): return 1\n")
    context.source.index.sync()
    packet = context.instruction_scope("owner.py")
    assert packet["seed_paths"] == ["owner.py"]
    assert packet["ranking_effect"] == "none"
    assert context.task("owner").items


def test_context_import_does_not_load_facade_or_task_authority() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from hashmarks.codemap.repository_context import RepositoryContext; assert 'hashmarks.codemap.engine' not in sys.modules; assert 'hashmarks.codemap.ownership_graph' not in sys.modules; assert 'hashmarks.codemap.evidence_packet' not in sys.modules",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_failed_context_releases_flight_and_read_scope_before_retry(
    context: RepositoryContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (context.workspace / "owner.py").write_text("def owner(): return 1\n")
    context.source.index.sync()

    def unavailable(*args: object, **kwargs: object) -> None:
        raise RuntimeError("context producer unavailable")

    with monkeypatch.context() as failure:
        failure.setattr(context, "_context_impl", unavailable)
        with pytest.raises(RuntimeError, match="context producer unavailable"):
            context.build("owner", disclosure=ContextDisclosure.OUTLINE)
    assert context._context_flight.in_flight() == 0
    assert context.reads.depth == 0
    assert context.build("owner", disclosure=ContextDisclosure.OUTLINE).items


def test_root_has_no_retired_context_methods() -> None:
    from hashmarks.codemap import CodeMap

    for name in (
        "context",
        "orient",
        "task_context",
        "task_context_plan",
        "work_context",
        "work_context_budget_sweep",
        "repository_instruction_scope",
        "_work_context_anchor",
    ):
        assert not callable(getattr(CodeMap, name, None))
