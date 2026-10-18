from __future__ import annotations

from pathlib import Path

from contract_assertions import assert_object, assert_records, assert_text

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
    return {
        assert_text(row["binding_id"]): row
        for row in assert_records(assert_object(delta["bindings"])["changed"])
    }


def test_relationship_fact_change_is_path_shared_but_range_impact_stays_local(
    tmp_path: Path,
) -> None:
    (tmp_path / "alpha.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "beta.py").write_text("VALUE = 1\n", encoding="utf-8")
    source = tmp_path / "source.py"
    source.write_text("from alpha import VALUE\nKEEP = 1\n", encoding="utf-8")
    (tmp_path / "unrelated.py").write_text("OTHER = 1\n", encoding="utf-8")

    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        before = codemap.bindings.observe(_bindings())

        source.write_text("from beta import VALUE\nKEEP = 1\n", encoding="utf-8")
        codemap.index.sync(["source.py"])
        after = codemap.bindings.observe(_bindings())
        delta = codemap.bindings.delta(before, after)
        coverage = codemap.bindings.coverage(
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
    assert assert_object(direct["direct_evidence"])["state"] == "changed"
    assert assert_object(stable["direct_evidence"])["state"] == "preserved"

    for row in (direct, stable):
        relationships = assert_object(row["relationship_evidence"])
        assert relationships["state"] == "changed"
        assert relationships["comparability"] == "comparable"
        assert assert_object(relationships["facts"])["state"] == "changed"
        assert assert_object(relationships["locators"])["state"] == "unchanged"

    assert assert_object(delta["bindings"])["preserved"] == ["unrelated"]
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
        codemap.index.sync()
        before = codemap.bindings.observe(bindings)

        source.write_text(
            "PAD = 0\nfrom dependency import VALUE\nKEEP = 1\n",
            encoding="utf-8",
        )
        codemap.index.sync(["source.py"])
        after = codemap.bindings.observe(bindings)
        delta = codemap.bindings.delta(before, after)
        coverage = codemap.bindings.coverage(
            after,
            changed_paths=["source.py"],
            change_set_complete=True,
            binding_delta=delta,
            binding_delta_before=before,
        )

    changed = _delta_by_id(delta)
    assert set(changed) == {"source:stable"}
    row = changed["source:stable"]
    assert assert_object(row["direct_evidence"])["state"] == "preserved"
    relationships = assert_object(row["relationship_evidence"])
    assert relationships["state"] == "changed"
    assert assert_object(relationships["facts"])["state"] == "unchanged"
    assert assert_object(relationships["locators"])["state"] == "changed"
    assert assert_object(relationships["observation"])["changed"] is False

    assert assert_object(delta["bindings"])["preserved"] == ["unrelated"]
    assert coverage["binding_impacts"] == [
        {
            "binding_id": "source:stable",
            "reasons": [
                "bound-member-changed",
                "relationship-locator-changed",
            ],
        }
    ]
