from __future__ import annotations

from pathlib import Path

from hashmarks.codemap.engine import CodeMap


def _bindings() -> list[dict[str, object]]:
    return [
        {
            "binding_id": "source:direct",
            "evidence": [
                {"path": "source.py", "start_line": 1, "end_line": 1},
            ],
        },
        {
            "binding_id": "source:stable-range",
            "evidence": [
                {"path": "source.py", "start_line": 2, "end_line": 2},
            ],
        },
        {
            "binding_id": "unrelated",
            "evidence": [
                {"path": "unrelated.py", "start_line": 1, "end_line": 1},
            ],
        },
    ]


def _delta_by_id(delta: dict[str, object]) -> dict[str, dict[str, object]]:
    return {row["binding_id"]: row for row in delta["bindings"]["changed"]}


def test_relationship_fact_change_is_path_shared_but_range_impact_stays_local(
    tmp_path: Path,
) -> None:
    (tmp_path / "alpha.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "beta.py").write_text("VALUE = 1\n", encoding="utf-8")
    source = tmp_path / "source.py"
    source.write_text("from alpha import VALUE\nKEEP = 1\n", encoding="utf-8")
    (tmp_path / "unrelated.py").write_text("OTHER = 1\n", encoding="utf-8")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(_bindings())

        source.write_text("from beta import VALUE\nKEEP = 1\n", encoding="utf-8")
        codemap.sync(["source.py"])
        after = codemap.repository_evidence_bindings(_bindings())
        delta = codemap.repository_evidence_binding_delta(before, after)
        coverage = codemap.repository_evidence_coverage(
            after,
            changed_paths=["source.py"],
            change_set_complete=True,
            binding_delta=delta,
            binding_delta_before=before,
        )

    changed = _delta_by_id(delta)
    assert set(changed) == {"source:direct", "source:stable-range"}

    direct = changed["source:direct"]
    stable = changed["source:stable-range"]
    assert direct["direct_evidence"]["state"] == "changed"
    assert stable["direct_evidence"]["state"] == "preserved"

    for row in (direct, stable):
        relationships = row["relationship_evidence"]
        assert relationships["state"] == "changed"
        assert relationships["comparability"] == "comparable"
        assert relationships["facts"]["state"] == "changed"
        assert relationships["locators"]["state"] == "preserved"

    assert delta["bindings"]["preserved"] == ["unrelated"]
    assert coverage["binding_impacts"] == [
        {
            "binding_id": "source:direct",
            "reasons": [
                "bound-member-changed",
                "bound-range-content-changed",
                "relationship-evidence-changed",
            ],
        },
        {
            "binding_id": "source:stable-range",
            "reasons": [
                "bound-member-changed",
                "relationship-evidence-changed",
            ],
        },
    ]


def test_relationship_locator_move_stays_separate_and_does_not_leak_bindings(
    tmp_path: Path,
) -> None:
    (tmp_path / "dependency.py").write_text("VALUE = 1\n", encoding="utf-8")
    source = tmp_path / "source.py"
    source.write_text(
        "from dependency import VALUE\nPAD = 0\nKEEP = 1\n",
        encoding="utf-8",
    )
    (tmp_path / "unrelated.py").write_text("OTHER = 1\n", encoding="utf-8")
    bindings = [
        {
            "binding_id": "source:stable",
            "evidence": [
                {"path": "source.py", "start_line": 3, "end_line": 3},
            ],
        },
        {
            "binding_id": "unrelated",
            "evidence": [
                {"path": "unrelated.py", "start_line": 1, "end_line": 1},
            ],
        },
    ]

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(bindings)

        source.write_text(
            "PAD = 0\nfrom dependency import VALUE\nKEEP = 1\n",
            encoding="utf-8",
        )
        codemap.sync(["source.py"])
        after = codemap.repository_evidence_bindings(bindings)
        delta = codemap.repository_evidence_binding_delta(before, after)
        coverage = codemap.repository_evidence_coverage(
            after,
            changed_paths=["source.py"],
            change_set_complete=True,
            binding_delta=delta,
            binding_delta_before=before,
        )

    changed = _delta_by_id(delta)
    assert set(changed) == {"source:stable"}
    row = changed["source:stable"]
    assert row["direct_evidence"]["state"] == "preserved"
    relationships = row["relationship_evidence"]
    assert relationships["state"] == "changed"
    assert relationships["facts"]["state"] == "unchanged"
    assert relationships["locators"]["state"] == "changed"
    assert relationships["observation"]["changed"] is False

    assert delta["bindings"]["preserved"] == ["unrelated"]
    assert coverage["binding_impacts"] == [
        {
            "binding_id": "source:stable",
            "reasons": [
                "bound-member-changed",
                "relationship-locator-changed",
            ],
        }
    ]
