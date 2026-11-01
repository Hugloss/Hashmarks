from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import pytest
from contract_assertions import assert_array, assert_object, assert_records

from hashmarks import CodeMap
from hashmarks.adapters import uv_lock_dependency_observation
from hashmarks.codemap.repository_dependencies import RepositoryDependencies
from hashmarks.file_store import UnstableFileError
from hashmarks.operation_contract import validate_operation_response


def _lock(version: str = "1.0", second: bool = False) -> bytes:
    lock = f'''version = 1
revision = 3

[[package]]
name = "application"
version = "0.1"
source = {{ virtual = "." }}
dependencies = [{{ name = "sample-distribution" }}]

[[package]]
name = "sample-distribution"
version = "{version}"
source = {{ registry = "https://example.invalid/simple" }}
'''
    if second:
        lock += """
[[package]]
name = "other-distribution"
version = "1.0"
source = { registry = "https://example.invalid/simple" }
"""
    return lock.encode()


def _metadata(
    lock: bytes, name: str = "sample-distribution", version: str = "1.0"
) -> dict[str, object]:
    raw = uv_lock_dependency_observation(lock=lock)
    selected = next(
        row for row in assert_records(raw["selections"]) if row["component_id"] == name
    )
    return {
        "node_id": selected["node_id"],
        "metadata": f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n\n".encode(),
        "record": b"different_import/__init__.py,,\ndifferent_import/api.py,,\n",
    }


def _workspace(path: Path) -> None:
    (path / "bridge.py").write_text(
        "from different_import import api\ndef run():\n    return api.answer()\n"
    )
    (path / "caller.py").write_text("from bridge import run\nresult = run()\n")
    (path / "unrelated.py").write_text("import something_else\n")


def _observation(
    codemap: CodeMap, lock: bytes, metadata: Sequence[Mapping[str, object]]
) -> dict[str, object]:
    return codemap.dependencies.observe(
        uv_lock_dependency_observation(lock=lock, distribution_metadata=metadata)
    )


