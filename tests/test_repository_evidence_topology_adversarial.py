from __future__ import annotations

from pathlib import Path

from hashmarks.codemap.engine import CodeMap


def _binding(binding_id: str, path: str) -> list[dict[str, object]]:
    return [
        {
            "binding_id": binding_id,
            "evidence": [
                {
                    "path": path,
                    "start_line": 1,
                    "end_line": 1,
                }
            ],
        }
    ]


def test_identical_span_bytes_keep_distinct_repository_path_authority(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("VALUE = 1\n", encoding="utf-8")
    bindings = [
        _binding("path:a", "a.py")[0],
        _binding("path:b", "b.py")[0],
    ]

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.repository_evidence_bindings(
            bindings,
            include_relationships=False,
        )

    rows = {row["binding_id"]: row for row in packet["bindings"]}
    first = rows["path:a"]
    second = rows["path:b"]
    first_evidence = first["evidence"][0]
    second_evidence = second["evidence"][0]

    assert first_evidence["path"] == "a.py"
    assert second_evidence["path"] == "b.py"
    assert first_evidence["state"] == second_evidence["state"] == "known-present"
    assert first_evidence["member_revision"] == second_evidence["member_revision"]
    assert first_evidence["span_identity"] == second_evidence["span_identity"]
    assert first["binding_definition_identity"] != second["binding_definition_identity"]
    assert (
        first["binding_observation_identity"] != second["binding_observation_identity"]
    )


def test_same_content_path_relocation_is_definition_change_not_content_change(
    tmp_path: Path,
) -> None:
    source = tmp_path / "a.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(
            _binding("moved", "a.py"),
            include_relationships=False,
        )

        moved = tmp_path / "b.py"
        source.replace(moved)
        codemap.sync(["a.py", "b.py"])
        after = codemap.repository_evidence_bindings(
            _binding("moved", "b.py"),
            include_relationships=False,
        )
        delta = codemap.repository_evidence_binding_delta(before, after)
        coverage = codemap.repository_evidence_coverage(
            after,
            changed_paths=["a.py", "b.py"],
            change_set_complete=True,
            binding_delta=delta,
            binding_delta_before=before,
        )

    before_binding = before["bindings"][0]
    after_binding = after["bindings"][0]
    before_evidence = before_binding["evidence"][0]
    after_evidence = after_binding["evidence"][0]

    assert before_evidence["path"] == "a.py"
    assert after_evidence["path"] == "b.py"
    assert before_evidence["span_identity"] == after_evidence["span_identity"]
    assert before_evidence["member_revision"] == after_evidence["member_revision"]
    assert (
        before_binding["binding_definition_identity"]
        != after_binding["binding_definition_identity"]
    )
    assert (
        before_binding["binding_observation_identity"]
        != after_binding["binding_observation_identity"]
    )

    changed = delta["bindings"]["changed"][0]
    assert changed["binding_id"] == "moved"
    assert changed["definition"]["state"] == "changed"
    assert changed["direct_evidence"]["state"] == "preserved"
    assert changed["locator_evidence"]["state"] == "preserved"
    assert changed["member_evidence"]["state"] == "preserved"
    assert coverage["binding_impacts"] == [
        {
            "binding_id": "moved",
            "reasons": ["binding-definition-changed"],
        }
    ]
