from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from hashmarks.codemap import CodeMap, CodeMapService, CodeMapServiceClient
from hashmarks.cli import main


def _write_repository(root: Path) -> None:
    (root / "pkg").mkdir()
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "pkg" / "state.py").write_text(
        "CACHE = {}\n"
        "\n"
        "def update(key, value):\n"
        "    current = CACHE.get(key)\n"
        "    CACHE.update({key: value})\n"
        "    return current\n",
        encoding="utf-8",
    )
    (root / "scripts").mkdir()
    (root / "scripts" / "__init__.py").write_text("", encoding="utf-8")
    (root / "scripts" / "loader.py").write_text(
        "from importlib.util import spec_from_file_location, module_from_spec\n"
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        "spec = spec_from_file_location('shadow_state', ROOT / 'pkg' / 'state.py')\n"
        "module = module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n",
        encoding="utf-8",
    )


def test_repository_findings_projects_existing_analyzers_without_low_signal_cache_noise(tmp_path: Path) -> None:
    _write_repository(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        result = codemap.repository_findings()

    assert result["schema"] == "hashmarks.repository-findings.v1"
    assert result["summary"] == {
        "findings": 3,
        "warnings": 2,
        "advisories": 1,
        "categories": {"cache-ownership": 1, "concurrency-risk": 1, "import-identity": 1},
    }
    by_code = {finding["code"]: finding for finding in result["findings"]}
    assert by_code["python-duplicate-module-identity"]["path"] == "scripts/loader.py"
    assert by_code["python-cache-owner-import-identity-risk"]["path"] == "pkg/state.py"
    assert by_code["python-read-modify-write-without-visible-guard"]["path"] == "pkg/state.py"
    assert result["analyzers"]["cache_ownership"]["owners"] >= 1
    assert all(finding["source_schema"].startswith("hashmarks.") for finding in result["findings"])
    assert "execution" in result["boundary"]


def test_repository_findings_path_scope_preserves_repository_import_risk_linkage(tmp_path: Path) -> None:
    _write_repository(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        result = codemap.repository_findings(["pkg/state.py"])

    assert {finding["path"] for finding in result["findings"]} == {"pkg/state.py"}
    assert {finding["code"] for finding in result["findings"]} == {
        "python-cache-owner-import-identity-risk",
        "python-read-modify-write-without-visible-guard",
    }
    assert result["analyzers"]["import_ownership"]["findings"] == 0


def test_cli_map_findings_is_one_step_repository_analysis_surface(tmp_path: Path, capsys) -> None:
    _write_repository(tmp_path)
    assert main(["map", "findings", "--workspace", str(tmp_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "hashmarks.repository-findings.v1"
    assert "python-duplicate-module-identity" in {finding["code"] for finding in payload["findings"]}


def _wait(client: CodeMapServiceClient) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            client.status()
            return
        except (OSError, RuntimeError):
            time.sleep(0.01)
    raise AssertionError("CodeMap service did not become ready")


def test_codemap_service_exposes_repository_findings(tmp_path: Path) -> None:
    _write_repository(tmp_path)
    socket_path = tmp_path / "findings.sock"
    service = CodeMapService(tmp_path, socket_path=socket_path)
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    client = CodeMapServiceClient(tmp_path, socket_path=socket_path)
    _wait(client)
    try:
        result = client.repository_findings()
        assert result["schema"] == "hashmarks.repository-findings.v1"
        assert result["summary"]["findings"] == 3
    finally:
        client.stop()
        thread.join(timeout=5)
