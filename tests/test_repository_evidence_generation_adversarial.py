from __future__ import annotations

from pathlib import Path

from hashmarks.codemap.engine import CodeMap


def _binding() -> list[dict[str, object]]:
    return [
        {
            "binding_id": "consumer",
            "evidence": [
                {
                    "path": "owner.py",
                    "start_line": 1,
                    "end_line": 1,
                }
            ],
        }
    ]


def test_unrelated_repository_generation_change_preserves_binding_observation(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("OWNER = 1\n", encoding="utf-8")
    unrelated = tmp_path / "unrelated.py"
    unrelated.write_text("VALUE = 1\n", encoding="utf-8")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(
            _binding(),
            include_relationships=False,
        )

        unrelated.write_text("VALUE = 2\n", encoding="utf-8")
        codemap.sync(["unrelated.py"])
        after = codemap.repository_evidence_bindings(
            _binding(),
            include_relationships=False,
        )

        delta = codemap.repository_evidence_binding_delta(before, after)
        coverage = codemap.repository_evidence_coverage(
            after,
            changed_paths=["unrelated.py"],
            change_set_complete=True,
            binding_delta=delta,
            binding_delta_before=before,
        )

    before_repository = before["repository"]
    after_repository = after["repository"]
    before_binding = before["bindings"][0]
    after_binding = after["bindings"][0]

    assert (
        before_repository["codemap_generation"]
        < after_repository["codemap_generation"]
    )
    assert before_repository["source_identity"] != after_repository["source_identity"]
    assert before["bindings_identity"] != after["bindings_identity"]

    assert (
        before_binding["binding_definition_identity"]
        == after_binding["binding_definition_identity"]
    )
    assert (
        before_binding["binding_observation_identity"]
        == after_binding["binding_observation_identity"]
    )

    assert delta["observer"]["changed"] is False
    assert delta["bindings"] == {
        "added": [],
        "removed": [],
        "preserved": ["consumer"],
        "changed": [],
    }
    assert delta["repository"]["before"] == before_repository
    assert delta["repository"]["after"] == after_repository

    assert coverage["classification"]["outside_declared_bindings"] == [
        "unrelated.py"
    ]
    assert coverage["classification"]["bound_member_precision_unknown"] == []
    assert coverage["binding_impacts"] == []
    assert coverage["coverage"]["state"] == "complete"
    assert coverage["coverage"]["outside_classification"] == "known"
