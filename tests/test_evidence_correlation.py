from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from hashmarks import CodeMap
from hashmarks.codemap.evidence_correlation import CORRELATION_PACKET_MAX_BYTES

if TYPE_CHECKING:
    from pathlib import Path


def _bundle(
    *anchors: dict[str, object], completeness: str = "complete"
) -> list[dict[str, object]]:
    return [
        {
            "bundle_id": "observation:1",
            "producer": {"kind": "test-fixture"},
            "completeness": completeness,
            "scope": {"kind": "test-fixture"},
            "truncation": "complete" if completeness == "complete" else "unknown",
            "anchors": list(anchors),
        }
    ]


def _binding(
    packet: dict[str, object],
    anchor: dict[str, object],
) -> dict[str, object]:
    binding_id = anchor["repository_evidence_binding_id"]
    rows = packet["repository_evidence"]["bindings"]
    return next(row for row in rows if row["binding_id"] == binding_id)


def test_evidence_correlation_extension_preserves_repository_coverage_owner(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "coverage-owner",
            "evidence": [{"path": "owner.py", "start_line": 1, "end_line": 1}],
        }
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.repository_evidence_bindings(
            binding, include_relationships=False
        )
        coverage = codemap.repository_evidence_coverage(
            packet,
            changed_paths=[],
            change_set_complete=True,
        )

    assert coverage["schema"] == "hashmarks.repository-evidence-coverage.v1"
    assert coverage["binding_impacts"] == []


