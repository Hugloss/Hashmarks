from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from hashmarks.codemap import CodeMapService, CodeMapServiceClient

if TYPE_CHECKING:
    from pathlib import Path


def _wait(client: CodeMapServiceClient) -> dict:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            return client.status()
        except (OSError, RuntimeError, ConnectionError):
            time.sleep(0.02)
    raise AssertionError("service did not become ready")


def test_codemap_service_shares_one_warm_authority(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "adapter.py").write_text("class NxImpactAdapter:\n    pass\n")
    (tmp_path / "tests" / "test_adapter.py").write_text(
        "from src.adapter import NxImpactAdapter\n"
    )
    socket_path = tmp_path / "service.sock"
    service = CodeMapService(tmp_path, socket_path=socket_path)
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    client_a = CodeMapServiceClient(tmp_path, socket_path=socket_path)
    client_b = CodeMapServiceClient(tmp_path, socket_path=socket_path)
    status = _wait(client_a)
    try:
        assert status["ownership"] == "single-warm-codemap"
        assert status["syncs"] == 1
        assert client_a.find_task("NxImpactAdapter")[0]["path"] == "src/adapter.py"
        action = client_b.task_action_map("NxImpactAdapter implementation test")
        assert action["edit"]["path"] == "src/adapter.py"
        assert action["verify"]["path"] == "tests/test_adapter.py"
        packet = client_b.task_decision_packet("NxImpactAdapter implementation test")
        assert packet["discrimination"]["needed"] is False
        after = client_a.status()
        assert after["syncs"] == 1
        assert after["requests"] >= 4
    finally:
        client_a.stop()
        thread.join(timeout=5)
    assert not thread.is_alive()
    assert not socket_path.exists()


def test_codemap_service_decision_brief(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "engine.py").write_text("def widget(): return 1\n")
    (tmp_path / "tests" / "test_engine.py").write_text(
        "from src.engine import widget\ndef test_widget(): assert widget() == 1\n"
    )
    socket_path = tmp_path / "brief.sock"
    service = CodeMapService(tmp_path, socket_path=socket_path)
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    client = CodeMapServiceClient(tmp_path, socket_path=socket_path)
    _wait(client)
    try:
        brief = client.task_decision_brief("widget implementation test")
        assert brief["schema"] == "hashmarks.task-decision-brief.v1"
        assert brief["edit"]["path"] == "src/engine.py"
        assert brief["verify"]["path"] == "tests/test_engine.py"
        assert brief["full_packet_available"] is True
    finally:
        client.stop()
        thread.join(timeout=5)


def test_service_refresh_after_change_brief_avoids_full_packet_surface(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "src" / "owner.py").write_text("def widget(): return 'old'\n")
    (tmp_path / "tests" / "test_owner.py").write_text(
        "from src.owner import widget\ndef test_widget(): assert widget() == 'new'\n"
    )
    socket_path = tmp_path / "refresh-brief.sock"
    service = CodeMapService(tmp_path, socket_path=socket_path)
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    client = CodeMapServiceClient(tmp_path, socket_path=socket_path)
    _wait(client)
    try:
        (tmp_path / "src" / "owner.py").write_text("def widget(): return 'new'\n")
        refreshed = client.refresh_after_change_brief(
            "widget implementation test", ["src/owner.py"]
        )
        assert refreshed["schema"] == "hashmarks.post-change-refresh-brief.v1"
        assert refreshed["scope"] == "changed-paths-only"
        assert "packet" not in refreshed
        assert refreshed["decision_brief"]["edit"]["path"] == "src/owner.py"
    finally:
        client.stop()
        thread.join(timeout=5)


def test_codemap_service_decision_brief_budget_sweep(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "engine.py").write_text("def widget(): return 1\n")
    (tmp_path / "tests" / "test_engine.py").write_text(
        "from src.engine import widget\ndef test_widget(): assert widget() == 2\n"
    )
    socket_path = tmp_path / "budget-sweep.sock"
    service = CodeMapService(tmp_path, socket_path=socket_path)
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    client = CodeMapServiceClient(tmp_path, socket_path=socket_path)
    _wait(client)
    try:
        sweep = client.task_decision_brief_budget_sweep(
            "widget implementation test", budgets=[1, 64, 128, 512]
        )
        assert sweep["schema"] == "hashmarks.task-decision-brief-budget-sweep.v1"
        assert sweep["rows"][0]["safe"] is False
        assert sweep["smallest_safe_budget"] in {64, 128, 512}
    finally:
        client.stop()
        thread.join(timeout=5)


