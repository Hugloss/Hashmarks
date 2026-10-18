"""Scope descriptors actually re-observe changed files and bounded relationships."""

from __future__ import annotations

from pathlib import Path

import pytest
from contract_assertions import (
    assert_array,
    assert_integer,
    assert_object,
    assert_records,
    assert_text,
)

from hashmarks.codemap import CodeMap
from hashmarks.evidence_context import describe_evidence_binding_reacquisition


def requery(cm: CodeMap, reference: dict[str, object]) -> dict[str, object]:
    query = assert_object(reference["requery"])
    binding_id = assert_text(query["binding_id"])
    include_relationships = query["include_relationships"]
    assert isinstance(include_relationships, bool)
    return cm.bindings.observe(
        [{"binding_id": binding_id, "evidence": assert_records(query["evidence"])}],
        dependency_paths={
            binding_id: [
                assert_text(path) for path in assert_array(query["dependency_paths"])
            ]
        },
        include_relationships=include_relationships,
        relationship_limit_per_path=assert_integer(
            query["relationship_limit_per_path"]
        ),
    )


def _change_input(root: Path, change: str) -> None:
    if change == "member":
        (root / "source.py").write_text(
            (root / "source.py").read_text() + "\nVALUE = 9\n"
        )
    elif change in ("span", "relationship"):
        (root / "source.py").write_text(
            "from other import other\n\ndef source():\n    return other()\n"
        )
    elif change == "dependency":
        (root / "dependency.py").write_text("def target():\n    return 5\n")
    else:
        (root / "source.py").unlink()


@pytest.mark.parametrize(
    "change", ["member", "span", "dependency", "relationship", "delete"]
)
def test_reacquisition_preserves_definition_but_observes_current_change(
    tmp_path: Path, change: str
) -> None:
    root, state = tmp_path / "repo", tmp_path / "state"
    root.mkdir()
    (root / "source.py").write_text(
        "from dependency import target\n\ndef source():\n    return target()\n"
    )
    (root / "dependency.py").write_text("def target():\n    return 1\n")
    (root / "other.py").write_text("def other():\n    return 2\n")
    with CodeMap(root, state_dir=state) as cm:
        cm.index.sync()
        before = cm.bindings.observe(
            [
                {
                    "binding_id": "consumer:source",
                    "evidence": [
                        {"scope": "member", "path": "source.py"},
                        {
                            "scope": "lines",
                            "path": "source.py",
                            "start_line": 1,
                            "end_line": 1,
                        },
                    ],
                }
            ],
            dependency_paths={"consumer:source": ["dependency.py"]},
            include_relationships=True,
            relationship_limit_per_path=1,
        )
    reference = describe_evidence_binding_reacquisition(
        before, binding_id="consumer:source"
    )
    assert reference["current_freshness_proven"] is False
    _change_input(root, change)
    with CodeMap(root, state_dir=state) as cm:
        cm.index.sync()
        after = requery(cm, reference)
        delta = cm.bindings.delta(before, after)
    old, new = (
        assert_records(before["bindings"])[0],
        assert_records(after["bindings"])[0],
    )
    assert old["binding_definition_identity"] == new["binding_definition_identity"]
    assert old["binding_observation_identity"] != new["binding_observation_identity"]
    assert after["bindings_identity"] != before["bindings_identity"]
    assert (
        assert_object(assert_object(new["relationships"])["bounds"])["limit_per_path"]
        == 1
    )
    assert assert_object(new["relationships"])["completeness"] == "bounded-not-claimed"
    assert [row["path"] for row in assert_records(new["dependencies"])] == [
        "dependency.py"
    ]
    (changed,) = assert_records(assert_object(delta["bindings"])["changed"])
    if change == "dependency":
        assert old["evidence"] == new["evidence"]
        assert assert_object(changed["direct_evidence"])["state"] == "preserved"
        assert assert_object(changed["declared_dependencies"])["state"] == "affected"
    elif change == "member":
        assert (
            assert_records(old["evidence"])[0]["span_identity"]
            == assert_records(new["evidence"])[0]["span_identity"]
        )
        assert assert_object(changed["direct_evidence"])["state"] == "changed"
    elif change == "span":
        assert (
            assert_records(old["evidence"])[0]["span_identity"]
            != assert_records(new["evidence"])[0]["span_identity"]
        )
    elif change == "relationship":
        assert (
            assert_object(old["relationships"])["relationships"]
            != assert_object(new["relationships"])["relationships"]
        )
    elif change == "delete":
        assert all(
            row["state"] == "known-absent" for row in assert_records(new["evidence"])
        )
    with CodeMap(root, state_dir=tmp_path / "fresh") as cm:
        cm.index.sync()
        rebuilt = requery(cm, reference)
    assert rebuilt["bindings"] == after["bindings"]
