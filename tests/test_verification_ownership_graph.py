from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.evidence_presentation import present_repository_evidence


def test_verification_ownership_keeps_unobserved_owner_scope_unknown(
    tmp_path: Path,
) -> None:
    (tmp_path / "backend.py").write_text("def unrelated():\n    return 1\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
    graph = cast(
        dict[str, Any],
        codemap.verification_ownership_graph("Inspect an unknown qx_helix_root task"),
    )
    summary = cast(dict[str, Any], graph["summary"])
    qualification = cast(dict[str, Any], graph["verification_qualification"])
    assert isinstance(summary, dict)
    assert isinstance(qualification, dict)
    assert graph["edit_candidates"] == []
    assert summary["unowned"] is None
    assert summary["ambiguous"] is None
    assert qualification["selection_reason"] == "no-edit-owner"


@pytest.mark.parametrize(
    "admissible,count,returned,expected",
    [
        (False, 0, 0, (None, None)),
        (False, 1, 1, (False, None)),
        (True, 2, 1, (False, True)),
        (True, 0, 0, (True, False)),
        (True, False, 0, (None, None)),
    ],
)
def test_verification_summary_preserves_scope_and_hidden_alternatives(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    admissible: bool,
    count: int,
    returned: int,
    expected: tuple[bool | None, bool | None],
) -> None:
    (tmp_path / "backend.py").write_text("def target42():\n    return 1\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_backend.py").write_text(
        "from backend import target42\n\ndef test_target42():\n    assert target42() == 1\n"
    )
    relevance: dict[str, object] = {
        "candidates": [{"path": "tests/test_backend.py"}] if returned else [],
        "candidate_count": count,
        "selected": None,
        "negative_evidence_admissible": admissible,
        "completeness": "complete" if admissible else "incomplete",
        "truncation": "complete" if admissible else "truncated",
        "bounds": {"returned_candidates": 1},
        "search_bound_reasons": [] if admissible else ["direct-reverse-ref-limit"],
    }
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        # Supply the existing semantic owner's observation to the public graph
        # projection; this test does not nominate edit/verification authority.
        monkeypatch.setattr(
            codemap, "verification_relevance", lambda _task, **_bounds: relevance
        )
        graph = cast(
            dict[str, Any],
            codemap.verification_ownership_graph("Change target42 in backend.py"),
        )
    summary = graph["summary"]
    assert isinstance(summary, dict)
    assert (summary["unowned"], summary["ambiguous"]) == expected
    assert graph["verification_qualification"] == {
        key: value
        for key, value in relevance.items()
        if key not in {"candidates", "selected"}
    }


def test_task_test_match_bounds_do_not_establish_absence(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    for index in range(70):
        (tests / f"test_token_{index:02d}.py").write_text(
            "def test_reset_token():\n    assert True\n"
        )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action: dict[str, object] = codemap.task_action_map("Fix reset_token")
        relevance_before = deepcopy(action["verification_relevance"])
        packet: dict[str, object] = cast(
            "dict[str, object]", codemap.task_evidence("Fix reset_token")
        )
        assert action["verification_relevance"] == relevance_before
    matches: list[dict[str, object]] = cast(
        list[dict[str, object]],
        cast(dict[str, Any], packet["verification"])["relevance"]["task_matches"],
    )

    assert len(matches["matches"]) == 16
    assert matches["observed_in_search"] == 64
    assert matches["omitted_from_projection"] == 48
    assert matches["search_truncated"] is True
    assert matches["negative_evidence_admissible"] is False
    assert matches["source_binding"] == "indexed-not-source-revalidated"
    assert packet["ownership"]["owner"] is None


def test_task_test_matches_preserve_unresolved_ownership_and_selection(
    tmp_path: Path,
) -> None:
    files = {
        "src/alpha.py": "def reset_token(value):\n    return value\n",
        "src/beta.py": "def reset_token(value):\n    return value\n",
        "src/test_reset_token.py": "def reset_token(value):\n    return value\n",
        "tests/test_token.py": "def test_reset_token():\n    assert True\n",
        "tests/test_other.py": "def test_other():\n    assert True\n",
    }
    for name, source in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet: dict[str, object] = cast(
            "dict[str, object]", codemap.task_evidence("Fix reset_token")
        )
    assert packet["ownership"]["owner"] is None
    relevance = packet["verification"]["relevance"]
    assert relevance["selection_changed"] is False
    matches = relevance["task_matches"]
    assert matches["edit_relationship"] == "unestablished"
    assert matches["verification_selection_authority"] is False
    assert matches["negative_evidence_admissible"] is False
    assert [row["path"] for row in matches["matches"]] == ["tests/test_token.py"]
    projection = cast(
        "dict[str, Any]", present_repository_evidence(packet, format="structured")
    )
    finding = next(
        row
        for group in projection["groups"]
        for row in group["findings"]
        if row["kind"] == "lexical_test_term_match"
    )
    assert finding["details"]["path"] == "tests/test_token.py"
    assert finding["assertion"] == "producer_claim"
    assert finding["source_context"]["task_match_qualification"] == {
        key: value for key, value in matches.items() if key != "matches"
    }


def test_lexical_verification_scouts_do_not_claim_references_or_replace_verifier(
    tmp_path: Path,
) -> None:
    files = {
        "src/internals/pipeline.py": "def transform(value):\n    return value\n",
        "src/test_redelivery.py": "def redelivery_ordering(value):\n    return value\n",
        "tests/test_pipeline.py": "from src.internals.pipeline import transform\ndef test_pipeline():\n    assert transform(1) == 1\n",
        "tests/internals/test_a_redelivery.py": "def test_redelivery_ordering():\n    assert True\n",
        "tests/internals/test_b_redelivery.py": "def test_redelivery_ordering():\n    assert True\n",
        "pyproject.toml": "[tool.pytest.ini_options]\ntestpaths=['tests']\n",
    }
    for name, source in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet: dict[str, object] = cast(
            "dict[str, object]",
            codemap.task_evidence(
                "Change transform in src/internals/pipeline.py for redelivery ordering",
                limit=3,
                per_role=1,
            ),
        )
    relevance = cast(dict[str, Any], packet["verification"]["relevance"])
    rows = {
        row["path"]: row for row in cast(list[dict[str, Any]], relevance["candidates"])
    }
    scouts = [rows[f"tests/internals/test_{name}_redelivery.py"] for name in ("a", "b")]
    assert all(
        row["direct_reference"] is False and row["indirect_reference"] is False
        for row in scouts
    )
    assert "src/test_redelivery.py" not in rows
    assert packet["ownership"]["owner"]["path"] == "src/internals/pipeline.py"
    assert relevance["task_matches"]["verification_selection_authority"] is False
    assert "tests/internals/test_a_redelivery.py" in {
        row["path"] for row in relevance["task_matches"]["matches"]
    }


@pytest.mark.parametrize(
    ("exports", "expected_direct", "expected_ambiguous"),
    [
        ("from .a import *\n", True, False),
        ("from .b import *\n", False, False),
        ("from .a import *\nfrom .b import *\n", False, True),
        ("from .a import handle\nfrom .b import handle\n", False, True),
    ],
)
@pytest.mark.parametrize("binding", ["import src.pkg as target", "import src.pkg"])
def test_module_alias_verifier_preserves_export_owner_identity(
    tmp_path: Path,
    exports: str,
    expected_direct: bool,
    expected_ambiguous: bool,
    binding: str,
) -> None:
    receiver = "target" if " as " in binding else "src.pkg"
    files = {
        "src/__init__.py": "",
        "src/pkg/__init__.py": exports,
        "src/pkg/a.py": "def handle(value):\n    return value\n",
        "src/pkg/b.py": "def handle(value):\n    return value + 1\n",
        "tests/test_facade.py": f"{binding}\ndef test_handle():\n    assert {receiver}.handle(1) == 1\n",
    }
    for name, source in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet: dict[str, object] = cast(
            "dict[str, object]", codemap.task_evidence("Change handle in src/pkg/a.py")
        )
    relevance = packet["verification"]["relevance"]
    verifier = next(
        row for row in relevance["candidates"] if row["path"] == "tests/test_facade.py"
    )
    assert verifier["direct_reference"] is expected_direct
    assert relevance["qualified_identity_ambiguous"] is expected_ambiguous
    assert packet["ownership"]["candidate"]["path"] == "src/pkg/a.py"


def test_indirect_verification_reference_requires_the_correct_import_owner(
    tmp_path: Path,
) -> None:
    files = {
        "src/__init__.py": "",
        "src/owner.py": "def normalize_widget(value):\n    return value.strip()\n",
        "src/route.py": "from .owner import normalize_widget\ndef handle_widget(value):\n    return normalize_widget(value)\n",
        "src/unrelated.py": "def handle_widget(value):\n    return value.upper()\n",
        "tests/test_route.py": "from src.route import handle_widget\ndef test_widget():\n    assert handle_widget(' x ') == 'x'\n",
        "tests/test_unrelated.py": "from src.unrelated import handle_widget\ndef test_widget():\n    assert handle_widget('x') == 'X'\n",
        "pyproject.toml": "[tool.pytest.ini_options]\ntestpaths=['tests']\n",
    }
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet: dict[str, object] = cast(
            "dict[str, object]",
            codemap.task_evidence("Change normalize_widget in src/owner.py"),
        )
    assert packet["ownership"]["owner"]["path"] == "src/owner.py"
    rows = {
        row["path"]: row for row in packet["verification"]["relevance"]["candidates"]
    }
    assert rows["tests/test_route.py"]["indirect_reference"] is True
    assert rows["tests/test_route.py"]["indirect_reference_symbols"] == [
        "handle_widget"
    ]
    assert rows["tests/test_unrelated.py"]["indirect_reference"] is False
    assert rows["tests/test_unrelated.py"]["indirect_via_paths"] == []


def test_verification_ownership_is_evidence_only_and_bounded(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths=['tests']\n", encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "thing.py").write_text(
        "def calculate(x):\n return x+1\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "test_thing.py").write_text(
        "from src.thing import calculate\n\ndef test_calculate():\n assert calculate(1)==2\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        graph = codemap.verification_ownership_graph(
            "change calculate behavior", limit=10
        )
    assert graph["schema"] == "hashmarks.verification-ownership.v2"
    assert graph["boundary"].endswith("does not execute or certify verification")
    assert any(v["path"] == "tests/test_thing.py" for v in graph["verification_owners"])
    verifier = next(
        v for v in graph["verification_owners"] if v["path"] == "tests/test_thing.py"
    )
    assert verifier["plan"]["runner"] == "pytest"


def test_verification_ownership_v2_links_direct_verifier_to_edit_authority(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths=['tests']\n", encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "state.py").write_text(
        "CACHE = {}\n\ndef calculate(x):\n return CACHE.get(x, x+1)\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "test_state.py").write_text(
        "from src.state import calculate\n\ndef test_calculate():\n assert calculate(1)==2\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        graph = codemap.verification_ownership_graph(
            "change calculate behavior", limit=10
        )
    assert graph["schema"] == "hashmarks.verification-ownership.v2"
    assert graph["edit_candidates"] == ["src/state.py"]
    authority = graph["edit_authorities"][0]
    assert authority["path"] == "src/state.py"
    verifier = next(
        v for v in graph["verification_owners"] if v["path"] == "tests/test_state.py"
    )
    assert verifier["covers_edit_candidates"] == ["src/state.py"]
    assert verifier["coverage_evidence"] == "direct-reference"
    assert graph["summary"]["verification_links"] == 1
    assert graph["summary"]["unlinked_edit_candidates"] == 0
    assert graph["boundary"].startswith(
        "verification/authority repository evidence only"
    )


def test_verification_ownership_v2_does_not_link_wording_only_verifier(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths=['tests']\n", encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "widget.py").write_text(
        "def calculate(x):\n return x+1\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "test_widget.py").write_text(
        "def test_calculate_contract():\n assert True\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        graph = codemap.verification_ownership_graph(
            "change calculate widget behavior", limit=10
        )
    assert graph["edit_candidates"] == ["src/widget.py"]
    assert graph["verification_owners"]
    assert all(not v["covers_edit_candidates"] for v in graph["verification_owners"])
    assert graph["summary"]["verification_links"] == 0
    assert graph["summary"]["unlinked_edit_candidates"] == 1


def test_dead_verifier_reference_cannot_claim_edit_coverage(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/owner.py").write_text("def ember_snow(value):\n    return value\n")
    (tmp_path / "tests/test_owner.py").write_text(
        "if False:\n    from src.owner import ember_snow\n\ndef test_owner():\n    assert True\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        graph = cast(
            dict[str, Any],
            codemap.verification_ownership_graph(
                "Fix ember_snow implementation and verify behavior"
            ),
        )
    verifier = next(
        row
        for row in cast(list[dict[str, Any]], graph["verification_owners"])
        if row["path"] == "tests/test_owner.py"
    )
    assert verifier["covers_edit_candidates"] == []
    assert verifier["coverage_evidence"] is None
    assert graph["summary"]["unlinked_edit_candidates"] == 1


def test_symbol_scoped_edit_does_not_link_sibling_verifier(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths=['tests']\n", encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/launch.py").write_text(
        "def launch_manifest_foundation():\n"
        "    return 'foundation'\n\n"
        "def runtime_authority_registry():\n"
        "    return 'registry'\n",
        encoding="utf-8",
    )
    (tmp_path / "tests/test_launch_foundation.py").write_text(
        "from src.launch import launch_manifest_foundation\n\n"
        "def test_launch_manifest_foundation():\n"
        "    assert launch_manifest_foundation() == 'foundation'\n",
        encoding="utf-8",
    )
    (tmp_path / "tests/test_runtime_authority_registry.py").write_text(
        "from src.launch import runtime_authority_registry\n\n"
        "def test_runtime_authority_registry():\n"
        "    assert runtime_authority_registry() == 'registry'\n",
        encoding="utf-8",
    )

    task = (
        "Change launch_manifest_foundation behavior and verify "
        "launch_manifest_foundation"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = cast(dict[str, Any], codemap.task_action_map(task, limit=20))
        graph = cast(
            dict[str, Any], codemap.verification_ownership_graph(task, limit=20)
        )

    assert action["edit"]["path"] == "src/launch.py"
    assert action["edit"]["name"] == "launch_manifest_foundation"
    assert action["verify"]["path"] == "tests/test_launch_foundation.py"

    by_path = {
        row["path"]: row
        for row in cast(list[dict[str, Any]], graph["verification_owners"])
    }
    assert by_path["tests/test_launch_foundation.py"]["covers_edit_candidates"] == [
        "src/launch.py"
    ]
    sibling = by_path.get("tests/test_runtime_authority_registry.py")
    if sibling is not None:
        assert sibling["covers_edit_candidates"] == []
        assert sibling["coverage_evidence"] is None


def test_unique_direct_verifier_outranks_indirect_and_canonical_candidates(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths=['tests']\n", encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/launch.py").write_text(
        "def launch_manifest_foundation():\n    return 'foundation'\n",
        encoding="utf-8",
    )
    (tmp_path / "src/wrapper.py").write_text(
        "from src.launch import launch_manifest_foundation\n\n"
        "def run_launch_foundation():\n"
        "    return launch_manifest_foundation()\n",
        encoding="utf-8",
    )
    (tmp_path / "tests/test_launch_foundation.py").write_text(
        "from src.launch import launch_manifest_foundation\n\n"
        "def test_launch_manifest_foundation():\n"
        "    assert launch_manifest_foundation() == 'foundation'\n",
        encoding="utf-8",
    )
    (tmp_path / "tests/test_wrapper.py").write_text(
        "from src.wrapper import run_launch_foundation\n\n"
        "def test_run_launch_foundation():\n"
        "    assert run_launch_foundation() == 'foundation'\n",
        encoding="utf-8",
    )
    (tmp_path / "tests/test_structural_contract.py").write_text(
        "def test_structural_launch_contract():\n    assert True\n",
        encoding="utf-8",
    )

    task = (
        "Refactor launch_manifest_foundation structural launch contract "
        "without changing behavior"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        relevance = cast(
            dict[str, Any],
            codemap.verification_relevance(task, limit=20, candidate_limit=16),
        )

    selected: dict[str, object] = cast(dict[str, object], relevance["selected"])

    assert selected["path"] == "tests/test_launch_foundation.py"
    assert selected["direct_reference"] is True
    assert selected["reference_symbols"] == ["launch_manifest_foundation"]
    assert selected["selection_reason"] in {
        "canonical-verification",
        "unique-exact-reference-plus-namespace-locality",
    }
    by_path = {
        row["path"]: row for row in cast(list[dict[str, Any]], relevance["candidates"])
    }
    assert by_path["tests/test_wrapper.py"]["indirect_reference"] is True


def test_module_alias_call_is_direct_verifier_for_exact_owner(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths=['tests']\n", encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src/policy.py").write_text(
        "def evaluate(value):\n    return value\n",
        encoding="utf-8",
    )
    (tmp_path / "src/other.py").write_text(
        "def evaluate(value):\n    return value\n",
        encoding="utf-8",
    )
    (tmp_path / "tests/test_policy.py").write_text(
        "from src import policy as subject\n\n"
        "def test_evaluate_policy():\n"
        "    assert subject.evaluate('x') == 'x'\n",
        encoding="utf-8",
    )
    (tmp_path / "tests/test_other.py").write_text(
        "from src import other as subject\n\n"
        "def test_evaluate_other():\n"
        "    assert subject.evaluate('x') == 'x'\n",
        encoding="utf-8",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        relevance = cast(
            dict[str, Any],
            codemap.verification_relevance(
                "Change policy.evaluate behavior", limit=20, candidate_limit=16
            ),
        )

    selected: dict[str, object] = cast(dict[str, object], relevance["selected"])

    assert selected["path"] == "tests/test_policy.py"
    assert selected["direct_reference"] is True
    assert selected["reference_symbols"] == ["evaluate"]
    by_path = {
        row["path"]: row for row in cast(list[dict[str, Any]], relevance["candidates"])
    }
    assert by_path["tests/test_other.py"]["direct_reference"] is False


def test_dead_module_alias_call_cannot_claim_direct_verification(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths=['tests']\n", encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src/policy.py").write_text(
        "def evaluate(value):\n    return value\n",
        encoding="utf-8",
    )
    (tmp_path / "tests/test_policy.py").write_text(
        "if False:\n"
        "    from src import policy as subject\n"
        "    subject.evaluate('x')\n\n"
        "def test_placeholder():\n"
        "    assert True\n",
        encoding="utf-8",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        relevance = cast(
            dict[str, Any],
            codemap.verification_relevance(
                "Change policy.evaluate behavior", limit=20, candidate_limit=16
            ),
        )

    row = next(
        candidate
        for candidate in cast(list[dict[str, Any]], relevance["candidates"])
        if candidate["path"] == "tests/test_policy.py"
    )
    assert row["direct_reference"] is False


def test_indirect_namespace_candidate_cannot_displace_reference_bound_canonical_verifier() -> (
    None
):
    canonical = {
        "path": "scripts/tests/test_hosted_dependency_capability.py",
        "direct_reference": False,
        "indirect_reference": True,
        "namespace_overlap": 0,
        "task_anchor_count": 6,
        "canonical_rank": 2,
    }
    namespace_candidate = {
        "path": "backend/tests/unit/repository_tooling/test_test_batches.py",
        "direct_reference": False,
        "indirect_reference": True,
        "namespace_overlap": 1,
        "task_anchor_count": 1,
        "canonical_rank": None,
    }

    selected, reason = CodeMap._verification_select_candidate(
        cast(list[dict[str, object]], [namespace_candidate, canonical]),
        canonical["path"],
    )

    assert selected == canonical
    assert reason == "canonical-verification"


def test_direct_or_unique_indirect_evidence_can_still_improve_weak_canonical_verifier() -> (
    None
):
    indirect_canonical = {
        "path": "tests/test_canonical.py",
        "direct_reference": False,
        "indirect_reference": True,
        "namespace_overlap": 0,
        "task_anchor_count": 3,
        "canonical_rank": 1,
    }
    direct = {
        "path": "tests/test_direct.py",
        "direct_reference": True,
        "indirect_reference": False,
        "namespace_overlap": 0,
        "task_anchor_count": 1,
        "canonical_rank": None,
    }
    selected, reason = CodeMap._verification_select_candidate(
        cast(list[dict[str, object]], [direct, indirect_canonical]),
        indirect_canonical["path"],
    )
    assert selected == direct
    assert reason == "unique-exact-reference-plus-namespace-locality"

    unbound_canonical = {
        **indirect_canonical,
        "direct_reference": False,
        "indirect_reference": False,
    }
    indirect = {
        "path": "tests/test_wrapper.py",
        "direct_reference": False,
        "indirect_reference": True,
        "namespace_overlap": 0,
        "task_anchor_count": 1,
        "canonical_rank": None,
    }
    selected, reason = CodeMap._verification_select_candidate(
        cast(list[dict[str, object]], [indirect, unbound_canonical]),
        cast(str, unbound_canonical["path"]),
    )
    assert selected == indirect
    assert reason == "unique-bounded-indirect-reference-plus-namespace-locality"


@pytest.mark.parametrize("conditional", [False, True])
def test_module_alias_call_uses_the_existing_reexport_authority(
    tmp_path: Path, conditional: bool
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths=['tests']\n", encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src/owner.py").write_text(
        "def target(value):\n    return value\n",
        encoding="utf-8",
    )
    (tmp_path / "src/facade.py").write_text(
        (
            "try:\n"
            "    from src.owner import target\n"
            "except ModuleNotFoundError:\n"
            "    from owner import target\n"
            if conditional
            else "from src.owner import target\n"
        ),
        encoding="utf-8",
    )
    (tmp_path / "tests/test_owner.py").write_text(
        "from src import facade as subject\n\n"
        "def test_target():\n"
        "    assert subject.target('x') == 'x'\n",
        encoding="utf-8",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        relevance = cast(
            dict[str, Any],
            codemap.verification_relevance(
                "Change owner.target behavior", limit=20, candidate_limit=16
            ),
        )
        action = cast(
            dict[str, Any],
            codemap.task_action_map("Change owner.target behavior", limit=20),
        )

    selected: dict[str, object] = cast(dict[str, object], relevance["selected"])

    assert selected["path"] == "tests/test_owner.py"
    # The import resolver admits the unconditional export. Its unsupported
    # conditional binding remains unknown; verification must not reinterpret it.
    assert selected["direct_reference"] is not conditional
    assert selected["reference_symbols"] == ([] if conditional else ["target"])
    assert relevance["qualified_identity_ambiguous"] is conditional
    assert relevance["unresolved_import_identity_paths"] == (
        ["tests/test_owner.py"] if conditional else []
    )
    assert action["edit"]["path"] == "src/owner.py"
    assert action["edit"]["name"] == "target"
    assert action["ambiguity"]["ambiguous"] is conditional


def test_module_alias_local_override_cannot_claim_reexported_owner(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths=['tests']\n", encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src/owner.py").write_text(
        "def target(value):\n    return value\n",
        encoding="utf-8",
    )
    (tmp_path / "src/facade.py").write_text(
        "from src.owner import target\n\ndef target(value):\n    return 'facade'\n",
        encoding="utf-8",
    )
    (tmp_path / "tests/test_facade.py").write_text(
        "from src import facade as subject\n\n"
        "def test_target():\n"
        "    assert subject.target('x') == 'facade'\n",
        encoding="utf-8",
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        relevance = codemap.verification_relevance(
            "Change owner.target behavior", limit=20, candidate_limit=16
        )

    row = next(
        candidate
        for candidate in relevance["candidates"]
        if candidate["path"] == "tests/test_facade.py"
    )
    assert row["direct_reference"] is False
    assert relevance["qualified_identity_ambiguous"] is False


def test_bounded_verification_candidates_always_retain_selected_verifier() -> None:
    candidates = [
        {
            "path": f"tests/test_decoy_{index}.py",
            "direct_reference": False,
            "indirect_reference": True,
            "namespace_overlap": 1,
            "task_anchor_count": 1,
            "canonical_rank": None,
        }
        for index in range(9)
    ]
    selected = {
        "path": "scripts/tests/test_canonical.py",
        "direct_reference": False,
        "indirect_reference": True,
        "namespace_overlap": 0,
        "task_anchor_count": 4,
        "canonical_rank": 1,
    }
    candidates.append(selected)

    bounded = CodeMap._verification_bounded_candidates(
        cast(list[dict[str, object]], candidates),
        selected,
        8,
    )

    assert len(bounded) == 8
    assert [row["path"] for row in bounded[:7]] == [
        f"tests/test_decoy_{index}.py" for index in range(7)
    ]
    assert bounded[-1]["path"] == "scripts/tests/test_canonical.py"

    single = CodeMap._verification_bounded_candidates(
        cast(list[dict[str, object]], candidates),
        {**selected, "selection_reason": "canonical-verification"},
        1,
    )
    assert single == [selected]
