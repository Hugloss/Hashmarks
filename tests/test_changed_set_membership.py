"""Changed-set logical membership and supplied collection retain distinct authority."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from contract_assertions import assert_object, assert_records

from hashmarks import CodeMap
from hashmarks.verification_collection import COLLECTION_REPORT_SCHEMA
from hashmarks.verification_selection import verification_membership


@pytest.fixture
def repository(tmp_path: Path) -> Iterator[CodeMap]:
    workspace = tmp_path / "repository"
    tests = workspace / "tests"
    tests.mkdir(parents=True)
    (tests / "test_a.py").write_text(
        "raise RuntimeError('repository tests must not be imported')\n"
        "def test_a(): pass\n"
    )
    (tests / "test_b.test.ts").write_text("export const expected: string = 'ok';\n")
    (tests / "test_z.py").write_text("def test_z(): pass\n")
    with CodeMap(
        workspace,
        state_dir=tmp_path / "state",
        artifact_db=tmp_path / "artifacts.sqlite3",
    ) as repository:
        repository.index.sync()
        yield repository


def test_changed_set_membership_contains_exactly_available_returned_targets(
    repository: CodeMap,
) -> None:
    paths = ["tests/test_a.py", "tests/test_b.test.ts", "tests/test_z.py"]
    packet = repository.verification.changed_set([*reversed(paths), paths[0]])
    assert packet == repository.verification.changed_set(paths)
    assert packet["changed_paths"] == paths
    targets = assert_records(packet["targets"])
    assert [row["path"] for row in targets] == paths
    expected = verification_membership([{"path": paths[0]}, {"path": paths[2]}])
    assert packet["membership"] == expected
    assert {
        assert_object(row["member"])["member_id"]
        for row in targets
        if row["member"] is not None
    } == {row["member_id"] for row in assert_records(expected["members"])}
    unavailable = targets[1]
    assert unavailable["member"] is None
    nomination = assert_object(unavailable["nomination"])
    assert nomination["available"] is False
    assert nomination["reason"] == "unsupported-repository-verification-source"

    bounded = repository.verification.changed_set(paths, limit=2)
    returned = assert_records(bounded["targets"])
    assert [row["path"] for row in returned] == paths[:2]
    assert returned[1] == unavailable
    assert bounded["membership"] == verification_membership([{"path": paths[0]}])
    assert bounded["truncated"] is True
    assert bounded["completeness"] == "incomplete"
    assert assert_object(bounded["bounds"])["omitted_targets"] == 1
    assert bounded["negative_evidence_admissible"] is False


def _collection_report() -> dict[str, object]:
    return {
        "schema": COLLECTION_REPORT_SCHEMA,
        "selection_kind": "native-collected",
        "producer": {"name": "supplied-native-collector", "version": "1"},
        "provenance": {"report_id": "supplied:one", "revision": "opaque-run-id"},
        "scope": {"paths": ["tests/test_a.py"]},
        "status": "succeeded",
        "completeness": "unknown",
        "truncation": "unknown",
        "members": [
            {"path": "tests/test_a.py", "test_symbol": "test_a[opaque::parameter]"}
        ],
        "inputs": [{"path": "tests/test_a.py", "member_revision": None}],
    }


def test_changed_set_preserves_canonical_supplied_collection_and_unknown_source(
    repository: CodeMap,
) -> None:
    report = _collection_report()
    canonical = repository.verification.observe_membership(report)
    packet = repository.verification.changed_set(
        ["tests/test_a.py"], collection_report=report
    )
    collection = assert_object(packet["collection"])
    assert collection == canonical
    assert collection["report"] == report
    assert collection["membership_authority"] == "caller-claimed"
    assert collection["collection_completeness_authority"] == "caller-claimed"
    assert collection["repository_absence"] == "not-inferred"
    assert assert_object(collection["source_equivalence"])["state"] == "unknown"
    assert assert_records(collection["source_members"])[0]["member_revision"]
    bundle = assert_records(assert_object(collection["correlation"])["bundles"])[0]
    assert bundle["producer"] == report["producer"]
    assert bundle["provenance"] == report["provenance"]
    assert bundle["provenance_authority"] == "caller-claimed"
    assert bundle["completeness"] == "unknown"
    assert collection["membership"] == verification_membership(
        assert_records(report["members"])
    )
    assert packet["membership"] == verification_membership(
        [{"path": "tests/test_a.py"}]
    )
    assert packet["membership"] != collection["membership"]
    assert packet["correlation"] is None
    assert packet["negative_evidence_admissible"] is False
    assert (
        packet["execution_authority"] == collection["execution_authority"] == "external"
    )
