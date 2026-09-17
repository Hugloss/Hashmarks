from pathlib import Path

from hashmarks.codemap import CodeMap


def test_javascript_test_parent_import_resolves_active_owner(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"type":"module"}\n')
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "route.js").write_text(
        'import { Ember731 } from "./engine_b.js";\nexport function routeEmber731(){return Ember731()}\n'
    )
    (tmp_path / "src" / "engine_a.js").write_text(
        'export function Ember731(){return "old"}\n'
    )
    (tmp_path / "src" / "engine_b.js").write_text(
        'export function Ember731(){return "old"}\n'
    )
    (tmp_path / "tests" / "ember731.test.js").write_text(
        'import test from "node:test";\nimport { routeEmber731 } from "../src/route.js";\ntest("Ember731",()=>routeEmber731());\n'
    )
    with CodeMap(tmp_path) as c:
        c.sync()
        brief = c.task_action_brief("Change Ember731 accepted response")
    assert brief["edit"] == "src/engine_b.js"
    assert (
        brief["owner_path"]
        == "tests/ember731.test.js --imports--> src/route.js --imports--> src/engine_b.js"
    )


def test_go_same_package_test_uses_task_local_entry_then_module_owner(
    tmp_path: Path,
) -> None:
    (tmp_path / "go.mod").write_text("module example.local/demo\n\ngo 1.23\n")
    for d in ("route", "enginea", "engineb"):
        (tmp_path / d).mkdir()
    (tmp_path / "route" / "route.go").write_text(
        'package route\nimport "example.local/demo/engineb"\nfunc Ember731() string { return engineb.Ember731() }\n'
    )
    (tmp_path / "enginea" / "a.go").write_text(
        'package enginea\nfunc Ember731() string { return "old" }\n'
    )
    (tmp_path / "engineb" / "b.go").write_text(
        'package engineb\nfunc Ember731() string { return "old" }\n'
    )
    (tmp_path / "route" / "ember731_test.go").write_text(
        'package route\nimport "testing"\nfunc TestEmber731(t *testing.T){}\n'
    )
    with CodeMap(tmp_path) as c:
        c.sync()
        brief = c.task_action_brief("Change Ember731 accepted response")
    assert brief["edit"] == "engineb/b.go"
    assert brief["verify"] == ["go", "test", "./route"]
    assert brief["owner_path"] == "route/route.go --imports--> engineb/b.go"


def test_sql_test_literal_reference_beats_archive_decoy(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths=["tests"]\n'
    )
    (tmp_path / "queries").mkdir()
    (tmp_path / "archive").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "queries" / "ember731_active.sql").write_text(
        "SELECT 'old' AS ember731_label;\n"
    )
    (tmp_path / "archive" / "ember731_old.sql").write_text(
        "SELECT 'old' AS ember731_label;\n"
    )
    (tmp_path / "tests" / "test_ember731.py").write_text(
        'from pathlib import Path\ndef test_ember731():\n    Path("queries/ember731_active.sql").read_text()\n'
    )
    with CodeMap(tmp_path) as c:
        c.sync()
        brief = c.task_action_brief("For Ember731, change the SQL result label")
    assert brief["edit"] == "queries/ember731_active.sql"
    assert (
        brief["owner_path"]
        == "tests/test_ember731.py --references--> queries/ember731_active.sql"
    )


def test_javascript_parent_escape_import_is_not_resolved_into_workspace(
    tmp_path: Path,
) -> None:
    (tmp_path / "package.json").write_text('{"type":"module"}\n')
    (tmp_path / "tests").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "outside.js").write_text(
        'export function Ember731(){return "decoy"}\n'
    )
    (tmp_path / "tests" / "ember731.test.js").write_text(
        'import test from "node:test";\n'
        'import { Ember731 } from "../../src/outside.js";\n'
        'test("Ember731",()=>Ember731());\n'
    )
    with CodeMap(tmp_path) as c:
        c.sync()
        graph = c.ownership_relation_graph(
            "Change Ember731 accepted response", "tests/ember731.test.js"
        )
    assert graph["selected"] is None
    assert not any(
        str(edge.get("to") or "") == "src/outside.js" for edge in graph["edges"]
    )


def test_sql_parent_escape_literal_is_not_promoted_as_owner(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths=["tests"]\n'
    )
    (tmp_path / "queries").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "queries" / "ember731.sql").write_text(
        "SELECT 'old' AS ember731_label;\n"
    )
    (tmp_path / "tests" / "test_ember731.py").write_text(
        "from pathlib import Path\n"
        "def test_ember731():\n"
        '    Path("../queries/ember731.sql").read_text()\n'
    )
    with CodeMap(tmp_path) as c:
        c.sync()
        brief = c.task_action_brief("For Ember731, change the SQL result label")
    assert (
        brief.get("owner_path")
        != "tests/test_ember731.py --references--> queries/ember731.sql"
    )