def test_codemap_service_task_action_brief(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "engine.py").write_text("def widget(): return 1\n")
    (tmp_path / "tests" / "test_engine.py").write_text(
        "from src.engine import widget\ndef test_widget(): assert widget() == 2\n"
    )
    socket_path = tmp_path / "agent-action.sock"
    service = CodeMapService(tmp_path, socket_path=socket_path)
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    client = CodeMapServiceClient(tmp_path, socket_path=socket_path)
    _wait(client)
    try:
        brief = client.task_action_brief("widget implementation test", token_budget=64)
        assert brief["schema"] == "hashmarks.task-action-brief.v1"
        assert brief["status"] == "safe-fresh"
        assert brief["edit"] == "src/engine.py"
        assert isinstance(brief["verify"], list)
    finally:
        client.stop()
        thread.join(timeout=5)


def test_service_agent_task_start_returns_bounded_source_evidence(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "engine.py").write_text(
        "def normalize_widget(value: str) -> str:\n    return value.strip()\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_engine.py").write_text(
        "from src.engine import normalize_widget\n"
        "def test_normalize_widget(): assert normalize_widget(' A ') == 'a'\n",
        encoding="utf-8",
    )
    socket_path = tmp_path / "start.sock"
    service = CodeMapService(tmp_path, socket_path=socket_path)
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    client = CodeMapServiceClient(tmp_path, socket_path=socket_path)
    _wait(client)
    try:
        start = client.task_evidence(
            "Change normalize_widget to lowercase the trimmed value and verify normalize_widget",
            token_budget=512,
        )
        assert start["schema"] == "hashmarks.task-evidence.v1"
        assert start["status"] == "safe-fresh"
        assert start["edit"] == "src/engine.py"
        assert start["source_budget"]["complete"] is True
        assert start["edit_evidence"]["representation"] == "source-range"
        assert "test_normalize_widget" not in start["edit_evidence"]["content"]
    finally:
        client.stop()
        thread.join(timeout=5)


def test_codemap_service_exposes_import_ownership_diagnostic(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "scripts" / "helper.py").write_text("CACHE = {}\n", encoding="utf-8")
    (tmp_path / "scripts" / "loader.py").write_text(
        "from importlib.util import spec_from_file_location, module_from_spec\n"
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        "spec = spec_from_file_location('scripts.helper', ROOT / 'scripts' / 'helper.py')\n"
        "module = module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n",
        encoding="utf-8",
    )
    socket_path = tmp_path / "import-ownership.sock"
    service = CodeMapService(tmp_path, socket_path=socket_path)
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    client = CodeMapServiceClient(tmp_path, socket_path=socket_path)
    _wait(client)
    try:
        result = client.import_ownership_findings()
        assert result["schema"] == "hashmarks.import-ownership.v2"
        assert result["summary"]["warnings"] == 1
        assert result["findings"][0]["target_module"] == "scripts.helper"
    finally:
        client.stop()
        thread.join(timeout=5)


def test_codemap_service_exposes_v01115_ownership_intelligence_surfaces(
    tmp_path: Path,
) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "state.py").write_text(
        "CACHE = {}\n\ndef read(key):\n    return CACHE.get(key)\n\ndef write(key, value):\n    current = CACHE.get(key)\n    CACHE.update({key: value})\n    return current\n",
        encoding="utf-8",
    )
    (tmp_path / "pkg" / "consumer.py").write_text(
        "from pkg.state import CACHE\n\ndef get(key):\n    return CACHE.get(key)\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_state.py").write_text(
        "from pkg.state import read\n\ndef test_read():\n    assert read('x') is None\n",
        encoding="utf-8",
    )
    socket_path = tmp_path / "ownership-intelligence.sock"
    service = CodeMapService(tmp_path, socket_path=socket_path)
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    client = CodeMapServiceClient(tmp_path, socket_path=socket_path)
    _wait(client)
    try:
        cache = client.cache_ownership_findings()
        invalidation = client.cache_invalidation_ownership_graph(["pkg/state.py"])
        authority = client.repository_ownership_graph()
        concurrency = client.concurrency_risk_findings(["pkg/state.py"])
        verification = client.verification_ownership_graph(
            "Fix read behavior in pkg state", candidate_limit=4
        )
        assert cache["schema"] == "hashmarks.cache-ownership.v1"
        assert invalidation["schema"] == "hashmarks.cache-invalidation-ownership.v1"
        assert authority["schema"] == "hashmarks.authority-ownership-graph.v3"
        assert concurrency["schema"] == "hashmarks.concurrency-risk.v1"
        assert verification["schema"] == "hashmarks.verification-ownership.v2"
    finally:
        client.stop()
        thread.join(timeout=5)
