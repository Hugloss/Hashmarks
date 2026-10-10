"""Genuine producer metadata through publication, edits and durable reopening."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from native_evidence_support import import_native_scip, materialize_scip

from hashmarks.codemap import CodeMap
from hashmarks.codemap.repository_index_store import WorkspaceMapStore


def _reads(source: Path) -> list[dict[str, Any]]:
    raw = json.loads((source / "index.json").read_text())
    document = next(
        row for row in raw["documents"] if row["relative_path"] == "src/engine.py"
    )
    return [
        row
        for row in document["occurrences"]
        if row["symbol"].endswith("normalize_widget().(value)")
        and row["symbol_roles"] == 8
    ]


def _reference(cm: CodeMap) -> dict[str, Any]:
    packet: Any = cm.refs("value")
    (reference,) = packet["native_references"]
    return reference


def _documentation(cm: CodeMap) -> list[str]:
    rows = cm.store.native_definitions("normalize_widget")
    row = next(row for row in rows if row["symbol"].endswith("normalize_widget()."))
    return json.loads(row["relationships_json"])["declaration"]["documentation"]


def test_genuine_reference_roles_and_locations_survive_publication_and_reopen(
    tmp_path: Path,
    native_scip_corpus: Path,
) -> None:
    source = native_scip_corpus / "python" / "metadata-before"
    reads = _reads(source)
    assert len(reads) == 2
    assert [row["range"] for row in reads] == [[2, 11, 16], [2, 19, 24]]
    root, state = tmp_path / "repo", tmp_path / "state"
    materialize_scip(root, source)
    with CodeMap(root, state_dir=state) as cm:
        cm.sync()
        static = cm.deps("normalize_widget")["edges"]
        import_native_scip(cm, source)
        reference = _reference(cm)
        metadata = reference["occurrence_metadata"]
        assert metadata["received"] == metadata["retained"] == 2
        assert metadata["duplicates"] == metadata["omitted"] == 0
        assert metadata["truncated"] is False
        assert metadata["negative_evidence_admissible"] is False
        assert metadata["source_binding"]["state"] == "matching"
        assert [
            row["locator"]["start"]["character"] for row in metadata["occurrences"]
        ] == [11, 19]
        for row in metadata["occurrences"]:
            assert row["locator"]["start"]["line"] == 2
            assert row["occurrence_roles"] == {
                "producer_role_bits": 8,
                "observed_roles": ["read_access"],
                "unrecognized_role_bits": 0,
                "authority": "direct-scip-occurrence-flags",
                "negative_evidence_admissible": False,
            }
        assert "Normalisera räknare 😀 med två läsningar." in _documentation(cm)
        assert cm.deps("normalize_widget")["edges"] == static
        dependencies: Any = cm.deps("normalize_widget")
        assert reference in dependencies["native_edges"]
    with CodeMap(root, state_dir=state) as reopened:
        assert _reference(reopened) == reference
        assert "Normalisera räknare 😀 med två läsningar." in _documentation(reopened)


def test_documentation_edit_invalidates_roles_until_fresh_native_reimport(
    tmp_path: Path,
    native_scip_corpus: Path,
) -> None:
    root, state = tmp_path / "repo", tmp_path / "state"
    before = native_scip_corpus / "python" / "metadata-before"
    after = native_scip_corpus / "python" / "metadata-after"
    materialize_scip(root, before)
    with CodeMap(root, state_dir=state) as cm:
        cm.sync()
        import_native_scip(cm, before)
        original = _reference(cm)
        materialize_scip(root, after)
        assert cm.refs("value")["native_references"] == []
        cm.sync(["src/engine.py"])
        assert cm.refs("value")["native_references"] == []
        import_native_scip(cm, after)
        assert (
            _reference(cm)["occurrence_metadata"]["occurrences"]
            == original["occurrence_metadata"]["occurrences"]
        )
        current = _reference(cm)
        assert current["occurrence_metadata"]["source_binding"]["state"] == "matching"
        assert "Normalisera räknare 😀 med uppdaterad dokumentation." in _documentation(
            cm
        )
        assert "Normalisera räknare 😀 med två läsningar." not in _documentation(cm)
    with CodeMap(root, state_dir=state) as reopened:
        assert _reference(reopened) == current
        (root / "src/engine.py").unlink()
        assert reopened.refs("value")["native_references"] == []
    with CodeMap(root, state_dir=state) as reopened:
        assert reopened.refs("value")["native_references"] == []


def test_genuine_reference_metadata_cannot_cross_denied_source_visibility(
    tmp_path: Path,
    native_scip_corpus: Path,
) -> None:
    root, state = tmp_path / "repo", tmp_path / "state"
    materialize_scip(root, native_scip_corpus / "python" / "metadata-before")
    with CodeMap(root, state_dir=state) as cm:
        cm.sync()
        import_native_scip(cm, native_scip_corpus / "python" / "metadata-before")
        assert _reference(cm)["occurrence_metadata"]["retained"] == 2
        (root / ".hashmarks-context.toml").write_text(
            '[[rule]]\npattern = "src/engine.py"\nvisibility = "deny"\n'
        )
        assert cm.refs("value")["native_references"] == []
    with CodeMap(root, state_dir=state) as reopened:
        assert reopened.refs("value")["native_references"] == []


def test_genuine_many_reads_are_bounded_with_conserved_occurrence_counts(
    tmp_path: Path,
    native_scip_corpus: Path,
) -> None:
    source = native_scip_corpus / "python" / "metadata-bounded"
    reads = _reads(source)
    assert len(reads) == 130
    root, state = tmp_path / "repo", tmp_path / "state"
    materialize_scip(root, source)
    with CodeMap(root, state_dir=state) as cm:
        cm.sync()
        import_native_scip(cm, source)
        metadata = _reference(cm)["occurrence_metadata"]
        assert metadata["received"] == 130
        assert metadata["retained"] == len(metadata["occurrences"]) == 128
        assert metadata["omitted"] == 2
        assert metadata["duplicates"] == 0
        assert metadata["truncated"] is True
        assert metadata["negative_evidence_admissible"] is False
    with CodeMap(root, state_dir=state) as reopened:
        assert _reference(reopened)["occurrence_metadata"] == metadata


def test_duplicate_and_different_role_masks_are_accounted_without_merging(
    tmp_path: Path,
    native_scip_corpus: Path,
) -> None:
    source = native_scip_corpus / "python" / "metadata-before"
    root, state = tmp_path / "repo", tmp_path / "state"
    materialize_scip(root, source)
    raw = json.loads((source / "index.json").read_text())
    occurrences = raw["documents"][0]["occurrences"]
    read = _reads(source)[0]
    occurrences.extend([read, {**read, "symbol_roles": 8 | 1024}])
    index = tmp_path / "adversarial-index.json"
    index.write_text(json.dumps(raw))
    with CodeMap(root, state_dir=state) as cm:
        cm.sync()
        cm.import_scip(
            index, provenance=json.loads((source / "provenance.json").read_text())
        )
        metadata = _reference(cm)["occurrence_metadata"]
        assert metadata["received"] == 4
        assert metadata["retained"] == 3
        assert metadata["duplicates"] == 1
        assert metadata["omitted"] == 0
        assert sorted(
            row["occurrence_roles"]["producer_role_bits"]
            for row in metadata["occurrences"]
        ) == [8, 8, 1032]
        roles = next(
            row["occurrence_roles"]
            for row in metadata["occurrences"]
            if row["occurrence_roles"]["producer_role_bits"] == 1032
        )
        assert roles["observed_roles"] == ["read_access"]
        assert roles["unrecognized_role_bits"] == 1024
        original = metadata["occurrences"]
        occurrences.reverse()
        index.write_text(json.dumps(raw))
        cm.import_scip(
            index, provenance=json.loads((source / "provenance.json").read_text())
        )
        assert _reference(cm)["occurrence_metadata"]["occurrences"] == original


def test_old_index_reimport_preserves_different_source_binding_without_strengthening_roles(
    tmp_path: Path,
    native_scip_corpus: Path,
) -> None:
    root, state = tmp_path / "repo", tmp_path / "state"
    before = native_scip_corpus / "python" / "metadata-before"
    after = native_scip_corpus / "python" / "metadata-after"
    materialize_scip(root, after)
    with CodeMap(root, state_dir=state) as cm:
        cm.sync()
        import_native_scip(cm, before)
        metadata = _reference(cm)["occurrence_metadata"]
        assert metadata["source_binding"]["state"] == "different"
        assert (
            metadata["source_binding"]["claimed_revision"]
            != metadata["source_binding"]["observed_revision"]
        )
        assert metadata["negative_evidence_admissible"] is False
        import_native_scip(cm, after)
        assert (
            _reference(cm)["occurrence_metadata"]["source_binding"]["state"]
            == "matching"
        )


def test_old_native_cache_is_rebuilt_without_inventing_missing_role_evidence(
    tmp_path: Path,
    native_scip_corpus: Path,
) -> None:
    root, state = tmp_path / "repo", tmp_path / "state"
    source = native_scip_corpus / "python" / "metadata-before"
    materialize_scip(root, source)
    with CodeMap(root, state_dir=state) as cm:
        cm.sync()
        import_native_scip(cm, source)
        assert _reference(cm)["occurrence_metadata"]["retained"] == 2
        database = cm.store.db_path
    with closing(sqlite3.connect(database)) as db:
        db.execute("ALTER TABLE native_edge DROP COLUMN occurrence_metadata_json")
        db.commit()
    with CodeMap(root, state_dir=state) as reopened:
        reopened.sync()
        assert reopened.refs("value")["native_references"] == []
        import_native_scip(reopened, source)
        assert _reference(reopened)["occurrence_metadata"]["retained"] == 2


def test_native_store_missing_metadata_remains_null_after_reopen(
    tmp_path: Path,
) -> None:
    database = tmp_path / "native.sqlite3"
    store = WorkspaceMapStore(database)
    try:
        store.replace_native_occurrences(
            "opaque-producer",
            [],
            [
                {
                    "path": "code.py",
                    "source": "caller",
                    "target_symbol": "target",
                    "target_name": "target",
                    "line": 1,
                }
            ],
        )
    finally:
        store.close()
    store = WorkspaceMapStore(database)
    try:
        assert store.native_refs("target")[0]["occurrence_metadata"] is None
        assert store.native_edges_from("code.py")[0]["occurrence_metadata"] is None
    finally:
        store.close()


def test_genuine_roles_without_producer_revision_keep_unknown_source_binding(
    tmp_path: Path,
    native_scip_corpus: Path,
) -> None:
    root, state = tmp_path / "repo", tmp_path / "state"
    source = native_scip_corpus / "python" / "metadata-before"
    materialize_scip(root, source)
    with CodeMap(root, state_dir=state) as cm:
        cm.sync()
        cm.import_scip(source / "index.json")
        metadata = _reference(cm)["occurrence_metadata"]
        assert metadata["source_binding"]["state"] == "unknown"
        assert metadata["source_binding"]["claimed_revision"] is None
        assert metadata["retained"] == 2
        assert metadata["negative_evidence_admissible"] is False
