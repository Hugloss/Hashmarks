"""Changed-set verification borrows correlation and canonical presentation."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from copy import deepcopy
from pathlib import Path

import pytest
from contract_assertions import assert_array, assert_object, assert_records

from hashmarks import CodeMap
from hashmarks.evidence_presentation import (
    present_repository_evidence,
    presentation_response,
)
from hashmarks.evidence_presentation_conformance import validate_evidence_presentation


def _repository(root: Path) -> None:
    root.mkdir(exist_ok=True)
    (root / "owner.py").write_text("def calculate():\n    return 1\n")
    (root / "tests").mkdir()
    (root / "tests/test_owner.py").write_text(
        "from owner import calculate\n"
        "def test_calculate():\n    assert calculate() == 1\n"
    )


def _bundle(*anchors: Mapping[str, object]) -> list[dict[str, object]]:
    return [
        {
            "bundle_id": "runtime",
            "producer": {"kind": "traceback"},
            "scope": {"run": "external-observation"},
            "provenance": {"observed_at": "2026-11-01T12:00:00Z"},
            "completeness": "unknown",
            "truncation": "unknown",
            "anchors": list(anchors),
        }
    ]


def _anchor(packet: Mapping[str, object]) -> dict[str, object]:
    correlation = assert_object(packet["correlation"])
    bundle = assert_records(correlation["bundles"])[0]
    return assert_records(bundle["anchors"])[0]


@pytest.fixture(scope="module")
def repository(tmp_path_factory: pytest.TempPathFactory) -> Iterator[CodeMap]:
    root = tmp_path_factory.mktemp("changed-set-correlation")
    _repository(root)
    with CodeMap(root) as repository:
        repository.index.sync()
        yield repository


@pytest.fixture(scope="module")
def packet(repository: CodeMap) -> dict[str, object]:
    return repository.verification.changed_set(
        ["tests/test_owner.py"],
        correlation_bundles=_bundle(
            {
                "anchor_id": "frame",
                "path": "/app/owner.py",
                "line": 2,
                "symbol": "calculate",
                "metadata": {"revision": "opaque-runtime-version"},
            }
        ),
        path_mappings=[{"external_prefix": "/app", "repository_prefix": ""}],
    )


def test_changed_set_keeps_canonical_runtime_correlation(
    repository: CodeMap, packet: dict[str, object]
) -> None:
    correlation = assert_object(packet["correlation"])
    direct = repository.correlation.observe(
        _bundle(
            {
                "anchor_id": "frame",
                "path": "/app/owner.py",
                "line": 2,
                "symbol": "calculate",
                "metadata": {"revision": "opaque-runtime-version"},
            }
        ),
        path_mappings=[{"external_prefix": "/app", "repository_prefix": ""}],
        include_relationships=False,
    )
    assert correlation == direct
    anchor = _anchor(packet)
    assert assert_object(anchor["resolution"])["state"] == "resolved-unique"
    assert assert_object(anchor["source_equivalence"])["state"] == "unknown"
    assert correlation["causation"] == "not-inferred"
    assert correlation["storage"] == "request-scoped-not-persisted"
    assert packet["execution_authority"] == "external"


def test_changed_set_runtime_source_revision_survives_drift(tmp_path: Path) -> None:
    _repository(tmp_path)
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        member, _ = repository.source.member("owner.py")
        bundles = _bundle(
            {
                "anchor_id": "frame",
                "path": "owner.py",
                "line": 2,
                "symbol": "calculate",
                "member_revision": member["member_revision"],
            }
        )
        before = repository.verification.changed_set(
            ["owner.py"], correlation_bundles=bundles
        )
        (tmp_path / "owner.py").write_text("def calculate():\n    return 2\n")
        repository.index.sync(["owner.py"])
        after = repository.verification.changed_set(
            ["owner.py"], correlation_bundles=bundles
        )
    assert assert_object(_anchor(before)["source_equivalence"])["state"] == "proven"
    assert assert_object(_anchor(after)["source_equivalence"])["state"] == "mismatch"
    assert before["evidence_identity"] != after["evidence_identity"]


def test_changed_set_keeps_ambiguous_runtime_symbol(tmp_path: Path) -> None:
    _repository(tmp_path)
    (tmp_path / "other.py").write_text("def calculate():\n    return 2\n")
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        packet = repository.verification.changed_set(
            ["owner.py"],
            correlation_bundles=_bundle({"anchor_id": "frame", "symbol": "calculate"}),
        )
    resolution = assert_object(_anchor(packet)["resolution"])
    assert resolution["state"] == "resolved-ambiguous"
    assert {row["path"] for row in assert_records(resolution["candidates"])} == {
        "owner.py",
        "other.py",
    }
    assert assert_object(_anchor(packet)["source_equivalence"])["state"] == "unknown"


@pytest.mark.parametrize(
    ("completeness", "truncation", "state"),
    [("unknown", "unknown", "unknown"), ("incomplete", "truncated", "incomplete")],
)
def test_changed_set_preserves_runtime_scope_uncertainty(
    repository: CodeMap, completeness: str, truncation: str, state: str
) -> None:
    bundles = _bundle({"anchor_id": "missing", "path": "missing.py"})
    bundles[0].update(completeness=completeness, truncation=truncation)
    packet = repository.verification.changed_set(
        ["owner.py"], correlation_bundles=bundles
    )
    correlation = assert_object(packet["correlation"])
    scope = assert_object(correlation["completeness"])
    assert scope["state"] == state
    assert scope["negative_evidence"] == "not-admissible"
    assert scope["authority"] == "caller-claimed"
    assert assert_object(_anchor(packet)["resolution"])["state"] == "unresolved"


def test_changed_set_correlation_reuses_existing_anchor_bound(
    repository: CodeMap,
) -> None:
    bundles = _bundle(
        *({"anchor_id": f"frame:{index}", "path": "owner.py"} for index in range(257))
    )
    with pytest.raises(ValueError, match="anchors|exceeds"):
        repository.verification.changed_set(["owner.py"], correlation_bundles=bundles)


def test_changed_set_without_runtime_input_does_not_invent_observations(
    repository: CodeMap,
) -> None:
    packet = repository.verification.changed_set(["owner.py"])
    assert packet["correlation"] is None
    assert packet["negative_evidence_admissible"] is False


@pytest.mark.parametrize("language", ["python", "typescript"])
def test_changed_set_relevance_uses_authored_nomination_without_legacy_planning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    if language == "python":
        _repository(tmp_path)
        changed = "owner.py"
        verifier = "tests/test_owner.py"
    else:
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "src/total.ts").write_text(
            "export function total() { return 1; }\n"
        )
        (tmp_path / "tests/total.test.ts").write_text(
            'import { total } from "../src/total";\n'
            'import { test, expect } from "vitest";\n'
            'test("total", () => { expect(total()).toBe(1); });\n'
        )
        (tmp_path / "package.json").write_text(
            '{"name":"example","devDependencies":{"vitest":"^3"}}'
        )
        changed = "src/total.ts"
        verifier = "tests/total.test.ts"

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("changed-set evidence cannot consult command planning")

    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        for name in ("plan", "_python_verification_plan", "_pytest_declared"):
            monkeypatch.setattr(repository.verification, name, forbidden)
        packet = repository.verification.changed_set([changed])
    relevance = assert_object(assert_records(packet["changes"])[0]["relevance"])
    candidate = next(
        row
        for row in assert_records(relevance["candidates"])
        if row["path"] == verifier
    )
    assert candidate["runner_available"] is True


def _reexport_repository(root: Path) -> None:
    for path, source in {
        "pkg/__init__.py": "from .bridge import total\n",
        "pkg/bridge.py": "from .owner import total\n",
        "pkg/owner.py": "def total(): return 1\n",
        "pkg/other.py": "def total(): return 2\n",
        "tests/test_total.py": "from pkg import total\ndef test_total(): assert total() == 1\n",
    }.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source)


def test_changed_set_binds_every_qualified_reexport_contributor(tmp_path: Path) -> None:
    _reexport_repository(tmp_path)
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        packet = repository.verification.changed_set(["pkg/owner.py"])
        change = assert_records(packet["changes"])[0]
        relationship = next(
            row
            for row in assert_records(change["relationships"])
            if row["target"] == "tests/test_total.py"
        )
        members = assert_records(relationship["supporting_source_members"])
        assert {"pkg/__init__.py", "pkg/bridge.py"} <= {row["path"] for row in members}
        for row in members:
            current, _ = repository.source.member(str(row["path"]))
            assert row["member_revision"] == current["member_revision"]


@pytest.mark.parametrize("facade", ["pkg/__init__.py", "pkg/bridge.py"])
def test_changed_set_rechecks_reexport_contributors_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, facade: str
) -> None:
    _reexport_repository(tmp_path)
    with CodeMap(tmp_path) as repository:
        repository.index.sync()
        original = repository.verification._changed_target
        changed = False

        def mutate(path: str) -> dict[str, object]:
            nonlocal changed
            target = original(path)
            if not changed:
                changed = True
                (tmp_path / facade).write_text("from .other import total\n")
            return target

        monkeypatch.setattr(repository.verification, "_changed_target", mutate)
        packet = repository.verification.changed_set(["pkg/owner.py"])
    assert changed is True
    assert packet["targets"] == []


@pytest.mark.parametrize("format", ["structured", "compact", "text"])
def test_changed_set_presentation_reuses_native_nested_evidence(
    packet: dict[str, object], format: str
) -> None:
    original = deepcopy(packet)
    response = presentation_response("changed_set_verification", packet, format=format)
    projection = assert_object(response["presentation"])
    assert projection["supported"] is True
    assert projection["source_evidence_identity"] == packet["evidence_identity"]
    assert validate_evidence_presentation(packet, projection)["valid"] is True
    findings = [
        row
        for group in assert_records(projection["groups"])
        for row in assert_records(group["findings"])
    ]
    correlated = next(
        row
        for row in findings
        if row["source_refs"] == ["/correlation/bundles/0/anchors/0"]
    )
    assert correlated["details"] == _anchor(packet)
    assert correlated["assertion"] == "producer_claim"
    native = present_repository_evidence(
        assert_object(packet["correlation"]), format=format
    )
    native_rows = [
        row
        for group in assert_records(native["groups"])
        for row in assert_records(group["findings"])
    ]
    standalone = next(
        row for row in native_rows if row["source_refs"] == ["/bundles/0/anchors/0"]
    )
    assert correlated["details"] == standalone["details"]
    assert correlated["assertion"] == standalone["assertion"]
    change = assert_records(packet["changes"])[0]
    assert any(
        row["source_refs"] == ["/changes/0/consumer_scope"]
        and row["details"] == change["consumer_scope"]
        for row in findings
    )
    assert (
        assert_object(correlated["source_context"])["negative_evidence_admissible"]
        is False
    )
    target = assert_records(packet["targets"])[0]
    nomination = assert_object(target["nomination"])
    assert any(
        row["source_refs"] == ["/targets/0/nomination/verification_target"]
        and row["details"] == nomination["verification_target"]
        for row in findings
    )
    assert packet == original == response["result"]


@pytest.mark.parametrize("key", ["changes", "targets"])
def test_changed_set_presentation_rejects_malformed_collections(
    packet: dict[str, object], key: str
) -> None:
    malformed = {**packet, key: ["invalid"]}
    with pytest.raises(ValueError, match=f"malformed changed-set verification {key}"):
        present_repository_evidence(malformed)
