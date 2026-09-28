from __future__ import annotations

from pathlib import Path

from hashmarks.codemap.engine import CodeMap


def _binding(binding_id: str, evidence_path: str) -> dict[str, object]:
    return {
        "binding_id": binding_id,
        "evidence": [
            {
                "path": evidence_path,
                "start_line": 1,
                "end_line": 1,
            }
        ],
    }


def _changed_by_id(delta: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        row["binding_id"]: row
        for row in delta["bindings"]["changed"]
    }


def test_equal_dependency_bytes_at_new_path_are_definition_change_not_observation_change(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("stable\n", encoding="utf-8")
    (tmp_path / "dep-a.lock").write_text("same\n", encoding="utf-8")
    (tmp_path / "dep-b.lock").write_text("same\n", encoding="utf-8")
    binding = [_binding("consumer", "owner.py")]

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(
            binding,
            dependency_paths={"consumer": ["dep-a.lock"]},
            include_relationships=False,
        )
        after = codemap.repository_evidence_bindings(
            binding,
            dependency_paths={"consumer": ["dep-b.lock"]},
            include_relationships=False,
        )
        delta = codemap.repository_evidence_binding_delta(before, after)
        coverage = codemap.repository_evidence_coverage(
            after,
            changed_paths=[],
            change_set_complete=True,
            binding_delta=delta,
            binding_delta_before=before,
        )

    before_binding = before["bindings"][0]
    after_binding = after["bindings"][0]
    before_dependency = before_binding["dependencies"][0]
    after_dependency = after_binding["dependencies"][0]

    assert before_dependency["path"] == "dep-a.lock"
    assert after_dependency["path"] == "dep-b.lock"
    assert (
        before_dependency["member_revision"]
        == after_dependency["member_revision"]
    )
    assert (
        before_binding["binding_definition_identity"]
        != after_binding["binding_definition_identity"]
    )

    changed = delta["bindings"]["changed"][0]
    declared = changed["declared_dependencies"]
    assert declared["state"] == "definition-changed"
    assert declared["definition"] == {
        "state": "changed",
        "added": ["dep-b.lock"],
        "removed": ["dep-a.lock"],
    }
    assert declared["observations"] == {
        "state": "unchanged",
        "changes": [],
    }
    assert changed["direct_evidence"]["state"] == "preserved"
    assert changed["member_evidence"]["state"] == "preserved"
    assert coverage["binding_impacts"] == [
        {
            "binding_id": "consumer",
            "reasons": ["binding-definition-changed"],
        }
    ]


def test_shared_declared_dependency_affects_only_bindings_that_declared_it(
    tmp_path: Path,
) -> None:
    for path in ("owner-a.py", "owner-b.py", "owner-c.py"):
        (tmp_path / path).write_text("stable\n", encoding="utf-8")
    shared = tmp_path / "shared.lock"
    other = tmp_path / "other.lock"
    shared.write_text("one\n", encoding="utf-8")
    other.write_text("stable\n", encoding="utf-8")

    bindings = [
        _binding("consumer:a", "owner-a.py"),
        _binding("consumer:b", "owner-b.py"),
        _binding("consumer:c", "owner-c.py"),
    ]
    dependencies = {
        "consumer:a": ["shared.lock"],
        "consumer:b": ["shared.lock"],
        "consumer:c": ["other.lock"],
    }

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.repository_evidence_bindings(
            bindings,
            dependency_paths=dependencies,
            include_relationships=False,
        )

        shared.write_text("two\n", encoding="utf-8")
        codemap.sync(["shared.lock"])
        after = codemap.repository_evidence_bindings(
            bindings,
            dependency_paths=dependencies,
            include_relationships=False,
        )
        delta = codemap.repository_evidence_binding_delta(before, after)
        coverage = codemap.repository_evidence_coverage(
            after,
            changed_paths=["shared.lock"],
            change_set_complete=True,
            binding_delta=delta,
            binding_delta_before=before,
        )

    changed = _changed_by_id(delta)
    assert set(changed) == {"consumer:a", "consumer:b"}
    assert delta["bindings"]["preserved"] == ["consumer:c"]

    for binding_id in ("consumer:a", "consumer:b"):
        row = changed[binding_id]
        assert row["direct_evidence"]["state"] == "preserved"
        assert row["member_evidence"]["state"] == "preserved"
        declared = row["declared_dependencies"]
        assert declared["state"] == "affected"
        assert declared["definition"]["state"] == "preserved"
        assert declared["observations"]["state"] == "changed"
        assert declared["observations"]["changes"] == [
            {
                "path": "shared.lock",
                "state": "changed",
                "member_changed": True,
                "observation_state_changed": False,
            }
        ]

    assert coverage["classification"]["declared_dependencies_changed"] == [
        "shared.lock"
    ]
    assert coverage["binding_impacts"] == [
        {
            "binding_id": "consumer:a",
            "reasons": ["declared-dependency-changed"],
        },
        {
            "binding_id": "consumer:b",
            "reasons": ["declared-dependency-changed"],
        },
    ]
