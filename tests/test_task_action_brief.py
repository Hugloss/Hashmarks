import json
from pathlib import Path

from hashmarks.codemap import CodeMap


def _repo(root: Path) -> None:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src" / "engine.py").write_text(
        "def widget(value: str) -> str:\n    return value + '-old'\n"
    )
    (root / "tests" / "test_engine.py").write_text(
        "from src.engine import widget\n\ndef test_widget():\n    assert widget('x') == 'x-new'\n"
    )


def test_task_action_brief_is_smaller_than_authority_brief_and_action_complete(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as c:
        c.sync()
        full = c.task_decision_brief("widget implementation test", token_budget=64)
        agent = c.task_action_brief("widget implementation test", token_budget=64)
    assert agent["schema"] == "hashmarks.task-action-brief.v1"
    assert agent["status"] == "safe-fresh"
    assert agent["edit"] == "src/engine.py"
    assert agent["verify"] == full["verification_argv"]
    assert "decision_generation" not in agent
    assert "full_packet_available" not in agent
    assert "safe" not in agent
    assert len(json.dumps(agent, sort_keys=True, separators=(",", ":")).encode()) < len(
        json.dumps(full, sort_keys=True, separators=(",", ":")).encode()
    )


def test_task_action_brief_fails_closed_without_hiding_missing_roles(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as c:
        c.sync()
        agent = c.task_action_brief("widget implementation test", token_budget=1)
    assert agent["status"] == "unsafe"
    assert agent["missing"]


def test_task_action_brief_auto_budget_qualifies_instead_of_assuming_fixed_minimum(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as c:
        c.sync()
        auto = c.task_action_brief("widget implementation test")
        forced_tiny = c.task_action_brief("widget implementation test", token_budget=1)
    assert auto["status"] == "safe-fresh"
    assert forced_tiny["status"] == "unsafe"


def test_task_action_brief_fast_budget_matches_diagnostic_sweep(tmp_path: Path) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as c:
        c.sync()
        sweep = c.task_decision_brief_budget_sweep(
            "widget implementation test", budgets=[1, 32, 64, 96, 128]
        )
        auto = c.task_action_brief(
            "widget implementation test", candidate_budgets=[1, 32, 64, 96, 128]
        )
        expected = c.task_action_brief(
            "widget implementation test", token_budget=sweep["smallest_safe_budget"]
        )
    assert sweep["smallest_safe_budget"] is not None
    assert auto == expected


def test_task_action_brief_auto_budget_does_not_call_diagnostic_sweep(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as c:
        c.sync()

        def forbidden(*args, **kwargs):
            raise AssertionError(
                "diagnostic sweep must not run on production brief path"
            )

        c.task_decision_brief_budget_sweep = forbidden  # type: ignore[method-assign]
        brief = c.task_action_brief("widget implementation test")
    assert brief["status"] == "safe-fresh"


def test_task_action_brief_computes_canonical_action_map_once(tmp_path: Path) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as c:
        c.sync()
        original = c.task_action_map
        calls = 0

        def counted(*args, **kwargs):
            nonlocal calls
            calls += 1
            return original(*args, **kwargs)

        c.task_action_map = counted  # type: ignore[method-assign]
        brief = c.task_action_brief("widget implementation test")
    assert brief["status"] == "safe-fresh"
    assert calls == 1


def test_rare_ticket_action_brief_uses_exact_index_anchor_without_general_find(
    tmp_path: Path,
) -> None:
    (tmp_path / "src" / "abc123").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "archive").mkdir()
    (tmp_path / "src" / "abc123" / "engine_a.py").write_text(
        'def ABC123(): return "old"\n'
    )
    (tmp_path / "src" / "abc123" / "engine_b.py").write_text(
        'def ABC123(): return "old"\n'
    )
    (tmp_path / "src" / "abc123" / "route.py").write_text(
        "from src.abc123.engine_b import ABC123\ndef route_abc123(): return ABC123()\n"
    )
    (tmp_path / "tests" / "test_abc123.py").write_text(
        "from src.abc123.route import route_abc123\n"
        'def test_abc123(): assert route_abc123() == "new"\n'
    )
    (tmp_path / "archive" / "abc123_old.py").write_text(
        'def ABC123(): return "legacy"\n'
    )
    with CodeMap(tmp_path) as c:
        c.sync()
        original_find = c.find
        queries: list[str] = []

        def counted(query: str, *, limit: int = 20):
            queries.append(query)
            return original_find(query, limit=limit)

        c.find = counted  # type: ignore[method-assign]
        brief = c.task_action_brief("For ABC123 change the accepted response")
    assert brief["status"] == "safe-fresh"
    assert brief["edit"] == "src/abc123/engine_b.py"
    assert brief["verify"] == [
        "python",
        "-m",
        "pytest",
        "-q",
        "tests/test_abc123.py::test_abc123",
    ]
    assert queries == []


def test_rare_ticket_fast_path_is_not_used_for_configuration_authority(
    tmp_path: Path,
) -> None:
    (tmp_path / "src" / "abc123").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "abc123" / "engine.py").write_text(
        'def ABC123(): return "old"\n'
    )
    (tmp_path / "src" / "abc123" / "policy.toml").write_text('mode = "old"\n')
    (tmp_path / "tests" / "test_abc123.py").write_text(
        "from src.abc123.engine import ABC123\n"
        'def test_abc123(): assert ABC123() == "new"\n'
    )
    with CodeMap(tmp_path) as c:
        c.sync()

        def forbidden(*args, **kwargs):
            raise AssertionError(
                "configuration authority must use the normal evidence path"
            )

        c._rare_task_anchor_hits = forbidden  # type: ignore[method-assign]
        brief = c.task_action_brief("For ABC123 change the configuration policy")
    assert brief["status"] in {"safe-fresh", "unsafe"}


def test_multi_term_task_local_island_beats_large_generic_vocabulary(
    tmp_path: Path,
) -> None:
    (tmp_path / "src/case").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "vendor").mkdir()
    for index in range(30):
        (tmp_path / "vendor" / f"routing_{index}.py").write_text(
            "def request_response(request):\n    return 'generic response implementation behavior'\n"
        )
    (tmp_path / "src/case/engine.py").write_text(
        "def resolveCobaltGrove():\n    return 'old'\n"
    )
    (tmp_path / "src/case/route.py").write_text(
        "from .engine import resolveCobaltGrove\n\ndef route_value():\n    return resolveCobaltGrove()\n\n# cobalt grove accepted response\n"
    )
    (tmp_path / "tests/test_case.py").write_text(
        "from src.case.route import route_value\n\ndef test_case():\n    assert route_value() == 'new'\n\n# cobalt grove behavior verification\n"
    )
    codemap = CodeMap(tmp_path)
    codemap.sync()
    try:
        brief = codemap.task_action_brief(
            "Change the cobalt grove accepted response from old to new. Update the implementation that drives the request and verify the behavior."
        )
        assert brief["status"] == "safe-fresh"
        assert brief["edit"] == "src/case/engine.py"
        assert brief["verify"][-1].startswith("tests/test_case.py")
    finally:
        codemap.close()


def test_multi_term_island_does_not_activate_when_multiple_tests_share_terms(
    tmp_path: Path,
) -> None:
    (tmp_path / "src/a").mkdir(parents=True)
    (tmp_path / "src/b").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    for name in ("a", "b"):
        (tmp_path / f"src/{name}/engine.py").write_text(
            "def resolve(): return 'old'\n# cobalt grove\n"
        )
        (tmp_path / f"tests/test_{name}.py").write_text(
            f"from src.{name}.engine import resolve\ndef test_{name}(): assert resolve() == 'old'\n# cobalt grove\n"
        )
    codemap = CodeMap(tmp_path)
    codemap.sync()
    try:
        hits = codemap._task_local_lexical_island_hits(
            "cobalt grove behavior", limit=20
        )
        assert hits == ()
    finally:
        codemap.close()


def test_task_action_brief_never_claims_safe_without_edit_target(
    tmp_path: Path,
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_only.py").write_text(
        "def test_only(): assert True\n# scarlet field behavior\n"
    )
    codemap = CodeMap(tmp_path)
    codemap.sync()
    try:
        brief = codemap.task_action_brief(
            "Change the scarlet field behavior and verify it"
        )
        assert brief["status"] == "unsafe"
        assert "edit" not in brief
        assert brief["discrimination"] == "no-supported-owner-candidate"
    finally:
        codemap.close()


def test_multi_term_lexical_island_does_not_intercept_plain_compound_symbol_lookup(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/adapter.py").write_text("class NxImpactAdapter:\n    pass\n")
    (tmp_path / "tests/test_adapter.py").write_text(
        "from src.adapter import NxImpactAdapter\n"
    )
    codemap = CodeMap(tmp_path)
    codemap.sync()
    try:
        assert codemap.find_task("NxImpactAdapter")[0].path == "src/adapter.py"
    finally:
        codemap.close()


def test_task_action_brief_does_not_launder_named_dependency_into_owner(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/publish.py").write_text(
        "def publish_result(value):\n    return value\n", encoding="utf-8"
    )
    (tmp_path / "src/authority.py").write_text(
        "class AuthorityReceipt:\n"
        "    def canonical_identity(self):\n"
        "        return 'canonical'\n",
        encoding="utf-8",
    )
    (tmp_path / "tests/test_publish.py").write_text(
        "from src.publish import publish_result\n"
        "def test_publish(): assert publish_result('x') == 'x'\n",
        encoding="utf-8",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        brief = codemap.task_action_brief(
            "Fix publish_result so it uses AuthorityReceipt.canonical_identity"
        )

    assert brief["edit"] == "src/publish.py"
    assert brief["status"] == "safe-fresh"


def test_task_action_brief_keeps_ambiguous_candidate_out_of_edit_authority(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    for name in ("a", "b"):
        (tmp_path / "src" / f"{name}.py").write_text(
            "def publish_result(value):\n    return value\n", encoding="utf-8"
        )
    (tmp_path / "tests/test_publish.py").write_text(
        "def test_publish(): assert True\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map("Fix publish_result")
        brief = codemap.task_action_brief("Fix publish_result", token_budget=256)

    assert action["edit"]["path"] in {"src/a.py", "src/b.py"}
    assert action["ownership_authority"]["owner_resolved"] is False
    assert action["admitted_edit"] is None
    assert brief["status"] == "unsafe"
    assert "edit" not in brief
    assert brief["candidate"] in {"src/a.py", "src/b.py"}
    assert brief["discrimination"] == "competing-action-roles"


def test_task_action_brief_receipt_is_assembled_inside_decision_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        original = codemap._decision_evidence_receipt

        def observed(*args, **kwargs):
            assert codemap._decision_session_depth > 0
            return original(*args, **kwargs)

        monkeypatch.setattr(codemap, "_decision_evidence_receipt", observed)
        brief = codemap.task_action_brief("widget implementation test", token_budget=64)

    assert brief["status"] == "safe-fresh"



@pytest.mark.parametrize("limit,per_role", [(3, 1), (8, 2), (20, 3)])
def test_ambiguity_is_sticky_across_retrieval_presentation_bounds(
    tmp_path: Path, limit: int, per_role: int
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    for name in ("left", "right"):
        (tmp_path / "src" / f"{name}.py").write_text(
            "def duplicate_owner(value):\n    return value\n", encoding="utf-8"
        )
    (tmp_path / "tests/test_duplicate.py").write_text(
        "def test_duplicate(): assert True\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map(
            "Fix duplicate_owner", limit=limit, per_role=per_role
        )

    assert action["ownership_authority"]["owner_resolved"] is False
    assert action["ownership_authority"]["resolved_owner"] is None
    assert action["ownership_authority"]["candidate_owner"] in {
        "src/left.py",
        "src/right.py",
    }
    assert action["ambiguity"]["ambiguous"] is True
