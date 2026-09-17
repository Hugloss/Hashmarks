from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from hashmarks.codemap import CodeMap

if TYPE_CHECKING:
    from pathlib import Path


def _repo(root: Path) -> None:
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "owner.py").write_text(
        "def widget(value: str) -> str:\n    return value + '-old'\n"
    )
    (root / "src" / "route.py").write_text(
        "from .owner import widget\n\ndef run(value: str) -> str:\n    return widget(value)\n"
    )
    (root / "tests" / "test_widget.py").write_text(
        "from src.route import run\n\ndef test_widget_contract():\n    assert run('x') == 'x-new'\n"
    )


def _encoded(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def test_profiles_share_one_snapshot_identity_and_are_deterministic(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        profiles = {
            name: codemap.repository_intelligence_profile(
                "Fix widget accepted response behavior",
                ["src/owner.py"],
                profile=name,
            )
            for name in ("compact", "standard", "audit")
        }
        repeated = codemap.repository_intelligence_profile(
            "Fix widget accepted response behavior",
            ["src/owner.py"],
            profile="compact",
        )

    identities = {row["source_snapshot_identity"] for row in profiles.values()}
    assert len(identities) == 1
    assert profiles["compact"] == repeated
    assert (
        profiles["compact"]["profile_identity"]
        != profiles["standard"]["profile_identity"]
    )
    assert (
        profiles["standard"]["profile_identity"]
        != profiles["audit"]["profile_identity"]
    )
    assert len(_encoded(profiles["compact"])) < len(_encoded(profiles["standard"]))
    assert len(_encoded(profiles["standard"])) < len(_encoded(profiles["audit"]))


def test_profile_density_contract_preserves_authoritative_facts(tmp_path: Path) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        compact = codemap.repository_intelligence_profile(
            "Fix widget accepted response behavior",
            ["src/owner.py"],
            profile="compact",
        )
        standard = codemap.repository_intelligence_profile(
            "Fix widget accepted response behavior",
            ["src/owner.py"],
            profile="standard",
        )
        audit = codemap.repository_intelligence_profile(
            "Fix widget accepted response behavior",
            ["src/owner.py"],
            profile="audit",
        )

    compact_evidence = compact["evidence"]
    standard_evidence = standard["evidence"]
    snapshot = audit["evidence"]["snapshot"]
    assert (
        compact_evidence["verification"]["member"] == snapshot["verification"]["member"]
    )
    assert standard_evidence["ownership"] == snapshot["ownership"]
    assert standard_evidence["freshness"] == snapshot["freshness"]
    assert snapshot["verification"]["facts"]
    assert "facts" not in standard_evidence["verification"]
    assert "ownership" not in compact_evidence
    assert compact["storage"] == "derived-not-persisted"
    assert compact["execution_effect"] == "none"


def test_audit_profile_contains_exact_snapshot(tmp_path: Path) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        snapshot = codemap.repository_intelligence_snapshot(
            "Fix widget accepted response behavior",
            ["src/owner.py"],
        )
        audit = codemap._profile_from_snapshot(snapshot, profile="audit")
    assert audit["source_snapshot_identity"] == snapshot["snapshot_identity"]
    assert audit["evidence"]["snapshot"] == snapshot


def test_invalid_profile_fails_closed(tmp_path: Path) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="profile must be one of"):
            codemap.repository_intelligence_profile(
                "Fix widget accepted response behavior",
                ["src/owner.py"],
                profile="tiny",
            )


def test_profile_service_roundtrip(tmp_path: Path) -> None:
    import threading
    import time

    from hashmarks.codemap import CodeMapService, CodeMapServiceClient

    _repo(tmp_path)
    socket_path = tmp_path / "profile.sock"
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
        profile = client.repository_intelligence_query(
            "profile",
            "Fix widget accepted response behavior",
            ["src/owner.py"],
            profile="compact",
        )["result"]
        assert profile["schema"] == "hashmarks.evidence-profile.v1"
        assert profile["profile"] == "compact"
    finally:
        client.stop()
        thread.join(timeout=5)