def test_native_distribution_names_do_not_become_import_names_and_updates_rebind(
    tmp_path: Path,
) -> None:
    _workspace(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        without = _observation(codemap, _lock(), ())
        unknown = codemap.dependencies.import_correspondence(
            without, source_path="bridge.py", import_target="different_import.api"
        )
        assert unknown["distribution_state"] == "unknown"
        before = _observation(codemap, _lock(), [_metadata(_lock())])
        first = codemap.dependencies.consumers(
            before,
            source_paths=["bridge.py", "caller.py", "unrelated.py"],
            node_ids=[str(_metadata(_lock())["node_id"])],
        )
        after = _observation(
            codemap, _lock("2.0"), [_metadata(_lock("2.0"), version="2.0")]
        )
        second = codemap.dependencies.consumers(
            after,
            source_paths=["bridge.py"],
            node_ids=[str(_metadata(_lock("2.0"), version="2.0")["node_id"])],
        )
        delta = codemap.dependencies.delta(before, after)

    validate_operation_response("dependency_consumers", first)
    rows = assert_records(first["consumers"])
    assert [row["source_path"] for row in rows] == ["bridge.py"]
    assert rows[0]["import_target"] == "different_import.api"
    assert rows[0]["import_claim_authority"] == "source-observed-static-import"
    assert assert_object(rows[0]["source_member"])["member_revision"]
    assert rows[0]["ownership_completeness"] == "incomplete"
    affected = assert_object(
        assert_records(first["downstream_relationships"])[0]["relationships"]
    )
    assert "caller.py" in assert_array(affected["affected_files"])
    assert "unrelated.py" not in assert_array(affected["affected_files"])
    assert (
        assert_records(second["consumers"])[0]["distribution_nodes"]
        != rows[0]["distribution_nodes"]
    )
    assert before["observation_identity"] != after["observation_identity"]
    assert delta["selections_added"]
    assert (
        assert_object(first["consumer_scope"])["negative_evidence"] == "not-admissible"
    )
    assert assert_object(first["consumer_scope"])["completeness"] == "incomplete"


def test_namespace_owners_and_metadata_completeness_are_not_collapsed(
    tmp_path: Path,
) -> None:
    lock = _lock(second=True)
    first = _metadata(lock)
    other = _metadata(lock, "other-distribution")
    _workspace(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        observation = _observation(codemap, lock, [first, other])
        result = codemap.dependencies.consumers(
            observation, source_paths=["bridge.py"], node_ids=[str(first["node_id"])]
        )
    row = assert_records(result["consumers"])[0]
    assert row["distribution_state"] == "resolved-ambiguous"
    assert set(assert_array(row["distribution_nodes"])) == {
        first["node_id"],
        other["node_id"],
    }
    assert row["ownership_completeness"] == "incomplete"
    assert (
        len(
            assert_records(
                assert_object(result["dependency_provenance"])["evidence_sources"]
            )
        )
        == 4
    )


@pytest.mark.parametrize(
    "record",
    [
        None,
        b"different_import/__init__.pyi,,\n",
        b"different_import.cpython-311-x86_64-linux-gnu.so,,\n",
    ],
)
def test_missing_stub_or_native_extension_metadata_never_invents_runtime_owner(
    record: bytes | None,
) -> None:
    entry = _metadata(_lock())
    entry["record"] = record
    raw = uv_lock_dependency_observation(lock=_lock(), distribution_metadata=[entry])
    assert raw["module_ownership"] == []
    assert assert_records(raw["coverage"])[-1]["completeness"] == "incomplete"


@pytest.mark.parametrize(
    "record", [b"different_import.api.py,,\n", b"different_import.api/__init__.py,,\n"]
)
def test_record_path_components_cannot_masquerade_as_dotted_modules(
    record: bytes,
) -> None:
    entry = _metadata(_lock())
    entry["record"] = record
    raw = uv_lock_dependency_observation(lock=_lock(), distribution_metadata=[entry])
    assert raw["module_ownership"] == []


def test_top_level_declaration_alone_is_not_accepted_as_module_proof() -> None:
    entry = _metadata(_lock())
    entry["top_level"] = b"unrelated_name\n"
    with pytest.raises(ValueError, match="unknown Python distribution metadata field"):
        uv_lock_dependency_observation(lock=_lock(), distribution_metadata=[entry])


def test_python_consumer_profile_uses_semantic_namespace_not_producer_kind(
    tmp_path: Path,
) -> None:
    _workspace(tmp_path)
    raw = uv_lock_dependency_observation(
        lock=_lock(), distribution_metadata=[_metadata(_lock())]
    )
    assert_object(raw["producer"])["kind"] = "another-external-producer"
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        observation = codemap.dependencies.observe(raw)
        nodes = [str(_metadata(_lock())["node_id"])]
        assert codemap.dependencies.consumers(
            observation, source_paths=["bridge.py"], node_ids=nodes
        )["consumers"]
        for component in assert_records(raw["components"]):
            if component["component_id"] == "sample-distribution":
                component["ecosystem"] = "maven"
        unsupported = codemap.dependencies.observe(raw)
        with pytest.raises(ValueError, match="Python distribution selections"):
            codemap.dependencies.consumers(
                unsupported, source_paths=["bridge.py"], node_ids=nodes
            )


def test_mixed_module_namespaces_do_not_upgrade_a_python_owner_to_unique(
    tmp_path: Path,
) -> None:
    _workspace(tmp_path)
    lock = _lock(second=True)
    first = _metadata(lock)
    other = _metadata(lock, "other-distribution")
    raw = uv_lock_dependency_observation(
        lock=lock, distribution_metadata=[first, other]
    )
    for component in assert_records(raw["components"]):
        if component["component_id"] == "other-distribution":
            component["ecosystem"] = "maven"
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        observation = codemap.dependencies.observe(raw)
        result = codemap.dependencies.consumers(
            observation, source_paths=["bridge.py"], node_ids=[str(first["node_id"])]
        )
    assert result["consumers"] == []
    assert assert_object(result["consumer_scope"])["completeness"] == "incomplete"


def test_dependency_consumers_cannot_borrow_foreign_relationship_authority(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path / "left") as left, CodeMap(tmp_path / "right") as right:
        with pytest.raises(ValueError, match="share one repository read scope"):
            RepositoryDependencies(
                left.source,
                left.relationships.imports,
                left.correlation,
                right.relationships,
            )


def test_static_conditional_imports_dynamic_calls_and_source_shadowing_remain_distinct(
    tmp_path: Path,
) -> None:
    (tmp_path / "conditional.py").write_text(
        "if enabled:\n    from different_import import api\n"
    )
    (tmp_path / "dynamic.py").write_text(
        "import importlib\n# import different_import\n"
        "text = 'from different_import import api'\n"
        "importlib.import_module('different_import')\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        observation = _observation(codemap, _lock(), [_metadata(_lock())])
        result = codemap.dependencies.consumers(
            observation,
            source_paths=["conditional.py", "dynamic.py"],
            node_ids=[str(_metadata(_lock())["node_id"])],
        )
        assert assert_records(result["consumers"])[0]["conditional_or_deferred"] is True
        assert len(assert_records(result["consumers"])) == 1
        assert assert_object(result["consumer_scope"])["completeness"] == "incomplete"
        (tmp_path / "different_import.py").write_text("api = object()\n")
        codemap.index.sync()
        refreshed = _observation(codemap, _lock(), [_metadata(_lock())])
        shadowed = codemap.dependencies.consumers(
            refreshed,
            source_paths=["conditional.py"],
            node_ids=[str(_metadata(_lock())["node_id"])],
        )
        assert shadowed["consumers"] == []
        assert (
            assert_object(shadowed["consumer_scope"])["negative_evidence"]
            == "not-admissible"
        )


def test_bounded_projection_does_not_strengthen_consumer_scope(tmp_path: Path) -> None:
    for index in range(3):
        (tmp_path / f"consumer{index}.py").write_text("import different_import\n")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        observation = _observation(codemap, _lock(), [_metadata(_lock())])
        result = codemap.dependencies.consumers(
            observation,
            source_paths=[f"consumer{index}.py" for index in range(3)],
            node_ids=[str(_metadata(_lock())["node_id"])],
            limit=1,
        )
    assert result["observed_consumer_count"] == 3
    assert len(assert_array(result["consumers"])) == 1
    assert result["truncation"] == "truncated"
    assert (
        assert_object(result["consumer_scope"])["negative_evidence"] == "not-admissible"
    )


def test_stale_foreign_and_tampered_dependency_evidence_refuse_consumers(
    tmp_path: Path,
) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    _workspace(left)
    with CodeMap(left) as codemap, CodeMap(right) as foreign:
        codemap.index.sync()
        foreign.index.sync()
        observation = _observation(codemap, _lock(), [_metadata(_lock())])
        nodes = [str(_metadata(_lock())["node_id"])]
        with pytest.raises(ValueError, match="binding mismatch"):
            foreign.dependencies.consumers(
                observation, source_paths=["bridge.py"], node_ids=nodes
            )
        tampered = dict(observation, observation_identity="sha256:" + "0" * 64)
        with pytest.raises(ValueError, match="identity mismatch"):
            codemap.dependencies.consumers(
                tampered, source_paths=["bridge.py"], node_ids=nodes
            )
        (left / "bridge.py").write_text("import other\n")
        codemap.index.sync()
        with pytest.raises(ValueError, match="binding mismatch"):
            codemap.dependencies.consumers(
                observation, source_paths=["bridge.py"], node_ids=nodes
            )


def test_unavailable_and_malformed_sources_keep_scope_incomplete(
    tmp_path: Path,
) -> None:
    (tmp_path / "broken.py").write_text("from different_import import (\n")
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        observation = _observation(codemap, _lock(), [_metadata(_lock())])
        result = codemap.dependencies.consumers(
            observation,
            source_paths=["broken.py", "missing.py"],
            node_ids=[str(_metadata(_lock())["node_id"])],
        )
    assert result["consumers"] == []
    assert assert_object(result["source_scope"])["unavailable"] == [
        "broken.py",
        "missing.py",
    ]
    assert assert_object(result["source_scope"])["completeness"] == "incomplete"


@pytest.mark.parametrize(
    "changed, message",
    [
        ({"metadata": b"Name: foreign\nVersion: 1.0\n"}, "does not match"),
        (
            {
                "metadata": b"Name: sample-distribution\nName: sample-distribution\nVersion: 1.0\n"
            },
            "one Name",
        ),
        ({"metadata": b"Name: sample-distribution\nVersion: 9\n"}, "does not match"),
        ({"node_id": "unselected"}, "exact dependency selection"),
        ({"record": b"not-a-three-column-record\n"}, "three columns"),
        ({"extra": "claim"}, "unknown Python"),
    ],
)
def test_metadata_translation_refuses_malformed_or_foreign_claims(
    changed: dict[str, object], message: str
) -> None:
    entry = _metadata(_lock())
    entry.update(changed)
    with pytest.raises(ValueError, match=message):
        uv_lock_dependency_observation(lock=_lock(), distribution_metadata=[entry])


def test_source_changes_during_consumer_observation_refuse_partial_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        observation = _observation(codemap, _lock(), [_metadata(_lock())])
        original = codemap.relationships.affected

        def mutate(query: str, *, max_depth: int = 12) -> dict[str, object]:
            result = original(query, max_depth=max_depth)
            (tmp_path / "bridge.py").write_text("import replaced\n")
            return result

        monkeypatch.setattr(codemap.relationships, "affected", mutate)
        with pytest.raises(UnstableFileError, match="source changed"):
            codemap.dependencies.consumers(
                observation,
                source_paths=["bridge.py"],
                node_ids=[str(_metadata(_lock())["node_id"])],
            )


@pytest.mark.parametrize(
    "field, value",
    [
        ("source_paths", [[]]),
        ("node_ids", [[]]),
        ("source_paths", "bridge.py"),
        ("node_ids", "distribution"),
    ],
)
def test_consumer_scope_rejects_malformed_inputs(
    tmp_path: Path, field: str, value: object
) -> None:
    _workspace(tmp_path)
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        observation = _observation(codemap, _lock(), [_metadata(_lock())])
        kwargs: dict[str, object] = {
            "source_paths": ["bridge.py"],
            "node_ids": [str(_metadata(_lock())["node_id"])],
        }
        kwargs[field] = value
        with pytest.raises(ValueError):
            codemap.dependencies.consumers(observation, **cast("dict", kwargs))


@pytest.mark.parametrize("entries", [{}, None, "metadata", [None]])
def test_metadata_container_must_not_silently_become_missing_evidence(
    entries: object,
) -> None:
    with pytest.raises(ValueError):
        uv_lock_dependency_observation(
            lock=_lock(),
            distribution_metadata=cast("Sequence[Mapping[str, object]]", entries),
        )
