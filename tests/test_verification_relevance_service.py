from __future__ import annotations

import threading
import time
from pathlib import Path

from hashmarks.codemap import CodeMapService, CodeMapServiceClient


def _wait(client: CodeMapServiceClient) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            client.status()
            return
        except (OSError, RuntimeError, ConnectionError):
            time.sleep(0.02)
    raise AssertionError("service did not become ready")


def test_service_exposes_verification_relevance(tmp_path: Path) -> None:
    (tmp_path / "packages" / "feature0042" / "tests").mkdir(parents=True)
    (tmp_path / "tests" / "regression").mkdir(parents=True)
    (tmp_path / "packages" / "feature0042" / "service.py").write_text(
        "def apply_policy(value):\n    return value\n"
    )
    expected = "packages/feature0042/tests/test_contract.py"
    (tmp_path / expected).write_text(
        "from packages.feature0042.service import apply_policy\n\n"
        "def test_contract():\n    assert apply_policy(1) == 1\n"
    )
    for index in range(25):
        (tmp_path / "tests" / "regression" / f"test_apply_policy_feature0042_{index:04d}.py").write_text(
            "from packages.feature0042.service import apply_policy\n\n"
            "def test_apply_policy_feature0042():\n    assert apply_policy(1) == 1\n"
        )
    socket_path = tmp_path / "verification.sock"
    service = CodeMapService(tmp_path, socket_path=socket_path)
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    client = CodeMapServiceClient(tmp_path, socket_path=socket_path)
    _wait(client)
    try:
        relevance = client.verification_relevance(
            "Fix apply_policy behavior for feature0042", candidate_limit=2
        )
        assert relevance["selected"]["path"] == expected
        assert len(relevance["candidates"]) == 2
        assert relevance["secret_knowledge_used"] is False
    finally:
        client.stop()
        thread.join(timeout=5)
