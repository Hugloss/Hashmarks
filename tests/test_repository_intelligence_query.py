from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

import pytest

from hashmarks import CodeMap
from hashmarks.codemap.repository_intelligence_query import (
    RepositoryIntelligenceQueryOptions,
)
from hashmarks.codemap.service import CodeMapService, CodeMapServiceClient

if TYPE_CHECKING:
    from pathlib import Path


def _repo(root: Path) -> tuple[Path, str]:
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    source = root / "src" / "owner.py"
    source.write_text("def widget(): return 'old'\n", encoding="utf-8")
    (root / "tests" / "test_owner.py").write_text(
        "from src.owner import widget\ndef test_widget(): assert widget() == 'new'\n",
        encoding="utf-8",
    )
    return source, "change widget behavior and verify widget test"


def test_query_facade_delegates_without_changing_producer_semantics(
    tmp_path: Path,
) -> None:
    _source, task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        expected = {
            "change-intelligence": codemap.change_intelligence_brief(
                task, ["src/owner.py"]
            ),
            "freshness": codemap.evidence_freshness_map(task, ["src/owner.py"]),
            "snapshot": codemap.repository_intelligence_snapshot(
                task, ["src/owner.py"]
            ),
            "profile": codemap.repository_intelligence_profile(
                task, ["src/owner.py"], profile="compact"
            ),
            "cross-repository": codemap.cross_repository_evidence_packet(
                task, ["src/owner.py"]
            ),
            "verification-explanation": codemap.explain_verification_selection(
                task, "tests/test_owner.py"
            ),
        }
        actual = {
            surface: codemap.repository_intelligence_query(
                surface,
                task,
                ["src/owner.py"] if surface != "verification-explanation" else (),
                options=RepositoryIntelligenceQueryOptions(
                    member_path=(
                        "tests/test_owner.py"
                        if surface == "verification-explanation"
                        else None
                    )
                ),
            )
            for surface in expected
        }
    for surface, envelope in actual.items():
        assert envelope["schema"] == "hashmarks.repository-intelligence-query.v1"
        assert envelope["surface"] == surface
        assert envelope["producer_schema"] == expected[surface]["schema"]
        assert envelope["result"] == expected[surface]
        assert envelope["storage"] == "derived-not-persisted"
        assert envelope["authority"] == "repository-intelligence-only"
        assert envelope["execution_effect"] == "none"


def test_query_facade_delta_matches_direct_delta(tmp_path: Path) -> None:
    source, task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        previous = codemap.repository_intelligence_snapshot(task, ["src/owner.py"])
        source.write_text("def widget(): return 'new'\n", encoding="utf-8")
        codemap.sync(["src/owner.py"])
        direct = codemap.repository_intelligence_delta(
            task,
            ["src/owner.py"],
            previous_snapshot=previous,
        )
        query = codemap.repository_intelligence_query(
            "delta",
            task,
            ["src/owner.py"],
            options=RepositoryIntelligenceQueryOptions(previous_snapshot=previous),
        )
    assert query["result"] == direct


def test_query_facade_is_deterministic_and_fails_closed(tmp_path: Path) -> None:
    _source, task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        first = codemap.repository_intelligence_query("profile", task, ["src/owner.py"])
        second = codemap.repository_intelligence_query(
            "profile", task, ["src/owner.py"]
        )
        assert first == second
        with pytest.raises(ValueError, match="surface must be one of"):
            codemap.repository_intelligence_query("magic", task, ["src/owner.py"])
        with pytest.raises(ValueError, match="changed_paths must not be empty"):
            codemap.repository_intelligence_query("snapshot", task)
        with pytest.raises(ValueError, match="previous_snapshot is required"):
            codemap.repository_intelligence_query("delta", task, ["src/owner.py"])


def test_query_facade_service_roundtrip(tmp_path: Path) -> None:
    _source, task = _repo(tmp_path)
    socket = tmp_path / "query.sock"
    service = CodeMapService(tmp_path, socket_path=socket)
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    client = CodeMapServiceClient(tmp_path, socket_path=socket)
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
        result = client.repository_intelligence_query(
            "profile",
            task,
            ["src/owner.py"],
            options=RepositoryIntelligenceQueryOptions(profile="compact"),
        )
        assert result["schema"] == "hashmarks.repository-intelligence-query.v1"
        assert result["producer_schema"] == "hashmarks.evidence-profile.v1"
        assert result["result"]["profile"] == "compact"
    finally:
        client.stop()
        thread.join(timeout=5)


def test_service_v2_rejects_removed_direct_repository_intelligence_ops(
    tmp_path: Path,
) -> None:
    _source, task = _repo(tmp_path)
    service = CodeMapService(tmp_path, socket_path=tmp_path / "unused.sock")
    removed = (
        "verification_selection_explanation",
        "change_intelligence_brief",
        "evidence_freshness_map",
        "repository_intelligence_snapshot",
        "repository_intelligence_profile",
        "cross_repository_evidence_packet",
        "repository_intelligence_delta",
        "intelligence_economics_receipt",
    )
    for op in removed:
        with pytest.raises(ValueError, match="unsupported operation"):
            service.dispatch(
                {"protocol": "hashmarks.codemap-service.v2", "op": op, "task": task}
            )


def test_service_client_exposes_single_repository_intelligence_protocol_facade(
    tmp_path: Path,
) -> None:
    client = CodeMapServiceClient(tmp_path, socket_path=tmp_path / "unused.sock")
    assert hasattr(client, "repository_intelligence_query")
    for name in (
        "explain_verification_selection",
        "change_intelligence_brief",
        "evidence_freshness_map",
        "repository_intelligence_snapshot",
        "repository_intelligence_profile",
        "cross_repository_evidence_packet",
        "repository_intelligence_delta",
        "intelligence_economics_receipt",
    ):
        assert not hasattr(client, name)
