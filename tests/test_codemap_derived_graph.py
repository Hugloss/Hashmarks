from __future__ import annotations

from typing import TYPE_CHECKING

from hashmarks.codemap import CodeMap

if TYPE_CHECKING:
    from pathlib import Path


def test_sync_persists_dependency_tracked_derived_surfaces(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    ws = tmp_path / "repo"
    ws.mkdir()
    (ws / "service.py").write_text("def public(x: int) -> int:\n    return x + 1\n")
    with CodeMap(ws) as codemap:
        result = codemap.sync()
        graph = codemap.derived_graph("service.py")
    assert result.indexed == 1
    nodes = {row["kind"]: row for row in graph["nodes"]}
    assert set(nodes) == {
        "content",
        "symbol_surface",
        "relationship_surface",
        "outline_surface",
        "lexical_surface",
    }
    assert nodes["symbol_surface"]["dependencies"] == ["service.py::content"]
    assert nodes["outline_surface"]["dependencies"] == ["service.py::symbol_surface"]
    assert all(row["identity"].startswith("sha256:") for row in nodes.values())


def test_body_only_change_can_preserve_symbol_surface_identity(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    ws = tmp_path / "repo"
    ws.mkdir()
    source = ws / "service.py"
    source.write_text("def public(x: int) -> int:\n    return x + 1\n")
    with CodeMap(ws) as codemap:
        codemap.sync()
        before = {x["kind"]: x for x in codemap.derived_graph("service.py")["nodes"]}
        source.write_text("def public(x: int) -> int:\n    y = x + 1\n    return y\n")
        codemap.sync(["service.py"])
        after = {x["kind"]: x for x in codemap.derived_graph("service.py")["nodes"]}
    assert before["content"]["identity"] != after["content"]["identity"]
    assert before["symbol_surface"]["identity"] == after["symbol_surface"]["identity"]
    assert (
        before["symbol_surface"]["input_identities"]
        != after["symbol_surface"]["input_identities"]
    )


def test_signature_change_changes_symbol_and_outline_surfaces(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    ws = tmp_path / "repo"
    ws.mkdir()
    source = ws / "service.py"
    source.write_text("def public(x: int) -> int:\n    return x\n")
    with CodeMap(ws) as codemap:
        codemap.sync()
        before = {x["kind"]: x for x in codemap.derived_graph("service.py")["nodes"]}
        source.write_text("def public(x: str) -> str:\n    return x\n")
        codemap.sync(["service.py"])
        after = {x["kind"]: x for x in codemap.derived_graph("service.py")["nodes"]}
    assert before["symbol_surface"]["identity"] != after["symbol_surface"]["identity"]
    assert before["outline_surface"]["identity"] != after["outline_surface"]["identity"]


def test_deleted_file_removes_derived_nodes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    ws = tmp_path / "repo"
    ws.mkdir()
    source = ws / "service.py"
    source.write_text("x = 1\n")
    with CodeMap(ws) as codemap:
        codemap.sync()
        assert codemap.derived_graph("service.py")["nodes"]
        source.unlink()
        codemap.sync(["service.py"])
        assert codemap.derived_graph("service.py")["nodes"] == []


def test_body_only_change_reports_semantic_invalidation_shields(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    ws = tmp_path / "repo"
    ws.mkdir()
    source = ws / "service.py"
    source.write_text("def public(x: int) -> int:\n    return x + 1\n")
    with CodeMap(ws) as codemap:
        codemap.sync()
        source.write_text("def public(x: int) -> int:\n    y = x + 1\n    return y\n")
        result = codemap.sync(["service.py"])
    assert result.semantic_invalidation_shields >= 1
    assert result.derived_surfaces_preserved >= result.semantic_invalidation_shields
    assert result.derived_surfaces_changed >= 1


def test_signature_change_does_not_shield_symbol_surface(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    ws = tmp_path / "repo"
    ws.mkdir()
    source = ws / "service.py"
    source.write_text("def public(x: int) -> int:\n    return x\n")
    with CodeMap(ws) as codemap:
        codemap.sync()
        source.write_text("def public(x: str) -> str:\n    return x\n")
        result = codemap.sync(["service.py"])
        nodes = {x["kind"]: x for x in codemap.derived_graph("service.py")["nodes"]}
    assert result.derived_surfaces_changed >= 2
    # content and symbol surface changed; any shield applies only to unrelated unchanged surfaces.
    assert nodes["symbol_surface"]["input_identities"]


def test_shielding_never_skips_line_level_storage_refresh(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    ws = tmp_path / "repo"
    ws.mkdir()
    source = ws / "service.py"
    source.write_text("def first():\n    return 1\n\ndef second():\n    return 2\n")
    with CodeMap(ws) as codemap:
        codemap.sync()
        before = {s["name"]: s for s in codemap.store.symbols_for_path("service.py")}
        source.write_text(
            "# inserted line\ndef first():\n    return 1\n\ndef second():\n    return 2\n"
        )
        result = codemap.sync(["service.py"])
        after = {s["name"]: s for s in codemap.store.symbols_for_path("service.py")}
    assert result.semantic_invalidation_shields >= 1
    assert before["first"]["start_line"] != after["first"]["start_line"]
    assert after["first"]["start_line"] == 2


def test_change_impact_projects_reachable_files_into_repository_surfaces(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    ws = tmp_path / "repo"
    ws.mkdir()
    (ws / "src").mkdir()
    (ws / "tests").mkdir()
    (ws / "docs").mkdir()
    (ws / "core.py").write_text("def value():\n    return 1\n")
    (ws / "api.py").write_text(
        "from core import value\ndef public():\n    return value()\n"
    )
    (ws / "tests" / "test_api.py").write_text(
        "from api import public\ndef test_public():\n    assert public() == 1\n"
    )
    with CodeMap(ws) as codemap:
        codemap.sync()
        impact = codemap.change_impact("core.py")
    impl = {row["path"] for row in impact["surfaces"]["implementation"]}
    verification = {row["path"] for row in impact["surfaces"]["verification"]}
    assert "api.py" in impl
    assert "tests/test_api.py" in verification
    assert impact["authority"] == "advisory-navigation-only"
    assert all(
        row["provenance"] == "reverse-file-graph"
        for row in impact["surfaces"]["implementation"]
    )


def test_change_impact_is_bounded_and_does_not_change_task_retrieval(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    ws = tmp_path / "repo"
    ws.mkdir()
    (ws / "a.py").write_text("def root():\n    return 1\n")
    for index in range(5):
        (ws / f"b{index}.py").write_text(
            f"from a import root\ndef use_{index}():\n    return root()\n"
        )
    with CodeMap(ws) as codemap:
        codemap.sync()
        before = tuple(hit.path for hit in codemap.find_task("root", limit=10))
        impact = codemap.change_impact("a.py", limit_per_surface=2)
        after = tuple(hit.path for hit in codemap.find_task("root", limit=10))
    assert len(impact["surfaces"]["implementation"]) <= 2
    assert before == after


def test_derived_graph_revalidates_exact_path_after_unsignaled_rewrite(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    ws = tmp_path / "repo"
    ws.mkdir()
    source = ws / "service.py"
    source.write_text("def public(x: int) -> int:\n    return x\n")
    with CodeMap(ws) as codemap:
        codemap.sync()
        before = {
            row["kind"]: row for row in codemap.derived_graph("service.py")["nodes"]
        }
        source.write_text("def renamed(x: str) -> str:\n    return x\n")
        after = {
            row["kind"]: row for row in codemap.derived_graph("service.py")["nodes"]
        }
    assert before["content"]["identity"] != after["content"]["identity"]
    assert before["symbol_surface"]["identity"] != after["symbol_surface"]["identity"]


def test_derived_graph_obeys_live_context_policy_before_exposing_nodes(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    ws = tmp_path / "repo"
    ws.mkdir()
    private = ws / "private"
    private.mkdir()
    source = private / "hidden.py"
    source.write_text("def hidden():\n    return 1\n")
    with CodeMap(ws) as codemap:
        codemap.sync()
        assert codemap.derived_graph("private/hidden.py")["nodes"]
        (ws / ".hashmarks-context.toml").write_text(
            '[[rule]]\npattern = "private/**"\nindex = false\n',
            encoding="utf-8",
        )
        assert codemap.derived_graph("private/hidden.py")["nodes"] == []
