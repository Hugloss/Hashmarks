from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from hashmarks.codemap import CodeMap, CodeMapService, CodeMapServiceClient


def _repo(root: Path) -> tuple[str, str, str]:
    backend = "maven:com.example:api"
    web = "npm:@demo/web"
    mobile = "npm:@demo/mobile"
    (root / "backend" / "src").mkdir(parents=True)
    (root / "web" / "src").mkdir(parents=True)
    (root / "mobile" / "src").mkdir(parents=True)
    (root / "contracts").mkdir()
    (root / "backend" / "pom.xml").write_text(
        "<project><groupId>com.example</groupId><artifactId>api</artifactId><version>1</version></project>"
    )
    (root / "web" / "package.json").write_text(json.dumps({"name": "@demo/web"}))
    (root / "mobile" / "package.json").write_text(json.dumps({"name": "@demo/mobile"}))
    (root / "backend" / "src" / "Api.java").write_text("class Api {}\n")
    (root / "web" / "src" / "api.ts").write_text("export const api = 1;\n")
    (root / "mobile" / "src" / "api.ts").write_text("export const api = 1;\n")
    (root / "contracts" / "api.yaml").write_text("openapi: 3.1.0\n")
    (root / ".hashmarks-project-links.toml").write_text(
        f"[[link]]\nsource='{web}'\ntarget='{backend}'\nkind='api-client'\n"
        f"[[link]]\nsource='{mobile}'\ntarget='{web}'\nkind='mobile-shell'\n"
        f"[[shared_input]]\npath='contracts/api.yaml'\nprojects=['{web}','{backend}']\nkind='contract'\n"
    )
    return backend, web, mobile


def _prepare(codemap: CodeMap) -> None:
    codemap.sync()
    codemap.enrich_projects(("npm-package-graph", "maven-pom-graph", "declared-project-links"))


def test_cross_repository_packet_preserves_provenance_and_freshness(tmp_path: Path) -> None:
    backend, web, mobile = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        _prepare(codemap)
        packet = codemap.cross_repository_evidence_packet(
            "Update backend API implementation", ["backend/src/Api.java"],
        )
        repeated = codemap.cross_repository_evidence_packet(
            "Update backend API implementation", ["backend/src/Api.java"],
        )

    assert packet == repeated
    assert packet["schema"] == "hashmarks.cross-repository-evidence-packet.v1"
    assert packet["source"]["project_identities"] == [backend]
    assert packet["dependents"] == [
        {"project_identity": web, "depth": 1},
        {"project_identity": mobile, "depth": 2},
    ]
    assert {row["producer"] for row in packet["relationships"]} == {"declared-project-links"}
    assert packet["freshness"]["state"] == "dependent"
    assert packet["freshness"]["dependency_state"] == "current"
    assert packet["freshness"]["dependencies"] == [
        {"producer": "declared-project-links", "state": "current"}
    ]
    unresolved_scopes = {row["scope"] for row in packet["unresolved"]}
    assert unresolved_scopes == {"ownership", "verification"}
    assert packet["storage"] == "derived-not-persisted"
    assert packet["execution_effect"] == "none"


def test_shared_input_packet_reports_all_affected_projects(tmp_path: Path) -> None:
    backend, web, mobile = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        _prepare(codemap)
        packet = codemap.cross_repository_evidence_packet(
            "Update shared API contract", ["contracts/api.yaml"],
        )

    projects = {row["project_identity"]: row["depth"] for row in packet["dependents"]}
    assert projects == {backend: 1, web: 1, mobile: 2}
    assert packet["freshness"]["dependency_state"] == "current"


def test_no_cross_repository_evidence_is_explicitly_unresolved(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "owner.py").write_text("VALUE = 1\n")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.cross_repository_evidence_packet("Update owner value", ["src/owner.py"])

    reasons = {row["reason"] for row in packet["unresolved"]}
    assert "no-cross-repository-impact-supported" in reasons
    assert packet["source"]["project_identities"] == []
    assert packet["dependents"] == []
    assert packet["freshness"]["state"] == "unknown"


def test_cross_repository_packet_service_roundtrip(tmp_path: Path) -> None:
    _repo(tmp_path)
    socket_path = tmp_path / "cross-repo.sock"
    service = CodeMapService(tmp_path, socket_path=socket_path)
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    client = CodeMapServiceClient(tmp_path, socket_path=socket_path)
    deadline = time.time() + 5
    while True:
        try:
            client.status()
            break
        except OSError:
            if time.time() >= deadline:
                raise
            time.sleep(0.01)
    try:
        client.sync()
        service._map().enrich_projects(("npm-package-graph", "maven-pom-graph", "declared-project-links"))
        packet = client.repository_intelligence_query(
            "cross-repository", "Update backend API implementation", ["backend/src/Api.java"],
        )["result"]
        assert packet["schema"] == "hashmarks.cross-repository-evidence-packet.v1"
        assert packet["authority"] == "repository-intelligence-only"
    finally:
        client.stop()
        thread.join(timeout=5)
