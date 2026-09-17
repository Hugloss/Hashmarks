from __future__ import annotations

import json
import threading
import time
from typing import TYPE_CHECKING

from hashmarks import cli
from hashmarks.codemap import CodeMap
from hashmarks.codemap.service import CodeMapService, CodeMapServiceClient

if TYPE_CHECKING:
    from pathlib import Path


def _repo(root: Path) -> str:
    (root / "src" / "case").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "__init__.py").write_text("", encoding="utf-8")
    (root / "src" / "case" / "__init__.py").write_text("", encoding="utf-8")
    (root / "src" / "case" / "engine.py").write_text(
        "def apply_ember(value: str) -> str:\n    return 'old' if value == 'accepted' else value\n",
        encoding="utf-8",
    )
    (root / "src" / "case" / "route.py").write_text(
        "from .engine import apply_ember\n\ndef handle_ember(value: str) -> str:\n    return apply_ember(value)\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_behavior.py").write_text(
        "from src.case.route import handle_ember\n\ndef test_ember_accepted_response_contract():\n    assert handle_ember('accepted') == 'new'\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\npythonpath = ['.']\n", encoding="utf-8"
    )
    return "Accepted responses are transformed by the wrong active owner for ember"


def test_task_change_impact_composes_owner_path_and_verification(
    tmp_path: Path,
) -> None:
    task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        start = codemap.task_evidence(task)
        assert start["edit"] == "src/case/engine.py"
        (tmp_path / "src/case/engine.py").write_text(
            "def apply_ember(value: str) -> str:\n    return 'new' if value == 'accepted' else value\n",
            encoding="utf-8",
        )
        impact = codemap.task_change_impact(task, ["src/case/engine.py"])

    assert impact["schema"] == "hashmarks.task-change-impact.v1"
    assert impact["owner"] == "external"
    assert impact["authority"] == "advisory"
    assert impact["completeness"] == "not-claimed"
    implementations = impact["surfaces"]["implementation"]
    verification = impact["surfaces"]["verification"]
    assert implementations[0]["path"] == "src/case/route.py"
    assert implementations[0]["via"] == "task-owner-path"
    assert verification[0]["path"] == "tests/test_behavior.py"
    assert verification[0]["verify"]["runner"] == "pytest"
    assert verification[0]["selected"] is True
    encoded = json.dumps(impact, sort_keys=True)
    assert '"content"' not in encoded
    assert '"argv"' not in encoded


def test_task_change_impact_config_root_is_typed_and_gets_verification(
    tmp_path: Path,
) -> None:
    from scripts.agent_evaluation.generate_hard_agent_corpus import generate

    repo = tmp_path / "repo"
    public = tmp_path / "public.json"
    secret = tmp_path / "secret.json"
    generate(repo, public, secret, cases_per_category=1)
    tasks = json.loads(public.read_text(encoding="utf-8"))["tasks"]
    config_task = next(row for row in tasks if row["id"] == "hard-004")
    with CodeMap(repo) as codemap:
        codemap.sync()
        start = codemap.task_evidence(config_task["query"])
        assert start["edit"].endswith("policy.toml")
        impact = codemap.task_change_impact(config_task["query"], [start["edit"]])
    changed = impact["changed"][0]
    assert "contract" in changed["roles"]
    assert "build_config" in changed["roles"]
    assert (
        impact["surfaces"]["verification"][0]["path"]
        == "tests/case_004/test_behavior.py"
    )


def test_task_change_impact_bounded_fanout_never_claims_complete_impact(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "core.py").write_text(
        "def shared(): return 1\n", encoding="utf-8"
    )
    for index in range(20):
        (tmp_path / "src" / f"consumer_{index}.py").write_text(
            "from src.core import shared\ndef consume(): return shared()\n",
            encoding="utf-8",
        )
    (tmp_path / "tests" / "test_core.py").write_text(
        "from src.core import shared\ndef test_shared(): assert shared() == 1\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        impact = codemap.task_change_impact(
            "change shared implementation",
            ["src/core.py"],
            impact_limit_per_surface=3,
            max_depth=3,
        )
    assert len(impact["surfaces"]["implementation"]) == 3
    assert impact["bounds"]["per_surface"] == 3
    assert impact["completeness"] == "not-claimed"


