from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from hashmarks import CodeMap
from hashmarks.codemap.change_impact import ChangeImpactOptions
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


def test_economics_receipt_measures_hashmarks_owned_evidence_only(
    tmp_path: Path,
) -> None:
    _source, task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        receipt = codemap.intelligence_economics_receipt(task, ["src/owner.py"])
    assert receipt["schema"] == "hashmarks.intelligence-economics-receipt.v1"
    rows = receipt["profile_economics"]
    assert (
        rows["compact"]["serialized_bytes"]
        < rows["standard"]["serialized_bytes"]
        < rows["audit"]["serialized_bytes"]
    )
    assert rows["compact"]["saved_vs_audit_bytes"] > 0
    assert receipt["evidence_counts"]["changed_paths"] == 1
    assert receipt["measurement"]["unit"] == "serialized-json-utf8-bytes"
    excluded = set(receipt["measurement"]["excluded"])
    assert {
        "model-tokens",
        "tool-calls",
        "execution-attempts",
        "billing",
        "certification",
    } <= excluded
    assert receipt["storage"] == "derived-not-persisted"
    assert receipt["authority"] == "repository-intelligence-only"
    assert receipt["execution_effect"] == "none"


def test_economics_receipt_is_deterministic_and_identity_bound(tmp_path: Path) -> None:
    _source, task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        first = codemap.intelligence_economics_receipt(task, ["src/owner.py"])
        second = codemap.intelligence_economics_receipt(task, ["src/owner.py"])
        snapshot = codemap.repository_intelligence_snapshot(task, ["src/owner.py"])
    assert first == second
    assert first["source_snapshot_identity"] == snapshot["snapshot_identity"]


def test_economics_receipt_delta_economics_use_existing_delta_authority(
    tmp_path: Path,
) -> None:
    source, task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        previous = codemap.repository_intelligence_snapshot(task, ["src/owner.py"])
        source.write_text("def widget(): return 'new'\n", encoding="utf-8")
        codemap.sync(["src/owner.py"])
        receipt = codemap.intelligence_economics_receipt(
            task, ["src/owner.py"], previous_snapshot=previous
        )
    delta = receipt["delta_economics"]
    assert delta["from_snapshot_identity"] == previous["snapshot_identity"]
    assert delta["to_snapshot_identity"] == receipt["source_snapshot_identity"]
    assert delta["delta_bytes"] > 0
    assert delta["retransmit_pair_bytes"] > 0


def test_economics_receipt_applies_typed_impact_bounds(tmp_path: Path) -> None:
    _source, task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        receipt = codemap.intelligence_economics_receipt(
            task,
            ["src/owner.py"],
            options=ChangeImpactOptions(
                impact_limit_per_surface=2,
                max_depth=1,
            ),
        )

    assert receipt["bounds"]["depth"] == 1
    assert receipt["bounds"]["per_surface"] == 2


def test_query_facade_exposes_economics_without_changing_receipt(
    tmp_path: Path,
) -> None:
    _source, task = _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        direct = codemap.intelligence_economics_receipt(task, ["src/owner.py"])
        query = codemap.repository_intelligence_query(
            "economics", task, ["src/owner.py"]
        )
    assert query["producer_schema"] == "hashmarks.intelligence-economics-receipt.v1"
    assert query["result"] == direct


def test_economics_service_roundtrip(tmp_path: Path) -> None:
    _source, task = _repo(tmp_path)
    socket = tmp_path / "economics.sock"
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
        receipt = client.repository_intelligence_query(
            "economics", task, ["src/owner.py"]
        )["result"]
        assert receipt["schema"] == "hashmarks.intelligence-economics-receipt.v1"
    finally:
        client.stop()
        thread.join(timeout=5)
