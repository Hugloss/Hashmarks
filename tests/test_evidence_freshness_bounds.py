from __future__ import annotations

from pathlib import Path

import pytest
from contract_assertions import assert_records

from hashmarks.codemap import CodeMap


@pytest.mark.parametrize(
    ("snapshot", "expected"),
    [
        (None, (False, "no freshness snapshot")),
        (
            {"bind_generation": True, "generation": "bad"},
            (False, "invalid generation snapshot"),
        ),
        (
            {"bind_generation": False, "manifests": ["pom.xml"]},
            (False, "invalid manifest snapshot"),
        ),
        (
            {"bind_generation": False, "manifests": {"pom.xml": "old"}},
            (False, "manifest changed: pom.xml"),
        ),
        ({"bind_generation": False, "manifests": {"pom.xml": "current"}}, (True, None)),
    ],
)
def test_evidence_freshness_rejects_unproven_snapshot_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    snapshot: dict[str, object] | None,
    expected: tuple[bool, str | None],
) -> None:
    with CodeMap(tmp_path) as codemap:
        monkeypatch.setattr(
            codemap.native, "_evidence_snapshot", lambda *args: snapshot
        )
        monkeypatch.setattr(codemap.native, "_manifest_digest", lambda path: "current")
        assert codemap.native._evidence_fresh("project", "provider") == expected


def test_project_provenance_traversal_is_bounded_and_ordered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    edges = [
        {"source": "D", "target": "B", "kind": "declared", "producer": "p"},
        {"source": "C", "target": "A", "kind": "declared", "producer": "p"},
        {
            "source": "A",
            "target": "B",
            "kind": "import",
            "producer": "p",
            "confidence": "inferred",
        },
        {"source": "B", "target": "C", "kind": "declared", "producer": "p"},
    ]
    with CodeMap(tmp_path) as codemap:
        monkeypatch.setattr(codemap.native, "_fresh_project_edges", lambda: edges)
        assert codemap.native._fresh_project_dependents_with_provenance(
            {"B"}, limit=0
        ) == {
            "roots": ["B"],
            "affected": [],
            "edges": [],
        }
        bounded = codemap.native._fresh_project_dependents_with_provenance(
            {"B"}, max_depth=3, limit=2
        )
        full = codemap.native._fresh_project_dependents_with_provenance(
            {"B"}, max_depth=3, limit=4
        )
        edges.reverse()
        assert (
            codemap.native._fresh_project_dependents_with_provenance(
                {"B"}, max_depth=3, limit=2
            )
            == bounded
        )
        assert (
            codemap.native._fresh_project_dependents_with_provenance(
                {"B"}, max_depth=3, limit=4
            )
            == full
        )
    assert bounded["affected"] == [
        {"project": "A", "depth": 1},
        {"project": "D", "depth": 1},
    ]
    assert full["affected"] == [
        {"project": "A", "depth": 1},
        {"project": "D", "depth": 1},
        {"project": "C", "depth": 2},
    ]
    expected = [
        {
            "from": "A",
            "to": "B",
            "kind": "import",
            "producer": "p",
            "confidence": "inferred",
        },
        {"from": "C", "to": "A", "kind": "declared", "producer": "p"},
        {"from": "D", "to": "B", "kind": "declared", "producer": "p"},
    ]
    assert (
        sorted(assert_records(full["edges"]), key=lambda row: str(row["from"]))
        == expected
    )
    assert sorted(
        assert_records(bounded["edges"]), key=lambda row: str(row["from"])
    ) == [
        expected[0],
        expected[2],
    ]
