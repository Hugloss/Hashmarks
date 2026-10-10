"""Real Pyright/TypeScript responses through current CodeMap and source changes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from native_evidence_support import (
    assert_hover_capture,
    assert_hover_presentation,
    assert_projection,
    import_native_scip,
    lsp_capture,
    materialize_scip,
)

from hashmarks.codemap import CodeMap
from hashmarks.codemap.semantic_relationship_delta import semantic_relationship_delta
from hashmarks.codemap.semantic_relationship_model import (
    validate_relationship_observation,
)
from hashmarks.digest import FILE_DOMAIN, hash_bytes
from hashmarks.evidence_presentation import FORMATS, present_repository_evidence


def observe(cm: CodeMap, root: Path, source: Path, name: str) -> Any:
    row = next(
        row
        for row in json.loads((source / "captures.json").read_text())
        if row["name"] == name
    )
    try:
        return cm.structural_locality(
            row["subject"],
            result_mode="relationships",
            supplied_observations=[lsp_capture(root, source, name)],
        )
    except ValueError as exc:
        raise AssertionError(
            "an admitted genuine capture must remain readable"
        ) from exc


def lsp_row(packet: Any) -> Any:
    return next(
        row
        for row in packet["observations"]
        if row["producer"].endswith("langserver")
        or row["producer"] == "typescript-language-server"
    )


def _assert_hover_formats(packet: Any, capture: Any) -> None:
    for format in FORMATS:
        if format != "none":
            assert_hover_presentation(
                packet, present_repository_evidence(packet, format=format), capture
            )


@pytest.mark.parametrize(
    "language,state",
    [
        ("python", "before"),
        ("python", "moved"),
        ("python", "after"),
        ("python", "hover"),
        ("typescript", "before"),
        ("typescript", "moved"),
        ("typescript", "after"),
        ("typescript", "ambiguous"),
    ],
)
def test_native_lsp_raw_capture_integrity_and_uri_only_replay(
    tmp_path: Path, language: str, state: str, native_lsp_corpus: Path
) -> None:
    source = native_lsp_corpus / language / state
    metadata = json.loads((source / "capture.json").read_text())
    assert (
        metadata["captures_sha256"]
        == hashlib.sha256((source / "captures.json").read_bytes()).hexdigest()
    )
    assert (
        metadata["transcript_sha256"]
        == hashlib.sha256((source / "transcript.json").read_bytes()).hexdigest()
    )
    assert metadata["producer_version"]
    for path, revision in metadata["source_revisions"].items():
        assert (
            hash_bytes((source / path).read_bytes(), domain=FILE_DOMAIN).hash
            == revision
        )
    originals = json.loads((source / "captures.json").read_text())
    for row in originals:
        replay = lsp_capture(tmp_path, source, row["name"])
        # Undo only admitted URI replacements; all other captured fields are exact.
        restored = json.dumps(replay)
        for path in metadata["source_revisions"]:
            restored = restored.replace(
                (tmp_path / path).as_uri(), metadata["original_root_uri"] + "/" + path
            )
        assert json.loads(restored) == row["capture"]


@pytest.mark.parametrize(
    "name",
    ["hover-disk", "hover-string-token", "hover-integer-token", "hover-null"],
)
def test_native_hover_accepts_exact_protocol_responses_without_edges(
    tmp_path: Path, name: str, native_lsp_corpus: Path
) -> None:
    root = tmp_path / "repo"
    source = native_lsp_corpus / "python" / "hover"
    materialize_scip(root, source)
    capture = lsp_capture(root, source, name)
    with CodeMap(root) as cm:
        cm.sync()
        packet = observe(cm, root, source, name)
    row = assert_hover_capture(packet, capture)
    assert row["freshness"] == "current"
    assert row["source_bindings"][0]["state"] == "matching"
    assert row["capability"]["request_id"] == capture["request"]["id"]
    assert_projection(packet, "structural_locality", "relationships")
    _assert_hover_formats(packet, capture)


def test_native_hover_unsaved_buffer_and_document_reopen_preserve_authority(
    tmp_path: Path, native_lsp_corpus: Path
) -> None:
    root = tmp_path / "repo"
    source = native_lsp_corpus / "python" / "hover"
    materialize_scip(root, source)
    old_capture = lsp_capture(root, source, "hover-disk")
    changed_capture = lsp_capture(root, source, "hover-buffer")
    with CodeMap(root) as cm:
        cm.sync()
        before = observe(cm, root, source, "hover-disk")
        old = assert_hover_capture(before, old_capture)
        unsaved = observe(cm, root, source, "hover-buffer")
        changed = assert_hover_capture(unsaved, changed_capture)
        assert changed["freshness"] == "unknown"
        assert changed["source_bindings"][0]["state"] == "different"
        unqualified = semantic_relationship_delta(before, unsaved)
        assert unqualified["comparable"] is False
        assert (
            "after-producer-freshness-unproven"
            in unqualified["incomparability_reasons"]
        )
        assert_projection(unqualified, "evidence_comparison", "relationships")
        _assert_hover_formats(unsaved, changed_capture)
        reopened = observe(cm, root, source, "hover-reopened")
        reopened_capture = lsp_capture(root, source, "hover-reopened")
        reopened_row = assert_hover_capture(reopened, reopened_capture)
        assert reopened_row["freshness"] == "current"
        assert reopened_row["source_bindings"][0]["state"] == "matching"
        assert (
            reopened_row["source_bindings"][0]["provenance"]["document_lifetime"]
            != old["source_bindings"][0]["provenance"]["document_lifetime"]
        )
        _assert_hover_formats(reopened, reopened_capture)


def test_native_hover_save_delta_and_codemap_reopen_do_not_replay(
    tmp_path: Path, native_lsp_corpus: Path
) -> None:
    root, state = tmp_path / "repo", tmp_path / "state"
    source = native_lsp_corpus / "python" / "hover"
    materialize_scip(root, source)
    old_capture = lsp_capture(root, source, "hover-disk")
    changed_capture = lsp_capture(root, source, "hover-buffer")
    with CodeMap(root, state_dir=state) as cm:
        cm.sync()
        before = observe(cm, root, source, "hover-disk")
        old = assert_hover_capture(before, old_capture)

        # Save the exact text the real server observed; neither capture is edited.
        (root / "src/source.py").write_text(
            changed_capture["documents"]["src/source.py"]["text"], encoding="utf-8"
        )
        cm.sync()
        after = observe(cm, root, source, "hover-buffer")
        saved = assert_hover_capture(after, changed_capture)
        assert saved["freshness"] == "current"
        assert saved["source_bindings"][0]["state"] == "matching"
        stale = observe(cm, root, source, "hover-disk")
        assert assert_hover_capture(stale, old_capture)["freshness"] == "unknown"
        delta = semantic_relationship_delta(before, after)
        assert delta["comparable"] is True
        (change,) = delta["producer_deltas"]
        assert change["capability"]["changed"] is True
        assert (
            change["capability"]["before"]["hover_observation"]
            == (old["capability"]["hover_observation"])
        )
        assert (
            change["capability"]["after"]["hover_observation"]
            == (saved["capability"]["hover_observation"])
        )
        assert change["facts"]["added"] == change["facts"]["removed"] == []
        assert (
            change["observed_claim_set_changes"]["repository_absence_inferred"] is False
        )
        assert_projection(delta, "evidence_comparison", "relationships")
        _assert_hover_formats(after, changed_capture)
    with CodeMap(root, state_dir=state) as cm:
        cm.sync()
        current: Any = cm.structural_locality(
            "src/source.py::target", result_mode="relationships"
        )
    assert all(
        row["producer"] != changed_capture["producer"]
        for row in current["observations"]
    )


@pytest.mark.parametrize(
    "name,direction", [("incoming", "result-to-query"), ("outgoing", "query-to-result")]
)
def test_native_lsp_cross_file_call_identity_direction_and_ranges(
    tmp_path: Path, name: str, direction: str, native_lsp_corpus: Path
) -> None:
    root = tmp_path / "repo"
    source = native_lsp_corpus / "python" / "before"
    materialize_scip(root, source)
    with CodeMap(root) as cm:
        cm.sync()
        packet = observe(cm, root, source, name)
    (claim,) = lsp_row(packet)["claims"]
    assert claim["basis"]["direction"] == direction
    assert (
        claim["source"]["resolution"]["candidates"][0]["symbol_id"]
        == "src/caller.py::caller"
    )
    assert (
        claim["target"]["resolution"]["candidates"][0]["symbol_id"]
        == "src/callee.py::target"
    )
    assert claim["basis"]["fromRanges"] == [
        {"start": {"line": 4, "character": 11}, "end": {"line": 4, "character": 17}}
    ]
    assert (
        claim["basis"]["captured_location"]["fromRanges"]
        == lsp_capture(root, source, name)["response"]["result"][0]["fromRanges"]
    )
    assert packet["negative_evidence_admissible"] is False
    validate_relationship_observation(packet)
    assert_projection(packet, "structural_locality", "relationships")


def test_native_lsp_body_query_and_duplicate_names_do_not_qualify_selected_subject(
    tmp_path: Path, native_lsp_corpus: Path
) -> None:
    root = tmp_path / "repo"
    source = native_lsp_corpus / "python" / "before"
    materialize_scip(root, source)
    with CodeMap(root) as cm:
        cm.sync()
        for name, expected in [
            ("body-definition", "src/callee.py::target"),
            ("duplicate-definition", "src/other.py::target"),
        ]:
            packet = observe(cm, root, source, name)
            (claim,) = lsp_row(packet)["claims"]
            assert claim["source"]["resolution"]["state"] == "unresolved"
            assert claim["source"]["source_binding"]["state"] == "matching"
            assert claim["source"]["locator"]["start"] == {"line": 4, "character": 11}
            assert (
                claim["target"]["resolution"]["candidates"][0]["symbol_id"] == expected
            )
            assert packet["producer_correspondence"]["unresolved_claims"] == 1
            assert packet["producer_correspondence"]["pairs"] == []
            validate_relationship_observation(packet)


@pytest.mark.parametrize("include_declaration,expected", [(True, 3), (False, 2)])
def test_native_lsp_references_preserve_declaration_scope_and_unresolved_uses(
    tmp_path: Path, include_declaration: bool, expected: int, native_lsp_corpus: Path
) -> None:
    root = tmp_path / "repo"
    source = native_lsp_corpus / "python" / "before"
    materialize_scip(root, source)
    with CodeMap(root) as cm:
        cm.sync()
        packet = observe(
            cm, root, source, "references-" + str(include_declaration).lower()
        )
    claims = lsp_row(packet)["claims"]
    assert len(claims) == expected
    assert all(claim["basis"]["direction"] == "result-to-query" for claim in claims)
    assert all(
        claim["target"]["resolution"]["state"] == "unique-candidate" for claim in claims
    )
    assert sum(
        claim["source"]["resolution"]["state"] == "unique-candidate" for claim in claims
    ) == int(include_declaration)
    assert packet["producer_correspondence"]["unresolved_claims"] == 2


def test_native_lsp_buffer_lifetime_never_strengthens_disk_correspondence(
    tmp_path: Path, native_lsp_corpus: Path
) -> None:
    root = tmp_path / "repo"
    source = native_lsp_corpus / "python" / "before"
    materialize_scip(root, source)
    with CodeMap(root, state_dir=tmp_path / "state") as cm:
        cm.sync()
        changed = observe(cm, root, source, "open-buffer")
        reopened = observe(cm, root, source, "reopened-buffer")
    (old,) = lsp_row(changed)["claims"]
    (new,) = lsp_row(reopened)["claims"]
    assert old["source"]["source_binding"]["state"] == "different"
    assert old["source"]["resolution"]["state"] == "unresolved"
    assert changed["producer_correspondence"]["unresolved_claims"] == 1
    assert new["source"]["source_binding"]["state"] == "matching"
    assert new["source"]["resolution"]["state"] == "unique-candidate"
    assert (
        old["source"]["source_binding"]["provenance"]["document_lifetime"]
        != new["source"]["source_binding"]["provenance"]["document_lifetime"]
    )


def test_native_lsp_disk_edit_rename_delete_and_reopen_do_not_replay(
    tmp_path: Path, native_lsp_corpus: Path
) -> None:
    root, state = tmp_path / "repo", tmp_path / "state"
    source = native_lsp_corpus / "python" / "before"
    materialize_scip(root, source)
    (root / "unrelated.py").write_text("UNCHANGED = True\n")
    with CodeMap(root, state_dir=state) as cm:
        cm.sync()
        before = observe(cm, root, source, "incoming")
        (root / "src/callee.py").write_text("def target():\n    return 55\n")
        stale = observe(cm, root, source, "incoming")
        assert (
            lsp_row(stale)["claims"][0]["target"]["source_binding"]["state"]
            == "different"
        )
        moved_source = native_lsp_corpus / "python" / "moved"
        materialize_scip(root, moved_source)
        assert not (root / "src/callee.py").exists()
        assert (root / "unrelated.py").exists()
        cm.sync()
        moved = observe(cm, root, moved_source, "incoming")
        assert (
            lsp_row(moved)["claims"][0]["target"]["resolution"]["candidates"][0][
                "symbol_id"
            ]
            == "src/renamed.py::target"
        )
        (root / "src/caller.py").unlink()
        deleted = observe(cm, root, moved_source, "incoming")
        assert lsp_row(deleted)["claims"] == []
        assert lsp_row(deleted)["accounting"]["denied_or_unadmitted"] == 1
        assert (
            next(
                binding
                for binding in lsp_row(deleted)["source_bindings"]
                if binding["path"] == "src/caller.py"
            )["state"]
            == "unknown"
        )

    materialize_scip(root, source)
    for directory in (state, tmp_path / "fresh"):
        with CodeMap(root, state_dir=directory) as cm:
            cm.sync()
            current = observe(cm, root, source, "incoming")
            assert (
                current["producer_correspondence"] == before["producer_correspondence"]
            )
            assert (
                observe(cm, root, source, "prepare-target")["observations"][0]["claims"]
                == []
            )
            without = cm.structural_locality(
                "src/callee.py::target", result_mode="relationships"
            )
            assert without["observations"] == []


@pytest.mark.parametrize("state,line", [("before", 3), ("moved", 5), ("after", 3)])
def test_native_only_typescript_method_accepts_genuine_lsp_without_lexical_promotion(
    tmp_path: Path,
    state: str,
    line: int,
    native_lsp_corpus: Path,
    native_scip_corpus: Path,
) -> None:
    root = tmp_path / "repo"
    source = native_lsp_corpus / "typescript" / state
    materialize_scip(root, source)
    with CodeMap(root) as cm:
        cm.sync()
        import_native_scip(cm, native_scip_corpus / "typescript" / state)
        packet = observe(cm, root, source, "method-definition")
        with pytest.raises(KeyError):
            cm.structural_locality("src/engine.ts::normalize")
    (claim,) = lsp_row(packet)["claims"]
    assert claim["source"]["locator"]["start"] == {"line": line, "character": 4}
    assert claim["source"]["resolution"]["state"] == "unresolved"
    assert claim["source"]["key"]["supplied_subject"] == "src/engine.ts::normalize"
    assert (
        claim["basis"]["captured_location"]["range"]
        == lsp_capture(root, source, "method-definition")["response"]["result"][0][
            "range"
        ]
    )
    assert {row["producer"] for row in packet["observations"]} == {
        "scip-typescript:0.4.0",
        "typescript-language-server",
    }
    assert packet["producer_correspondence"]["pairs"] == []
    assert packet["producer_correspondence"]["unresolved_claims"] >= 1
    validate_relationship_observation(packet)
    assert_projection(packet, "structural_locality", "relationships")


def test_genuine_scip_lsp_claims_preserve_unknown_encoding_and_independent_claims(
    tmp_path: Path, native_lsp_corpus: Path, native_scip_corpus: Path
) -> None:
    root = tmp_path / "repo"
    source = native_lsp_corpus / "typescript" / "ambiguous"
    materialize_scip(root, source)
    with CodeMap(root) as cm:
        cm.sync()
        import_native_scip(cm, native_scip_corpus / "typescript" / "ambiguous")
        with pytest.raises(KeyError, match="ambiguous"):
            cm.structural_locality(
                "src/engine.ts::normalize", result_mode="relationships"
            )
        packet = observe(cm, root, source, "implementations")
    assert len(lsp_row(packet)["claims"]) == 2
    scip = next(
        row
        for row in packet["observations"]
        if row["producer"].startswith("scip-typescript:")
    )
    assert len(scip["claims"]) == 2
    assert all(
        claim["source"]["locator"]["position_encoding"] == "unknown"
        for claim in scip["claims"]
    )
    assert all(
        claim["source"]["resolution"]["state"] == "unresolved"
        for claim in scip["claims"]
    )
    assert all(
        claim["basis"]["direction"] == "result-to-query"
        for claim in lsp_row(packet)["claims"]
    )
    assert packet["producer_correspondence"]["pairs"] == []
    assert packet["negative_evidence_admissible"] is False


@pytest.mark.parametrize(
    "name,count",
    [("references-true", 2), ("references-false", 1), ("incoming", 0), ("outgoing", 1)],
)
def test_native_typescript_navigation_preserves_scope_and_external_call(
    tmp_path: Path,
    name: str,
    count: int,
    native_lsp_corpus: Path,
    native_scip_corpus: Path,
) -> None:
    root = tmp_path / "repo"
    source = native_lsp_corpus / "typescript" / "before"
    materialize_scip(root, source)
    with CodeMap(root) as cm:
        cm.sync()
        import_native_scip(cm, native_scip_corpus / "typescript" / "before")
        packet = observe(cm, root, source, name)
        prepared = observe(cm, root, source, "prepare-method")
    row = lsp_row(packet)
    assert len(row["claims"]) == count
    assert row["negative_evidence_admissible"] is False
    assert lsp_row(prepared)["claims"] == []
    (item,) = lsp_capture(root, source, "prepare-method")["response"]["result"]
    assert lsp_row(prepared)["capability"]["prepared_candidates"][0]["item"] == item
    if name in ("incoming", "outgoing"):
        assert lsp_capture(root, source, name)["request"]["params"]["item"] == item
    if name == "outgoing":
        (claim,) = row["claims"]
        assert claim["basis"]["direction"] == "query-to-result"
        assert claim["target"]["resolution"]["state"] == "outside-repository"
        (raw,) = lsp_capture(root, source, name)["response"]["result"]
        assert claim["target"]["locator"]["uri"] == raw["to"]["uri"]
        assert claim["basis"]["fromRanges"] == raw["fromRanges"]
    elif name.startswith("references"):
        assert all(
            claim["basis"]["direction"] == "result-to-query" for claim in row["claims"]
        )
        assert all(
            claim["target"]["resolution"]["state"] == "unresolved"
            for claim in row["claims"]
        )
    validate_relationship_observation(packet)
