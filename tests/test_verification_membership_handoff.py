"""Supplied native collection stays a claim even when its source bytes match."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records

from hashmarks import (
    CodeMap,
    native_producer_implementation_identity,
    validate_native_consumer_bundle,
)
from hashmarks.codemap.repository_observation import evidence_identity, packet_digest
from hashmarks.file_store import UnstableFileError
from hashmarks.verification_collection import (
    COLLECTION_REPORT_SCHEMA,
    MEMBERSHIP_OBSERVATION_SCHEMA,
)
from hashmarks.verification_selection import (
    validate_verification_membership,
    verification_membership,
)


@pytest.fixture
def repository(tmp_path: Path) -> Iterator[CodeMap]:
    workspace = tmp_path / "repository"
    workspace.mkdir()
    (workspace / "test_example.py").write_text(
        "raise RuntimeError('repository tests must never be imported')\n"
        "def test_top(): pass\nclass TestGroup:\n    def test_case(self): pass\n"
    )
    (workspace / "pyproject.toml").write_text(
        '[project]\nname="neutral"\nversion="1"\n'
    )
    with CodeMap(workspace, state_dir=tmp_path / "state") as codemap:
        codemap.index.sync()
        yield codemap


def _report(repository: CodeMap, *extra_inputs: str) -> dict[str, object]:
    inputs = []
    for path in ("test_example.py", "pyproject.toml", *extra_inputs):
        member, _ = repository.source.member(path)
        inputs.append({"path": path, "member_revision": member["member_revision"]})
    return {
        "schema": COLLECTION_REPORT_SCHEMA,
        "selection_kind": "native-collected",
        "producer": {"name": "neutral-collector", "version": "1"},
        "provenance": {"report_id": "supplied:one"},
        "scope": {"paths": ["test_example.py"]},
        "status": "succeeded",
        "completeness": "complete",
        "truncation": "complete",
        "members": [
            {"path": "test_example.py", "test_symbol": "test_top"},
            {"path": "test_example.py", "test_symbol": "TestGroup::test_case[a::b]"},
        ],
        "inputs": inputs,
    }


def _resign(packet: dict[str, object]) -> None:
    packet["observation_identity"] = evidence_identity(
        MEMBERSHIP_OBSERVATION_SCHEMA,
        {key: value for key, value in packet.items() if key != "observation_identity"},
    )


def test_membership_preserves_native_selectors_and_existing_identity(
    repository: CodeMap,
) -> None:
    report = _report(repository)
    packet = repository.verification.observe_membership(report)
    membership = assert_object(packet["membership"])
    assert membership == verification_membership(assert_records(report["members"]))
    assert validate_verification_membership(membership)["valid"] is True
    assert assert_object(packet["source_equivalence"])["state"] == "proven"
    assert packet["membership_authority"] == "caller-claimed"
    assert packet["collection_completeness_authority"] == "caller-claimed"
    assert packet["repository_absence"] == "not-inferred"
    result = validate_native_consumer_bundle(
        packet,
        expected_producer_implementation_identity=native_producer_implementation_identity(),
    )
    assert result["valid"] is True, result
    normalized = assert_object(result.get("normalized"))
    assert normalized["members"] == membership["members"]
    assert result["execution_authority"] == result["result_authority"] == "external"


def test_ordering_and_caller_mutation_do_not_change_issued_membership(
    repository: CodeMap,
) -> None:
    report = _report(repository)
    before = repository.verification.observe_membership(report)
    report["members"] = list(reversed(assert_records(report["members"])))
    report["inputs"] = list(reversed(assert_records(report["inputs"])))
    reordered = repository.verification.observe_membership(report)
    assert before == reordered
    assert_records(report["members"])[0]["test_symbol"] = "changed-by-caller"
    assert validate_native_consumer_bundle(before)["valid"] is True
    assert assert_object(before["report"])["members"] != report["members"]


def test_caller_selection_does_not_become_a_native_collection(
    repository: CodeMap,
) -> None:
    report = _report(repository)
    native = repository.verification.observe_membership(report)
    report["selection_kind"] = "caller-selected"
    selected = repository.verification.observe_membership(report)
    assert native["membership"] == selected["membership"]
    assert native["report_identity"] != selected["report_identity"]
    assert assert_object(selected["report"])["selection_kind"] == "caller-selected"
    assert selected["membership_authority"] == "caller-claimed"


def test_today_source_does_not_supply_missing_collection_revision(
    repository: CodeMap,
) -> None:
    report = _report(repository)
    report["inputs"] = []
    packet = repository.verification.observe_membership(report)
    equivalence = assert_object(packet["source_equivalence"])
    assert equivalence == {
        "state": "unknown",
        "scope": "explicit-nominated-inputs",
        "input_count": 1,
    }
    result = validate_native_consumer_bundle(packet, require_fresh=True)
    assert result["valid"] is False
    assert "fresh-source-evidence-required" in result["reasons"]


@pytest.mark.parametrize("path", ["test_example.py", "pyproject.toml"])
def test_source_or_configuration_change_is_not_rebound_to_old_collection(
    repository: CodeMap, path: str
) -> None:
    report = _report(repository)
    before = repository.verification.observe_membership(report)
    target = repository.workspace / path
    target.write_text(target.read_text() + "\n# changed after external collection\n")
    unsynchronized = repository.verification.observe_membership(report)
    assert assert_object(unsynchronized["source_equivalence"])["state"] == "unknown"
    repository.index.sync([path])
    after = repository.verification.observe_membership(report)
    assert assert_object(after["source_equivalence"])["state"] == "mismatch"
    assert before["membership"] == after["membership"]
    assert before["observation_identity"] != after["observation_identity"]
    assert validate_native_consumer_bundle(before)["valid"] is True
    assert validate_native_consumer_bundle(after)["valid"] is True
    assert validate_native_consumer_bundle(after, require_fresh=True)["valid"] is False


def _repair_capture(root: Path, *, git_backed: bool) -> None:
    root.mkdir()
    (root / "owner.py").write_text("def widget(): return 'old'\n")
    (root / "test_example.py").write_text(
        "from owner import widget\ndef test_top(): assert widget() == 'new'\n"
    )
    (root / "pyproject.toml").write_text("[tool.pytest.ini_options]\ntestpaths=['.']\n")
    if not git_backed:
        return
    for command in (
        ["git", "init", "--quiet"],
        ["git", "add", "--all"],
        [
            "git",
            "-c",
            "user.name=Neutral fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "same captured baseline",
        ],
    ):
        subprocess.run(command, cwd=root, check=True)


def _assert_reobserved_membership(
    repository: CodeMap,
    report: dict[str, object],
    previous: dict[str, object],
) -> None:
    reobserved = repository.verification.observe_membership(report)
    recollected = repository.verification.observe_membership(
        _report(repository, "owner.py")
    )
    assert assert_object(reobserved["source_equivalence"])["state"] == "mismatch"
    assert assert_object(recollected["source_equivalence"])["state"] == "proven"
    assert (
        previous["membership"] == reobserved["membership"] == recollected["membership"]
    )
    assert previous["observation_identity"] != recollected["observation_identity"]
    assert previous["source_members"] != recollected["source_members"]
    assert validate_native_consumer_bundle(previous)["valid"] is True
    for observation in (reobserved, recollected):
        assert assert_object(observation["repository"])["freshness"] == "unknown"
        checked = validate_native_consumer_bundle(
            observation,
            expected_producer_implementation_identity=native_producer_implementation_identity(),
        )
        assert checked["valid"] is True, checked
        assert (
            checked["execution_authority"] == checked["result_authority"] == "external"
        )
        assert (
            validate_native_consumer_bundle(observation, require_fresh=True)["valid"]
            is False
        )


@pytest.mark.parametrize(
    "git_backed", [False, pytest.param(True, marks=pytest.mark.host_git)]
)
@pytest.mark.parametrize(
    "changed_path", ["owner.py", "test_example.py", "pyproject.toml"]
)
def test_repair_handoff_separates_membership_from_source_and_capture(
    tmp_path: Path, git_backed: bool, changed_path: str
) -> None:
    task = "Change owner.py widget implementation and verify test_top"
    for name in ("before", "after"):
        _repair_capture(tmp_path / name, git_backed=git_backed)
    with CodeMap(tmp_path / "before", state_dir=tmp_path / "before-state") as before:
        before.index.sync()
        previous = before.tasks.evidence(task)
        report = _report(before, "owner.py")
        membership = before.verification.observe_membership(report)
        next_bytes = (before.workspace / changed_path).read_bytes().replace(
            b"'old'", b"'new'"
        ) + b"\n# next captured source\n"
        (before.workspace / changed_path).write_bytes(next_bytes)
        delta = before.changes.task_delta(
            task, [changed_path], previous_evidence=previous
        )
        assert delta["path_changes"][0]["state"] == "changed"
        assert delta["generation_after"] > delta["generation_before"]
        _assert_reobserved_membership(before, report, membership)

    with CodeMap(tmp_path / "after", state_dir=tmp_path / "after-state") as after:
        (after.workspace / changed_path).write_bytes(next_bytes)
        after.index.sync()
        fresh = after.tasks.evidence(task)
        assert fresh["provenance"]["freshness"] == "unknown"
        if git_backed:
            assert (
                fresh["evidence_receipt"]["repository_identity"]
                == previous["evidence_receipt"]["repository_identity"]
            )
            delta = after.changes.task_delta(
                task, [changed_path], previous_evidence=previous
            )
            assert delta["path_changes"] == [
                {"path": changed_path, "state": "unchanged"}
            ]
            if changed_path == "owner.py":
                assert delta["previous_index_binding"] == "mismatch"
                assert "candidate-source-revision" in delta["invalidated"]
        else:
            with pytest.raises(ValueError, match="repository-mismatch"):
                after.changes.task_delta(
                    task, [changed_path], previous_evidence=previous
                )
        _assert_reobserved_membership(after, report, membership)


def test_deleted_source_remains_unavailable(repository: CodeMap) -> None:
    report = _report(repository)
    (repository.workspace / "test_example.py").unlink()
    packet = repository.verification.observe_membership(report)
    assert assert_object(packet["source_equivalence"])["state"] == "unknown"
    correlation = assert_object(packet["correlation"])
    bindings = assert_records(
        assert_object(correlation["repository_evidence"])["bindings"]
    )
    source = next(
        row
        for binding in bindings
        for row in assert_records(binding["evidence"])
        if row["path"] == "test_example.py"
    )
    assert source["state"] == "known-absent"
    assert validate_native_consumer_bundle(packet)["valid"] is True


@pytest.mark.parametrize("visibility", ["deny", "outline"])
def test_source_visibility_cannot_be_upgraded_by_a_matching_revision(
    repository: CodeMap, visibility: str
) -> None:
    report = _report(repository)
    (repository.workspace / ".hashmarks-context.toml").write_text(
        f'[[rule]]\npattern="test_example.py"\nvisibility="{visibility}"\n'
    )
    repository.index.sync()
    packet = repository.verification.observe_membership(report)
    assert assert_object(packet["source_equivalence"])["state"] == "unknown"
    source = next(
        row
        for row in assert_records(packet["source_members"])
        if row["path"] == "test_example.py"
    )
    assert source["state"] == "unsupported"


def test_oversized_source_remains_unknown(repository: CodeMap) -> None:
    report = _report(repository)
    (repository.workspace / "test_example.py").write_text("x" * 1_048_577)
    packet = repository.verification.observe_membership(report)
    assert assert_object(packet["source_equivalence"])["state"] == "unknown"
    source = next(
        row
        for row in assert_records(packet["source_members"])
        if row["path"] == "test_example.py"
    )
    assert source["reason"] == "source-size-bound"


def test_unreadable_source_remains_unknown(
    repository: CodeMap, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _report(repository)

    def unavailable(path: Path) -> None:
        raise PermissionError(path)

    monkeypatch.setattr(repository.file_store, "read_bytes_stable", unavailable)
    packet = repository.verification.observe_membership(report)
    assert assert_object(packet["source_equivalence"])["state"] == "unknown"
    assert all(
        row["state"] == "unknown" for row in assert_records(packet["source_members"])
    )


def test_change_during_correlation_cannot_issue_a_byte_bound_membership(
    repository: CodeMap, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _report(repository)
    original = repository.correlation.observe

    def changed(bundles: object, *, include_relationships: bool) -> dict[str, object]:
        packet = original(
            assert_records(bundles), include_relationships=include_relationships
        )
        (repository.workspace / "test_example.py").write_text("def changed(): pass\n")
        return packet

    monkeypatch.setattr(repository.correlation, "observe", changed)
    with pytest.raises(UnstableFileError, match="changed during observation"):
        repository.verification.observe_membership(report)


def test_current_source_qualification_does_not_strengthen_collection_completeness(
    repository: CodeMap, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _report(repository)
    report.update(status="failed", completeness="incomplete", truncation="unknown")
    generation = repository.store.generation()
    monkeypatch.setattr(
        repository.reads, "generation_status", lambda: (generation, generation, False)
    )
    packet = repository.verification.observe_membership(report)
    result = validate_native_consumer_bundle(packet, require_fresh=True)
    assert result["valid"] is True, result
    assert assert_object(packet["report"])["completeness"] == "incomplete"
    assert packet["collection_completeness_authority"] == "caller-claimed"


@pytest.mark.parametrize("status", ["failed", "unknown"])
def test_partial_collection_preserves_claimed_incompleteness(
    repository: CodeMap, status: str
) -> None:
    report = _report(repository)
    report.update(status=status, completeness="incomplete", truncation="unknown")
    packet = repository.verification.observe_membership(report)
    assert assert_object(packet["report"])["status"] == status
    assert assert_object(packet["report"])["completeness"] == "incomplete"
    assert packet["collection_completeness_authority"] == "caller-claimed"
    assert validate_native_consumer_bundle(packet)["valid"] is True


def test_explicit_empty_is_not_unknown_membership_or_repository_absence(
    repository: CodeMap,
) -> None:
    report = _report(repository)
    report["members"] = []
    empty = repository.verification.observe_membership(report)
    membership = assert_object(empty["membership"])
    assert membership["schema"] == "hashmarks.verification-empty-membership.v1"
    assert membership["members"] == [] and membership["member_count"] == 0
    assert validate_verification_membership(membership)["valid"] is False
    assert validate_native_consumer_bundle(empty)["valid"] is True
    report.update(
        members=None, status="unknown", completeness="unknown", truncation="unknown"
    )
    unknown = repository.verification.observe_membership(report)
    assert unknown["membership"] is None
    result = validate_native_consumer_bundle(unknown)
    assert result["valid"] is True
    assert assert_object(result.get("normalized"))["members"] is None
    assert unknown["observation_identity"] != empty["observation_identity"]
    assert (
        empty["repository_absence"] == unknown["repository_absence"] == "not-inferred"
    )


@pytest.mark.parametrize(
    "change",
    ["duplicate", "unsafe-path", "invalid-revision", "complete-failure", "extra-field"],
)
def test_invalid_supplied_reports_fail_before_observation(
    repository: CodeMap, change: str
) -> None:
    report = _report(repository)
    if change == "duplicate":
        members = assert_records(report["members"])
        report["members"] = [*members, members[0]]
    elif change == "unsafe-path":
        report["members"] = [{"path": "../foreign.py"}]
    elif change == "invalid-revision":
        report["inputs"] = [
            {"path": "test_example.py", "member_revision": "unqualified"}
        ]
    elif change == "complete-failure":
        report["status"] = "failed"
    else:
        report["execute"] = True
    with pytest.raises(ValueError):
        repository.verification.observe_membership(report)


def test_explicit_input_bound_cannot_silently_truncate_source_scope(
    repository: CodeMap,
) -> None:
    report = _report(repository)
    report["inputs"] = [
        {"path": f"configuration/{number}.toml", "member_revision": None}
        for number in range(257)
    ]
    with pytest.raises(ValueError, match="256"):
        repository.verification.observe_membership(report)


@pytest.mark.parametrize(
    "field", ["membership", "repository", "membership_authority", "source_equivalence"]
)
def test_resigned_projection_tampering_is_rejected(
    repository: CodeMap, field: str
) -> None:
    packet = repository.verification.observe_membership(_report(repository))
    if field == "membership":
        assert_records(assert_object(packet[field])["members"])[0]["test_symbol"] = (
            "other"
        )
    elif field == "repository":
        assert_object(packet[field])["source_identity"] = "sha256:" + "0" * 64
    elif field == "membership_authority":
        packet[field] = "hashmarks-proven"
    else:
        assert_object(packet[field])["state"] = "unknown"
    _resign(packet)
    assert validate_native_consumer_bundle(packet)["valid"] is False


@pytest.mark.parametrize(
    ("section", "field", "numeric_kind"),
    [
        ("membership", "member_count", "boolean"),
        ("source_equivalence", "input_count", "boolean"),
        ("repository", "codemap_generation", "float"),
    ],
)
@pytest.mark.parametrize("resign", [False, True])
def test_json_numeric_types_cannot_reuse_observation_identity(
    repository: CodeMap,
    section: str,
    field: str,
    numeric_kind: str,
    resign: bool,
) -> None:
    report = _report(repository)
    report["members"] = assert_records(report["members"])[:1]
    report["inputs"] = assert_records(report["inputs"])[:1]
    packet = repository.verification.observe_membership(report)
    projection = assert_object(packet[section])
    original = projection[field]
    assert type(original) is int
    replacement = True if numeric_kind == "boolean" else float(original)
    assert replacement == original
    projection[field] = replacement
    if resign:
        _resign(packet)
    assert validate_native_consumer_bundle(packet)["valid"] is False


def test_report_claims_cannot_be_substituted_under_retained_correlation(
    repository: CodeMap,
) -> None:
    packet = repository.verification.observe_membership(_report(repository))
    report = assert_object(packet["report"])
    assert_object(report["provenance"])["report_id"] = "substituted-report"
    packet["report_identity"] = evidence_identity(COLLECTION_REPORT_SCHEMA, report)
    _resign(packet)
    assert validate_native_consumer_bundle(packet)["valid"] is False


def test_correlation_equivalence_tampering_does_not_establish_revision_proof(
    repository: CodeMap,
) -> None:
    report = _report(repository)
    report["inputs"] = []
    packet = repository.verification.observe_membership(report)
    correlation = assert_object(packet["correlation"])
    anchors = assert_records(assert_records(correlation["bundles"])[0]["anchors"])
    anchors[0]["source_equivalence"] = {"state": "proven", "basis": []}
    correlation["correlation_identity"] = "sha256:" + packet_digest(
        "hashmarks.evidence-correlation.v2",
        {
            key: value
            for key, value in correlation.items()
            if key != "correlation_identity"
        },
    )
    assert_object(packet["source_equivalence"])["state"] = "proven"
    _resign(packet)
    assert validate_native_consumer_bundle(packet)["valid"] is False


def test_producer_expectation_and_legacy_contract_are_independent(
    repository: CodeMap,
) -> None:
    packet = repository.verification.observe_membership(_report(repository))
    mismatch = validate_native_consumer_bundle(
        packet, expected_producer_implementation_identity="sha256:" + "0" * 64
    )
    assert "producer-implementation-identity-not-expected" in mismatch["reasons"]
    assert validate_native_consumer_bundle(packet, contract={})["valid"] is False
    assert validate_native_consumer_bundle(packet, handoff={})["valid"] is False


def test_public_generic_validation_does_not_load_own_suite_configuration() -> None:
    code = """
import sys
from hashmarks import CodeMap, validate_native_consumer_bundle
validate_native_consumer_bundle({}, {})
for name in ('hashmarks.test_shards', 'hashmarks.qualification_units', 'hashmarks.qualification_classification'):
    assert name not in sys.modules, name
"""
    subprocess.run(
        [sys.executable, "-c", code], check=True, capture_output=True, text=True
    )


def test_standalone_example_uses_public_observation_and_validation() -> None:
    from examples.verification_membership import run_example

    result = run_example()
    matching = assert_object(result["matching"])
    changed = assert_object(result["changed"])
    empty = assert_object(result["empty"])
    assert assert_object(matching["source_equivalence"])["state"] == "proven"
    assert assert_object(changed["source_equivalence"])["state"] == "mismatch"
    assert assert_object(empty["membership"])["members"] == []
