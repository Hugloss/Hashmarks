from pathlib import Path

from hashmarks.codemap import CodeMap


def test_verification_ownership_is_evidence_only_and_bounded(tmp_path):
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


def test_verification_ownership_v2_links_direct_verifier_to_edit_authority(tmp_path):
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


def test_verification_ownership_v2_does_not_link_wording_only_verifier(tmp_path):
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
        graph = codemap.verification_ownership_graph(
            "Fix ember_snow implementation and verify behavior"
        )
    verifier = next(
        row
        for row in graph["verification_owners"]
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
        action = codemap.task_action_map(task, limit=20)
        graph = codemap.verification_ownership_graph(task, limit=20)

    assert action["edit"]["path"] == "src/launch.py"
    assert action["edit"]["name"] == "launch_manifest_foundation"
    assert action["verify"]["path"] == "tests/test_launch_foundation.py"

    by_path = {row["path"]: row for row in graph["verification_owners"]}
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
        relevance = codemap.verification_relevance(task, limit=20, candidate_limit=16)

    selected = relevance["selected"]
    assert selected["path"] == "tests/test_launch_foundation.py"
    assert selected["direct_reference"] is True
    assert selected["reference_symbols"] == ["launch_manifest_foundation"]
    assert selected["selection_reason"] in {
        "canonical-verification",
        "unique-exact-reference-plus-namespace-locality",
    }
    by_path = {row["path"]: row for row in relevance["candidates"]}
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
        relevance = codemap.verification_relevance(
            "Change policy.evaluate behavior", limit=20, candidate_limit=16
        )

    selected = relevance["selected"]
    assert selected["path"] == "tests/test_policy.py"
    assert selected["direct_reference"] is True
    assert selected["reference_symbols"] == ["evaluate"]
    by_path = {row["path"]: row for row in relevance["candidates"]}
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
        relevance = codemap.verification_relevance(
            "Change policy.evaluate behavior", limit=20, candidate_limit=16
        )

    row = next(
        candidate
        for candidate in relevance["candidates"]
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
        [namespace_candidate, canonical],
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
        [direct, indirect_canonical],
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
        [indirect, unbound_canonical],
        unbound_canonical["path"],
    )
    assert selected == indirect
    assert reason == "unique-bounded-indirect-reference-plus-namespace-locality"


def test_module_alias_call_through_exact_reexport_binds_original_owner(
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
        "try:\n"
        "    from src.owner import target\n"
        "except ModuleNotFoundError:\n"
        "    from owner import target\n",
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
        relevance = codemap.verification_relevance(
            "Change owner.target behavior", limit=20, candidate_limit=16
        )
        action = codemap.task_action_map("Change owner.target behavior", limit=20)

    selected = relevance["selected"]
    assert selected["path"] == "tests/test_owner.py"
    assert selected["direct_reference"] is True
    assert selected["reference_symbols"] == ["target"]
    assert relevance["qualified_identity_ambiguous"] is False
    assert relevance["unresolved_import_identity_paths"] == []
    assert action["edit"]["path"] == "src/owner.py"
    assert action["edit"]["name"] == "target"
    assert action["ambiguity"]["ambiguous"] is False


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
        candidates,
        selected,
        8,
    )

    assert len(bounded) == 8
    assert [row["path"] for row in bounded[:7]] == [
        f"tests/test_decoy_{index}.py" for index in range(7)
    ]
    assert bounded[-1]["path"] == "scripts/tests/test_canonical.py"

    single = CodeMap._verification_bounded_candidates(
        candidates,
        {**selected, "selection_reason": "canonical-verification"},
        1,
    )
    assert single == [selected]
