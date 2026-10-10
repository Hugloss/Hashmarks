"""Scope descriptors actually re-observe changed files and bounded relationships."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.evidence_context import describe_evidence_binding_reacquisition


def requery(cm: CodeMap, reference: Any) -> Any:
    query = reference["requery"]
    return cm.repository_evidence_bindings(
        [{"binding_id": query["binding_id"], "evidence": query["evidence"]}],
        dependency_paths={query["binding_id"]: query["dependency_paths"]},
        include_relationships=query["include_relationships"],
        relationship_limit_per_path=query["relationship_limit_per_path"],
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
        cm.sync()
        before: Any = cm.repository_evidence_bindings(
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
        cm.sync()
        after = requery(cm, reference)
        delta: Any = cm.repository_evidence_binding_delta(before, after)
    old, new = before["bindings"][0], after["bindings"][0]
    assert old["binding_definition_identity"] == new["binding_definition_identity"]
    assert old["binding_observation_identity"] != new["binding_observation_identity"]
    assert after["bindings_identity"] != before["bindings_identity"]
    assert new["relationships"]["bounds"]["limit_per_path"] == 1
    assert new["relationships"]["completeness"] == "bounded-not-claimed"
    assert [row["path"] for row in new["dependencies"]] == ["dependency.py"]
    (changed,) = delta["bindings"]["changed"]
    if change == "dependency":
        assert old["evidence"] == new["evidence"]
        assert changed["direct_evidence"]["state"] == "preserved"
        assert changed["declared_dependencies"]["state"] == "affected"
    elif change == "member":
        assert (
            old["evidence"][0]["span_identity"] == new["evidence"][0]["span_identity"]
        )
        assert changed["direct_evidence"]["state"] == "changed"
    elif change == "span":
        assert (
            old["evidence"][0]["span_identity"] != new["evidence"][0]["span_identity"]
        )
    elif change == "relationship":
        assert (
            old["relationships"]["relationships"]
            != new["relationships"]["relationships"]
        )
    elif change == "delete":
        assert all(row["state"] == "known-absent" for row in new["evidence"])
    with CodeMap(root, state_dir=tmp_path / "fresh") as cm:
        cm.sync()
        rebuilt = requery(cm, reference)
    assert rebuilt["bindings"] == after["bindings"]