def test_typescript_runtime_js_specifier_resolves_ts_source_owner(
    tmp_path: Path,
) -> None:
    (tmp_path / "package.json").write_text('{"type":"module"}\n')
    (tmp_path / "tsconfig.json").write_text(
        '{"compilerOptions":{"module":"NodeNext","moduleResolution":"NodeNext"},"include":["src/**/*.ts","tests/**/*.ts"]}\n'
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "route.ts").write_text(
        'import { ValueABC123 } from "./engine_b.js";\nexport function routeABC123(){return ValueABC123}\n'
    )
    (tmp_path / "src" / "engine_a.ts").write_text(
        'export const ValueABC123 = "old" as const;\n'
    )
    (tmp_path / "src" / "engine_b.ts").write_text(
        'export const ValueABC123 = "old" as const;\n'
    )
    (tmp_path / "tests" / "abc123.test.ts").write_text(
        'import { routeABC123 } from "../src/route.js";\nconst value = routeABC123(); void value;\n'
    )
    with CodeMap(tmp_path) as c:
        c.sync()
        brief = c.task_action_brief("For ABC123 change the accepted response")
    assert brief["edit"] == "src/engine_b.ts"
    assert (
        brief["owner_path"]
        == "tests/abc123.test.ts --imports--> src/route.ts --imports--> src/engine_b.ts"
    )


def test_uppercase_ticket_identifier_suppresses_unrelated_contract(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths=["tests"]\n'
    )
    (tmp_path / "src" / "abc123").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "contracts").mkdir()
    (tmp_path / "src" / "abc123" / "engine.py").write_text(
        'def ABC123(): return "old"\n'
    )
    (tmp_path / "tests" / "test_abc123.py").write_text(
        'from src.abc123.engine import ABC123\ndef test_abc123(): assert ABC123()=="new"\n'
    )
    (tmp_path / "contracts" / "generic_schema.py").write_text(
        "class AcceptedResponseContract: pass\n"
    )
    with CodeMap(tmp_path) as c:
        c.sync()
        brief = c.task_action_brief("For ABC123 change the accepted response contract")
    assert brief["edit"] == "src/abc123/engine.py"
    assert brief["verify"] == [
        "python",
        "-m",
        "pytest",
        "-q",
        "tests/test_abc123.py::test_abc123",
    ]
    assert "contract" not in brief


def test_go_same_package_unique_route_starts_structural_owner_when_phrase_is_content_only(
    tmp_path: Path,
) -> None:
    (tmp_path / "go.mod").write_text("module example.local/demo\n\ngo 1.23\n")
    for d in ("route", "service", "engine"):
        (tmp_path / d).mkdir()
    (tmp_path / "route" / "route.go").write_text(
        'package route\nimport "example.local/demo/service"\n'
        "func Value() string { return service.ResolveAmberValley() }\n\n"
        "// amber valley accepted response route\n"
    )
    (tmp_path / "service" / "service.go").write_text(
        'package service\nfunc ResolveAmberValley() string { return "old" }\n'
    )
    # Lexical decoy with the same task-specific symbol; it is not reachable.
    (tmp_path / "engine" / "engine.go").write_text(
        'package engine\nfunc ResolveAmberValley() string { return "old" }\n'
    )
    (tmp_path / "route" / "amber_test.go").write_text(
        'package route\nimport "testing"\nfunc TestAmber(t *testing.T){}\n'
        "// amber valley behavior verification\n"
    )
    with CodeMap(tmp_path) as c:
        c.sync()
        brief = c.task_action_brief(
            "Change the amber valley accepted response from old to new"
        )
    assert brief["status"] == "safe-fresh"
    assert brief["edit"] == "service/service.go"
    assert brief["verify"] == ["go", "test", "./route"]
    assert brief["owner_path"] == "route/route.go --imports--> service/service.go"


def test_go_same_package_unique_route_can_continue_to_engine_when_service_delegates(
    tmp_path: Path,
) -> None:
    (tmp_path / "go.mod").write_text("module example.local/demo\n\ngo 1.23\n")
    for d in ("route", "service", "engine"):
        (tmp_path / d).mkdir()
    (tmp_path / "route" / "route.go").write_text(
        'package route\nimport "example.local/demo/service"\n'
        "func Value() string { return service.Value() }\n\n"
        "// velvet lantern accepted response route\n"
    )
    (tmp_path / "service" / "service.go").write_text(
        'package service\nimport "example.local/demo/engine"\n'
        "func Value() string { return engine.ResolveVelvetLantern() }\n"
    )
    (tmp_path / "engine" / "engine.go").write_text(
        'package engine\nfunc ResolveVelvetLantern() string { return "old" }\n'
    )
    (tmp_path / "route" / "velvet_test.go").write_text(
        'package route\nimport "testing"\nfunc TestVelvet(t *testing.T){}\n'
        "// velvet lantern behavior verification\n"
    )
    with CodeMap(tmp_path) as c:
        c.sync()
        brief = c.task_action_brief(
            "Change the velvet lantern accepted response from old to new"
        )
    assert brief["status"] == "safe-fresh"
    assert brief["edit"] == "engine/engine.go"
    assert brief["verify"] == ["go", "test", "./route"]
    assert (
        brief["owner_path"]
        == "route/route.go --imports--> service/service.go --imports--> engine/engine.go"
    )
