"""Actual SCIP producer output through source changes, storage and formatting."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from native_evidence_support import (
    assert_projection,
    import_native_scip,
    materialize_scip,
)

from hashmarks.codemap import CodeMap
from hashmarks.codemap.semantic_relationship_delta import semantic_relationship_delta

TASK = "Change normalize_widget in src/engine.py to lowercase the trimmed value and verify its semantics."


def _claims(packet: Any) -> list[Any]:
    return [
        claim
        for observation in packet["observations"]
        for claim in observation["claims"]
    ]


def _observe(cm: CodeMap, target: str = "src/engine.ts::Engine") -> Any:
    return cm.structural_locality(target, result_mode="relationships")


def test_native_scip_capture_bytes_and_input_revisions_are_revalidated(
    native_scip_corpus: Path,
) -> None:
    from hashmarks.digest import FILE_DOMAIN, hash_bytes

    for capture in sorted(native_scip_corpus.glob("*/*/capture.json")):
        root = capture.parent
        metadata = json.loads(capture.read_text())
        assert (
            metadata["json_sha256"]
            == hashlib.sha256((root / "index.json").read_bytes()).hexdigest()
        )
        assert (
            metadata["binary_sha256"]
            == hashlib.sha256((root / "index.scip").read_bytes()).hexdigest()
        )
        assert metadata["source_revisions"]
        for path, revision in metadata["source_revisions"].items():
            assert (
                hash_bytes((root / path).read_bytes(), domain=FILE_DOMAIN).hash
                == revision
            )


def test_native_typescript_claims_move_remove_and_add_without_inferred_edges(
    tmp_path: Path, native_scip_corpus: Path
) -> None:
    root, state = tmp_path / "repo", tmp_path / "state"
    packets = []
    with CodeMap(root, state_dir=state) as cm:
        for endpoint in ("before", "moved", "after", "before"):
            source = native_scip_corpus / "typescript" / endpoint
            materialize_scip(root, source)
            cm.sync()
            import_native_scip(cm, source)
            packets.append(_observe(cm))
        method = _observe(cm, "src/engine.ts::Engine.normalize")
    before, moved, removed, added = packets
    assert len(_claims(before)) == 1
    claim = _claims(before)[0]
    assert claim["kind"] == "implementation"
    assert claim["source"]["key"]["symbol"].endswith("Engine#")
    assert claim["target"]["key"]["symbol"].endswith("Contract#")
    movement = semantic_relationship_delta(before, moved)
    assert movement["comparable"] is True
    assert movement["producer_deltas"][0]["facts"] == {"added": [], "removed": []}
    assert movement["producer_deltas"][0]["locators"]
    for old, new, changed in ((moved, removed, "removed"), (removed, added, "added")):
        delta = semantic_relationship_delta(old, new)
        assert delta["comparable"] is True
        assert len(delta["producer_deltas"][0]["facts"][changed]) == 1
        assert_projection(delta, "evidence_comparison", "relationships")
    assert _claims(method) == []
    for packet in packets:
        assert packet["coverage"]["negative_evidence_admissible"] is False
        assert_projection(packet, "structural_locality", "relationships")


def test_native_typescript_method_reference_flag_is_not_a_call_or_inverse(
    tmp_path: Path, native_scip_corpus: Path
) -> None:
    root = tmp_path / "repo"
    source = native_scip_corpus / "typescript" / "before"
    materialize_scip(root, source)
    with CodeMap(root, state_dir=tmp_path / "state") as cm:
        cm.sync()
        import_native_scip(cm, source)
        method = _observe(cm, "src/engine.ts::Engine.normalize")
    claims = _claims(method)
    assert {claim["kind"] for claim in claims} == {"reference", "implementation"}
    assert len(claims) == 2
    assert all(
        claim["source"]["key"]["symbol"].endswith("Engine#normalize().")
        for claim in claims
    )
    assert all(
        claim["target"]["key"]["symbol"].endswith("Contract#normalize().")
        for claim in claims
    )
    assert_projection(method, "structural_locality", "relationships")


def test_native_python_empty_claims_become_unavailable_before_reindex_and_reopen(
    tmp_path: Path, native_scip_corpus: Path
) -> None:
    root, state = tmp_path / "repo", tmp_path / "state"
    source = native_scip_corpus / "python" / "before"
    materialize_scip(root, source)
    with CodeMap(root, state_dir=state) as cm:
        cm.sync()
        import_native_scip(cm, source)
        previous: Any = cm.task_evidence(TASK)
        assert previous["semantic_relationships"]["observed_relationship_count"] == 0
        assert (
            previous["semantic_relationships"]["negative_evidence_admissible"] is False
        )
        source = native_scip_corpus / "python" / "after"
        materialize_scip(root, source)
        delta: Any = cm.task_post_change_delta(
            TASK, ["src/engine.py"], previous_evidence=previous
        )
        assert delta["semantic_relationships"]["after"] is None
        assert (
            delta["semantic_relationships"]["claim_set_comparison"] == "not-performed"
        )
        assert "semantic_relationships" not in cm.task_evidence(TASK)
        assert_projection(delta, "post_change")
        import_native_scip(cm, source)
        current: Any = cm.task_evidence(TASK)
    with CodeMap(root, state_dir=state) as reopened:
        restored: Any = reopened.task_evidence(TASK)
    with CodeMap(root, state_dir=tmp_path / "fresh") as fresh:
        fresh.sync()
        import_native_scip(fresh, source)
        rebuilt: Any = fresh.task_evidence(TASK)
    for packet in (current, restored, rebuilt):
        assert packet["semantic_relationships"]["observed_relationship_count"] == 0
        assert packet["semantic_relationships"]["evidence"]["claims"] == []
        assert packet["semantic_relationships"]["negative_evidence_admissible"] is False
        assert packet["ownership"]["owner"]["path"] == "src/engine.py"
        assert_projection(packet, "task_evidence")


def test_native_typescript_stale_index_is_not_current_or_replayed_after_deletion(
    tmp_path: Path, native_scip_corpus: Path
) -> None:
    root, state = tmp_path / "repo", tmp_path / "state"
    source = native_scip_corpus / "typescript" / "before"
    materialize_scip(root, source)
    with CodeMap(root, state_dir=state) as cm:
        cm.sync()
        import_native_scip(cm, source)
        before = _observe(cm)
        materialize_scip(root, native_scip_corpus / "typescript" / "after")
        cm.sync(["src/engine.ts"])
        stale = _observe(cm)
        assert stale["observations"][0]["freshness"] == "stale"
        comparison = semantic_relationship_delta(before, stale)
        assert comparison["comparable"] is False
        assert comparison["producer_deltas"][0]["facts"] == {"added": [], "removed": []}
        assert_projection(comparison, "evidence_comparison", "relationships")
        (root / "src" / "engine.ts").unlink()
        cm.sync(["src/engine.ts"])
        current: Any = cm.task_evidence(
            "Change Engine in src/engine.ts to document its behavior."
        )
        assert "semantic_relationships" not in current
    with CodeMap(root, state_dir=state) as reopened:
        packet: Any = reopened.task_evidence(
            "Change Engine in src/engine.ts to document its behavior."
        )
    assert "semantic_relationships" not in packet
