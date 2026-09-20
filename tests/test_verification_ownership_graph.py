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
        "def launch_manifest_foundation():\n"
        "    return 'foundation'\n",
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
        "def test_structural_launch_contract():\n"
        "    assert True\n",
        encoding="utf-8",
    )

    task = (
        "Refactor launch_manifest_foundation structural launch contract "
        "without changing behavior"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        relevance = codemap.verification_relevance(
            task, limit=20, candidate_limit=16
        )

    selected = relevance["selected"]
    assert selected["path"] == "tests/test_launch_foundation.py"
    assert selected["direct_reference"] is True
    assert selected["reference_symbols"] == ["launch_manifest_foundation"]
    assert selected["selection_reason"] == (
        "unique-exact-reference-plus-namespace-locality"
    )
    by_path = {row["path"]: row for row in relevance["candidates"]}
    assert by_path["tests/test_wrapper.py"]["indirect_reference"] is True

