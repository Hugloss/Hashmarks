from pathlib import Path

from hashmarks.codemap import CodeMap


def _repo(root: Path) -> None:
    (root / "src/case").mkdir(parents=True)
    (root / "tests/case").mkdir(parents=True)
    (root / "src/__init__.py").write_text("")
    (root / "src/case/__init__.py").write_text("")
    (root / "src/case/engine.py").write_text(
        "def apply_case(value: str) -> str:\n    return value + '-active'\n"
    )
    (root / "src/case/route.py").write_text(
        "from .engine import apply_case\n\ndef handle_ember(value: str) -> str:\n    return apply_case(value)\n"
    )
    (root / "src/case/legacy.py").write_text(
        "def handle_ember(value: str) -> str:\n    return value + '-legacy'\n\ndef apply_case(value: str) -> str:\n    return value + '-duplicate'\n"
    )
    (root / "tests/case/test_behavior.py").write_text(
        "from src.case.route import handle_ember\n\ndef test_ember_contract():\n    assert handle_ember('x') == 'x-active'\n"
    )
    (root / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths=['tests']\n"
    )


def test_structural_owner_follows_active_test_route_engine_chain(tmp_path: Path):
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "Fix ember accepted response behavior owner", limit=20
        )
    assert action["verify"]["path"] == "tests/case/test_behavior.py"
    assert action["edit"]["path"] == "src/case/engine.py"
    assert action["ownership_resolution"]["depth"] == 2
    assert action["ownership_resolution"]["secret_knowledge_used"] is False


def test_structural_owner_does_not_choose_unreachable_duplicate_legacy_symbol(
    tmp_path: Path,
):
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "Fix ember accepted response behavior owner", limit=20
        )
    assert action["edit"]["path"] != "src/case/legacy.py"


def test_explicit_policy_task_keeps_configuration_authority(tmp_path: Path):
    _repo(tmp_path)
    (tmp_path / "src/case/policy.toml").write_text("mode='active'\nfeature='ember'\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "Change ember policy config for accepted response", limit=20
        )
    assert action["ownership_resolution"] is None
    assert action["edit"]["path"] == "src/case/policy.toml"


def test_contract_named_verification_surface_never_overrides_structural_edit_owner(
    tmp_path: Path,
):
    _repo(tmp_path)
    checks = tmp_path / "checks/case"
    checks.mkdir(parents=True)
    (checks / "test_contract.py").write_text(
        "from src.case.route import handle_ember\n\ndef test_ember_contract():\n    assert handle_ember('x').endswith('-active')\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "Repair ember behavior and identify its contract verification outside default tests",
            limit=20,
        )
    assert action["verify"]["path"] == "checks/case/test_contract.py"
    assert action["edit"]["path"] == "src/case/engine.py"
    assert action["edit"]["path"] != action["verify"]["path"]


def test_ownership_relation_graph_exposes_typed_owner_path(tmp_path: Path):
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        graph = codemap.ownership_relation_graph(
            "Fix ember accepted response behavior owner",
            "tests/case/test_behavior.py",
            max_depth=2,
        )
    assert graph["schema"] == "hashmarks.ownership-relation-graph.v1"
    assert graph["selected"] == "src/case/engine.py"
    assert graph["owner_path"] == [
        {
            "from": "tests/case/test_behavior.py",
            "to": "src/case/route.py",
            "relation": "imports",
        },
        {
            "from": "src/case/route.py",
            "to": "src/case/engine.py",
            "relation": "imports",
        },
    ]
    assert all(edge["to"] != "src/case/legacy.py" for edge in graph["edges"])
    assert graph["secret_knowledge_used"] is False


