from pathlib import Path

from hashmarks.codemap import CodeMap

def test_verification_ownership_is_evidence_only_and_bounded(tmp_path):
    (tmp_path/"pyproject.toml").write_text("[tool.pytest.ini_options]\ntestpaths=['tests']\n",encoding="utf-8")
    (tmp_path/"src").mkdir(); (tmp_path/"tests").mkdir()
    (tmp_path/"src"/"thing.py").write_text("def calculate(x):\n return x+1\n",encoding="utf-8")
    (tmp_path/"tests"/"test_thing.py").write_text(
        "from src.thing import calculate\n\ndef test_calculate():\n assert calculate(1)==2\n",encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        graph=codemap.verification_ownership_graph("change calculate behavior",limit=10)
    assert graph["schema"]=="hashmarks.verification-ownership.v2"
    assert graph["boundary"].endswith("does not execute or certify verification")
    assert any(v["path"]=="tests/test_thing.py" for v in graph["verification_owners"])
    verifier=next(v for v in graph["verification_owners"] if v["path"]=="tests/test_thing.py")
    assert verifier["plan"]["runner"]=="pytest"


def test_verification_ownership_v2_links_direct_verifier_to_edit_authority(tmp_path):
    (tmp_path/"pyproject.toml").write_text("[tool.pytest.ini_options]\ntestpaths=['tests']\n",encoding="utf-8")
    (tmp_path/"src").mkdir(); (tmp_path/"tests").mkdir()
    (tmp_path/"src"/"state.py").write_text("CACHE = {}\n\ndef calculate(x):\n return CACHE.get(x, x+1)\n",encoding="utf-8")
    (tmp_path/"tests"/"test_state.py").write_text(
        "from src.state import calculate\n\ndef test_calculate():\n assert calculate(1)==2\n",encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync(); graph=codemap.verification_ownership_graph("change calculate behavior",limit=10)
    assert graph["schema"]=="hashmarks.verification-ownership.v2"
    assert graph["edit_candidates"]==["src/state.py"]
    authority=graph["edit_authorities"][0]
    assert authority["path"]=="src/state.py"
    verifier=next(v for v in graph["verification_owners"] if v["path"]=="tests/test_state.py")
    assert verifier["covers_edit_candidates"]==["src/state.py"]
    assert verifier["coverage_evidence"]=="direct-reference"
    assert graph["summary"]["verification_links"]==1
    assert graph["summary"]["unlinked_edit_candidates"]==0
    assert graph["boundary"].startswith("verification/authority repository evidence only")


def test_verification_ownership_v2_does_not_link_wording_only_verifier(tmp_path):
    (tmp_path/"pyproject.toml").write_text("[tool.pytest.ini_options]\ntestpaths=['tests']\n",encoding="utf-8")
    (tmp_path/"src").mkdir(); (tmp_path/"tests").mkdir()
    (tmp_path/"src"/"widget.py").write_text("def calculate(x):\n return x+1\n",encoding="utf-8")
    (tmp_path/"tests"/"test_widget.py").write_text("def test_calculate_contract():\n assert True\n",encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync(); graph=codemap.verification_ownership_graph("change calculate widget behavior",limit=10)
    assert graph["edit_candidates"]==["src/widget.py"]
    assert graph["verification_owners"]
    assert all(not v["covers_edit_candidates"] for v in graph["verification_owners"])
    assert graph["summary"]["verification_links"]==0
    assert graph["summary"]["unlinked_edit_candidates"]==1


def test_dead_verifier_reference_cannot_claim_edit_coverage(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/owner.py").write_text("def ember_snow(value):\n    return value\n")
    (tmp_path / "tests/test_owner.py").write_text(
        "if False:\n    from src.owner import ember_snow\n\ndef test_owner():\n    assert True\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        graph = codemap.verification_ownership_graph("Fix ember_snow implementation and verify behavior")
    verifier = next(row for row in graph["verification_owners"] if row["path"] == "tests/test_owner.py")
    assert verifier["covers_edit_candidates"] == []
    assert verifier["coverage_evidence"] is None
    assert graph["summary"]["unlinked_edit_candidates"] == 1
