"""Real Pyright/TypeScript responses through current CodeMap and source changes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from contract_assertions import (
    assert_array,
    assert_number,
    assert_object,
    assert_records,
    assert_text,
)
from native_evidence_support import (
    assert_hover_capture,
    assert_hover_presentation,
    assert_lsp_transcript,
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


def observe(cm: CodeMap, root: Path, source: Path, name: str) -> dict[str, object]:
    row = next(
        row
        for row in json.loads((source / "captures.json").read_text())
        if row["name"] == name
    )
    try:
        return assert_object(
            cm.structural_locality(
                row["subject"],
                result_mode="relationships",
                supplied_observations=[lsp_capture(root, source, name)],
            )
        )
    except ValueError as exc:
        raise AssertionError(
            "an admitted genuine capture must remain readable"
        ) from exc


def lsp_row(packet: dict[str, object]) -> dict[str, object]:
    return next(
        row
        for row in assert_records(packet["observations"])
        if assert_text(row["producer"]).endswith("langserver")
        or assert_text(row["producer"]) == "typescript-language-server"
    )


def _assert_hover_formats(
    packet: dict[str, object], capture: dict[str, object]
) -> None:
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
    assert_lsp_transcript(source, metadata, originals)
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
    "field", ["text", "document_version", "document_lifetime", "response"]
)
def test_native_lsp_transcript_rejects_altered_capture(
    field: str, native_lsp_corpus: Path
) -> None:
    source = native_lsp_corpus / "python" / "hover"
    metadata = json.loads((source / "capture.json").read_text())
    captures = json.loads((source / "captures.json").read_text())
    capture = next(row["capture"] for row in captures if row["name"] == "hover-buffer")
    document = assert_object(assert_object(capture["documents"])["src/source.py"])
    if field == "text":
        document["text"] = (source / "src/source.py").read_text(encoding="utf-8")
    elif field == "response":
        assert_object(capture["response"])["result"] = None
    else:
        assert_object(document["provenance"])[field] = "altered"
    with pytest.raises(AssertionError):
        assert_lsp_transcript(source, metadata, captures)


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
    assert assert_records(row["source_bindings"])[0]["state"] == "matching"
    assert (
        assert_object(row["capability"])["request_id"]
        == assert_object(capture["request"])["id"]
    )
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
        assert assert_records(changed["source_bindings"])[0]["state"] == "different"
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
        assert assert_records(reopened_row["source_bindings"])[0]["state"] == "matching"
        assert (
            assert_object(
                assert_records(reopened_row["source_bindings"])[0]["provenance"]
            )["document_lifetime"]
            != assert_object(assert_records(old["source_bindings"])[0]["provenance"])[
                "document_lifetime"
            ]
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
            assert_text(
                assert_object(
                    assert_object(changed_capture["documents"])["src/source.py"]
                )["text"]
            ),
            encoding="utf-8",
        )
        cm.sync()
        after = observe(cm, root, source, "hover-buffer")
        saved = assert_hover_capture(after, changed_capture)
        assert saved["freshness"] == "current"
        assert assert_records(saved["source_bindings"])[0]["state"] == "matching"
        stale = observe(cm, root, source, "hover-disk")
        assert assert_hover_capture(stale, old_capture)["freshness"] == "unknown"
        delta = semantic_relationship_delta(before, after)
        assert delta["comparable"] is True
        (change,) = assert_records(delta["producer_deltas"])
        assert assert_object(change["capability"])["changed"] is True
        assert (
            assert_object(assert_object(change["capability"])["before"])[
                "hover_observation"
            ]
            == (assert_object(old["capability"])["hover_observation"])
        )
        assert (
            assert_object(assert_object(change["capability"])["after"])[
                "hover_observation"
            ]
            == (assert_object(saved["capability"])["hover_observation"])
        )
        assert (
            assert_object(change["facts"])["added"]
            == assert_object(change["facts"])["removed"]
            == []
        )
        assert (
            assert_object(change["observed_claim_set_changes"])[
                "repository_absence_inferred"
            ]
            is False
        )
        assert_projection(delta, "evidence_comparison", "relationships")
        _assert_hover_formats(after, changed_capture)
    with CodeMap(root, state_dir=state) as cm:
        cm.sync()
        current = cm.structural_locality(
            "src/source.py::target", result_mode="relationships"
        )
    assert all(
        assert_text(row["producer"]) != assert_text(changed_capture["producer"])
        for row in assert_records(current["observations"])
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
    (claim,) = assert_records(lsp_row(packet)["claims"])
    assert assert_object(claim["basis"])["direction"] == direction
    assert (
        assert_records(
            assert_object(assert_object(claim["source"])["resolution"])["candidates"]
        )[0]["symbol_id"]
        == "src/caller.py::caller"
    )
    assert (
        assert_records(
            assert_object(assert_object(claim["target"])["resolution"])["candidates"]
        )[0]["symbol_id"]
        == "src/callee.py::target"
    )
    assert assert_object(claim["basis"])["fromRanges"] == [
        {"start": {"line": 4, "character": 11}, "end": {"line": 4, "character": 17}}
    ]
    assert (
        assert_object(assert_object(claim["basis"])["captured_location"])["fromRanges"]
        == assert_records(
            assert_object(lsp_capture(root, source, name)["response"])["result"]
        )[0]["fromRanges"]
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
            (claim,) = assert_records(lsp_row(packet)["claims"])
            assert (
                assert_object(assert_object(claim["source"])["resolution"])["state"]
                == "unresolved"
            )
            assert (
                assert_object(assert_object(claim["source"])["source_binding"])["state"]
                == "matching"
            )
            assert assert_object(assert_object(claim["source"])["locator"])[
                "start"
            ] == {"line": 4, "character": 11}
            assert (
                assert_records(
                    assert_object(assert_object(claim["target"])["resolution"])[
                        "candidates"
                    ]
                )[0]["symbol_id"]
                == expected
            )
            assert (
                assert_number(
                    assert_object(packet["producer_correspondence"])[
                        "unresolved_claims"
                    ]
                )
                == 1
            )
            assert assert_object(packet["producer_correspondence"])["pairs"] == []
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
    claims = assert_records(lsp_row(packet)["claims"])
    assert len(claims) == expected
    assert all(
        assert_object(claim["basis"])["direction"] == "result-to-query"
        for claim in claims
    )
    assert all(
        assert_object(assert_object(claim["target"])["resolution"])["state"]
        == "unique-candidate"
        for claim in claims
    )
    assert sum(
        assert_object(assert_object(claim["source"])["resolution"])["state"]
        == "unique-candidate"
        for claim in claims
    ) == int(include_declaration)
    assert (
        assert_number(
            assert_object(packet["producer_correspondence"])["unresolved_claims"]
        )
        == 2
    )


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
    (old,) = assert_records(lsp_row(changed)["claims"])
    (new,) = assert_records(lsp_row(reopened)["claims"])
    assert (
        assert_object(assert_object(old["source"])["source_binding"])["state"]
        == "different"
    )
    assert (
        assert_object(assert_object(old["source"])["resolution"])["state"]
        == "unresolved"
    )
    assert (
        assert_number(
            assert_object(changed["producer_correspondence"])["unresolved_claims"]
        )
        == 1
    )
    assert (
        assert_object(assert_object(new["source"])["source_binding"])["state"]
        == "matching"
    )
    assert (
        assert_object(assert_object(new["source"])["resolution"])["state"]
        == "unique-candidate"
    )
    assert (
        assert_object(
            assert_object(assert_object(old["source"])["source_binding"])["provenance"]
        )["document_lifetime"]
        != assert_object(
            assert_object(assert_object(new["source"])["source_binding"])["provenance"]
        )["document_lifetime"]
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
            assert_object(
                assert_object(assert_records(lsp_row(stale)["claims"])[0]["target"])[
                    "source_binding"
                ]
            )["state"]
            == "different"
        )
        moved_source = native_lsp_corpus / "python" / "moved"
        materialize_scip(root, moved_source)
        assert not (root / "src/callee.py").exists()
        assert (root / "unrelated.py").exists()
        cm.sync()
        moved = observe(cm, root, moved_source, "incoming")
        assert (
            assert_records(
                assert_object(
                    assert_object(
                        assert_records(lsp_row(moved)["claims"])[0]["target"]
                    )["resolution"]
                )["candidates"]
            )[0]["symbol_id"]
            == "src/renamed.py::target"
        )
        (root / "src/caller.py").unlink()
        deleted = observe(cm, root, moved_source, "incoming")
        assert assert_records(lsp_row(deleted)["claims"]) == []
        assert (
            assert_object(lsp_row(deleted)["accounting"])["denied_or_unadmitted"] == 1
        )
        assert (
            next(
                binding
                for binding in assert_records(lsp_row(deleted)["source_bindings"])
                if binding["path"] == "src/caller.py"
            )["state"]
            == "unknown"
        )

    materialize_scip(root, source)
    for directory in (state, tmp_path / "fresh"):
        with CodeMap(root, state_dir=directory) as cm:
            cm.sync()
            current = observe(cm, root, source, "incoming")
            assert assert_object(current["producer_correspondence"]) == assert_object(
                before["producer_correspondence"]
            )
            assert (
                assert_records(
                    assert_records(
                        observe(cm, root, source, "prepare-target")["observations"]
                    )[0]["claims"]
                )
                == []
            )
            without = cm.structural_locality(
                "src/callee.py::target", result_mode="relationships"
            )
            assert assert_records(without["observations"]) == []


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
    (claim,) = assert_records(lsp_row(packet)["claims"])
    assert assert_object(assert_object(claim["source"])["locator"])["start"] == {
        "line": line,
        "character": 4,
    }
    assert (
        assert_object(assert_object(claim["source"])["resolution"])["state"]
        == "unresolved"
    )
    assert (
        assert_object(assert_object(claim["source"])["key"])["supplied_subject"]
        == "src/engine.ts::normalize"
    )
    assert (
        assert_object(assert_object(claim["basis"])["captured_location"])["range"]
        == assert_records(
            assert_object(lsp_capture(root, source, "method-definition")["response"])[
                "result"
            ]
        )[0]["range"]
    )
    assert {
        assert_text(row["producer"]) for row in assert_records(packet["observations"])
    } == {
        "scip-typescript:0.4.0",
        "typescript-language-server",
    }
    assert assert_object(packet["producer_correspondence"])["pairs"] == []
    assert (
        assert_number(
            assert_object(packet["producer_correspondence"])["unresolved_claims"]
        )
        >= 1
    )
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
    assert len(assert_records(lsp_row(packet)["claims"])) == 2
    scip = next(
        row
        for row in assert_records(packet["observations"])
        if assert_text(row["producer"]).startswith("scip-typescript:")
    )
    assert len(assert_records(scip["claims"])) == 2
    assert all(
        assert_object(assert_object(claim["source"])["locator"])["position_encoding"]
        == "unknown"
        for claim in assert_records(scip["claims"])
    )
    assert all(
        assert_object(assert_object(claim["source"])["resolution"])["state"]
        == "unresolved"
        for claim in assert_records(scip["claims"])
    )
    assert all(
        assert_object(claim["basis"])["direction"] == "result-to-query"
        for claim in assert_records(lsp_row(packet)["claims"])
    )
    assert assert_object(packet["producer_correspondence"])["pairs"] == []
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
    assert len(assert_records(row["claims"])) == count
    assert row["negative_evidence_admissible"] is False
    assert assert_records(lsp_row(prepared)["claims"]) == []
    (item,) = assert_records(
        assert_object(lsp_capture(root, source, "prepare-method")["response"])["result"]
    )
    assert (
        assert_records(
            assert_object(lsp_row(prepared)["capability"])["prepared_candidates"]
        )[0]["item"]
        == item
    )
    if name in ("incoming", "outgoing"):
        assert (
            assert_object(
                assert_object(lsp_capture(root, source, name)["request"])["params"]
            )["item"]
            == item
        )
    if name == "outgoing":
        (claim,) = assert_records(row["claims"])
        assert assert_object(claim["basis"])["direction"] == "query-to-result"
        assert (
            assert_object(assert_object(claim["target"])["resolution"])["state"]
            == "outside-repository"
        )
        (raw,) = assert_records(
            assert_object(lsp_capture(root, source, name)["response"])["result"]
        )
        assert (
            assert_object(assert_object(claim["target"])["locator"])["uri"]
            == assert_object(raw["to"])["uri"]
        )
        assert assert_object(claim["basis"])["fromRanges"] == raw["fromRanges"]
    elif name.startswith("references"):
        assert all(
            assert_object(claim["basis"])["direction"] == "result-to-query"
            for claim in assert_records(row["claims"])
        )
        assert all(
            assert_object(assert_object(claim["target"])["resolution"])["state"]
            == "unresolved"
            for claim in assert_records(row["claims"])
        )
    validate_relationship_observation(packet)