def test_external_runtime_path_maps_to_repository_symbol_without_gaining_authority(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src" / "worker.py"
    source.parent.mkdir()
    source.write_text(
        "def process_output_data(value: int) -> int:\n    return value + 1\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.correlate_evidence(
            _bundle(
                {
                    "anchor_id": "frame:0",
                    "path": "/app/src/worker.py",
                    "line": 2,
                    "symbol": "process_output_data",
                    "metadata": {"handling_ident": "opaque-123"},
                }
            ),
            path_mappings=[{"external_prefix": "/app", "repository_prefix": ""}],
        )

    anchor = packet["bundles"][0]["anchors"][0]
    assert packet["schema"] == "hashmarks.evidence-correlation.v1"
    assert packet["authority"] == "repository-intelligence-only"
    assert packet["interpretation_authority"] == "consumer-owned"
    assert packet["causation"] == "not-inferred"
    assert packet["storage"] == "request-scoped-not-persisted"
    assert anchor["resolution"]["state"] == "resolved-unique"
    assert anchor["resolution"]["repository_path"] == "src/worker.py"
    assert anchor["resolution"]["symbol"]["qualname"] == "process_output_data"
    assert anchor["source_equivalence"]["state"] == "unknown"


def test_opaque_commit_like_metadata_never_proves_repository_source_identity(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.correlate_evidence(
            _bundle(
                {
                    "anchor_id": "runtime",
                    "path": "owner.py",
                    "line": 1,
                    "metadata": {
                        "commit": "3916110",
                        "revision": "pretend-sha",
                    },
                }
            )
        )

    anchor = packet["bundles"][0]["anchors"][0]
    assert anchor["claims"]["metadata"]["commit"] == "3916110"
    assert anchor["source_equivalence"] == {
        "state": "unknown",
        "basis": [],
    }


def test_qualified_member_revision_proves_or_rejects_source_equivalence(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    base = _bundle({"anchor_id": "member", "path": "owner.py"})
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observed = codemap.correlate_evidence(base, include_relationships=False)
        observed_anchor = observed["bundles"][0]["anchors"][0]
        revision = _binding(observed, observed_anchor)["evidence"][0]["member_revision"]
        proven = codemap.correlate_evidence(
            _bundle(
                {
                    "anchor_id": "member",
                    "path": "owner.py",
                    "member_revision": revision,
                }
            ),
            include_relationships=False,
        )
        mismatch = codemap.correlate_evidence(
            _bundle(
                {
                    "anchor_id": "member",
                    "path": "owner.py",
                    "member_revision": "0" * 64,
                }
            ),
            include_relationships=False,
        )

    assert proven["bundles"][0]["anchors"][0]["source_equivalence"]["state"] == "proven"
    assert (
        mismatch["bundles"][0]["anchors"][0]["source_equivalence"]["state"]
        == "mismatch"
    )


def test_symbol_only_evidence_preserves_repository_ambiguity(
    tmp_path: Path,
) -> None:
    (tmp_path / "left.py").write_text(
        "def duplicate():\n    return 1\n", encoding="utf-8"
    )
    (tmp_path / "right.py").write_text(
        "def duplicate():\n    return 2\n", encoding="utf-8"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.correlate_evidence(
            _bundle({"anchor_id": "symbol", "symbol": "duplicate"}),
            include_relationships=False,
        )

    resolution = packet["bundles"][0]["anchors"][0]["resolution"]
    assert resolution["state"] == "resolved-ambiguous"
    assert [row["path"] for row in resolution["candidates"]] == [
        "left.py",
        "right.py",
    ]


def test_conflicting_symbol_and_line_stays_a_claim_conflict(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text(
        "def first():\n    return 1\n\ndef second():\n    return 2\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.correlate_evidence(
            _bundle(
                {
                    "anchor_id": "conflict",
                    "path": "owner.py",
                    "line": 2,
                    "symbol": "second",
                }
            ),
            include_relationships=False,
        )

    resolution = packet["bundles"][0]["anchors"][0]["resolution"]
    assert resolution["state"] == "claim-conflict"
    assert resolution["reason"] == "symbol-does-not-contain-claimed-line"


def test_missing_repository_member_does_not_become_resolved_by_mapping(
    tmp_path: Path,
) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.correlate_evidence(
            _bundle(
                {
                    "anchor_id": "missing",
                    "path": "/app/src/missing.py",
                    "line": 8,
                }
            ),
            path_mappings=[{"external_prefix": "/app", "repository_prefix": ""}],
            include_relationships=False,
        )

    anchor = packet["bundles"][0]["anchors"][0]
    assert anchor["resolution"]["state"] == "unresolved"
    assert anchor["resolution"]["repository_path"] == "src/missing.py"
    assert _binding(packet, anchor)["evidence"][0]["state"] == "known-absent"


def test_bundle_reordering_does_not_change_correlation_identity(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("A = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("B = 1\n", encoding="utf-8")
    left = [
        {
            "bundle_id": "b",
            "producer": {},
            "completeness": "complete",
            "scope": {"kind": "test-fixture"},
            "truncation": "complete",
            "anchors": [{"anchor_id": "b:0", "path": "b.py"}],
        },
        {
            "bundle_id": "a",
            "producer": {},
            "completeness": "complete",
            "scope": {"kind": "test-fixture"},
            "truncation": "complete",
            "anchors": [{"anchor_id": "a:0", "path": "a.py"}],
        },
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        first = codemap.correlate_evidence(left, include_relationships=False)
        second = codemap.correlate_evidence(
            list(reversed(left)), include_relationships=False
        )

    assert first == second
    assert [row["bundle_id"] for row in first["bundles"]] == ["a", "b"]


def test_anchor_reordering_within_bundle_does_not_change_correlation_identity(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("A = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("B = 1\n", encoding="utf-8")
    anchors = [
        {"anchor_id": "b:0", "path": "b.py", "metadata": {"ordinal": 2}},
        {"anchor_id": "a:0", "path": "a.py", "metadata": {"ordinal": 1}},
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        first = codemap.correlate_evidence(
            _bundle(*anchors), include_relationships=False
        )
        second = codemap.correlate_evidence(
            _bundle(*reversed(anchors)), include_relationships=False
        )

    assert first == second
    assert first["correlation_identity"] == second["correlation_identity"]
    assert [anchor["anchor_id"] for anchor in first["bundles"][0]["anchors"]] == [
        "a:0",
        "b:0",
    ]
    assert first["bundles"][0]["anchors"][0]["claims"]["metadata"] == {"ordinal": 1}


def test_symbol_candidate_bound_preserves_ambiguity(
    tmp_path: Path,
) -> None:
    source = tmp_path / "many.py"
    source.write_text(
        "\n\n".join(
            f"class C{index}:\n    def duplicate(self):\n        return {index}"
            for index in range(40)
        )
        + "\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.correlate_evidence(
            _bundle(
                {
                    "anchor_id": "dense",
                    "path": "many.py",
                    "symbol": "duplicate",
                }
            ),
            include_relationships=False,
        )

    resolution = packet["bundles"][0]["anchors"][0]["resolution"]
    assert resolution["state"] == "resolved-ambiguous"
    assert resolution["reason"] == "symbol-match-bound-exhausted"
    assert resolution["candidate_completeness"] == "bounded"
    assert len(resolution["candidates"]) == 32


def test_absolute_external_path_requires_explicit_mapping(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.correlate_evidence(
            _bundle(
                {
                    "anchor_id": "unmapped",
                    "path": "/runtime/owner.py",
                    "line": 1,
                }
            ),
            include_relationships=False,
        )

    anchor = packet["bundles"][0]["anchors"][0]
    assert anchor["resolution"]["state"] == "unresolved"
    assert anchor["resolution"]["reason"] == "external-path-mapping-required"
    assert _binding(packet, anchor)["evidence"] == []


def test_external_paths_and_mapping_prefixes_fail_closed_on_escape(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="must not contain '..'"):
            codemap.correlate_evidence(
                _bundle(
                    {
                        "anchor_id": "escape",
                        "path": "/app/../secret.py",
                    }
                ),
                path_mappings=[
                    {
                        "external_prefix": "/app",
                        "repository_prefix": "",
                    }
                ],
            )
        with pytest.raises(ValueError, match="must not contain '..'"):
            codemap.correlate_evidence(
                _bundle(
                    {
                        "anchor_id": "safe",
                        "path": "/app/owner.py",
                    }
                ),
                path_mappings=[
                    {
                        "external_prefix": "/app",
                        "repository_prefix": "../outside",
                    }
                ],
            )


def test_bundle_completeness_is_preserved_not_inferred(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.correlate_evidence(
            _bundle(
                {"anchor_id": "partial", "path": "owner.py"},
                completeness="incomplete",
            ),
            include_relationships=False,
        )

    assert packet["bundles"][0]["completeness"] == "incomplete"
    assert packet["completeness"] == {
        "state": "incomplete",
        "scope": "caller-declared-external-observations",
        "authority": "caller-claimed",
        "negative_evidence": "not-admissible",
    }


def test_complete_external_bundle_requires_explicit_non_truncation(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    bundle = _bundle({"anchor_id": "owner", "path": "owner.py"})[0]
    bundle.pop("truncation")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(
            ValueError,
            match="completeness=complete requires truncation=complete",
        ):
            codemap.correlate_evidence([bundle], include_relationships=False)


def test_truncated_external_bundle_cannot_authorize_negative_evidence(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    bundle = _bundle(
        {"anchor_id": "owner", "path": "owner.py"},
        completeness="incomplete",
    )[0]
    bundle["scope"] = {"stream": "masked-runtime", "window": "bounded-sample"}
    bundle["truncation"] = "truncated"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.correlate_evidence([bundle], include_relationships=False)

    assert packet["bundles"][0]["scope"] == bundle["scope"]
    assert packet["bundles"][0]["truncation"] == "truncated"
    assert packet["bundles"][0]["producer_authority"] == "caller-claimed"
    assert packet["completeness"] == {
        "state": "incomplete",
        "scope": "caller-declared-external-observations",
        "authority": "caller-claimed",
        "negative_evidence": "not-admissible",
    }


def test_complete_scoped_external_bundle_marks_negative_evidence_scope_only(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    bundle = _bundle({"anchor_id": "owner", "path": "owner.py"})[0]
    bundle["scope"] = {
        "stream": "masked-runtime",
        "window": "2026-09-21T08:00:00Z/2026-09-21T09:00:00Z",
    }
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.correlate_evidence([bundle], include_relationships=False)

    assert packet["completeness"] == {
        "state": "complete",
        "scope": "caller-declared-external-observations",
        "authority": "caller-claimed",
        "negative_evidence": "admissible-within-declared-scopes",
    }
    assert packet["bundles"][0]["scope"] == bundle["scope"]


def test_scope_and_truncation_change_definition_identity(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    first_bundle = _bundle(
        {"anchor_id": "owner", "path": "owner.py"},
        completeness="incomplete",
    )[0]
    first_bundle["scope"] = {"window": "first"}
    first_bundle["truncation"] = "truncated"
    second_bundle = json.loads(json.dumps(first_bundle))
    second_bundle["scope"] = {"window": "second"}
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        first = codemap.correlate_evidence([first_bundle], include_relationships=False)
        second = codemap.correlate_evidence(
            [second_bundle], include_relationships=False
        )
        delta = codemap.evidence_correlation_delta(first, second)

    assert (
        first["evidence_definition_identity"] != second["evidence_definition_identity"]
    )
    assert delta["definition"]["state"] == "changed"


def test_bundle_scope_is_bounded_and_json_compatible(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        bundle = _bundle(
            {"anchor_id": "missing", "path": "missing.py"},
            completeness="incomplete",
        )[0]
        bundle["scope"] = {"bad": object()}
        with pytest.raises(
            ValueError,
            match="evidence correlation request must contain JSON-compatible values",
        ):
            codemap.correlate_evidence([bundle], include_relationships=False)

        bundle["scope"] = {"value": "x" * 9000}
        with pytest.raises(ValueError, match="bundle scope exceeds 8192 encoded bytes"):
            codemap.correlate_evidence([bundle], include_relationships=False)


def test_uv_lock_upgrade_delta_reuses_repository_binding_authority(
    tmp_path: Path,
) -> None:
    lock = tmp_path / "uv.lock"
    lock.write_text(
        'version = 1\npackage = "cryptography==46.0.4"\n',
        encoding="utf-8",
    )
    evidence = _bundle(
        {
            "anchor_id": "dependency-lock",
            "path": "uv.lock",
            "metadata": {
                "producer": "uv-tree",
                "package": "cryptography",
                "reported_version": "46.0.4",
            },
        }
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.correlate_evidence(evidence, include_relationships=False)
        lock.write_text(
            'version = 1\npackage = "cryptography==47.0.0"\n',
            encoding="utf-8",
        )
        codemap.sync(["uv.lock"])
        after = codemap.correlate_evidence(
            evidence,
            include_relationships=False,
            previous_correlation=before,
        )

    delta = after["delta_from_previous"]
    assert delta["schema"] == "hashmarks.evidence-correlation-delta.v1"
    assert delta["definition"]["state"] == "preserved"
    changed = delta["repository_evidence_delta"]["bindings"]["changed"][0]
    assert changed["direct_evidence"]["state"] == "changed"
    assert changed["direct_evidence"]["changes"][0]["scope"] == "member"
    assert delta["causation"] == "not-inferred"
    assert delta["interpretation_authority"] == "consumer-owned"


def test_previous_correlation_rejects_tampered_top_level_packet(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.correlate_evidence(
            _bundle({"anchor_id": "owner", "path": "owner.py"}),
            include_relationships=False,
        )
        tampered = dict(before)
        tampered["causation"] = "producer-claimed"
        with pytest.raises(
            ValueError,
            match="correlation_identity does not match packet content",
        ):
            codemap.correlate_evidence(
                _bundle({"anchor_id": "owner", "path": "owner.py"}),
                include_relationships=False,
                previous_correlation=tampered,
            )


def test_previous_correlation_rejects_tampered_nested_repository_evidence(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.correlate_evidence(
            _bundle({"anchor_id": "owner", "path": "owner.py"}),
            include_relationships=False,
        )
        tampered = json.loads(json.dumps(before))
        bindings = tampered["repository_evidence"]["bindings"]
        bindings[0]["evidence"][0]["state"] = "known-absent"
        with pytest.raises(
            ValueError,
            match="correlation_identity does not match packet content",
        ):
            codemap.correlate_evidence(
                _bundle({"anchor_id": "owner", "path": "owner.py"}),
                include_relationships=False,
                previous_correlation=tampered,
            )


def test_previous_correlation_rejects_missing_or_malformed_identity(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.correlate_evidence(
            _bundle({"anchor_id": "owner", "path": "owner.py"}),
            include_relationships=False,
        )
        missing = dict(before)
        missing.pop("correlation_identity")
        with pytest.raises(ValueError, match="correlation_identity must use sha256"):
            codemap.evidence_correlation_delta(missing, before)

        malformed = dict(before)
        malformed["correlation_identity"] = "opaque"
        with pytest.raises(ValueError, match="correlation_identity must use sha256"):
            codemap.evidence_correlation_delta(before, malformed)


def test_duplicate_bundle_ids_fail_closed_before_correlation(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    bundle = {
        "bundle_id": "duplicate",
        "producer": {"kind": "test-fixture"},
        "completeness": "complete",
        "scope": {"kind": "test-fixture"},
        "truncation": "complete",
        "anchors": [{"anchor_id": "owner", "path": "owner.py"}],
    }
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="duplicate bundle_id: duplicate"):
            codemap.correlate_evidence(
                [bundle, dict(bundle)],
                include_relationships=False,
            )


def test_duplicate_anchor_ids_fail_closed_within_bundle(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(
            ValueError,
            match="duplicate anchor_id in bundle observation:1: owner",
        ):
            codemap.correlate_evidence(
                _bundle(
                    {"anchor_id": "owner", "path": "owner.py"},
                    {"anchor_id": "owner", "path": "owner.py"},
                ),
                include_relationships=False,
            )


def test_previous_correlation_rejects_tampered_authority_definition_and_bounds(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.correlate_evidence(
            _bundle({"anchor_id": "owner", "path": "owner.py"}),
            include_relationships=False,
        )
        mutations = [
            ("authority", "consumer-owned"),
            ("evidence_definition_identity", "sha256:" + "0" * 64),
            (
                "bounds",
                {"request_max_bytes": 1, "packet_max_bytes": 1, "max_anchors": 1},
            ),
            (
                "path_mappings",
                [{"external_prefix": "/app", "repository_prefix": "src"}],
            ),
        ]
        for field, value in mutations:
            tampered = json.loads(json.dumps(before))
            tampered[field] = value
            with pytest.raises(
                ValueError,
                match="correlation_identity does not match packet content",
            ):
                codemap.evidence_correlation_delta(tampered, before)


def test_correlation_request_reuses_binding_total_bound(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    anchors = [{"anchor_id": f"a:{index}", "path": "owner.py"} for index in range(257)]
    bundles = [
        {
            "bundle_id": "too-many",
            "producer": {},
            "completeness": "complete",
            "scope": {"kind": "test-fixture"},
            "truncation": "complete",
            "anchors": anchors[:256],
        },
        {
            "bundle_id": "one-more",
            "producer": {},
            "completeness": "complete",
            "scope": {"kind": "test-fixture"},
            "truncation": "complete",
            "anchors": anchors[256:],
        },
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="256 total anchors"):
            codemap.correlate_evidence(bundles, include_relationships=False)


def test_exact_module_locator_reuses_repository_module_identity(
    tmp_path: Path,
) -> None:
    (tmp_path / "src" / "utils").mkdir(parents=True)
    (tmp_path / "src" / "utils" / "kafka.py").write_text(
        "def publish():\n    return None\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="example"\nversion="0.0.0"\n\n'
        '[tool.setuptools.package-dir]\n""="src"\n',
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.correlate_evidence(
            _bundle(
                {"anchor_id": "owned", "module": "utils.kafka"},
                {"anchor_id": "external", "module": "httpx"},
            ),
            include_relationships=False,
        )

    anchors = {
        anchor["anchor_id"]: anchor for anchor in packet["bundles"][0]["anchors"]
    }
    owned = anchors["owned"]
    external = anchors["external"]
    assert owned["resolution"]["state"] == "resolved-unique"
    assert owned["resolution"]["repository_path"] == "src/utils/kafka.py"
    assert owned["resolution"]["reason"] == "module-only"
    assert external["resolution"]["state"] == "unresolved"
    assert external["resolution"]["reason"] == "module-not-found"


def test_module_claim_conflicting_with_exact_path_stays_conflict(
    tmp_path: Path,
) -> None:
    (tmp_path / "src" / "utils").mkdir(parents=True)
    source = tmp_path / "src" / "utils" / "kafka.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="example"\nversion="0.0.0"\n\n'
        '[tool.setuptools.package-dir]\n""="src"\n',
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.correlate_evidence(
            _bundle(
                {
                    "anchor_id": "conflict",
                    "path": "src/utils/kafka.py",
                    "module": "api.kafka_consumer",
                }
            ),
            include_relationships=False,
        )

    resolution = packet["bundles"][0]["anchors"][0]["resolution"]
    assert resolution["state"] == "claim-conflict"
    assert resolution["reason"] == "module-does-not-match-resolved-path"


def test_repeated_observations_share_one_repository_binding(
    tmp_path: Path,
) -> None:
    source = tmp_path / "worker.py"
    source.write_text(
        "def process_output_data(value: int) -> int:\n    return value + 1\n",
        encoding="utf-8",
    )
    anchors = [
        {
            "anchor_id": f"frame:{index}",
            "path": "worker.py",
            "line": 2,
            "symbol": "process_output_data",
            "metadata": {"event": index},
        }
        for index in range(256)
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with codemap.decision_session(diagnostics=True):
            packet = codemap.correlate_evidence(
                _bundle(*anchors),
                include_relationships=True,
            )
        diagnostics = codemap.decision_session_diagnostics()

    emitted = packet["bundles"][0]["anchors"]
    assert len(packet["repository_evidence"]["bindings"]) == 1
    assert len({row["repository_evidence_binding_id"] for row in emitted}) == 1
    assert all(
        set(row["repository_evidence"])
        == {
            "binding_id",
            "binding_definition_identity",
            "binding_observation_identity",
        }
        for row in emitted
    )
    encoded = json.dumps(packet, separators=(",", ":")).encode("utf-8")
    assert len(encoded) <= CORRELATION_PACKET_MAX_BYTES
    assert diagnostics["store_reads"]["store_symbol_candidates_at_path"] == 1


def test_core_packet_budget_fails_closed_for_dense_relationship_evidence(
    tmp_path: Path,
) -> None:
    anchors: list[dict[str, object]] = []
    for file_index in range(40):
        path = tmp_path / f"dense{file_index}.py"
        body = ["def target():\n"]
        body.extend(f"    f{i}()\n" for i in range(120))
        body.append("\n")
        for i in range(120):
            body.extend(
                (
                    f"def f{i}():\n",
                    f"    return {i}\n",
                    "\n",
                )
            )
        path.write_text("".join(body), encoding="utf-8")
        anchors.append(
            {
                "anchor_id": f"dense:{file_index}",
                "path": path.name,
                "line": 2,
                "symbol": "target",
            }
        )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(
            ValueError,
            match="packet exceeds 1048576 encoded bytes",
        ):
            codemap.correlate_evidence(
                _bundle(*anchors),
                include_relationships=True,
                relationship_limit_per_path=100,
            )


def test_external_temporal_provenance_is_preserved_but_not_repository_freshness(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    bundle = _bundle({"anchor_id": "owner", "path": "owner.py"})[0]
    bundle["provenance"] = {
        "event_time": "2026-09-21T08:00:00Z",
        "observed_time": "2026-09-21T08:00:02Z",
        "collected_time": "2026-09-21T08:01:00Z",
        "source": {"service": "worker", "placement": "pod-a"},
    }
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.correlate_evidence([bundle], include_relationships=False)

    emitted = packet["bundles"][0]
    assert emitted["provenance"] == bundle["provenance"]
    assert emitted["provenance_authority"] == "caller-claimed"
    assert emitted["repository_freshness_authority"] == "independent"


def test_temporal_provenance_changes_definition_not_repository_delta(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    first_bundle = _bundle({"anchor_id": "owner", "path": "owner.py"})[0]
    first_bundle["provenance"] = {"observed_time": "2026-09-21T08:00:00Z"}
    second_bundle = json.loads(json.dumps(first_bundle))
    second_bundle["provenance"] = {"observed_time": "2026-09-21T09:00:00Z"}
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        first = codemap.correlate_evidence([first_bundle], include_relationships=False)
        second = codemap.correlate_evidence(
            [second_bundle], include_relationships=False
        )
        delta = codemap.evidence_correlation_delta(first, second)

    assert delta["comparability"] == "not-comparable"
    assert delta["definition"]["state"] == "changed"
    assert delta["repository_evidence_delta"] is None


def test_same_definition_keeps_correlation_delta_comparable(tmp_path: Path) -> None:
    path = tmp_path / "owner.py"
    path.write_text("VALUE = 1\n", encoding="utf-8")
    bundle = _bundle({"anchor_id": "owner", "path": "owner.py"})
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.correlate_evidence(bundle, include_relationships=False)
        path.write_text("VALUE = 2\n", encoding="utf-8")
        codemap.sync(["owner.py"])
        after = codemap.correlate_evidence(bundle, include_relationships=False)
        delta = codemap.evidence_correlation_delta(before, after)

    assert delta["comparability"] == "comparable"
    assert delta["definition"]["state"] == "preserved"
    assert delta["repository_evidence_delta"] is not None


def test_bundle_provenance_is_bounded_and_json_compatible(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        bundle = _bundle(
            {"anchor_id": "missing", "path": "missing.py"},
            completeness="incomplete",
        )[0]
        bundle["provenance"] = {"bad": object()}
        with pytest.raises(
            ValueError,
            match="evidence correlation request must contain JSON-compatible values",
        ):
            codemap.correlate_evidence([bundle], include_relationships=False)

        bundle["provenance"] = {"value": "x" * 9000}
        with pytest.raises(
            ValueError,
            match="bundle provenance exceeds 8192 encoded bytes",
        ):
            codemap.correlate_evidence([bundle], include_relationships=False)


@pytest.mark.parametrize(
    ("external_path", "external_prefix"),
    [
        ("/app/src/owner.py", "/app/src"),
        ("C:\\workspace\\src\\owner.py", "C:\\workspace\\src"),
        ("C:/workspace/src/owner.py", "C:/workspace/src"),
        ("/mnt/c/workspace/src/owner.py", "/mnt/c/workspace/src"),
    ],
)
def test_path_mapping_portability_preserves_repository_identity(
    tmp_path: Path,
    external_path: str,
    external_prefix: str,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.correlate_evidence(
            _bundle({"anchor_id": "portable", "path": external_path}),
            path_mappings=[
                {"external_prefix": external_prefix, "repository_prefix": "src"}
            ],
            include_relationships=False,
        )

    resolution = packet["bundles"][0]["anchors"][0]["resolution"]
    assert resolution["state"] == "resolved-unique"
    assert resolution["repository_path"] == "src/owner.py"
    assert resolution["path_origin"] == "explicit-path-mapping"


def test_longest_path_mapping_prefix_wins_deterministically(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    mappings = [
        {"external_prefix": "/app", "repository_prefix": ""},
        {"external_prefix": "/app/pkg", "repository_prefix": "src"},
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.correlate_evidence(
            _bundle({"anchor_id": "owner", "path": "/app/pkg/owner.py"}),
            path_mappings=list(reversed(mappings)),
            include_relationships=False,
        )

    resolution = packet["bundles"][0]["anchors"][0]["resolution"]
    assert resolution["repository_path"] == "src/owner.py"


def test_source_equivalence_requires_independent_repository_identity(
    tmp_path: Path,
) -> None:
    source = tmp_path / "owner.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observed, _raw = codemap._repository_member_observation("owner.py")
        revision = observed["member_revision"]
        proven = codemap.correlate_evidence(
            _bundle(
                {
                    "anchor_id": "proven",
                    "path": "owner.py",
                    "member_revision": revision,
                    "metadata": {
                        "commit": "opaque-producer-label",
                        "image": "sha256:not-repository-identity",
                    },
                }
            ),
            include_relationships=False,
        )
        mismatch = codemap.correlate_evidence(
            _bundle(
                {
                    "anchor_id": "mismatch",
                    "path": "owner.py",
                    "member_revision": "0" * 64,
                }
            ),
            include_relationships=False,
        )
        unknown = codemap.correlate_evidence(
            _bundle(
                {
                    "anchor_id": "unknown",
                    "path": "owner.py",
                    "metadata": {"commit": revision, "version": "1.2.3"},
                }
            ),
            include_relationships=False,
        )

    assert proven["bundles"][0]["anchors"][0]["source_equivalence"]["state"] == "proven"
    assert (
        mismatch["bundles"][0]["anchors"][0]["source_equivalence"]["state"]
        == "mismatch"
    )
    assert unknown["bundles"][0]["anchors"][0]["source_equivalence"] == {
        "state": "unknown",
        "basis": [],
    }


def test_member_revision_and_span_identity_disagreement_is_mismatch(
    tmp_path: Path,
) -> None:
    source = tmp_path / "owner.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        baseline = codemap.correlate_evidence(
            _bundle({"anchor_id": "baseline", "path": "owner.py", "line": 1}),
            include_relationships=False,
        )
        anchor = baseline["bundles"][0]["anchors"][0]
        binding_id = anchor["repository_evidence_binding_id"]
        binding = next(
            row
            for row in baseline["repository_evidence"]["bindings"]
            if row["binding_id"] == binding_id
        )
        evidence = binding["evidence"][0]
        packet = codemap.correlate_evidence(
            _bundle(
                {
                    "anchor_id": "conflict",
                    "path": "owner.py",
                    "line": 1,
                    "member_revision": evidence["member_revision"],
                    "span_identity": "sha256:" + "0" * 64,
                }
            ),
            include_relationships=False,
        )

    equivalence = packet["bundles"][0]["anchors"][0]["source_equivalence"]
    assert equivalence["state"] == "mismatch"
    assert {row["kind"] for row in equivalence["basis"]} == {
        "member-revision",
        "span-identity",
    }


@pytest.mark.parametrize(
    ("producer_kind", "metadata"),
    [
        ("pytest", {"test": "tests/test_owner.py::test_owner", "outcome": "failed"}),
        ("ruff", {"code": "F821", "message": "undefined name"}),
        ("type-checker", {"diagnostic": "incompatible-return-value"}),
        ("compiler", {"diagnostic": "syntax-error"}),
        ("coverage", {"covered": False, "line": 1}),
        ("sbom-scanner", {"component": "example", "finding": "observed"}),
        ("splunk-style", {"logger": "worker", "event_id": "opaque"}),
        ("loki-style", {"stream": "worker", "event_id": "opaque"}),
        ("cloudwatch-style", {"log_group": "worker", "event_id": "opaque"}),
        ("sentry-style", {"event_id": "opaque", "issue": "caller-claimed"}),
        ("otel-style", {"trace_id": "opaque", "span_id": "opaque"}),
    ],
)
def test_producer_neutral_evidence_uses_same_repository_correlation_owner(
    tmp_path: Path,
    producer_kind: str,
    metadata: dict[str, object],
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    bundle = _bundle(
        {
            "anchor_id": producer_kind,
            "path": "owner.py",
            "line": 1,
            "metadata": metadata,
        }
    )[0]
    bundle["producer"] = {"kind": producer_kind}
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.correlate_evidence([bundle], include_relationships=False)

    emitted = packet["bundles"][0]
    anchor = emitted["anchors"][0]
    assert emitted["producer"] == {"kind": producer_kind}
    assert emitted["producer_authority"] == "caller-claimed"
    assert anchor["resolution"]["state"] == "resolved-unique"
    assert anchor["resolution"]["repository_path"] == "owner.py"
    assert packet["causation"] == "not-inferred"
    assert packet["interpretation_authority"] == "consumer-owned"


def test_evidence_payload_is_not_operational_telemetry(tmp_path: Path) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    secret_marker = "evidence-payload-must-not-be-telemetry"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.correlate_evidence(
            _bundle(
                {
                    "anchor_id": "otel",
                    "path": "owner.py",
                    "metadata": {"message": secret_marker},
                }
            ),
            include_relationships=False,
        )

    assert (
        packet["bundles"][0]["anchors"][0]["claims"]["metadata"]["message"]
        == secret_marker
    )
    assert packet["storage"] == "request-scoped-not-persisted"
    assert packet["execution_effect"] == "none"


def test_cross_bundle_correspondence_reports_same_target_without_incident_or_cause(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text(
        "def target():\n    return 1\n",
        encoding="utf-8",
    )
    bundles = []
    for bundle_id, producer in (("tests", "pytest"), ("logs", "otel-style")):
        bundle = _bundle(
            {
                "anchor_id": f"{bundle_id}:target",
                "path": "owner.py",
                "line": 1,
                "symbol": "target",
                "metadata": {"producer_event": bundle_id},
            }
        )[0]
        bundle["bundle_id"] = bundle_id
        bundle["producer"] = {"kind": producer}
        bundles.append(bundle)

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.correlate_evidence(bundles, include_relationships=False)

    assert packet["correspondence"] == [
        {
            "state": "same-repository-target",
            "scope": "symbol",
            "repository_path": "owner.py",
            "symbol": "target",
            "start_line": 1,
            "end_line": 2,
            "observations": [
                {"bundle_id": "logs", "anchor_id": "logs:target"},
                {"bundle_id": "tests", "anchor_id": "tests:target"},
            ],
            "causation": "not-inferred",
            "incident_identity": "not-inferred",
        }
    ]


def test_cross_bundle_correspondence_excludes_ambiguous_and_unresolved(
    tmp_path: Path,
) -> None:
    (tmp_path / "one.py").write_text(
        "def duplicate():\n    return 1\n", encoding="utf-8"
    )
    (tmp_path / "two.py").write_text(
        "def duplicate():\n    return 2\n", encoding="utf-8"
    )
    first = _bundle({"anchor_id": "ambiguous", "symbol": "duplicate"})[0]
    first["bundle_id"] = "first"
    second = _bundle({"anchor_id": "missing", "path": "missing.py"})[0]
    second["bundle_id"] = "second"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.correlate_evidence(
            [first, second], include_relationships=False
        )

    assert packet["correspondence"] == []


@pytest.mark.parametrize("anchor_count", [1, 10, 100, 256])
def test_final_correlation_scale_matrix_is_bounded_and_deterministic(
    tmp_path: Path,
    anchor_count: int,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    anchors = [
        {
            "anchor_id": f"anchor:{index:03d}",
            "path": "owner.py",
            "line": 1,
            "metadata": {"index": index, "text": "x" * 32},
        }
        for index in range(anchor_count)
    ]
    bundles = _bundle(*anchors)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        first = codemap.correlate_evidence(bundles, include_relationships=False)
        replay = codemap.correlate_evidence(
            list(reversed(bundles)),
            include_relationships=False,
        )

    assert len(first["bundles"][0]["anchors"]) == anchor_count
    assert len(first["repository_evidence"]["bindings"]) == 1
    assert first["correlation_identity"] == replay["correlation_identity"]
    assert len(json.dumps(first, separators=(",", ":")).encode("utf-8")) <= 1_048_576


def test_cross_bundle_correspondence_is_identity_bound_and_tamper_detected(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    bundles = []
    for bundle_id in ("a", "b"):
        bundle = _bundle({"anchor_id": bundle_id, "path": "owner.py"})[0]
        bundle["bundle_id"] = bundle_id
        bundles.append(bundle)
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.correlate_evidence(bundles, include_relationships=False)
        tampered = json.loads(json.dumps(packet))
        tampered["correspondence"][0]["causation"] = "same-cause"
        with pytest.raises(
            ValueError,
            match="correlation_identity does not match packet content",
        ):
            codemap.evidence_correlation_delta(packet, tampered)


def test_external_evidence_correlation_cannot_create_edit_ownership(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text(
        "def publish_result(value):\n    return value\n", encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_owner.py").write_text(
        "from owner import publish_result\n"
        "def test_publish(): assert publish_result('x') == 'x'\n",
        encoding="utf-8",
    )
    task = "Fix publish_result behavior"
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.task_action_map(task)
        correlated = codemap.correlate_evidence(
            _bundle(
                {
                    "anchor_id": "runtime-frame",
                    "path": "owner.py",
                    "symbol": "publish_result",
                    "metadata": {"runtime": "observed"},
                }
            ),
            include_relationships=False,
        )
        after = codemap.task_action_map(task)

    assert correlated["authority"] == "repository-intelligence-only"
    assert correlated["interpretation_authority"] == "consumer-owned"
    assert before["ownership_authority"] == after["ownership_authority"]


def test_external_evidence_conflict_is_retained_without_mutating_owner(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text(
        "def first():\n    return 1\n\ndef second():\n    return 2\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_owner.py").write_text(
        "from owner import first\ndef test_first(): assert first() == 1\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        before = codemap.task_action_map("Fix first")
        correlated = codemap.correlate_evidence(
            _bundle(
                {
                    "anchor_id": "conflict",
                    "path": "owner.py",
                    "line": 1,
                    "symbol": "second",
                }
            ),
            include_relationships=False,
        )
        after = codemap.task_action_map("Fix first")

    anchor = correlated["bundles"][0]["anchors"][0]
    assert anchor["resolution"]["state"] == "claim-conflict"
    assert before["ownership_authority"] == after["ownership_authority"]


def test_correlation_delta_rejects_foreign_repository_packet(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    for repo in (left, right):
        (repo / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")

    with CodeMap(left) as codemap:
        codemap.sync()
        before = codemap.correlate_evidence(
            _bundle({"anchor_id": "member", "path": "owner.py"}),
            include_relationships=False,
        )
    with CodeMap(right) as codemap:
        codemap.sync()
        after = codemap.correlate_evidence(
            _bundle({"anchor_id": "member", "path": "owner.py"}),
            include_relationships=False,
        )
        with pytest.raises(ValueError, match="before correlation repository-mismatch"):
            codemap.evidence_correlation_delta(before, after)


def test_previous_correlation_from_foreign_repository_fails_closed(
    tmp_path: Path,
) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    for repo in (left, right):
        (repo / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")

    with CodeMap(left) as codemap:
        codemap.sync()
        previous = codemap.correlate_evidence(
            _bundle({"anchor_id": "member", "path": "owner.py"}),
            include_relationships=False,
        )
    with CodeMap(right) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="before correlation repository-mismatch"):
            codemap.correlate_evidence(
                _bundle({"anchor_id": "member", "path": "owner.py"}),
                include_relationships=False,
                previous_correlation=previous,
            )

def test_correlation_delta_rejects_nested_repository_evidence_tampering(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.correlate_evidence(
            _bundle({"anchor_id": "member", "path": "owner.py"}),
            include_relationships=False,
        )
        tampered = json.loads(json.dumps(packet))
        tampered["repository_evidence"]["bindings"][0]["binding_id"] = (
            "repository-evidence:forged"
        )
        tampered["correlation_identity"] = "sha256:" + codemap._packet_digest(
            "hashmarks.evidence-correlation.v1",
            {
                key: value
                for key, value in tampered.items()
                if key not in {"correlation_identity", "delta_from_previous"}
            },
        )

        with pytest.raises(ValueError, match="bindings identity mismatch"):
            codemap.evidence_correlation_delta(tampered, packet)

def test_correlation_definition_identity_is_bundle_order_invariant(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text("A = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("B = 1\n", encoding="utf-8")
    first = _bundle({"anchor_id": "a", "path": "a.py"})[0]
    second = _bundle({"anchor_id": "b", "path": "b.py"})[0]
    second["bundle_id"] = "observation:2"

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        forward = codemap.correlate_evidence(
            [first, second], include_relationships=False
        )
        reverse = codemap.correlate_evidence(
            [second, first], include_relationships=False
        )

    assert (
        forward["evidence_definition_identity"]
        == reverse["evidence_definition_identity"]
    )


def test_incomplete_correlation_never_admits_negative_evidence(tmp_path: Path) -> None:
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.correlate_evidence(
            _bundle(
                {"anchor_id": "missing", "path": "missing.py"},
                completeness="incomplete",
            ),
            include_relationships=False,
        )

    assert packet["completeness"]["state"] == "unknown"
    assert packet["completeness"]["negative_evidence"] == "not-admissible"

