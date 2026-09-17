from __future__ import annotations

from pathlib import Path

import pytest

from hashmarks.codemap.engine import CodeMap
from hashmarks.codemap.query_router import QueryIntent, route_query


def test_query_router_classifies_strong_intents() -> None:
    assert route_query("AuthService").intent is QueryIntent.IDENTIFIER
    assert route_query("backend/src/auth/service.py").intent is QueryIntent.PATH
    assert route_query("callers references AuthService").intent is QueryIntent.RELATIONSHIP
    assert route_query("pyproject config dependency").intent is QueryIntent.CONFIG
    assert route_query("pytest fixture auth").intent is QueryIntent.TEST
    assert route_query("class function signature").intent is QueryIntent.STRUCTURAL
    assert route_query("architecture ownership lifecycle").intent is QueryIntent.CONCEPTUAL
    assert route_query("strange mixed words").intent is QueryIntent.HYBRID


def test_path_config_and_test_routes_prune_native_definition_expansion() -> None:
    for query in ("src/app.ts", "pyproject config", "pytest fixture"):
        route = route_query(query)
        assert route.native_definitions is False
        assert route.lexical_lookup is True
        assert route.path_lookup is True


def test_ambiguous_route_preserves_hybrid_retrieval() -> None:
    route = route_query("strange mixed words")
    assert route.intent is QueryIntent.HYBRID
    assert route.native_definitions is True
    assert route.caller_expansion is True
    assert route.path_lookup is True
    assert route.lexical_lookup is True


def test_codemap_exposes_route_without_search(tmp_path: Path) -> None:
    (tmp_path / "service.py").write_text("class AuthService:\n    pass\n")
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        route = codemap.query_route("AuthService")
        assert route.intent is QueryIntent.IDENTIFIER
        assert route.as_dict()["schema"] == "hashmarks.codemap-query-route.v1"
        assert codemap.find("AuthService")[0].path == "service.py"


def test_query_router_exposes_intent_scoped_repository_domains() -> None:
    route = route_query("who owns release packaging and which make command enforces the contract")
    domains = route.as_dict()["preferred_domains"]
    assert domains[:2] == ["ownership", "build"]
    assert "contract" in domains
    assert "source" not in domains


