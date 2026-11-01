"""Retained dependency projections preserve provenance across current source drift."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from copy import deepcopy
from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records

from hashmarks import CodeMap, hash_file
from hashmarks.adapters import uv_lock_dependency_observation
from hashmarks.evidence_presentation import (
    present_repository_evidence,
    presentation_response,
)
from hashmarks.evidence_presentation_conformance import validate_evidence_presentation
from hashmarks.file_store import UnstableFileError

_LOCK = b"""version = 1
revision = 3

[[package]]
name = "application"
version = "0.1"
source = { virtual = "." }
dependencies = [{ name = "sample-distribution" }]

[[package]]
name = "sample-distribution"
version = "1.0"
source = { registry = "https://example.invalid/simple" }
"""
_PACKAGES = [{"ecosystem": "pypi", "name": "sample-distribution"}]
_ABSENT = [{"ecosystem": "pypi", "name": "absent-distribution"}]


def _workspace(path: Path) -> None:
    path.mkdir(exist_ok=True)
    (path / "uv.lock").write_bytes(_LOCK)
    (path / "bridge.py").write_text("import sample_api\n", encoding="utf-8")


def _snapshot(path: Path, *, claimed: bool = True) -> dict[str, object]:
    raw = uv_lock_dependency_observation(lock=_LOCK)
    node = next(
        row["node_id"]
        for row in assert_records(raw["selections"])
        if row["component_id"] == "sample-distribution"
    )
    return uv_lock_dependency_observation(
        lock=_LOCK,
        repository_inputs=[
            {
                "path": "uv.lock",
                **(
                    {"member_revision": hash_file(path / "uv.lock").hash}
                    if claimed
                    else {}
                ),
            }
        ],
        distribution_metadata=[
            {
                "node_id": node,
                "metadata": (
                    b"Metadata-Version: 2.1\nName: sample-distribution\n"
                    b"Version: 1.0\n\n"
                ),
                "record": b"sample_api/__init__.py,,\n",
            }
        ],
    )


@pytest.fixture
def repository(tmp_path: Path) -> Iterator[CodeMap]:
    workspace = tmp_path / "repo"
    _workspace(workspace)
    with CodeMap(workspace, state_dir=tmp_path / "state") as repository:
        repository.index.sync()
        yield repository


def _projection(repository: CodeMap) -> dict[str, object]:
    observation = repository.dependencies.observe(_snapshot(repository.workspace))
    return repository.dependencies.projection(
        observation, packages=_PACKAGES, source_paths=["bridge.py"]
    )


def _scope(packet: Mapping[str, object]) -> dict[str, object]:
    return assert_object(packet["source_scope"])


def _consumer(packet: Mapping[str, object]) -> dict[str, object]:
    return assert_object(packet["consumer_evidence"])


def _forbid_source(*args: object, **kwargs: object) -> dict[str, object]:
    raise AssertionError("malformed retained input reached native source reads")


def test_requalification_keeps_original_observation_members_and_identity(
    repository: CodeMap,
) -> None:
    observation = repository.dependencies.observe(_snapshot(repository.workspace))
    original = deepcopy(observation)
    generation = repository.store.generation()
    packet = repository.dependencies.projection(
        observation, packages=_PACKAGES, source_paths=["bridge.py"]
    )
    retained = deepcopy(packet)
    requalified = repository.dependencies.requalify(packet)

    assert packet["schema"] == "hashmarks.dependency-projection.v1"
    assert packet == retained == requalified
    assert packet["projection_identity"] == requalified["projection_identity"]
    assert packet["observation"] == observation == original
    assert repository.store.generation() == generation
    assert _scope(packet)["freshness"] == "current"
    assert [
        row["state"] for row in assert_records(_scope(packet)["correspondence"])
    ] == ["matched"]
    assert _consumer(packet)["state"] == "observed"
    canonical = repository.dependencies.consumers(
        observation,
        source_paths=["bridge.py"],
        node_ids=[
            str(row["node_id"])
            for row in assert_records(observation["selections"])
            if row["component_id"] == "sample-distribution"
        ],
    )
    assert _consumer(packet)["observation"] == canonical
    assert packet["execution_authority"] == "external"
    assert packet["result_authority"] == "external"
    assert packet["certification_authority"] == "external"
    assert packet["negative_evidence"] == "not-admissible"


@pytest.mark.parametrize("mutation", ["edit", "delete", "deny", "oversize"])
def test_requalification_cannot_rebind_changed_or_unavailable_source(
    repository: CodeMap, mutation: str
) -> None:
    before = _projection(repository)
    original = deepcopy(before)
    path = repository.workspace / "bridge.py"
    if mutation == "edit":
        path.write_text("import other_api\n", encoding="utf-8")
    elif mutation == "delete":
        path.unlink()
    elif mutation == "oversize":
        path.write_bytes(b"#" * 8_388_609)
    else:
        (repository.workspace / ".hashmarks-context.toml").write_text(
            '[[rule]]\npattern="bridge.py"\nindex=false\n', encoding="utf-8"
        )
        repository.index.sync()
    after = repository.dependencies.requalify(before)

    assert before == original
    assert after["observation"] == before["observation"]
    assert after["request"] == before["request"]
    assert _scope(after)["retained_members"] == _scope(before)["retained_members"]
    assert _scope(after)["freshness"] != "current"
    assert all(
        row["state"] != "matched"
        for row in assert_records(_scope(after)["correspondence"])
    )
    assert _consumer(after)["state"] == "unavailable"
    assert _consumer(after)["observation"] is None
    assert after["projection_identity"] != before["projection_identity"]
    assert after["negative_evidence"] == "not-admissible"


@pytest.mark.parametrize("mutation", ["edit", "delete", "deny", "oversize"])
def test_retained_dependency_input_drift_does_not_refresh_away_provenance(
    repository: CodeMap, mutation: str
) -> None:
    before = _projection(repository)
    original = deepcopy(before)
    path = repository.workspace / "uv.lock"
    if mutation == "edit":
        path.write_bytes(_LOCK.replace(b'"1.0"', b'"2.0"'))
    elif mutation == "delete":
        path.unlink()
    elif mutation == "oversize":
        path.write_bytes(b"#" * 8_388_609)
    else:
        (repository.workspace / ".hashmarks-context.toml").write_text(
            '[[rule]]\npattern="uv.lock"\nindex=false\n', encoding="utf-8"
        )
        repository.index.sync()
    after = repository.dependencies.requalify(before)

    assert before == original
    assert after["observation"] == before["observation"]
    assessment = assert_object(after["assessment"])
    assert assert_object(assessment["source_scope"])["freshness"] != "current"
    assert (
        assert_object(assessment["resolved_inventory"])["negative_evidence"]
        == "not-admissible"
    )
    assert _consumer(after)["state"] == "unavailable"
    assert _consumer(after)["observation"] is None


def test_missing_producer_revision_never_gains_consumer_admission(
    repository: CodeMap,
) -> None:
    observation = repository.dependencies.observe(
        _snapshot(repository.workspace, claimed=False)
    )
    packet = repository.dependencies.projection(
        observation, packages=_PACKAGES, source_paths=["bridge.py"]
    )
    source = assert_object(assert_object(packet["assessment"])["source_scope"])
    assert source["freshness"] == "current"
    assert source["source_equivalence"] == "unknown"
    assert _consumer(packet)["state"] == "unavailable"
    assert _consumer(packet)["observation"] is None


def test_requalification_keeps_historical_absence_separate_from_current_inputs(
    repository: CodeMap,
) -> None:
    observation = repository.dependencies.observe(_snapshot(repository.workspace))
    before = repository.dependencies.projection(observation, packages=_ABSENT)
    package = assert_records(before["packages"])[0]
    assert assert_records(package["contexts"])[0]["membership"] == "absent"
    current = assert_records(package["current_inventory"])[0]
    assert current["membership"] == "absent"
    assert current["negative_evidence"] == "admissible-within-declared-scope"
    (repository.workspace / "uv.lock").write_bytes(_LOCK + b"# changed input\n")

    after = repository.dependencies.requalify(before)

    revised = assert_records(after["packages"])[0]
    assert revised["contexts"] == package["contexts"]
    assert assert_records(revised["current_inventory"])[0]["membership"] == "unknown"
    assert (
        assert_records(revised["current_inventory"])[0]["negative_evidence"]
        == "not-admissible"
    )
    assert after["observation"] == before["observation"]


@pytest.mark.parametrize("restriction", ["index=false", 'visibility="outline"'])
def test_requalification_observes_new_input_restriction_without_index_publication(
    repository: CodeMap, restriction: str
) -> None:
    observation = repository.dependencies.observe(_snapshot(repository.workspace))
    before = repository.dependencies.projection(
        observation, packages=_ABSENT, source_paths=["bridge.py"]
    )
    generation = repository.store.generation()
    (repository.workspace / ".hashmarks-context.toml").write_text(
        f'[[rule]]\npattern="uv.lock"\n{restriction}\n', encoding="utf-8"
    )

    after = repository.dependencies.requalify(before)

    package = assert_records(after["packages"])[0]
    assert assert_records(package["contexts"])[0]["membership"] == "absent"
    assert assert_records(package["current_inventory"])[0]["membership"] == "unknown"
    assert (
        assert_records(package["current_inventory"])[0]["negative_evidence"]
        == "not-admissible"
    )
    assert repository.store.generation() == generation
    assert after["observation"] == before["observation"]


def test_requalification_restricts_source_disclosure_while_lock_stays_current(
    repository: CodeMap, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _projection(repository)
    generation = repository.store.generation()
    (repository.workspace / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern="bridge.py"\nvisibility="outline"\n', encoding="utf-8"
    )
    monkeypatch.setattr(repository.index, "sync", _forbid_source)

    after = repository.dependencies.requalify(before)

    inputs = assert_object(assert_object(after["assessment"])["source_scope"])
    assert inputs["freshness"] == "current"
    assert inputs["source_equivalence"] == "proven"
    source = assert_records(_scope(after)["observations"])[0]
    assert source["availability"] == "unavailable"
    assert assert_object(source["member"])["reason"] == "source-evidence-not-visible"
    assert _scope(after)["freshness"] != "current"
    assert _consumer(after)["state"] == "unavailable"
    assert _consumer(after)["observation"] is None
    assert repository.store.generation() == generation
    assert _scope(after)["retained_members"] == _scope(before)["retained_members"]


def test_unreconciled_unrelated_policy_does_not_initialize_a_current_consumer_join(
    repository: CodeMap, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _projection(repository)
    generation = repository.store.generation()
    (repository.workspace / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern="unrelated.py"\nindex=false\n', encoding="utf-8"
    )
    monkeypatch.setattr(repository.index, "sync", _forbid_source)

    for _ in range(2):
        after = repository.dependencies.requalify(before)

        assert _scope(after)["freshness"] == "current"
        assert _consumer(after)["state"] == "unavailable"
        assert _consumer(after)["reason"] == "codemap-scope-stale"
        assert _consumer(after)["observation"] is None
        assert repository.store.generation() == generation


def test_unbound_input_cannot_promote_historical_absence(
    repository: CodeMap,
) -> None:
    observation = repository.dependencies.observe(
        _snapshot(repository.workspace, claimed=False)
    )
    packet = repository.dependencies.projection(observation, packages=_ABSENT)
    package = assert_records(packet["packages"])[0]

    assert assert_records(package["contexts"])[0]["membership"] == "absent"
    current = assert_records(package["current_inventory"])[0]
    assert current["membership"] == "unknown"
    assert current["source_equivalence"] == "unknown"
    assert current["negative_evidence"] == "not-admissible"


def test_current_inventory_preserves_each_contexts_independent_coverage(
    repository: CodeMap,
) -> None:
    snapshot = _snapshot(repository.workspace)
    snapshot["contexts"] = ["lock", "uncovered"]
    observation = repository.dependencies.observe(snapshot)
    packet = repository.dependencies.projection(observation, packages=_ABSENT)
    package = assert_records(packet["packages"])[0]
    historical = {row["context"]: row for row in assert_records(package["contexts"])}
    current = {
        row["context"]: row for row in assert_records(package["current_inventory"])
    }

    assert historical["lock"]["membership"] == "absent"
    assert historical["uncovered"]["membership"] == "unknown"
    assert current["lock"]["membership"] == "absent"
    assert current["uncovered"]["membership"] == "unknown"
    assert current["uncovered"]["negative_evidence"] == "not-admissible"
    assert (
        assert_object(assert_object(packet["assessment"])["resolved_inventory"])[
            "completeness"
        ]
        == "unknown"
    )


def test_context_selected_package_keeps_consumer_observed_contexts_explicit(
    repository: CodeMap,
) -> None:
    snapshot = _snapshot(repository.workspace)
    snapshot["contexts"] = ["lock", "runtime"]
    for source in assert_records(snapshot["evidence_sources"]):
        source["context"] = ""
    for selection in assert_records(snapshot["selections"]):
        selection["contexts"] = ["lock", "runtime"]
    for key in ("roots", "inventory", "relationships", "module_ownership", "coverage"):
        rows = assert_records(snapshot[key])
        snapshot[key] = [*rows, *[{**row, "context": "runtime"} for row in rows]]
    observation = repository.dependencies.observe(snapshot)

    packet = repository.dependencies.projection(
        observation,
        packages=[{**_PACKAGES[0], "context": "lock"}],
        source_paths=["bridge.py"],
    )

    package = assert_records(packet["packages"])[0]
    assert [row["context"] for row in assert_records(package["contexts"])] == ["lock"]
    assert (
        _consumer(packet)["context_scope"] == "all-declared-contexts-for-selected-nodes"
    )
    consumers = assert_object(_consumer(packet)["observation"])
    assert assert_records(consumers["consumers"])[0]["observed_contexts"] == [
        "lock",
        "runtime",
    ]
    assert packet["observation"] == observation


def test_new_generation_preserves_exact_inputs_without_rebinding_consumer_join(
    repository: CodeMap,
) -> None:
    before = _projection(repository)
    (repository.workspace / "unrelated.py").write_text("value = 2\n", encoding="utf-8")
    repository.index.sync(["unrelated.py"])
    after = repository.dependencies.requalify(before)

    assert after["observation"] == before["observation"]
    assert _scope(after)["freshness"] == "current"
    source = assert_object(assert_object(after["assessment"])["source_scope"])
    assert source["freshness"] == "current"
    assert source["source_equivalence"] == "proven"
    assert assert_object(after["repository"])["binding_state"] == "stale"
    assert _consumer(after)["state"] == "unavailable"
    assert _consumer(after)["observation"] is None


def test_foreign_projection_keeps_scoped_correspondence_without_current_join(
    repository: CodeMap, tmp_path: Path
) -> None:
    before = _projection(repository)
    foreign = tmp_path / "foreign"
    _workspace(foreign)
    with CodeMap(foreign, state_dir=tmp_path / "foreign-state") as other:
        other.index.sync()
        after = other.dependencies.requalify(before)

    assert after["observation"] == before["observation"]
    assert _scope(after)["retained_members"] == _scope(before)["retained_members"]
    assert _scope(after)["freshness"] == "current"
    assert assert_object(after["repository"])["binding_state"] == "stale"
    assert _consumer(after)["state"] == "unavailable"
    assert _consumer(after)["observation"] is None


def test_retained_requalification_does_not_initialize_an_empty_index(
    repository: CodeMap, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _projection(repository)
    with CodeMap(repository.workspace, state_dir=tmp_path / "uninitialized") as empty:
        generation = empty.store.generation()
        assert not empty.store.has_files()
        monkeypatch.setattr(empty.index, "sync", _forbid_source)
        after = empty.dependencies.requalify(before)

        assert empty.store.generation() == generation
        assert not empty.store.has_files()
    assert after["observation"] == before["observation"]
    assert _scope(after)["retained_members"] == _scope(before)["retained_members"]
    assert _scope(after)["freshness"] == "current"
    assert _consumer(after)["state"] == "unavailable"
    assert _consumer(after)["observation"] is None


def test_projection_rechecks_earlier_source_after_later_source_observation(
    repository: CodeMap, monkeypatch: pytest.MonkeyPatch
) -> None:
    (repository.workspace / "second.py").write_text("value = 1\n", encoding="utf-8")
    repository.index.sync(["second.py"])
    observation = repository.dependencies.observe(_snapshot(repository.workspace))
    original = repository.source.observe
    changed = False

    def observe(path: str, **kwargs: object) -> dict[str, object]:
        nonlocal changed
        max_bytes = kwargs["max_bytes"]
        assert isinstance(max_bytes, int)
        packet = original(path, max_bytes=max_bytes)
        if path == "second.py" and not changed:
            changed = True
            (repository.workspace / "bridge.py").write_text("changed = True\n")
        return packet

    monkeypatch.setattr(repository.source, "observe", observe)
    with pytest.raises(UnstableFileError, match="inputs changed during observation"):
        repository.dependencies.projection(
            observation, packages=_ABSENT, source_paths=["bridge.py", "second.py"]
        )
    assert changed


@pytest.mark.parametrize("field", ["observation", "request", "source_scope"])
def test_requalification_rejects_tampering_before_source_reads(
    repository: CodeMap, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    packet = _projection(repository)
    tampered = deepcopy(packet)
    assert_object(tampered[field])["injected"] = True
    monkeypatch.setattr(repository.source, "observe", _forbid_source)
    with pytest.raises(ValueError):
        repository.dependencies.requalify(tampered)


def test_projection_rejects_tampered_dependency_observation_before_source_reads(
    repository: CodeMap, monkeypatch: pytest.MonkeyPatch
) -> None:
    observation = repository.dependencies.observe(_snapshot(repository.workspace))
    assert_records(observation["selections"])[0]["version"] = "forged"
    monkeypatch.setattr(repository.source, "observe", _forbid_source)
    with pytest.raises(ValueError, match="identity mismatch|not normalized"):
        repository.dependencies.projection(
            observation, packages=_PACKAGES, source_paths=["bridge.py"]
        )


def test_unknown_context_cannot_become_an_empty_absent_scope(
    repository: CodeMap, monkeypatch: pytest.MonkeyPatch
) -> None:
    observation = repository.dependencies.observe(_snapshot(repository.workspace))
    monkeypatch.setattr(repository.source, "observe", _forbid_source)
    with pytest.raises(ValueError, match="context"):
        repository.dependencies.projection(
            observation,
            packages=[{**_PACKAGES[0], "context": "not-declared"}],
            source_paths=["bridge.py"],
        )


def test_consumer_output_bound_retains_observed_count_and_unknown_absence(
    repository: CodeMap,
) -> None:
    (repository.workspace / "bridge.py").write_text(
        "import sample_api.one\nimport sample_api.two\nimport sample_api.three\n",
        encoding="utf-8",
    )
    repository.index.sync(["bridge.py"])
    observation = repository.dependencies.observe(_snapshot(repository.workspace))
    packet = repository.dependencies.projection(
        observation, packages=_PACKAGES, source_paths=["bridge.py"], limit=1
    )
    consumers = assert_object(_consumer(packet)["observation"])

    assert _consumer(packet)["state"] == "observed"
    assert consumers["observed_consumer_count"] == 3
    assert len(assert_records(consumers["consumers"])) == 1
    assert consumers["truncation"] == packet["truncation"] == "truncated"
    assert (
        assert_object(consumers["consumer_scope"])["negative_evidence"]
        == "not-admissible"
    )
    assert packet["negative_evidence"] == "not-admissible"


def test_missing_adapter_semantics_stays_unqualified_derivation(
    repository: CodeMap,
) -> None:
    snapshot = _snapshot(repository.workspace)
    assert_object(snapshot["producer"]).pop("adapter_semantics")
    observation = repository.dependencies.observe(snapshot)
    packet = repository.dependencies.projection(observation, packages=_PACKAGES)

    assert packet["observation"] == observation
    assert packet["derivation"] is None
    assert _consumer(packet)["state"] == "not-requested"


def _findings(presentation: Mapping[str, object]) -> list[dict[str, object]]:
    return [
        row
        for group in assert_records(presentation["groups"])
        for row in assert_records(group["findings"])
    ]


@pytest.mark.parametrize("format", ["structured", "compact", "text"])
def test_projection_presentation_preserves_native_requalification(
    repository: CodeMap, format: str
) -> None:
    packet = _projection(repository)
    original = deepcopy(packet)
    response = presentation_response("dependency_projection", packet, format=format)
    presentation = assert_object(response["presentation"])
    assert presentation["supported"] is True
    assert presentation["source_evidence_identity"] == packet["projection_identity"]
    assert validate_evidence_presentation(packet, presentation)["valid"] is True
    findings = _findings(presentation)
    assert any(
        row["source_refs"] == ["/assessment"] and row["details"] == packet["assessment"]
        for row in findings
    )
    assert any(
        row["source_refs"] == ["/packages/0"]
        and row["details"] == assert_records(packet["packages"])[0]
        for row in findings
    )
    assert any(
        row["source_refs"] == ["/source_scope/correspondence/0"]
        and row["details"] == assert_records(_scope(packet)["correspondence"])[0]
        for row in findings
    )
    consumer_context = next(
        assert_object(row["details"])
        for row in assert_records(presentation["source_context"])
        if row["source_ref"] == "/consumer_evidence"
    )
    for key in ("selection_scope", "context_scope"):
        assert consumer_context[key] == _consumer(packet)[key]
        if format == "text":
            assert f'"{key}":"{_consumer(packet)[key]}"' in str(presentation["text"])
    consumer = assert_object(_consumer(packet)["observation"])
    assert any(
        row["source_ref"] == "/consumer_evidence/observation"
        and assert_object(row["details"]).get("capability") == consumer["capability"]
        and assert_object(row["details"]).get("consumer_scope")
        == consumer["consumer_scope"]
        for row in assert_records(presentation["source_context"])
    )
    assert packet == original == response["result"]


def test_structured_projection_reuses_canonical_consumer_and_dependency_views(
    repository: CodeMap,
) -> None:
    packet = _projection(repository)
    presentation = present_repository_evidence(packet, format="structured")
    for key, nested, prefix in (
        ("/components/0", assert_object(packet["observation"]), "/observation"),
        (
            "/member",
            assert_records(_scope(packet)["observations"])[0],
            "/source_scope/observations/0",
        ),
        (
            "/consumers/0",
            assert_object(_consumer(packet)["observation"]),
            "/consumer_evidence/observation",
        ),
    ):
        standalone = present_repository_evidence(nested, format="structured")
        native = next(
            row for row in _findings(standalone) if row["source_refs"] == [key]
        )
        projected = next(
            row
            for row in _findings(presentation)
            if row["source_refs"] == [prefix + key]
        )
        assert projected["details"] == native["details"]
        assert projected["assertion"] == native["assertion"]


@pytest.mark.parametrize("field", ["packages", "source_scope", "consumer_evidence"])
def test_projection_presentation_rejects_malformed_native_collections(
    repository: CodeMap, field: str
) -> None:
    packet = _projection(repository)
    packet[field] = ["malformed"]
    with pytest.raises(ValueError, match="malformed"):
        present_repository_evidence(packet)
