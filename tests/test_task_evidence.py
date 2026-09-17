import json
from pathlib import Path

from hashmarks import cli
from hashmarks.codemap import CodeMap


def _semantic_repo(root: Path) -> None:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src" / "engine.py").write_text(
        "def normalize_widget(value: str) -> dict[str, object]:\n"
        "    cleaned = value.strip()\n"
        "    return {'value': cleaned, 'length': len(value)}\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_engine.py").write_text(
        "from src.engine import normalize_widget\n\n"
        "def test_normalize_widget_semantics():\n"
        "    assert normalize_widget('  AbC  ') == {'value': 'abc', 'length': 3}\n",
        encoding="utf-8",
    )


def _task() -> str:
    return (
        "Change normalize_widget so it lowercases the trimmed value and reports "
        "the length after trimming. Verify normalize_widget semantics."
    )


def test_task_evidence_supplies_exact_edit_source_and_verify_command(
    tmp_path: Path,
) -> None:
    _semantic_repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        start = codemap.task_evidence(_task(), token_budget=512)

    assert start["schema"] == "hashmarks.task-evidence.v1"
    assert start["status"] == "safe-fresh"
    assert start["edit"] == "src/engine.py"
    assert start["verify"] == [
        "python",
        "-m",
        "pytest",
        "-q",
        "tests/test_engine.py::test_normalize_widget_semantics",
    ]
    assert start["verify_path"] == "tests/test_engine.py"
    assert start["source_budget"]["complete"] is True
    assert start["edit_evidence"]["representation"] == "source-range"
    assert "len(value)" in start["edit_evidence"]["content"]
    # The verification argv is a mechanically derived repository-bound description; its source body is
    # intentionally not preloaded into the consumer's starting context.
    assert "'length': 3" not in json.dumps(start, sort_keys=True)
    assert start["next_read"] is None


def test_task_evidence_never_emits_partial_source_when_exact_range_exceeds_budget(
    tmp_path: Path,
) -> None:
    _semantic_repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        start = codemap.task_evidence(_task(), token_budget=4)

    assert start["status"] == "safe-fresh"
    assert start["source_budget"]["complete"] is False
    assert start["next_read"]["reason"] == "exact-source-range-exceeds-start-budget"
    # A tiny budget may carry no structural fallback at all, but it must never
    # return a clipped implementation body as if it were complete evidence.
    assert (
        start["edit_evidence"] is None
        or start["edit_evidence"]["representation"] != "source-range"
    )


def test_task_evidence_respects_outline_only_policy(tmp_path: Path) -> None:
    _semantic_repo(tmp_path)
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "src/**"\nvisibility = "outline"\n', encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        start = codemap.task_evidence(_task(), token_budget=512)

    assert start["edit_evidence"]
    assert start["edit_evidence"]["representation"] in {"signature", "outline"}
    assert "len(value)" not in json.dumps(start, sort_keys=True)
    assert start["next_read"]["reason"] == "source-body-not-authorized"
    assert start["source_budget"]["complete"] is False