def test_task_change_impact_bounds_surfaces(tmp_path: Path) -> None:
    task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        impact = codemap.task_change_impact(
            task, ["src/case/engine.py"], impact_limit_per_surface=1, max_depth=2
        )
    assert all(len(rows) <= 1 for rows in impact["surfaces"].values())
    assert impact["bounds"]["per_surface"] == 1
    assert impact["bounds"]["depth"] == 2


def test_task_change_impact_never_discloses_denied_path(tmp_path: Path) -> None:
    task = _repo(tmp_path)
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "src/case/route.py"\nvisibility = "deny"\n',
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        impact = codemap.task_change_impact(task, ["src/case/engine.py"])
    encoded = json.dumps(impact, sort_keys=True)
    assert "src/case/route.py" not in encoded
    assert impact["surfaces"]["verification"][0]["path"] == "tests/test_behavior.py"


def test_task_change_impact_cli(tmp_path: Path, capsys) -> None:
    task = _repo(tmp_path)
    assert (
        cli.main(
            [
                "--workspace",
                str(tmp_path),
                "change-impact",
                task,
                "--changed",
                "src/case/engine.py",
                "--project-impact-limit",
                "20",
                "--project-impact-encoding",
                "compact",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "hashmarks.task-change-impact.v1"
    assert payload["surfaces"]["verification"][0]["path"] == "tests/test_behavior.py"


def _wait(client: CodeMapServiceClient) -> None:
    for _ in range(100):
        try:
            client.status()
            return
        except OSError:
            time.sleep(0.01)
    raise AssertionError("service did not start")


def test_service_task_change_impact(tmp_path: Path) -> None:
    task = _repo(tmp_path)
    socket_path = tmp_path / "change-impact.sock"
    service = CodeMapService(tmp_path, socket_path=socket_path)
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    client = CodeMapServiceClient(tmp_path, socket_path=socket_path)
    _wait(client)
    try:
        impact = client.task_change_impact(
            task,
            ["src/case/engine.py"],
            project_impact_limit=20,
            project_impact_encoding="compact",
        )
        assert impact["schema"] == "hashmarks.task-change-impact.v1"
        assert impact["owner"] == "external"
        assert impact["surfaces"]["verification"][0]["path"] == "tests/test_behavior.py"
    finally:
        client.stop()
        thread.join(timeout=5)


def test_task_change_impact_qualification_freezes_before_secret_join(
    tmp_path: Path,
) -> None:
    from scripts.agent_evaluation.generate_hard_agent_corpus import generate
    from scripts.agent_evaluation.score_agent_change_impact import run

    repo = tmp_path / "repo"
    public = tmp_path / "public.json"
    secret = tmp_path / "secret.json"
    output = tmp_path / "impact.json"
    generate(repo, public, secret, cases_per_category=1)
    payload = run(repo, public, secret, output)

    assert payload["summary"]["tasks"] == 6
    assert payload["summary"]["fully_correct"] == 6
    assert payload["summary"]["verify_relevant"] == 6
    assert payload["summary"]["no_source_or_argv_replay"] == 6
    assert (
        payload["protocol"]["secret_join_after_start_external_edit_and_impact_freeze"]
        is True
    )


def test_task_change_impact_reconstructs_same_package_go_owner_chain(
    tmp_path: Path,
) -> None:
    (tmp_path / "go.mod").write_text(
        "module example.local/demo\n\ngo 1.23\n", encoding="utf-8"
    )
    for name in ("route", "service", "engine"):
        (tmp_path / name).mkdir()
    (tmp_path / "engine/engine.go").write_text(
        'package engine\nfunc ResolveCobaltRidgeAlpha(value string) string { return value + "-old" }\n',
        encoding="utf-8",
    )
    (tmp_path / "service/service.go").write_text(
        'package service\nimport "example.local/demo/engine"\nfunc ServiceValue(value string) string { return engine.ResolveCobaltRidgeAlpha(value) }\n',
        encoding="utf-8",
    )
    (tmp_path / "route/route.go").write_text(
        'package route\nimport "example.local/demo/service"\nfunc RouteValue(value string) string { return service.ServiceValue(value) }\n',
        encoding="utf-8",
    )
    (tmp_path / "route/cobaltridgealpha_test.go").write_text(
        'package route\nimport "testing"\nfunc TestCobaltRidgeAlpha(t *testing.T) {}\n',
        encoding="utf-8",
    )
    task = "Change CobaltRidgeAlpha accepted response from old to new"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        start = codemap.task_evidence(task)
        assert start["edit"] == "engine/engine.go"
        assert start["verify_path"] == "route/cobaltridgealpha_test.go"
        assert "owner_path" not in start
        impact = codemap.task_change_impact(task, ["engine/engine.go"])

    implementation = [row["path"] for row in impact["surfaces"]["implementation"]]
    assert implementation[:2] == [
        "route/route.go",
        "service/service.go",
    ] or implementation[:2] == ["service/service.go", "route/route.go"]
    assert "service/service.go" in implementation
    assert "route/route.go" in implementation
    assert (
        impact["surfaces"]["verification"][0]["path"]
        == "route/cobaltridgealpha_test.go"
    )


def test_large_task_change_impact_matrix_small_smoke(tmp_path: Path) -> None:
    from scripts.agent_evaluation.score_large_agent_change_impact import run_matrix

    payload = run_matrix(
        tmp_path / "large",
        sizes=(12,),
        regular_tasks=2,
        largest_tasks=2,
    )
    assert payload["summary"]["scenarios"] == 4
    assert payload["summary"]["tasks"] == 8
    assert payload["summary"]["fully_correct"] == 8
    assert payload["summary"]["verify_relevant"] == 8
    assert payload["summary"]["dependency_relevant"] == 8
    assert payload["summary"]["no_source_or_argv_replay"] == 8


def test_exact_import_resolution_avoids_whole_file_map_materialization(
    tmp_path: Path,
) -> None:
    ts_root = tmp_path / "ts"
    (ts_root / "src").mkdir(parents=True)
    (ts_root / "src/engine.ts").write_text(
        "export const value = 'ok';\n", encoding="utf-8"
    )
    (ts_root / "src/route.ts").write_text(
        "import { value } from './engine.js';\nexport { value };\n",
        encoding="utf-8",
    )
    with CodeMap(ts_root) as codemap:
        codemap.sync()
        codemap.store.all_file_rows = lambda: (_ for _ in ()).throw(
            AssertionError("whole file map must not be materialized")
        )  # type: ignore[method-assign]
        assert codemap._resolve_import_paths("src/route.ts", "./engine.js") == [
            "src/engine.ts"
        ]

    go_root = tmp_path / "go"
    (go_root / "engine").mkdir(parents=True)
    (go_root / "route").mkdir()
    (go_root / "go.mod").write_text(
        "module example.local/demo\n\ngo 1.23\n", encoding="utf-8"
    )
    (go_root / "engine/engine.go").write_text(
        'package engine\nfunc Value() string { return "ok" }\n', encoding="utf-8"
    )
    (go_root / "route/route.go").write_text(
        'package route\nimport "example.local/demo/engine"\nfunc Value() string { return engine.Value() }\n',
        encoding="utf-8",
    )
    with CodeMap(go_root) as codemap:
        codemap.sync()
        codemap.store.all_file_rows = lambda: (_ for _ in ()).throw(
            AssertionError("whole file map must not be materialized")
        )  # type: ignore[method-assign]
        assert codemap._resolve_import_paths(
            "route/route.go", "example.local/demo/engine"
        ) == ["engine/engine.go"]


def test_task_change_impact_declared_project_provenance_and_shared_input_refresh(
    tmp_path: Path,
) -> None:
    (tmp_path / "backend/src").mkdir(parents=True)
    (tmp_path / "frontend/src").mkdir(parents=True)
    (tmp_path / "mobile/src").mkdir(parents=True)
    (tmp_path / "backend/pom.xml").write_text(
        "<project><groupId>com.example</groupId><artifactId>api</artifactId><version>1</version></project>",
        encoding="utf-8",
    )
    (tmp_path / "frontend/package.json").write_text(
        '{"name":"@demo/web"}', encoding="utf-8"
    )
    (tmp_path / "mobile/package.json").write_text(
        '{"name":"@demo/mobile"}', encoding="utf-8"
    )
    (tmp_path / "backend/src/Api.java").write_text("class Api {}\n", encoding="utf-8")
    (tmp_path / "frontend/src/api.ts").write_text(
        "export const api = 1\n", encoding="utf-8"
    )
    (tmp_path / "mobile/src/api.ts").write_text(
        "export const api = 1\n", encoding="utf-8"
    )
    (tmp_path / "openapi.yaml").write_text("openapi: 3.1.0\n", encoding="utf-8")
    (tmp_path / ".hashmarks-project-links.toml").write_text(
        "[[link]]\nsource='npm:@demo/web'\ntarget='maven:com.example:api'\nkind='api-client'\n"
        "[[link]]\nsource='npm:@demo/mobile'\ntarget='npm:@demo/web'\nkind='client-shell'\n"
        "[[shared_input]]\npath='openapi.yaml'\nprojects=['npm:@demo/web','maven:com.example:api']\nkind='contract'\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        codemap.enrich_projects(
            ("npm-package-graph", "maven-pom-graph", "declared-project-links")
        )
        source_impact = codemap.task_change_impact(
            "backend api change", ["backend/src/Api.java"]
        )
        assert source_impact["projects"] == ["npm:@demo/mobile", "npm:@demo/web"]
        rows = {
            row["project"]: row for row in source_impact["project_impact"]["affected"]
        }
        assert rows["npm:@demo/web"]["depth"] == 1
        assert any(
            edge["producer"] == "declared-project-links"
            for edge in source_impact["project_impact"]["edges"]
        )
        assert rows["npm:@demo/mobile"]["depth"] == 2

        (tmp_path / "openapi.yaml").write_text("openapi: 3.1.1\n", encoding="utf-8")
        shared_impact = codemap.task_change_impact(
            "openapi contract change", ["openapi.yaml"]
        )

    assert shared_impact["projects"] == [
        "maven:com.example:api",
        "npm:@demo/mobile",
        "npm:@demo/web",
    ]
    assert shared_impact["project_refresh"]["producer"] == "declared-project-links"
    assert shared_impact["project_refresh"]["changed"] == "openapi.yaml"
    project_rows = {
        row["project"]: row for row in shared_impact["project_impact"]["affected"]
    }
    assert any(
        edge["kind"] == "contract" for edge in shared_impact["project_impact"]["edges"]
    )
    assert project_rows["npm:@demo/mobile"]["depth"] == 2


def test_task_change_impact_project_provenance_is_bounded(tmp_path: Path) -> None:
    (tmp_path / "root").mkdir()
    (tmp_path / "root/package.json").write_text('{"name":"root"}', encoding="utf-8")
    (tmp_path / "root/value.ts").write_text(
        "export const value = 1\n", encoding="utf-8"
    )
    links = []
    for index in range(8):
        name = f"client-{index}"
        (tmp_path / name).mkdir()
        (tmp_path / name / "package.json").write_text(
            json.dumps({"name": name}), encoding="utf-8"
        )
        links.append(
            f"[[link]]\nsource='npm:{name}'\ntarget='npm:root'\nkind='consumer'\n"
        )
    (tmp_path / ".hashmarks-project-links.toml").write_text(
        "".join(links), encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        codemap.enrich_projects(("npm-package-graph", "declared-project-links"))
        impact = codemap.task_change_impact(
            "root value change", ["root/value.ts"], impact_limit_per_surface=3
        )
    assert len(impact["project_impact"]["affected"]) == 3
    assert len(impact["projects"]) == 8


def test_cross_repository_impact_qualification_small_smoke(tmp_path: Path) -> None:
    from scripts.score_cross_repository_impact import generate, run

    base = tmp_path / "cross"
    public = tmp_path / "public.json"
    secret = tmp_path / "secret.json"
    output = tmp_path / "result.json"
    generate(base, public, secret, scenarios=1, decoys=2)
    payload = run(base, public, secret, output)
    assert payload["summary"]["tasks"] == 2
    assert payload["summary"]["fully_correct"] == 2
    assert payload["summary"]["provenance_correct"] == 2
    assert payload["summary"]["shared_refresh_correct"] == 1
    assert payload["protocol"]["secret_join_after_packet_freeze"] is True


def test_project_impact_limit_is_independent_and_reports_truncation(tmp_path: Path):
    root = tmp_path
    for index in range(10):
        project = root / f"p{index}"
        (project / "src").mkdir(parents=True)
        (project / "package.json").write_text(
            json.dumps({"name": f"@scale/p{index}"}), encoding="utf-8"
        )
        (project / "src/index.ts").write_text(
            f"export const value = {index};\n", encoding="utf-8"
        )
    links = []
    for index in range(1, 10):
        links.append(
            f"[[link]]\nsource='npm:@scale/p{index}'\ntarget='npm:@scale/p0'\nkind='fanout'\n"
        )
    (root / ".hashmarks-project-links.toml").write_text(
        "".join(links), encoding="utf-8"
    )
    with CodeMap(root, artifact_db=root / "artifacts.sqlite3") as codemap:
        codemap.sync()
        codemap.enrich_projects(("npm-package-graph", "declared-project-links"))
        (root / "p0/src/index.ts").write_text(
            "export const value = 99;\n", encoding="utf-8"
        )
        bounded = codemap.task_change_impact(
            "update scale root",
            ["p0/src/index.ts"],
            max_depth=20,
            impact_limit_per_surface=2,
            project_impact_limit=3,
        )
        complete = codemap.task_change_impact(
            "update scale root",
            ["p0/src/index.ts"],
            max_depth=20,
            impact_limit_per_surface=2,
            project_impact_limit=20,
        )
    assert bounded["bounds"]["per_surface"] == 2
    assert bounded["bounds"]["project_impact"] == 3
    assert bounded["project_impact"]["reported_affected"] == 3
    assert bounded["project_impact"]["total_affected"] == 9
    assert bounded["project_impact"]["complete"] is False
    assert complete["project_impact"]["reported_affected"] == 9
    assert complete["project_impact"]["total_affected"] == 9
    assert complete["project_impact"]["complete"] is True


def test_declared_shared_input_refresh_rebinds_freshness_without_recollecting_topology(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "backend").mkdir()
    (tmp_path / "frontend").mkdir()
    (tmp_path / "backend/package.json").write_text(
        '{"name":"backend"}', encoding="utf-8"
    )
    (tmp_path / "frontend/package.json").write_text(
        '{"name":"frontend"}', encoding="utf-8"
    )
    (tmp_path / "backend/value.ts").write_text(
        "export const value = 1\n", encoding="utf-8"
    )
    (tmp_path / "contract.json").write_text('{"v":1}\n', encoding="utf-8")
    (tmp_path / ".hashmarks-project-links.toml").write_text(
        "[[shared_input]]\npath='contract.json'\nprojects=['npm:backend','npm:frontend']\nkind='contract'\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        codemap.enrich_projects(("npm-package-graph", "declared-project-links"))
        provider = next(
            p
            for p in codemap.project_graph_providers
            if p.name == "declared-project-links"
        )
        original_collect = provider.collect
        calls = 0

        def counted_collect(workspace):
            nonlocal calls
            calls += 1
            return original_collect(workspace)

        monkeypatch.setattr(provider, "collect", counted_collect)
        (tmp_path / "contract.json").write_text('{"v":2}\n', encoding="utf-8")
        impact = codemap.task_change_impact("contract changed", ["contract.json"])

    assert calls == 0
    assert impact["project_refresh"]["mode"] == "freshness-rebind"
    assert impact["project_refresh"]["changed_manifests"] == ["contract.json"]
    assert impact["projects"] == ["npm:backend", "npm:frontend"]


def test_declared_topology_change_recollects_provider(
    tmp_path: Path, monkeypatch
) -> None:
    for name in ("backend", "frontend", "mobile"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "package.json").write_text(
            json.dumps({"name": name}), encoding="utf-8"
        )
    (tmp_path / "backend/value.ts").write_text(
        "export const value = 1\n", encoding="utf-8"
    )
    links = tmp_path / ".hashmarks-project-links.toml"
    links.write_text(
        "[[link]]\nsource='npm:frontend'\ntarget='npm:backend'\nkind='consumer'\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        codemap.enrich_projects(("npm-package-graph", "declared-project-links"))
        provider = next(
            p
            for p in codemap.project_graph_providers
            if p.name == "declared-project-links"
        )
        original_collect = provider.collect
        calls = 0

        def counted_collect(workspace):
            nonlocal calls
            calls += 1
            return original_collect(workspace)

        monkeypatch.setattr(provider, "collect", counted_collect)
        links.write_text(
            "[[link]]\nsource='npm:frontend'\ntarget='npm:backend'\nkind='consumer'\n"
            "[[link]]\nsource='npm:mobile'\ntarget='npm:frontend'\nkind='consumer'\n",
            encoding="utf-8",
        )
        impact = codemap.task_change_impact(
            "declared topology changed", [".hashmarks-project-links.toml"]
        )
        source = codemap.task_change_impact("backend changed", ["backend/value.ts"])

    assert calls == 1
    assert impact["project_refresh"]["mode"] == "topology-recollect"
    assert impact["project_refresh"]["changed"] == ".hashmarks-project-links.toml"
    assert source["projects"] == ["npm:frontend", "npm:mobile"]


def test_unreported_shared_input_change_does_not_rebind_stale_project_evidence(
    tmp_path: Path,
) -> None:
    (tmp_path / "backend").mkdir()
    (tmp_path / "frontend").mkdir()
    (tmp_path / "backend/package.json").write_text(
        '{"name":"backend"}', encoding="utf-8"
    )
    (tmp_path / "frontend/package.json").write_text(
        '{"name":"frontend"}', encoding="utf-8"
    )
    (tmp_path / "backend/value.ts").write_text(
        "export const value = 1\n", encoding="utf-8"
    )
    (tmp_path / "contract.json").write_text('{"v":1}\n', encoding="utf-8")
    (tmp_path / ".hashmarks-project-links.toml").write_text(
        "[[shared_input]]\npath='contract.json'\nprojects=['npm:backend','npm:frontend']\nkind='contract'\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        codemap.enrich_projects(("npm-package-graph", "declared-project-links"))
        (tmp_path / "contract.json").write_text('{"v":2}\n', encoding="utf-8")
        impact = codemap.task_change_impact("backend changed", ["backend/value.ts"])
        fresh, reason = codemap._evidence_fresh("project", "declared-project-links")

    assert impact.get("project_refresh") is None
    assert fresh is False
    assert reason == "manifest changed: contract.json"


def test_task_change_impact_compact_project_provenance_round_trips(
    tmp_path: Path,
) -> None:
    from hashmarks.codemap import COMPACT_PROJECT_IMPACT_SCHEMA, expand_project_impact

    (tmp_path / "root").mkdir()
    (tmp_path / "root/package.json").write_text('{"name":"root"}', encoding="utf-8")
    (tmp_path / "root/value.ts").write_text(
        "export const value = 1\n", encoding="utf-8"
    )
    links = []
    for index in range(6):
        name = f"client-{index}"
        (tmp_path / name).mkdir()
        (tmp_path / name / "package.json").write_text(
            json.dumps({"name": name}), encoding="utf-8"
        )
        links.append(
            f"[[link]]\nsource='npm:{name}'\ntarget='npm:root'\nkind='consumer'\n"
        )
    (tmp_path / ".hashmarks-project-links.toml").write_text(
        "".join(links), encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        codemap.enrich_projects(("npm-package-graph", "declared-project-links"))
        verbose = codemap.task_change_impact(
            "root value change", ["root/value.ts"], project_impact_limit=20
        )
        compact = codemap.task_change_impact(
            "root value change",
            ["root/value.ts"],
            project_impact_limit=20,
            project_impact_encoding="compact",
        )

    assert compact["project_impact"]["schema"] == COMPACT_PROJECT_IMPACT_SCHEMA
    assert expand_project_impact(compact["project_impact"]) == verbose["project_impact"]
    assert len(json.dumps(compact, sort_keys=True, separators=(",", ":"))) < len(
        json.dumps(verbose, sort_keys=True, separators=(",", ":"))
    )


def test_task_change_impact_rejects_unknown_project_impact_encoding(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        try:
            codemap.task_change_impact(
                "ember", ["src/case/engine.py"], project_impact_encoding="magic"
            )
        except ValueError as exc:
            assert str(exc) == "project_impact_encoding must be verbose or compact"
        else:
            raise AssertionError("unknown encoding must fail closed")
