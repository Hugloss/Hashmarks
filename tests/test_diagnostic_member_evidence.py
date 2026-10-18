"""Producer-handoff and conserved per-file diagnostic evidence contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import TYPE_CHECKING, Any, TypedDict, Unpack

import pytest
from contract_assertions import (
    assert_array,
    assert_integer,
    assert_number,
    assert_object,
    assert_records,
    assert_text,
)

from hashmarks.codemap.diagnostic_observation import (
    diagnostic_observation_delta,
    external_diagnostic_observation,
)
from hashmarks.codemap.diagnostic_source_revision import (
    diagnostic_source_revision_evidence,
)
from hashmarks.codemap.engine import CodeMap
from hashmarks.codemap.repository_delta import (
    RepositoryGenerationBinding,
)
from hashmarks.codemap.repository_observation import packet_digest
from hashmarks.digest import FILE_DOMAIN, hash_bytes
from hashmarks.evidence_presentation import present_repository_evidence
from hashmarks.mcp_surface import HashmarksMcpSurface, McpSurfaceError
from hashmarks.repository_intelligence_validation import (
    validate_repository_intelligence_evidence,
)

if TYPE_CHECKING:
    from pathlib import Path


def _provenance(version: object = 7, **overrides: object) -> dict[str, object]:
    return {
        "producer_session": "server:1",
        "document_lifetime": "open:1",
        "document_version": version,
        "source_kind": "buffer",
        "binding_basis": "reported-version",
        **overrides,
    }


def _diagnostic(path: str | None, rule: str = "E1") -> dict[str, object]:
    return {"tool": "fixture-lsp", "path": path, "rule": rule, "message": rule}


class _SourceOptions(TypedDict, total=False):
    source_revisions: Mapping[str, str] | None
    source_provenance: Mapping[str, Mapping[str, object]] | None
    collection_by_path: Mapping[str, str] | None


_BINDING = RepositoryGenerationBinding("repo:fixture", 7)


def _observe(
    rows: Sequence[Mapping[str, object]],
    *,
    binding: RepositoryGenerationBinding = _BINDING,
    scope_paths: Sequence[str] = ("owner.py", "related.py", "other.py"),
    collection_state: str | None = "fresh-complete",
    **options: Unpack[_SourceOptions],
) -> dict[str, object]:
    return external_diagnostic_observation(
        producer="fixture-lsp",
        binding=binding,
        environment_identity="config:fixture",
        outcome="fail",
        scope_paths=scope_paths,
        collection_state=collection_state,
        diagnostics=rows,
        **options,
    )


def _path_rows(delta: dict[str, object]) -> dict[str | None, dict[str, object]]:
    result: dict[str | None, dict[str, object]] = {}
    for row in assert_records(assert_object(delta["diagnostics"])["path_deltas"]):
        path = row["path"]
        assert path is None or isinstance(path, str)
        result[path] = row
    return result


def test_delayed_publication_keeps_its_captured_revision(tmp_path: Path) -> None:
    captured = b"print(old_name)\r\n"
    revision = hash_bytes(captured, domain=FILE_DOMAIN).hash
    (tmp_path / "owner.py").write_bytes(b"print(new_name)\n")
    packet = _observe(
        [_diagnostic("owner.py")],
        source_revisions={"owner.py": revision},
        source_provenance={"owner.py": _provenance(6)},
    )
    with CodeMap(tmp_path) as cm:
        cm.index.sync()
        current = cm.source.observe("owner.py")
    compared = diagnostic_source_revision_evidence(packet, [current])
    assert compared["different_count"] == 1
    assert (
        assert_object(assert_array(compared["rows"])[0])[
            "producer_claimed_member_revision"
        ]
        == revision
    )
    assert (
        assert_object(assert_object(compared["source_provenance"])["owner.py"])[
            "document_version"
        ]
        == 6
    )
    checked = validate_repository_intelligence_evidence(compared)
    assert checked["valid"] is True
    assert (
        assert_object(checked["normalized"])["source_provenance"]
        == packet["source_provenance"]
    )
    assert assert_object(checked["normalized"])["stale"] is None
    assert (
        validate_repository_intelligence_evidence(compared, require_fresh=True)["valid"]
        is False
    )


def test_unsaved_buffer_uses_exact_utf8_without_normalization(tmp_path: Path) -> None:
    buffer = "name = 'å'\r\n"
    revision = hash_bytes(buffer.encode("utf-8"), domain=FILE_DOMAIN).hash
    assert (
        revision
        != hash_bytes(buffer.replace("\r\n", "\n").encode(), domain=FILE_DOMAIN).hash
    )
    (tmp_path / "owner.py").write_text("name = 'saved'\n", encoding="utf-8")
    packet = _observe(
        [],
        source_revisions={"owner.py": revision},
        source_provenance={"owner.py": _provenance()},
    )
    with CodeMap(tmp_path) as cm:
        cm.index.sync()
        source = cm.source.observe("owner.py")
    compared = diagnostic_source_revision_evidence(packet, [source])
    assert compared["different_count"] == 1
    assert (
        assert_object(assert_object(packet["source_provenance"])["owner.py"])[
            "source_kind"
        ]
        == "buffer"
    )


def test_document_version_change_preserves_diagnostic_fact_identity() -> None:
    before = _observe(
        [_diagnostic("owner.py")],
        source_revisions={"owner.py": "a" * 64},
        source_provenance={"owner.py": _provenance(6)},
    )
    after = _observe(
        [_diagnostic("owner.py")],
        source_revisions={"owner.py": "a" * 64},
        source_provenance={"owner.py": _provenance(8)},
    )
    delta: Any = diagnostic_observation_delta(before, after)
    assert delta["source_provenance"]["changed"] is True
    assert delta["source_revisions"]["changed"] is False
    assert delta["diagnostics"]["added"] == delta["diagnostics"]["removed"] == []
    assert delta["diagnostics"]["unchanged_count"] == 1
    assert (
        assert_object(_path_rows(delta)["owner.py"]["source_revisions"])["state"]
        == "unchanged"
    )
    checked = validate_repository_intelligence_evidence(delta)
    assert checked["valid"] is True
    assert (
        assert_object(checked["normalized"])["source_provenance"]
        == delta["source_provenance"]
    )
    assert (
        assert_object(checked["normalized"])["projection_coverage"] == "projection-only"
    )
    omitted_refs = {
        row["source_ref"]
        for row in assert_records(
            assert_object(checked["normalized"])["unprojected_sections"]
        )
    }
    assert omitted_refs == {
        "/producer",
        "/producer_context",
        "/outcome",
        "/collection",
        "/authority",
        "/execution_effect",
        "/diagnostics/before_count",
        "/diagnostics/after_count",
        "/diagnostics/added",
        "/diagnostics/removed",
        "/diagnostics/unchanged_count",
        "/diagnostics/added_in_changed_scope",
        "/diagnostics/possible_relocations",
        "/diagnostics/source_correspondence",
        "/diagnostics/qualification",
    }


@pytest.mark.parametrize(
    "changed_context",
    [{"producer_session": "server:2"}, {"document_lifetime": "open:2"}],
)
def test_reused_versions_after_restart_or_reopen_preserve_incomparability(
    changed_context: dict[str, str],
) -> None:
    before = _observe(
        [_diagnostic("owner.py")],
        source_revisions={"owner.py": "a" * 64},
        source_provenance={"owner.py": _provenance()},
    )
    after = _observe(
        [],
        source_revisions={"owner.py": "a" * 64},
        source_provenance={"owner.py": _provenance(**changed_context)},
    )
    delta: Any = diagnostic_observation_delta(before, after)
    assert len(delta["diagnostics"]["removed"]) == 1
    assert delta["source_provenance"]["changed"] is True
    assert delta["diagnostics"]["qualification"]["qualified_removed_identities"] == []


def test_versionless_unbound_diagnostics_remain_unknown() -> None:
    packet = _observe(
        [_diagnostic("owner.py")],
        source_provenance={"owner.py": _provenance(None, binding_basis="unknown")},
    )
    assert "source_revisions" not in packet
    assert validate_repository_intelligence_evidence(packet)["valid"] is True
    compared = diagnostic_source_revision_evidence(packet, [])
    assert compared["coverage"] == "unknown"
    assert compared["unclaimed_diagnostic_count"] == 1
    assert compared["source_provenance"] == packet["source_provenance"]
    assert validate_repository_intelligence_evidence(compared)["valid"] is True


def test_unchanged_pull_facts_do_not_reuse_the_previous_source_binding() -> None:
    before = _observe(
        [_diagnostic("owner.py")],
        source_revisions={"owner.py": "a" * 64},
        source_provenance={
            "owner.py": _provenance(6, binding_basis="synchronized-request")
        },
    )
    after = _observe(
        assert_records(before["diagnostics"]),
        source_revisions={"owner.py": "b" * 64},
        source_provenance={
            "owner.py": _provenance(7, binding_basis="synchronized-request")
        },
    )
    delta: Any = diagnostic_observation_delta(before, after)
    assert delta["diagnostics"]["unchanged_count"] == 1
    assert delta["diagnostics"]["added"] == []
    assert delta["source_revisions"]["after"] == {"owner.py": "b" * 64}
    assert delta["source_provenance"]["after"]["owner.py"]["document_version"] == 7


@pytest.mark.parametrize(
    "invalid",
    [
        {"document_version": True},
        {"document_version": "7"},
        {"document_version": 2**31},
        {"producer_session": ""},
        {"document_lifetime": ""},
        {"source_kind": "editor"},
        {"binding_basis": "latest-file"},
        {"binding_basis": "unknown"},
        {"document_version": None},
    ],
)
def test_invalid_or_contradictory_provenance_fails_producer_and_public_validation(
    invalid: dict[str, object],
) -> None:
    claims = {"owner.py": _provenance(**invalid)}
    with pytest.raises(ValueError):
        _observe([], source_revisions={"owner.py": "a" * 64}, source_provenance=claims)
    packet = _observe([], source_revisions={"owner.py": "a" * 64})
    packet["source_provenance"] = claims
    assert validate_repository_intelligence_evidence(packet)["valid"] is False


@pytest.mark.parametrize("field", ["source_provenance", "collection_by_path"])
def test_member_claims_reject_out_of_scope_and_duplicate_aliases(field: str) -> None:
    revisions = {"owner.py": "a" * 64}
    for paths in (("outside.py",), ("owner.py", "./owner.py")):
        with pytest.raises(ValueError):
            if field == "source_provenance":
                _observe(
                    [],
                    source_revisions=revisions,
                    source_provenance={path: _provenance() for path in paths},
                )
            else:
                _observe(
                    [],
                    source_revisions=revisions,
                    collection_by_path={path: "fresh-complete" for path in paths},
                )


def test_per_path_complete_empty_report_differs_from_missing_report() -> None:
    before = _observe([_diagnostic("related.py"), _diagnostic("other.py")])
    after = _observe(
        [],
        collection_state="fresh-partial",
        collection_by_path={"related.py": "fresh-complete"},
    )
    delta = diagnostic_observation_delta(before, after, changed_paths=["owner.py"])
    rows = _path_rows(delta)
    assert rows["related.py"]["collection_after"] == "fresh-complete"
    assert rows["other.py"]["collection_after"] == "unknown"
    qualified = assert_object(delta["diagnostics"])["qualification"]
    assert (
        assert_object(qualified)["qualified_removed_identities"]
        == rows["related.py"]["removed_identities"]
    )
    assert (
        assert_object(qualified)["unqualified_removed_identities"]
        == rows["other.py"]["removed_identities"]
    )
    assert len(assert_array(assert_object(delta["diagnostics"])["removed"])) == 2
    assert validate_repository_intelligence_evidence(delta)["valid"] is True


@pytest.mark.parametrize("complete", [False, True])
def test_cross_file_changes_conserve_every_fact_without_claiming_causation(
    complete: bool,
) -> None:
    before = _observe(
        [
            _diagnostic("owner.py", "old"),
            _diagnostic("related.py", "old"),
            _diagnostic("other.py"),
        ],
        source_revisions={"related.py": "a" * 64},
    )
    after = _observe(
        [
            _diagnostic("owner.py", "new"),
            _diagnostic("related.py", "new"),
            _diagnostic("other.py"),
        ],
        source_revisions={"related.py": "a" * 64},
    )
    delta = diagnostic_observation_delta(
        before, after, changed_paths=["owner.py"], change_set_complete=complete
    )
    rows = _path_rows(delta)
    assert rows["owner.py"]["edit_relation"] == "reported-changed"
    assert rows["related.py"]["edit_relation"] == (
        "caller-claimed-unchanged" if complete else "unknown"
    )
    assert assert_object(rows["related.py"]["source_revisions"])["state"] == "unchanged"
    assert assert_object(rows["related.py"]["relationship"])["state"] == "unknown"
    assert len(assert_array(rows["other.py"]["unchanged_identities"])) == 1
    for field in ("added", "removed"):
        assert {
            identity
            for row in rows.values()
            for identity in assert_array(row[field + "_identities"])
        } == {
            row["identity"]
            for row in assert_records(assert_object(delta["diagnostics"])[field])
        }
    assert all(row["causation"] == "not-inferred" for row in rows.values())
    assert validate_repository_intelligence_evidence(delta)["valid"] is True
    assert (
        validate_repository_intelligence_evidence(delta, require_fresh=True)["valid"]
        is False
    )


def test_unlocated_and_out_of_scope_diagnostics_are_accounted_for() -> None:
    after = _observe(
        [_diagnostic(None), _diagnostic("../outside.py"), _diagnostic("unscoped.py")]
    )
    delta = diagnostic_observation_delta(
        _observe([]), after, changed_paths=["owner.py"], change_set_complete=True
    )
    rows = _path_rows(delta)
    assert len(assert_array(rows[None]["added_identities"])) == 2
    assert rows[None]["edit_relation"] == "unknown"
    assert rows["unscoped.py"]["scope_after"] is False
    assert rows["unscoped.py"]["collection_after"] == "unknown"
    assert (
        assert_object(assert_object(delta["diagnostics"])["qualification"])[
            "qualified_added_identities"
        ]
        == []
    )
    assert validate_repository_intelligence_evidence(delta)["valid"] is True


@pytest.mark.parametrize(
    "mutation",
    [
        "counts",
        "membership",
        "edit",
        "collection",
        "revision",
        "scope",
        "complete",
        "changed_flag",
    ],
)
def test_public_delta_validator_reproves_path_projection(mutation: str) -> None:
    delta = diagnostic_observation_delta(
        _observe([]), _observe([_diagnostic("related.py")]), changed_paths=["owner.py"]
    )
    tampered = deepcopy(delta)
    row = _path_rows(tampered)["related.py"]
    if mutation == "counts":
        diagnostics = assert_object(tampered["diagnostics"])
        diagnostics["after_count"] = assert_integer(diagnostics["after_count"]) + 1
    elif mutation == "membership":
        row["after_identities"] = []
    elif mutation == "edit":
        row["edit_relation"] = "reported-changed"
    elif mutation == "collection":
        row["collection_after"] = "unavailable"
    elif mutation == "revision":
        assert_object(row["source_revisions"])["state"] = "unchanged"
    elif mutation == "scope":
        row["scope_after"] = False
    elif mutation == "complete":
        assert_object(tampered["change_set"])["completeness"] = "complete"
    else:
        assert_object(tampered["source_provenance"])["changed"] = True
    assert validate_repository_intelligence_evidence(tampered)["valid"] is False


def test_public_delta_validator_reproves_collection_qualification() -> None:
    delta = diagnostic_observation_delta(
        _observe([]), _observe([_diagnostic("related.py")])
    )
    assert_object(assert_object(delta["diagnostics"])["qualification"])[
        "qualified_added_identities"
    ] = []
    assert validate_repository_intelligence_evidence(delta)["valid"] is False


def test_public_delta_validator_rejects_extra_producer_context_fields() -> None:
    delta = diagnostic_observation_delta(_observe([]), _observe([]))
    assert_object(assert_object(delta["producer_context"])["before"])[
        "document_version"
    ] = 7
    assert validate_repository_intelligence_evidence(delta)["valid"] is False


@pytest.mark.parametrize("bad", [None, 0, 1, "true", [], {}])
def test_change_set_completeness_requires_boolean_in_native_and_mcp(
    tmp_path: Path, bad: object
) -> None:
    before, after = _observe([]), _observe([])
    # Malformed values enter these boundaries through the JSON transport.
    untrusted_complete = json.loads(json.dumps(bad))
    with pytest.raises(ValueError, match="change_set_complete"):
        diagnostic_observation_delta(
            before, after, change_set_complete=untrusted_complete
        )
    surface = HashmarksMcpSurface(str(tmp_path), state_dir=str(tmp_path / "state"))
    try:
        with pytest.raises(McpSurfaceError, match="change_set_complete"):
            surface.evidence_comparison(
                before,
                after,
                result_mode="diagnostics",
                change_set_complete=untrusted_complete,
            )
    finally:
        surface.close()


def _correlation(root: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    (root / "owner.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (root / "related.py").write_text(
        "from owner import f\nprint(f())\n", encoding="utf-8"
    )
    (root / "other.py").write_text("def f():\n    return 2\nf()\n", encoding="utf-8")
    with CodeMap(root) as cm:
        cm.index.sync()
        # Supply current identity capability at its native boundary; retain real
        # indexed imports, symbol resolution, canonical bindings and identities.
        monkeypatch.setattr(
            cm.reads, "generation_status", lambda: (cm.store.generation(), None, False)
        )
        return cm.correlation.observe(
            [
                {
                    "bundle_id": "post-edit-diagnostics",
                    "producer": {"kind": "diagnostics"},
                    "anchors": [
                        {"anchor_id": "related", "path": "related.py"},
                        {"anchor_id": "other", "path": "other.py"},
                        {"anchor_id": "target", "module": "owner", "symbol": "f"},
                    ],
                }
            ]
        )


def test_related_annotation_uses_qualified_native_evidence_without_short_name_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    correlation = _correlation(tmp_path, monkeypatch)
    repo = assert_object(correlation["repository_evidence"])["repository"]
    binding = RepositoryGenerationBinding(
        assert_text(assert_object(repo)["repository_identity"]),
        assert_integer(assert_object(repo)["codemap_generation"]),
    )
    before = _observe([], binding=binding)
    after = _observe(
        [_diagnostic("related.py"), _diagnostic("other.py")], binding=binding
    )
    delta = diagnostic_observation_delta(
        before, after, changed_paths=["owner.py"], relationship_evidence=correlation
    )
    rows = _path_rows(delta)
    related = rows["related.py"]["relationship"]
    assert assert_object(related)["state"] == "observed-related"
    assert (
        assert_object(
            assert_object(assert_array(assert_object(related)["evidence"])[0])["edge"]
        )["target"]
        == "owner.f"
    )
    assert (
        assert_object(
            assert_object(assert_array(assert_object(related)["evidence"])[0])[
                "target_resolution"
            ]
        )["path"]
        == "owner.py"
    )
    assert (
        assert_object(assert_array(assert_object(related)["evidence"])[0])[
            "completeness"
        ]
        == "bounded-not-claimed"
    )
    assert assert_object(rows["other.py"]["relationship"])["state"] == "unknown"
    assert rows["related.py"]["edit_relation"] == "unknown"
    assert len(assert_array(assert_object(delta["diagnostics"])["added"])) == 2
    checked = validate_repository_intelligence_evidence(delta)
    assert checked["valid"] is True
    relationship_omission = next(
        row
        for row in assert_records(
            assert_object(checked["normalized"])["unprojected_sections"]
        )
        if row["source_ref"] == "/relationship_evidence"
    )
    assert (
        relationship_omission["source_identity"] == correlation["correlation_identity"]
    )
    assert (
        assert_object(checked["normalized"])["diagnostic_path_deltas"]
        == assert_object(delta["diagnostics"])["path_deltas"]
    )
    assert all(row["causation"] == "not-inferred" for row in rows.values())


@pytest.mark.parametrize("context", ["generation", "repository", "freshness"])
def test_stale_or_foreign_relationship_evidence_never_hides_diagnostic_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, context: str
) -> None:
    correlation = _correlation(tmp_path, monkeypatch)
    repo = assert_object(correlation["repository_evidence"])["repository"]
    binding = RepositoryGenerationBinding(
        assert_text(assert_object(repo)["repository_identity"])
        if context != "repository"
        else "foreign",
        assert_integer(assert_object(repo)["codemap_generation"])
        + (context == "generation"),
    )
    if context == "freshness":
        # Regenerate canonical identities after changing the retained capability.
        assert_object(repo)["freshness"] = "unknown"

        native = assert_object(correlation["repository_evidence"])
        assert_object(native)["bindings_identity"] = "sha256:" + packet_digest(
            assert_text(native["schema"]),
            {key: value for key, value in native.items() if key != "bindings_identity"},
        )
        correlation["correlation_identity"] = "sha256:" + packet_digest(
            assert_text(correlation["schema"]),
            {
                key: value
                for key, value in correlation.items()
                if key != "correlation_identity"
            },
        )
    delta = diagnostic_observation_delta(
        _observe([], binding=binding),
        _observe([_diagnostic("related.py")], binding=binding),
        changed_paths=["owner.py"],
        relationship_evidence=correlation,
    )
    assert (
        assert_object(_path_rows(delta)["related.py"]["relationship"])["state"]
        == "unknown"
    )
    assert len(assert_array(assert_object(delta["diagnostics"])["added"])) == 1
    assert validate_repository_intelligence_evidence(delta)["valid"] is True


def test_relationship_packet_tampering_is_rejected_before_annotation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    correlation = _correlation(tmp_path, monkeypatch)
    repo = assert_object(correlation["repository_evidence"])["repository"]
    binding = RepositoryGenerationBinding(
        assert_text(assert_object(repo)["repository_identity"]),
        assert_integer(assert_object(repo)["codemap_generation"]),
    )
    assert_object(
        assert_object(
            assert_array(assert_object(correlation["repository_evidence"])["bindings"])[
                0
            ]
        )["relationships"]
    )["state"] = "not-requested"
    with pytest.raises(ValueError, match="identity mismatch"):
        diagnostic_observation_delta(
            _observe([], binding=binding),
            _observe([], binding=binding),
            relationship_evidence=correlation,
        )


def test_member_evidence_is_canonical_and_does_not_alias_producer_inputs() -> None:
    provenance = {"./owner.py": _provenance()}
    collections = {"./owner.py": "fresh-complete"}
    observed = _observe(
        [],
        source_revisions={"./owner.py": "a" * 64},
        source_provenance=provenance,
        collection_by_path=collections,
    )
    provenance["./owner.py"]["document_version"] = 100
    collections["./owner.py"] = "unavailable"
    assert (
        assert_object(assert_object(observed["source_provenance"])["owner.py"])[
            "document_version"
        ]
        == 7
    )
    assert observed["collection_by_path"] == {"owner.py": "fresh-complete"}
    checked = validate_repository_intelligence_evidence(observed)
    assert checked["valid"] is True
    assert_object(
        assert_object(assert_object(checked["normalized"])["source_provenance"])[
            "owner.py"
        ]
    )["document_version"] = 200
    assert (
        assert_object(assert_object(observed["source_provenance"])["owner.py"])[
            "document_version"
        ]
        == 7
    )


@pytest.mark.parametrize("format", ["structured", "compact", "text"])
def test_mcp_and_bounded_presentations_preserve_member_evidence(
    tmp_path: Path, format: str
) -> None:
    before = _observe(
        [_diagnostic("owner.py", "old"), _diagnostic("related.py", "old")],
        source_revisions={"owner.py": "a" * 64},
        source_provenance={"owner.py": _provenance(6)},
    )
    after = _observe(
        [_diagnostic("owner.py", "new"), _diagnostic("related.py", "new")],
        source_revisions={"owner.py": "b" * 64},
        source_provenance={"owner.py": _provenance(7)},
    )
    surface = HashmarksMcpSurface(str(tmp_path), state_dir=str(tmp_path / "state"))
    try:
        result = surface.evidence_comparison(
            before,
            after,
            result_mode="diagnostics",
            changed_paths=["owner.py"],
            change_set_complete=True,
        )
    finally:
        surface.close()
    assert result == diagnostic_observation_delta(
        before, after, changed_paths=["owner.py"], change_set_complete=True
    )
    projection = present_repository_evidence(result, format=format)
    findings = [
        finding
        for group in assert_records(projection["groups"])
        for finding in assert_array(group["findings"])
    ]
    assert any(
        assert_object(finding)["kind"] == "diagnostic_source_provenance"
        and assert_object(finding)["details"] == result["source_provenance"]
        for finding in findings
    )
    assert (
        len(
            [
                finding
                for finding in findings
                if assert_object(finding)["kind"] == "diagnostic_path_delta"
            ]
        )
        == 3
    )
    wide = diagnostic_observation_delta(
        _observe([]), _observe([_diagnostic(f"file_{index}.py") for index in range(60)])
    )
    bounded = present_repository_evidence(wide, format=format)
    assert any(
        assert_number(group["omitted_from_presentation"]) > 0
        for group in assert_records(bounded["groups"])
    )
    assert len(assert_array(assert_object(result["diagnostics"])["added"])) == 2
    assert validate_repository_intelligence_evidence(result)["valid"] is True