def test_task_evidence_fails_closed_before_disclosing_evidence_without_edit_authority(
    tmp_path: Path,
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_only.py").write_text(
        "def test_scarlet_field():\n    assert True\n# scarlet field behavior\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        start = codemap.task_evidence("Change the scarlet field behavior and verify it")

    assert start["status"] == "unsafe"
    assert start["edit_evidence"] is None
    assert start["next_read"] is None
    assert start["discrimination"] == "no-safe-edit-candidate"


def test_task_evidence_computes_action_map_once(tmp_path: Path) -> None:
    _semantic_repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        original = codemap.task_action_map
        calls = 0

        def counted(*args, **kwargs):
            nonlocal calls
            calls += 1
            return original(*args, **kwargs)

        codemap.task_action_map = counted  # type: ignore[method-assign]
        start = codemap.task_evidence(_task())

    assert start["status"] == "safe-fresh"
    assert calls == 1


def test_task_evidence_cli_exposes_native_start_packet(tmp_path: Path, capsys) -> None:
    _semantic_repo(tmp_path)
    assert (
        cli.main(
            [
                "--workspace",
                str(tmp_path),
                "task-evidence",
                _task(),
                "--budget",
                "512",
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["schema"] == "hashmarks.task-evidence.v1"
    assert output["edit"] == "src/engine.py"
    assert output["source_budget"]["complete"] is True


def test_task_evidence_and_owner_graph_never_cross_agent_deny_boundary(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "hidden").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "hidden" / "engine.py").write_text(
        "def cobalt_owner() -> str:\n    return 'implementation-secret'\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "route.py").write_text(
        "from hidden.engine import cobalt_owner\n\n"
        "def cobalt_route() -> str:\n    return cobalt_owner()\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_route.py").write_text(
        "from src.route import cobalt_route\n\n"
        "def test_cobalt_route():\n    assert cobalt_route() == 'new'\n",
        encoding="utf-8",
    )
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "hidden/**"\nvisibility = "deny"\n', encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        graph = codemap.ownership_relation_graph(
            "Change cobalt route behavior and verify it",
            "tests/test_route.py",
            max_depth=3,
        )
        start = codemap.task_evidence("Change cobalt route behavior and verify it")

    encoded = json.dumps({"graph": graph, "start": start}, sort_keys=True)
    assert "hidden/engine.py" not in encoded
    assert "implementation-secret" not in encoded
    assert start.get("edit") != "hidden/engine.py"


def test_task_evidence_qualification_freezes_before_secret_join(tmp_path: Path) -> None:
    from scripts.agent_evaluation.generate_hard_agent_corpus import generate
    from scripts.agent_evaluation.score_agent_start import run

    repo = tmp_path / "repo"
    public = tmp_path / "public.json"
    secret = tmp_path / "secret.json"
    output = tmp_path / "qualification.json"
    generate(repo, public, secret, cases_per_category=1)
    payload = run(repo, public, secret, output, token_budget=1536)

    assert payload["summary"]["tasks"] == 6
    assert payload["summary"]["fully_correct"] == 6
    assert payload["summary"]["stable_packets"] == 6
    assert payload["protocol"]["secret_join_after_two_frozen_passes"] is True
    assert payload["summary"]["source_complete"] == 6
    assert payload["summary"]["next_read_reasons"] == {}
    assert payload["summary"]["provenance_complete"] == 6
    assert payload["summary"]["revision_current"] == 6
    assert sum(payload["summary"]["freshness_states"].values()) == 6
    assert payload["categories"]["configuration-ownership"]["source_complete"] == 1


def test_task_evidence_keeps_typescript_test_path_when_runner_is_project_scoped(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tsconfig.json").write_text(
        '{"compilerOptions":{"strict":true,"module":"NodeNext","moduleResolution":"NodeNext"}}\n',
        encoding="utf-8",
    )
    (tmp_path / "src" / "engine.ts").write_text(
        'export function acceptedResponse(): string { return "old"; }\n',
        encoding="utf-8",
    )
    (tmp_path / "tests" / "cobalt.test.ts").write_text(
        'import { acceptedResponse } from "../src/engine.js";\n'
        "// TSCOBALT41 route behavior\n"
        'if (acceptedResponse() !== "new") throw new Error("mismatch");\n',
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        start = codemap.task_evidence(
            "For TSCOBALT41 change the accepted response from old to new and verify the route behavior",
            token_budget=512,
        )
    assert start["status"] == "safe-fresh"
    assert start["edit"] == "src/engine.ts"
    assert start["verify"] == ["tsc", "--noEmit", "-p", "tsconfig.json"]
    assert start["verify_path"] == "tests/cobalt.test.ts"
    encoded = json.dumps(start, sort_keys=True)
    assert "throw new Error" not in encoded
