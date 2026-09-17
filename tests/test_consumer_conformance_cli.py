import json
from pathlib import Path

from scripts.consumer_conformance import main


def test_consumer_conformance_cli_emits_self_checking_vectors(capsys) -> None:
    root = Path(__file__).resolve().parents[1]
    assert main(["--root", str(root)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "hashmarks.consumer-conformance-suite.v1"
    assert len(payload["vectors"]) == 10
    assert all(
        row["result"]["valid"] == row["expected_valid"] for row in payload["vectors"]
    )
    assert payload["execution_authority"] == "external"
    assert payload["result_authority"] == "external"
    assert payload["certification_authority"] == "external"
