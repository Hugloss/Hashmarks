"""Real source changes and authority lifecycle for explicit literal sets."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from native_evidence_support import (
    assert_literal_returned_counts,
    materialize_dependency,
)

from hashmarks.client import IdentityClient
from hashmarks.codemap import CodeMap


@pytest.mark.parametrize("limit", [1, 2, 5, 100])
def test_literal_display_conserves_member_counts_and_original_locations(
    tmp_path: Path, limit: int
) -> None:
    sources = {
        "a.py": "def pack():\r\n    return 'café ZipInfo ZipInfo'\r\n",
        "b.py": "def unpack():\n    # ZipInfo\n    return 'Zip'\n",
        "c.py": "def empty():\n    return 0\n",
    }
    for path, source in sources.items():
        (tmp_path / path).write_bytes(source.encode("utf-8"))
    with CodeMap(tmp_path) as cm:
        cm.sync()
        packet: Any = cm.scoped_source_literals(
            ["c.py", "a.py", "b.py", "a.py"],
            ["missing", "ZipInfo", "Zip"],
            limit=limit,
            context_lines=1,
        )
        reordered = cm.scoped_source_literals(
            list(sources), ["Zip", "missing", "ZipInfo"], limit=limit, context_lines=1
        )
        single: Any = cm.scoped_source_occurrences(
            list(sources), "ZipInfo", context_lines=1
        )
    assert packet == reordered
    assert_literal_returned_counts(packet)
    assert packet["observed_match_count"] == packet["exact_match_count"] == 7
    assert packet["observed_source_bytes"] == sum(
        len(source.encode("utf-8")) for source in sources.values()
    )
    assert packet["source_coverage"] == "complete"
    assert packet["truncation"] == ("truncated" if limit < 7 else "complete")
    expected = [
        ("a.py", 2, 18, "Zip"),
        ("a.py", 2, 18, "ZipInfo"),
        ("a.py", 2, 26, "Zip"),
        ("a.py", 2, 26, "ZipInfo"),
        ("b.py", 2, 7, "Zip"),
        ("b.py", 2, 7, "ZipInfo"),
        ("b.py", 3, 13, "Zip"),
    ]
    assert [
        (row["path"], row["line"], row["column"], row["literal"])
        for row in packet["occurrences"]
    ] == expected[:limit]
    originals = {row["evidence_identity"]: row for row in single["occurrences"]}
    for row in packet["occurrences"]:
        assert row["column_unit"] == "unicode-codepoint"
        assert row["enclosing_symbol"] in {"pack", "unpack"}
        assert row["occurrence_kind"] in {"string-literal", "comment"}
        if row["literal"] == "ZipInfo":
            assert row == originals[row["evidence_identity"]]


@pytest.mark.parametrize("producer", ["uv", "maven"])
def test_manifest_literal_changes_reconcile_and_reopen_without_old_locations(
    tmp_path: Path, producer: str, native_dependency_corpus: Path
) -> None:
    root, state = tmp_path / "repo", tmp_path / "state"
    materialize_dependency(root, native_dependency_corpus / producer / "v1")
    paths = ["pyproject.toml", "uv.lock"] if producer == "uv" else ["pom.xml"]
    literals = ["dummy-dep", "1.0.0", "2.0.0"]
    with CodeMap(root, state_dir=state) as cm:
        cm.sync()
        before: Any = cm.scoped_source_literals(paths, literals)
        saved = deepcopy(before)
        materialize_dependency(root, native_dependency_corpus / producer / "v2")
        unsynced: Any = cm.scoped_source_literals(paths, literals)
        # Unindexed manifests expose their freshly captured bytes directly;
        # source completeness does not prove repository freshness.
        assert unsynced["source_coverage"] == "complete"
        assert unsynced["freshness"] == "unknown"
        assert unsynced["exact_match_count"] == (6 if producer == "uv" else 2)
        assert all(
            row["negative_evidence"] == "not-admissible"
            for row in unsynced["literal_observations"]
        )
        assert all(row["literal"] != "1.0.0" for row in unsynced["occurrences"])
        cm.sync(paths)
        after: Any = cm.scoped_source_literals(paths, literals)
        assert before == saved
    for packet, version in ((before, "1.0.0"), (after, "2.0.0")):
        facts = {row["literal"]: row for row in packet["literal_observations"]}
        assert facts[version]["exact_match_count"] == 1
        assert facts["dummy-dep"]["exact_match_count"] == (5 if producer == "uv" else 1)
        assert (
            facts["2.0.0" if version == "1.0.0" else "1.0.0"]["exact_match_count"] == 0
        )
        assert_literal_returned_counts(packet)
    old = next(row for row in before["occurrences"] if row["literal"] == "1.0.0")
    new = next(row for row in after["occurrences"] if row["literal"] == "2.0.0")
    assert old["member_revision"] != new["member_revision"]
    assert old["evidence_identity"] != new["evidence_identity"]
    with CodeMap(root, state_dir=state) as cm:
        reopened: Any = cm.scoped_source_literals(paths, literals)
        assert reopened == after


@pytest.mark.parametrize("producer", ["uv", "maven"])
def test_manifest_literal_rename_delete_and_reopen_preserve_missing_scope(
    tmp_path: Path, producer: str, native_dependency_corpus: Path
) -> None:
    root, state = tmp_path / "repo", tmp_path / "state"
    materialize_dependency(root, native_dependency_corpus / producer / "v2")
    target = "uv.lock" if producer == "uv" else "pom.xml"
    renamed = "moved-" + target
    literals = ["dummy-dep", "1.0.0", "2.0.0"]
    with CodeMap(root, state_dir=state) as cm:
        cm.sync()
        (root / target).rename(root / renamed)
        missing: Any = cm.scoped_source_literals([target], literals)
        assert missing["source_coverage"] == "unknown"
        assert missing["exact_match_count"] is None
        assert all(row["path"] != target for row in missing["occurrences"])
        cm.sync([target, renamed])
        renamed_packet: Any = cm.scoped_source_literals([renamed], literals)
        assert all(row["path"] == renamed for row in renamed_packet["occurrences"])
        assert renamed_packet["exact_match_count"] == (4 if producer == "uv" else 2)
        (root / renamed).unlink()
        cm.sync([renamed])
    with CodeMap(root, state_dir=state) as cm:
        deleted: Any = cm.scoped_source_literals([renamed], literals)
    assert deleted["occurrences"] == []
    assert deleted["exact_match_count"] is None
    assert deleted["negative_evidence"] == "not-admissible"
    assert deleted["member_observations"][0]["state"] == "known-absent"


@pytest.mark.parametrize(
    ("path", "content", "reason"),
    [
        (".env", b"REJECTED_SENTINEL=needle\n", "repository-evidence-denied"),
        ("missing.py", None, "member-not-present"),
        ("encoded.py", b"\xffREJECTED_SENTINEL needle\n", "invalid-utf8"),
        ("binary.py", b"\x00REJECTED_SENTINEL needle\n", "null-byte-text"),
        ("large.py", b"REJECTED_SENTINEL needle\n" * 5, "source-size-bound"),
    ],
)
def test_literal_partial_scope_preserves_positive_rows_without_absence(
    tmp_path: Path, path: str, content: bytes | None, reason: str
) -> None:
    (tmp_path / "safe.py").write_text("value = 'needle'\n", encoding="utf-8")
    if content is not None:
        (tmp_path / path).write_bytes(content)
    with CodeMap(tmp_path) as cm:
        cm.sync()
        packet: Any = cm.scoped_source_literals(
            ["safe.py", path],
            ["needle", "absent"],
            max_member_bytes=32,
            context_lines=1,
        )
    assert packet["source_coverage"] == "unknown"
    assert packet["exact_match_count"] is None
    assert packet["observed_match_count"] == 1
    assert [(row["path"], row["literal"]) for row in packet["occurrences"]] == [
        ("safe.py", "needle")
    ]
    assert all(
        row["exact_match_count"] is None
        and row["negative_evidence"] == "not-admissible"
        for row in packet["literal_observations"]
    )
    rejected = next(row for row in packet["member_observations"] if row["path"] == path)
    assert rejected["reason"] == reason
    assert rejected["observed_match_counts"] is None
    assert "REJECTED_SENTINEL" not in json.dumps(packet)
    assert_literal_returned_counts(packet)


@pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="native inotify barrier"
)
def test_real_identity_watcher_qualifies_absence_then_invalidates_immediate_edit(
    tmp_path: Path,
) -> None:
    root, state = tmp_path / "repo", tmp_path / "state"
    root.mkdir()
    target = root / "a.py"
    target.write_text("value = 'left left right'\n", encoding="utf-8")
    (root / "outside.py").write_text("value = 'absent'\n", encoding="utf-8")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "hashmarks.cli",
            "--workspace",
            str(root),
            "--state-dir",
            str(state),
            "daemon",
            "start",
        ],
        env={**os.environ, "HASHMARKS_NO_UPDATE_CHECK": "1"},
        check=True,
        capture_output=True,
    )
    client = IdentityClient(root, state_dir=state)
    try:
        client.input_root(["a.py"])
        with CodeMap(root, state_dir=state) as cm:
            cm.sync()
            before: Any = cm.scoped_source_literals(
                ["a.py"], ["left", "right", "absent"], limit=1
            )
            assert before["freshness"] == "current"
            assert before["truncation"] == "truncated"
            assert before["exact_match_count"] == 3
            facts = {row["literal"]: row for row in before["literal_observations"]}
            assert facts["absent"]["exact_match_count"] == 0
            assert facts["absent"]["negative_evidence"] == (
                "admissible-within-explicit-member-set"
            )
            assert_literal_returned_counts(before)
            target.write_text("value = 'left right absent'\n", encoding="utf-8")
            stale: Any = cm.scoped_source_literals(
                ["a.py"], ["left", "absent"], limit=1
            )
            assert stale["freshness"] == "stale"
            assert stale["source_coverage"] == "unknown"
            assert stale["exact_match_count"] is None
            assert stale["occurrences"] == []
            cm.sync(["a.py"])
            after: Any = cm.scoped_source_literals(
                ["a.py"], ["left", "absent"], limit=1
            )
            assert after["freshness"] == "current"
            assert after["exact_match_count"] == 2
            assert all(
                row["negative_evidence"] == "not-admissible"
                for row in after["literal_observations"]
            )
            assert_literal_returned_counts(after)
        with CodeMap(root, state_dir=state) as cm:
            reopened: Any = cm.scoped_source_literals(["a.py"], ["unseen"])
        assert reopened["freshness"] == "current"
        assert reopened["exact_match_count"] == 0
        assert reopened["negative_evidence"] == (
            "admissible-within-explicit-member-and-literal-set"
        )
    finally:
        client.stop()