def test_ownership_relation_graph_is_cycle_safe(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/__init__.py").write_text("")
    (tmp_path / "src/a.py").write_text("from .b import b\n\ndef a():\n    return b()\n")
    (tmp_path / "src/b.py").write_text(
        'from .a import a\n\ndef b():\n    return "ok"\n'
    )
    (tmp_path / "tests/test_cycle.py").write_text(
        'from src.a import a\n\ndef test_cycle():\n    assert a() == "ok"\n'
    )
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths=['tests']\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        graph = codemap.ownership_relation_graph(
            "Fix cycle behavior", "tests/test_cycle.py", max_depth=4
        )
    assert graph["cycle_count"] >= 1
    assert (
        graph["cycle_policy"]
        == "bounded-ancestor-cycle-cutoff-plus-revisit-deduplication"
    )
    assert len(graph["edges"]) < 12
    assert graph["selected"] in {"src/a.py", "src/b.py"}


def test_decision_brief_carries_compact_owner_path(tmp_path: Path):
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        brief = codemap.task_decision_brief(
            "Fix ember accepted response behavior owner"
        )
    assert brief["edit"]["path"] == "src/case/engine.py"
    assert brief["owner_path"][-1] == {
        "from": "src/case/route.py",
        "to": "src/case/engine.py",
        "relation": "imports",
    }


def test_import_alone_nominates_but_does_not_prove_owner(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/__init__.py").write_text("")
    (tmp_path / "src/wrapper.py").write_text("from src.worker import run\n")
    (tmp_path / "src/worker.py").write_text("def run():\n    return 1\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        graph = codemap.ownership_relation_graph(
            "Change unrelated behavior", "src/wrapper.py", max_depth=2
        )
    assert graph["candidates"]
    assert graph["selected"] is None
    assert (
        graph["relation_authority"]
        == "imports-and-calls-are-evidence-not-ownership-truth"
    )


def test_unique_third_hop_call_delegation_refines_owner(tmp_path: Path) -> None:
    (tmp_path / "src/case").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "package.json").write_text('{"type":"module"}\n')
    (tmp_path / "tsconfig.json").write_text(
        '{"compilerOptions":{"module":"NodeNext","moduleResolution":"NodeNext","target":"ES2022"},"include":["src/**/*.ts","tests/**/*.ts"]}\n'
    )
    (tmp_path / "src/case/engine.ts").write_text(
        'export function resolveFrostedMeadow(){ return "old" as const; }\n'
    )
    (tmp_path / "src/case/service.ts").write_text(
        'import { resolveFrostedMeadow } from "./engine.js";\nexport function serviceValue(){ return resolveFrostedMeadow(); }\n'
    )
    (tmp_path / "src/case/route.ts").write_text(
        'import { serviceValue } from "./service.js";\nexport function routeValue(){ return serviceValue(); }\n\n\n// frosted meadow accepted response\n'
    )
    (tmp_path / "tests/frosted.test.ts").write_text(
        'import { routeValue } from "../src/case/route.js";\nconst actual: "new" = routeValue();\nvoid actual;\n// frosted meadow behavior\n'
    )
    codemap = CodeMap(tmp_path)
    codemap.sync()
    try:
        brief = codemap.task_action_brief(
            "Change the frosted meadow accepted response from old to new and verify it"
        )
        assert brief["edit"] == "src/case/engine.ts"
        assert "service.ts --imports--> src/case/engine.ts" in brief["owner_path"]
        graph = codemap.ownership_relation_graph(
            "frosted meadow accepted response", "tests/frosted.test.ts", max_depth=3
        )
        assert graph["selection_reason"] == "unique-task-local-delegation-continuation"
    finally:
        codemap.close()


def test_third_hop_multiple_call_targets_do_not_guess_deeper_owner(
    tmp_path: Path,
) -> None:
    (tmp_path / "src/case").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "package.json").write_text('{"type":"module"}\n')
    (tmp_path / "tsconfig.json").write_text(
        '{"compilerOptions":{"module":"NodeNext","moduleResolution":"NodeNext","target":"ES2022"},"include":["src/**/*.ts","tests/**/*.ts"]}\n'
    )
    (tmp_path / "src/case/a.ts").write_text(
        'export function firstFrosted(){ return "old" as const; }\n'
    )
    (tmp_path / "src/case/b.ts").write_text(
        'export function secondFrosted(){ return "old" as const; }\n'
    )
    (tmp_path / "src/case/service.ts").write_text(
        'import { firstFrosted } from "./a.js";\nimport { secondFrosted } from "./b.js";\nexport function serviceValue(){ return firstFrosted() + secondFrosted(); }\n'
    )
    (tmp_path / "src/case/route.ts").write_text(
        'import { serviceValue } from "./service.js";\nexport function routeValue(){ return serviceValue(); }\n// frosted meadow accepted response\n'
    )
    (tmp_path / "tests/frosted.test.ts").write_text(
        'import { routeValue } from "../src/case/route.js";\nvoid routeValue();\n// frosted meadow behavior\n'
    )
    codemap = CodeMap(tmp_path)
    codemap.sync()
    try:
        graph = codemap.ownership_relation_graph(
            "frosted meadow accepted response", "tests/frosted.test.ts", max_depth=3
        )
        assert graph["selected"] == "src/case/service.ts"
        assert graph["selection_reason"] == "bounded-two-hop-corroboration"
    finally:
        codemap.close()
