from __future__ import annotations

from hashmarks.cli import main
from hashmarks.codemap import CodeMap


def _package(root) -> None:
    (root / "pkg").mkdir()
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")


def test_cache_invalidation_resolves_local_alias_to_exact_owner(tmp_path):
    _package(tmp_path)
    (tmp_path / "pkg" / "state.py").write_text(
        "CACHE = {}\nALIAS = CACHE\n\ndef reset():\n    ALIAS.clear()\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        graph = codemap.cache_invalidation_ownership_graph()
    edge = next(e for e in graph["edges"] if e["relation"] == "invalidates-cache")
    assert graph["schema"] == "hashmarks.cache-invalidation-ownership.v1"
    assert edge["source"] == "invalidator:pkg/state.py:reset"
    assert edge["target"] == "cache:pkg/state.py:CACHE"
    assert edge["confidence"] == "local-owner"
    assert edge["method"] == "clear"
    assert edge["target"] not in graph["unresolved_cache_owners"]


def test_cache_invalidation_resolves_imported_symbol_alias(tmp_path):
    _package(tmp_path)
    (tmp_path / "pkg" / "state.py").write_text("CACHE = {}\n", encoding="utf-8")
    (tmp_path / "consumer.py").write_text(
        "from pkg.state import CACHE as STATE_CACHE\nLOCAL = STATE_CACHE\n\ndef invalidate():\n    LOCAL.clear()\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        graph = codemap.cache_invalidation_ownership_graph(["consumer.py"])
    edge = graph["edges"][0]
    assert edge["source"] == "invalidator:consumer.py:invalidate"
    assert edge["target"] == "cache:pkg/state.py:CACHE"
    assert edge["confidence"] == "qualified-symbol-import"


def test_cache_invalidation_resolves_module_alias_without_same_name_guess(tmp_path):
    _package(tmp_path)
    (tmp_path / "pkg" / "a.py").write_text("CACHE = {}\n", encoding="utf-8")
    (tmp_path / "pkg" / "b.py").write_text("CACHE = {}\n", encoding="utf-8")
    (tmp_path / "consumer.py").write_text(
        "import pkg.a as active_state\n\ndef reset():\n    active_state.CACHE.clear()\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        graph = codemap.cache_invalidation_ownership_graph(["consumer.py"])
    assert len(graph["edges"]) == 1
    edge = graph["edges"][0]
    assert edge["target"] == "cache:pkg/a.py:CACHE"
    assert edge["confidence"] == "qualified-module-import"
    assert "cache:pkg/b.py:CACHE" in graph["unresolved_cache_owners"]


def test_cache_invalidation_resolves_relative_import(tmp_path):
    _package(tmp_path)
    (tmp_path / "pkg" / "state.py").write_text("CACHE = {}\n", encoding="utf-8")
    (tmp_path / "pkg" / "consumer.py").write_text(
        "from .state import CACHE\n\ndef reset():\n    CACHE.clear()\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        graph = codemap.cache_invalidation_ownership_graph(["pkg/consumer.py"])
    assert graph["edges"][0]["target"] == "cache:pkg/state.py:CACHE"


def test_cache_invalidation_does_not_attach_unqualified_same_name(tmp_path):
    _package(tmp_path)
    (tmp_path / "pkg" / "state.py").write_text("CACHE = {}\n", encoding="utf-8")
    (tmp_path / "other.py").write_text(
        "def reset(CACHE):\n    CACHE.clear()\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        graph = codemap.cache_invalidation_ownership_graph(["other.py"])
    assert graph["edges"] == []
    assert graph["summary"]["owners_without_resolved_invalidator"] == 1


def test_cache_invalidation_resolves_decorator_cache_clear(tmp_path):
    _package(tmp_path)
    (tmp_path / "pkg" / "memo.py").write_text(
        "from functools import lru_cache\n\n@lru_cache(maxsize=8)\ndef value(x):\n    return x\n",
        encoding="utf-8",
    )
    (tmp_path / "maintenance.py").write_text(
        "from pkg.memo import value\n\ndef reset():\n    value.cache_clear()\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        graph = codemap.cache_invalidation_ownership_graph(["maintenance.py"])
    edge = graph["edges"][0]
    assert edge["target"] == "cache:pkg/memo.py:value"
    assert edge["method"] == "cache_clear"


def test_cli_cache_invalidation_ownership(tmp_path, capsys):
    _package(tmp_path)
    (tmp_path / "pkg" / "state.py").write_text(
        "CACHE = {}\n\ndef reset():\n    CACHE.clear()\n", encoding="utf-8"
    )
    assert main(["map", "sync", "--workspace", str(tmp_path)]) == 0
    capsys.readouterr()
    assert (
        main(["map", "cache-invalidation-ownership", "--workspace", str(tmp_path)]) == 0
    )
    out = capsys.readouterr().out
    assert '"schema": "hashmarks.cache-invalidation-ownership.v1"' in out
    assert '"relation": "invalidates-cache"' in out


def test_cache_invalidation_imported_symbol_shadowed_by_parameter_is_not_authority(
    tmp_path,
):
    _package(tmp_path)
    (tmp_path / "pkg" / "state.py").write_text("CACHE = {}\n", encoding="utf-8")
    (tmp_path / "consumer.py").write_text(
        "from pkg.state import CACHE\n\ndef reset(CACHE):\n    CACHE.clear()\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        graph = codemap.cache_invalidation_ownership_graph(["consumer.py"])
    assert graph["edges"] == []


def test_cache_invalidation_module_alias_shadowed_by_local_is_not_authority(tmp_path):
    _package(tmp_path)
    (tmp_path / "pkg" / "state.py").write_text("CACHE = {}\n", encoding="utf-8")
    (tmp_path / "consumer.py").write_text(
        "import pkg.state as state\n\ndef reset(other):\n    state = other\n    state.CACHE.clear()\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        graph = codemap.cache_invalidation_ownership_graph(["consumer.py"])
    assert graph["edges"] == []


def test_cache_invalidation_function_local_alias_to_import_remains_resolvable(tmp_path):
    _package(tmp_path)
    (tmp_path / "pkg" / "state.py").write_text("CACHE = {}\n", encoding="utf-8")
    (tmp_path / "consumer.py").write_text(
        "from pkg.state import CACHE\n\ndef reset():\n    local = CACHE\n    local.clear()\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        graph = codemap.cache_invalidation_ownership_graph(["consumer.py"])
    assert graph["edges"][0]["target"] == "cache:pkg/state.py:CACHE"
