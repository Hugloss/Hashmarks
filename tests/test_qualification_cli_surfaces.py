import json
from pathlib import Path

from scripts.qualification_economics import main as economics_main
from scripts.qualification_handoff import main as handoff_main


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_handoff_cli_emits_external_authority_contract(capsys) -> None:
    assert handoff_main(["--root", str(_root())]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["execution_authority"] == "external"
    assert value["result_authority"] == "external"
    assert value["certification_authority"] == "external"
    assert value["producer"]["implementation_identity"].startswith("sha256:")


def test_economics_cli_reports_membership_preservation_without_execution_policy(
    capsys,
) -> None:
    assert economics_main(["--root", str(_root())]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["exact_total_membership_preserved"] is True
    assert value["ordinary_correctness_members_avoided"] == 7
    assert value["authority"] == "repository-intelligence-economics-only"
    assert value["execution_layout"] == "external"