def test_repository_control_surface_domains_are_not_global_boosts(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("Ownership: release belongs to ReleaseAuthority.\n", encoding="utf-8")
    (tmp_path / "Makefile").write_text("release:\n\tpython scripts/release.sh\n", encoding="utf-8")
    (tmp_path / "ARCHITECTURE.md").write_text("ReleaseAuthority owns release lifecycle boundaries.\n", encoding="utf-8")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "release.sh").write_text("#!/bin/sh\necho release authority\n", encoding="utf-8")
    (tmp_path / "service.py").write_text("class ReleaseAuthority:\n    pass\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        ownership = codemap.find("who owns release authority and build contract", limit=8)
        identifier = codemap.find("ReleaseAuthority", limit=8)
    paths = {hit.path for hit in ownership}
    assert "AGENTS.md" in paths
    assert "Makefile" in paths
    assert "ARCHITECTURE.md" in paths
    assert "scripts/release.sh" in paths
    assert identifier[0].path == "service.py"


def test_task_query_formulation_is_candidate_visible_and_governance_aware(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("Ownership authority architecture contract.\n", encoding="utf-8")
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "README.md").write_text("Backend API ownership boundary.\n", encoding="utf-8")
    (tmp_path / "backend" / "service.py").write_text("class WidgetRoute:\n    pass\n", encoding="utf-8")
    task = "Where does an API route change belong, what must the API layer not own, and which architectural contract governs it?"
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        formulated = codemap.formulate_task_query(task)
        hits = codemap.find_task(task, limit=8)
    assert "api" in formulated.split()
    assert "ownership" in formulated.split()
    assert "architecture" in formulated.split()
    assert "contract" in formulated.split()
    assert any(hit.path in {"AGENTS.md", "backend/README.md"} for hit in hits)


def test_task_query_views_add_generic_evidence_families_without_project_filenames(tmp_path: Path) -> None:
    (tmp_path / "PRIVACY.md").write_text("Security privacy redaction exposure rules.\n", encoding="utf-8")
    (tmp_path / "CI_CD_CONTRACT.md").write_text("CI CD release delivery automation contract.\n", encoding="utf-8")
    (tmp_path / "service.py").write_text("def publish_public_log():\n    return 'ok'\n", encoding="utf-8")
    task = "How do public logs avoid leaking private values during release automation?"
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        views = codemap.task_query_views(task)
        hits = codemap.find_task(task, limit=8)
    assert views["schema"] == "hashmarks.task-query-views.v2"
    assert {"privacy", "security", "redaction"} <= set(views["evidence"].split())
    assert {"release", "automation"} <= set(views["evidence"].split())
    paths = {hit.path for hit in hits}
    assert "PRIVACY.md" in paths
    assert "CI_CD_CONTRACT.md" in paths


def test_task_query_evidence_family_does_not_change_exact_identifier_leader(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("Release privacy security architecture.\n", encoding="utf-8")
    (tmp_path / "service.py").write_text("class ReleaseAuthority:\n    pass\n", encoding="utf-8")
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        hits = codemap.find_task("ReleaseAuthority", limit=6)
    assert hits[0].path == "service.py"


def test_find_task_deduplicates_identical_query_views(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "service.py").write_text("class Widget:\n    pass\n", encoding="utf-8")
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        original = codemap.find
        calls: list[str] = []
        def counted(query: str, *, limit: int = 20):
            calls.append(query)
            return original(query, limit=limit)
        monkeypatch.setattr(codemap, "find", counted)
        codemap.find_task("Widget", limit=6)
    assert len(calls) == len(set(calls))
    assert len(calls) <= 2


def test_find_task_preserves_scoped_agents_for_ambiguous_localized_task(tmp_path: Path, monkeypatch) -> None:
    from hashmarks.codemap.model import SearchHit

    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        monkeypatch.setattr(
            codemap,
            "task_query_views",
            lambda task: {
                "schema": "hashmarks.task-query-views.v2",
                "base": "scheduler schedule interval",
                "governance": "scheduler schedule interval ownership authority agents",
                "evidence": "scheduler schedule interval",
            },
        )
        base = tuple(
            SearchHit(path=f"backend/src/pkg/item_{index}.py", score=100.0 - index, kind="file")
            for index in range(20)
        )
        governance = (
            SearchHit(path="backend/AGENTS.md", score=90.0, kind="file"),
            *tuple(
                SearchHit(path=f"backend/src/pkg/item_{index}.py", score=89.0 - index, kind="file")
                for index in range(20)
            ),
        )
        monkeypatch.setattr(
            codemap,
            "find",
            lambda query, *, limit=20: governance if "ownership" in query else base,
        )
        hits = codemap.find_task("ignored", limit=20)
    assert hits[-1].path == "backend/AGENTS.md"


def test_find_task_does_not_override_high_confidence_relationship_route(tmp_path: Path, monkeypatch) -> None:
    from hashmarks.codemap.model import SearchHit

    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        monkeypatch.setattr(
            codemap,
            "task_query_views",
            lambda task: {
                "schema": "hashmarks.task-query-views.v2",
                "base": "imports dependency declarations",
                "governance": "imports dependency declarations ownership authority agents",
                "evidence": "imports dependency declarations",
            },
        )
        base = tuple(
            SearchHit(path=f"backend/src/pkg/item_{index}.py", score=100.0 - index, kind="file")
            for index in range(20)
        )
        governance = (
            SearchHit(path="backend/AGENTS.md", score=90.0, kind="file"),
            *tuple(
                SearchHit(path=f"backend/src/pkg/item_{index}.py", score=89.0 - index, kind="file")
                for index in range(20)
            ),
        )
        monkeypatch.setattr(
            codemap,
            "find",
            lambda query, *, limit=20: governance if "ownership" in query else base,
        )
        hits = codemap.find_task("ignored", limit=20)
    assert "backend/AGENTS.md" not in {hit.path for hit in hits}


def test_find_task_preserves_deep_scoped_readme_for_conceptual_localization(tmp_path: Path, monkeypatch) -> None:
    from hashmarks.codemap.model import SearchHit

    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        monkeypatch.setattr(
            codemap,
            "task_query_views",
            lambda task: {
                "schema": "hashmarks.task-query-views.v2",
                "base": "runtime ownership immutable representation",
                "governance": "runtime ownership immutable representation architecture contract readme",
                "evidence": "runtime ownership immutable representation",
            },
        )
        base = tuple(
            [
                SearchHit(path="backend/src/pkg/runtime/a.py", score=100.0, kind="file"),
                SearchHit(path="backend/src/pkg/runtime/b.py", score=99.0, kind="file"),
            ]
            + [
                SearchHit(path=f"tests/item_{index}.py", score=98.0 - index, kind="file")
                for index in range(18)
            ]
        )
        governance = tuple(base[:17]) + (
            SearchHit(path="backend/src/pkg/runtime/README.md", score=82.0, kind="file"),
        ) + tuple(base[17:])
        monkeypatch.setattr(
            codemap,
            "find",
            lambda query, *, limit=20: governance if "architecture" in query else base,
        )
        hits = codemap.find_task("ignored", limit=20)
    assert hits[-1].path == "backend/src/pkg/runtime/README.md"


def test_find_task_does_not_preserve_scoped_readme_without_two_localized_results(tmp_path: Path, monkeypatch) -> None:
    from hashmarks.codemap.model import SearchHit

    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        monkeypatch.setattr(
            codemap,
            "task_query_views",
            lambda task: {
                "schema": "hashmarks.task-query-views.v2",
                "base": "runtime ownership immutable representation",
                "governance": "runtime ownership immutable representation architecture contract readme",
                "evidence": "runtime ownership immutable representation",
            },
        )
        base = tuple(
            [SearchHit(path="backend/src/pkg/runtime/a.py", score=100.0, kind="file")]
            + [
                SearchHit(path=f"tests/item_{index}.py", score=99.0 - index, kind="file")
                for index in range(19)
            ]
        )
        governance = tuple(base[:17]) + (
            SearchHit(path="backend/src/pkg/runtime/README.md", score=82.0, kind="file"),
        ) + tuple(base[17:])
        monkeypatch.setattr(
            codemap,
            "find",
            lambda query, *, limit=20: governance if "architecture" in query else base,
        )
        hits = codemap.find_task("ignored", limit=20)
    assert "backend/src/pkg/runtime/README.md" not in {hit.path for hit in hits}


def test_find_task_does_not_preserve_scoped_readme_for_relationship_route(tmp_path: Path, monkeypatch) -> None:
    from hashmarks.codemap.model import SearchHit

    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        monkeypatch.setattr(
            codemap,
            "task_query_views",
            lambda task: {
                "schema": "hashmarks.task-query-views.v2",
                "base": "imports dependency runtime representation",
                "governance": "imports dependency runtime representation architecture contract readme",
                "evidence": "imports dependency runtime representation",
            },
        )
        base = tuple(
            [
                SearchHit(path="backend/src/pkg/runtime/a.py", score=100.0, kind="file"),
                SearchHit(path="backend/src/pkg/runtime/b.py", score=99.0, kind="file"),
            ]
            + [
                SearchHit(path=f"tests/item_{index}.py", score=98.0 - index, kind="file")
                for index in range(18)
            ]
        )
        governance = tuple(base[:17]) + (
            SearchHit(path="backend/src/pkg/runtime/README.md", score=82.0, kind="file"),
        ) + tuple(base[17:])
        monkeypatch.setattr(
            codemap,
            "find",
            lambda query, *, limit=20: governance if "architecture" in query else base,
        )
        hits = codemap.find_task("ignored", limit=20)
    assert "backend/src/pkg/runtime/README.md" not in {hit.path for hit in hits}


def test_task_graph_adjacency_is_additive_bounded_and_provenanced(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    tests = tmp_path / "tests"
    tests.mkdir()
    (pkg / "service.py").write_text(
        "def execute_widget():\n    return 'ok'\n",
        encoding="utf-8",
    )
    (tests / "test_service.py").write_text(
        "from pkg.service import execute_widget\n\ndef test_widget():\n    assert execute_widget() == 'ok'\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        primary = codemap.find_task("test widget execute_widget", limit=1)
        adjacency = codemap.task_graph_adjacency(
            "test widget execute_widget", seed_limit=1, limit=3
        )
    assert [row["path"] for row in adjacency["primary"]] == [hit.path for hit in primary]
    assert adjacency["bounds"]["max_hops"] == 1
    assert len(adjacency["adjacent"]) <= 3
    if adjacency["adjacent"]:
        assert adjacency["adjacent"][0]["provenance"]
        assert adjacency["adjacent"][0]["provenance"][0]["seed_rank"] == 1


def test_task_graph_adjacency_never_rewrites_canonical_find_task(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def alpha():\n    return beta()\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def beta():\n    return 1\n", encoding="utf-8")
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        before = codemap.find_task("alpha", limit=5)
        codemap.task_graph_adjacency("alpha", seed_limit=5, limit=4)
        after = codemap.find_task("alpha", limit=5)
    assert [hit.as_dict() for hit in after] == [hit.as_dict() for hit in before]


def test_task_graph_adjacency_validates_bounds(tmp_path: Path) -> None:
    (tmp_path / "service.py").write_text("def service():\n    return 1\n", encoding="utf-8")
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        import pytest
        with pytest.raises(ValueError):
            codemap.task_graph_adjacency("service", seed_limit=0)
        with pytest.raises(ValueError):
            codemap.task_graph_adjacency("service", limit=0)
        with pytest.raises(ValueError):
            codemap.task_graph_adjacency("service", per_seed_edge_limit=0)


def test_scoped_authority_resolves_root_nested_and_override_without_ranking_effect(tmp_path: Path):
    (tmp_path / "AGENTS.md").write_text("root authority\n", encoding="utf-8")
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "AGENTS.md").write_text("backend authority\n", encoding="utf-8")
    pkg = backend / "pkg"
    pkg.mkdir()
    (pkg / "AGENTS.md").write_text("package authority\n", encoding="utf-8")
    (pkg / "AGENTS.override.md").write_text("package override\n", encoding="utf-8")
    source = pkg / "service.py"
    source.write_text("def serve():\n    return 1\n", encoding="utf-8")
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        before = [hit.path for hit in codemap.find_task("serve service", limit=20)]
        value = codemap.repository_instruction_scope("backend/pkg/service.py")
        after = [hit.path for hit in codemap.find_task("serve service", limit=20)]
    assert value["scope_source"] == "explicit-path"
    assert [row["path"] for row in value["authority"]] == [
        "AGENTS.md", "backend/AGENTS.md", "backend/pkg/AGENTS.md", "backend/pkg/AGENTS.override.md"
    ]
    assert value["authority"][-1]["kind"] == "override"
    assert value["authority"][-1]["specificity"] == 2
    assert before == after
    assert value["ranking_effect"] == "none"


def test_scoped_authority_does_not_treat_readme_as_authority(tmp_path: Path):
    (tmp_path / "AGENTS.md").write_text("root authority\n", encoding="utf-8")
    area = tmp_path / "area"
    area.mkdir()
    (area / "README.md").write_text("architecture ownership words but not authority\n", encoding="utf-8")
    source = area / "service.py"
    source.write_text("def serve():\n    return 1\n", encoding="utf-8")
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        value = codemap.repository_instruction_scope("area/service.py")
    assert [row["path"] for row in value["authority"]] == ["AGENTS.md"]


def test_explain_task_retrieval_reports_rrf_provenance_without_changing_results(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "alpha.py").write_text("def alpha_service():\n    return 1\n", encoding="utf-8")
    (root / "test_alpha.py").write_text("from alpha import alpha_service\n", encoding="utf-8")
    with CodeMap(root, state_dir=tmp_path / "state") as codemap:
        codemap.sync()
        before = codemap.find_task("alpha service test", limit=5)
        explained = codemap.explain_task_retrieval("alpha service test", limit=5)
        after = codemap.find_task("alpha service test", limit=5)
    assert [hit.path for hit in before] == [hit.path for hit in after]
    assert explained["schema"] == "hashmarks.task-retrieval-provenance.v1"
    assert explained["ranking_effect"] == "none"
    assert [row["path"] for row in explained["selected"]] == [hit.path for hit in before]
    assert explained["selected"][0]["discovered_by"]
    assert {item["lane"] for row in explained["selected"] for item in row["discovered_by"]} <= {"base", "governance", "evidence"}


def test_explain_task_retrieval_validates_limit(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    with CodeMap(root, state_dir=tmp_path / "state") as codemap:
        with pytest.raises(ValueError, match="limit must be >= 1"):
            codemap.explain_task_retrieval("alpha", limit=0)


def test_find_task_reuses_generation_bound_result_without_replaying_views(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "src" / "alpha.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("def alpha():\n    return 1\n", encoding="utf-8")
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        calls = 0
        original_find = codemap.find

        def counted_find(query: str, *, limit: int = 20):
            nonlocal calls
            calls += 1
            return original_find(query, limit=limit)

        monkeypatch.setattr(codemap, "find", counted_find)
        first = codemap.find_task("alpha implementation", limit=10)
        first_calls = calls
        second = codemap.find_task("alpha implementation", limit=10)
        assert second == first
        assert calls == first_calls
        assert first_calls >= 1


def test_find_task_cache_is_invalidated_by_codemap_generation(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "src" / "alpha.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def alpha():\n    return 1\n", encoding="utf-8")
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        calls = 0
        original_find = codemap.find

        def counted_find(query: str, *, limit: int = 20):
            nonlocal calls
            calls += 1
            return original_find(query, limit=limit)

        monkeypatch.setattr(codemap, "find", counted_find)
        codemap.find_task("alpha implementation", limit=10)
        before = calls
        source.write_text("def alpha():\n    return 2\n", encoding="utf-8")
        codemap.sync(["src/alpha.py"])
        codemap.find_task("alpha implementation", limit=10)
        assert calls > before


def test_task_context_plan_is_bounded_and_route_sensitive(tmp_path: Path) -> None:
    (tmp_path / "service.py").write_text("class AuthService:\n    pass\n", encoding="utf-8")
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        identifier = codemap.task_context_plan("AuthService")
        conceptual = codemap.task_context_plan("review ownership authority architecture contract")
        assert 512 <= int(identifier["token_budget"]) <= 2400
        assert 512 <= int(conceptual["token_budget"]) <= 2400
        assert int(conceptual["token_budget"]) > int(identifier["token_budget"])
        assert identifier["ranking_effect"] == "none"


def test_task_context_explicit_budget_overrides_adaptive_plan(tmp_path: Path) -> None:
    (tmp_path / "service.py").write_text("class AuthService:\n    pass\n", encoding="utf-8")
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        pack = codemap.task_context("AuthService", token_budget=600, disclosure="outline")
        assert pack.budget == 600
        assert pack.disclosure.value == "outline"


def test_task_relationships_composes_typed_layers_without_changing_primary(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("root authority\n", encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    (src / "AGENTS.md").write_text("source authority\n", encoding="utf-8")
    (src / "alpha.py").write_text("from src.beta import beta\n\ndef alpha():\n    return beta()\n", encoding="utf-8")
    (src / "beta.py").write_text("def beta():\n    return 1\n", encoding="utf-8")
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        before = [hit.path for hit in codemap.find_task("alpha beta", limit=10)]
        value = codemap.task_relationships("alpha beta", seed_limit=10)
        after = [hit.path for hit in codemap.find_task("alpha beta", limit=10)]
    assert before == after
    assert value["ranking_effect"] == "none"
    assert value["schema"] == "hashmarks.task-relationships.v1"
    assert any(row["layer"] == "authority" and row["relation"] == "governs" for row in value["relationships"])
    assert set(value["layer_counts"]) <= {"code-graph", "change-impact", "authority"}


def test_task_relationships_validates_bounds(tmp_path: Path) -> None:
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        with pytest.raises(ValueError, match="seed_limit"):
            codemap.task_relationships("alpha", seed_limit=0)
        with pytest.raises(ValueError, match="adjacency_limit"):
            codemap.task_relationships("alpha", adjacency_limit=0)


def test_retrieval_stability_replays_without_changing_canonical_result(tmp_path: Path) -> None:
    (tmp_path / "alpha.py").write_text("def alpha_service():\n    return 1\n", encoding="utf-8")
    (tmp_path / "test_alpha.py").write_text("from alpha import alpha_service\n", encoding="utf-8")
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        before = codemap.find_task("alpha service test", limit=10)
        value = codemap.retrieval_stability("alpha service test", limit=10, repeats=4)
        after = codemap.find_task("alpha service test", limit=10)
    assert value["schema"] == "hashmarks.retrieval-stability.v1"
    assert value["stable"] is True
    assert value["divergences"] == []
    assert len(set(value["fingerprints"])) == 1
    assert value["ranking_effect"] == "none"
    assert before == after


def test_retrieval_stability_validates_bounds(tmp_path: Path) -> None:
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        with pytest.raises(ValueError, match="limit must be >= 1"):
            codemap.retrieval_stability("alpha", limit=0)
        with pytest.raises(ValueError, match="repeats must be >= 2"):
            codemap.retrieval_stability("alpha", repeats=1)
        with pytest.raises(ValueError, match="repeats must be <= 20"):
            codemap.retrieval_stability("alpha", repeats=21)


def test_task_entry_points_projects_roles_without_changing_find_task(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("authority for service\n", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"name":"demo"}\n', encoding="utf-8")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "notes.md").write_text("package configuration historical notes\n", encoding="utf-8")
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        before = [hit.path for hit in codemap.find_task("package configuration", limit=20)]
        value = codemap.task_entry_points("package configuration", limit=20)
        after = [hit.path for hit in codemap.find_task("package configuration", limit=20)]
    assert before == after
    assert value["ranking_effect"] == "none"
    assert value["discovery_effect"] == "none"
    assert value["recommended"]
    assert value["recommended"][0]["role"] == "config_build"
    assert value["recommended"][0]["path"] == "package.json"


def test_task_entry_points_prefers_scoped_authority_for_authority_task(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("service authority\n", encoding="utf-8")
    (tmp_path / "service.py").write_text("def service():\n    return 1\n", encoding="utf-8")
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        value = codemap.task_entry_points("service authority ownership", limit=20)
    assert value["recommended"][0]["role"] == "authority"
    assert value["recommended"][0]["path"] == "AGENTS.md"


def test_task_entry_points_reports_test_authority_ambiguity_without_ranking_change(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("authority\n", encoding="utf-8")
    tests = tmp_path / "tests"; tests.mkdir()
    (tests / "test_service.py").write_text("def test_service():\n    assert True\n", encoding="utf-8")
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        before = [hit.path for hit in codemap.find_task("service tests AGENTS authority", limit=20)]
        value = codemap.task_entry_points("service tests AGENTS authority", limit=20)
        after = [hit.path for hit in codemap.find_task("service tests AGENTS authority", limit=20)]
    assert before == after
    assert value["schema"] == "hashmarks.task-entry-points.v2"
    assert value["ambiguity"]["ambiguous"] is True
    assert set(value["ambiguity"]["explicit_roles"]) >= {"authority", "verification"}
    assert {row["path"] for row in value["ambiguity"]["alternatives"]} >= {"AGENTS.md", "tests/test_service.py"}



def test_task_entry_points_never_projects_test_source_as_implementation(tmp_path: Path) -> None:
    src = tmp_path / "src"; src.mkdir()
    tests = tmp_path / "tests"; tests.mkdir()
    (src / "service.py").write_text("def submit_order():\n    return 1\n", encoding="utf-8")
    (tests / "test_service.py").write_text(
        "from src.service import submit_order\n\ndef test_submit_order():\n    assert submit_order() == 1\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        value = codemap.task_entry_points("submit_order implementation", limit=20)
    assert value["roles"]["implementation"]
    assert value["roles"]["implementation"][0]["path"] == "src/service.py"
    assert all(not str(row["path"]).startswith("tests/") for row in value["roles"]["implementation"])
    assert value["recommended"][0]["role"] == "implementation"
    assert value["recommended"][0]["path"] == "src/service.py"


def test_task_entry_points_prefers_stronger_same_role_symbol_evidence(tmp_path: Path) -> None:
    src = tmp_path / "src"; src.mkdir()
    (src / "service.py").write_text(
        "class OrderService:\n    def __init__(self, store: OrderStore):\n        self.store = store\n",
        encoding="utf-8",
    )
    (src / "storage.py").write_text(
        "class OrderStore:\n    def save_order(self):\n        return 1\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        canonical = [hit.path for hit in codemap.find_task("OrderStore save_order persistence", limit=20)]
        value = codemap.task_entry_points("OrderStore save_order persistence", limit=20)
        after = [hit.path for hit in codemap.find_task("OrderStore save_order persistence", limit=20)]
    assert canonical == after
    assert value["roles"]["implementation"][0]["path"] == "src/storage.py"
    assert value["roles"]["implementation"][0]["role_symbol_specificity"] > value["roles"]["implementation"][1]["role_symbol_specificity"]
    assert value["recommended"][0]["path"] == "src/storage.py"

def test_task_entry_points_reports_vite_test_config_ambiguity(tmp_path: Path) -> None:
    (tmp_path / "vite.config.ts").write_text("export default { test: { environment: 'jsdom' } }\n", encoding="utf-8")
    tests = tmp_path / "tests"; tests.mkdir()
    (tests / "panel.test.ts").write_text("export function panelTest() { return true }\n", encoding="utf-8")
    with CodeMap(tmp_path, state_dir=tmp_path / ".state") as codemap:
        codemap.sync()
        value = codemap.task_entry_points("vite test environment", limit=20)
    assert value["ambiguity"]["ambiguous"] is True
    assert set(value["ambiguity"]["explicit_roles"]) >= {"config_build", "verification"}


def test_task_entry_points_distinctive_test_identifier_resolves_role_ambiguity(tmp_path: Path) -> None:
    (tmp_path / "contracts").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "contracts" / "release.schema.json").write_text('{"title":"release checksum contract"}\n', encoding="utf-8")
    (tmp_path / "tests" / "test_release_contract.py").write_text(
        "def test_release_checksum_contract():\n    assert True\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        value = codemap.task_entry_points(
            "test_release_checksum_contract checksum contract test", limit=20
        )
    ambiguity = value["ambiguity"]
    assert ambiguity["schema"] == "hashmarks.entry-point-ambiguity.v2"
    assert set(ambiguity["explicit_roles"]) >= {"contract", "verification"}
    assert ambiguity["ambiguous"] is False
    assert ambiguity["reason"] == "resolved-by-distinctive-role-anchor"
    assert ambiguity["resolution"]["role"] == "verification"
    assert ambiguity["resolution"]["path"] == "tests/test_release_contract.py"
    assert "test_release_checksum_contract" in ambiguity["resolution"]["task_anchor_tokens"]
    assert ambiguity["secret_knowledge_used"] is False



def test_task_entry_points_generic_implementation_test_stays_ambiguous(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests" / "test_widget.py").write_text("def test_widget(): assert True\n", encoding="utf-8")
    (tmp_path / "src" / "widget.py").write_text("def widget(): return 1\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        value = codemap.task_entry_points("widget implementation test", limit=20)
    ambiguity = value["ambiguity"]
    assert set(ambiguity["explicit_roles"]) >= {"implementation", "verification"}
    assert ambiguity["ambiguous"] is True
    assert ambiguity["reason"] == "multiple-explicit-role-cues"
    assert ambiguity["resolution"]["status"] == "unresolved"
    assert ambiguity["discrimination_question"]
