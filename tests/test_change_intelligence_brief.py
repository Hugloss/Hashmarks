from __future__ import annotations

import json
import threading
import time
from typing import TYPE_CHECKING

from hashmarks.codemap import CodeMap
from hashmarks.codemap.service import CodeMapService, CodeMapServiceClient

if TYPE_CHECKING:
    from pathlib import Path


def _repo(root: Path) -> str:
    (root / "src" / "case").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "__init__.py").write_text("")
    (root / "src" / "case" / "__init__.py").write_text("")
    (root / "src" / "case" / "engine.py").write_text(
        "def ember(v): return v + '-old'\n"
    )
    (root / "src" / "case" / "route.py").write_text(
        "from .engine import ember\ndef handle(v): return ember(v)\n"
    )
    (root / "tests" / "test_ember.py").write_text(
        "from src.case.route import handle\ndef test_ember(): assert handle('x') == 'x-new'\n"
    )
    (root / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\npythonpath=['.']\n"
    )
    return "Fix ember implementation and verify behavior"


def test_change_intelligence_brief_is_compact_identity_bound_repository_truth(
    tmp_path: Path,
) -> None:
    task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.task_decision_packet(task)
        brief = codemap.change_intelligence_brief(task, ["src/case/engine.py"])

    assert brief["schema"] == "hashmarks.change-intelligence-brief.v1"
    assert brief["authority"] == "repository-intelligence-only"
    assert brief["execution_effect"] == "none"
    assert brief["completeness"] == "not-claimed"
    assert (
        brief["repository"]["repository_identity"]
        == packet["identity"]["repository_identity"]
    )
    assert brief["changed"][0]["revision"]
    assert "ember" in brief["changed"][0]["symbols"]
    assert brief["verification"]["member"] == "tests/test_ember.py"
    assert brief["verification"]["explanation_identity"].startswith("sha256:")
    assert brief["affected"]["verification"][0]["path"] == "tests/test_ember.py"
    assert len(json.dumps(brief, sort_keys=True)) < len(
        json.dumps(packet, sort_keys=True)
    )
    encoded = json.dumps(brief, sort_keys=True)
    assert '"argv"' not in encoded
    assert '"content"' not in encoded


def test_verification_explanation_selected_and_why_not_are_deterministic(
    tmp_path: Path,
) -> None:
    task = _repo(tmp_path)
    (tmp_path / "tests" / "test_other.py").write_text("def test_other(): assert True\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        first = codemap.explain_verification_selection(task)
        second = codemap.explain_verification_selection(task)
        why_not = codemap.explain_verification_selection(task, "tests/test_other.py")
        absent = codemap.explain_verification_selection(task, "tests/not_present.py")

    assert first == second
    assert first["status"] == "selected"
    assert first["member"] == "tests/test_ember.py"
    assert first["authority"] == "repository-intelligence-only"
    assert why_not["status"] in {"not-selected", "insufficient-evidence"}
    assert why_not["reason"] in {
        "lower-bounded-verification-evidence",
        "canonical-selection-retained",
        "not-in-bounded-candidate-set",
    }
    assert absent["status"] == "insufficient-evidence"
    assert absent["reason"] == "not-in-bounded-candidate-set"
    assert absent["explanation_identity"] != first["explanation_identity"]


def _wait(client: CodeMapServiceClient) -> None:
    for _ in range(100):
        try:
            client.status()
            return
        except OSError:
            time.sleep(0.01)
    raise AssertionError("service did not start")


def test_service_exposes_change_brief_and_verification_explanation(
    tmp_path: Path,
) -> None:
    task = _repo(tmp_path)
    socket_path = tmp_path / "hm.sock"
    service = CodeMapService(tmp_path, socket_path=socket_path)
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    client = CodeMapServiceClient(tmp_path, socket_path=socket_path)
    _wait(client)
    try:
        brief = client.repository_intelligence_query(
            "change-intelligence", task, ["src/case/engine.py"]
        )["result"]
        explanation = client.repository_intelligence_query(
            "verification-explanation", task, member_path="tests/test_ember.py"
        )["result"]
        assert brief["verification"]["member"] == "tests/test_ember.py"
        assert explanation["status"] == "selected"
    finally:
        client.stop()
        thread.join(timeout=5)
