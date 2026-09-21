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
            "anchors": list(anchors),
        }
    ]


def test_evidence_correlation_extension_preserves_repository_coverage_owner(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text("VALUE = 1\n", encoding="utf-8")
    binding = [
        {
            "binding_id": "coverage-owner",
            "evidence": [
                {"path": "owner.py", "start_line": 1, "end_line": 1}
            ],
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
        "def process_output_data(value: int) -> int:\n"
        "    return value + 1\n",
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
            path_mappings=[
                {"external_prefix": "/app", "repository_prefix": ""}
            ],
        )

    anchor = packet["bundles"][0]["anchors"][0]
    assert packet["schema"] == "hashmarks.evidence-correlation.v1"
    assert packet["authority"] == "repository-intelligence-only"
    assert packet["interpretation_authority"] == "consumer-owned"
    assert packet["causation"] == "not-inferred"
    assert packet["storage"] == "request-scoped-not-persisted"
    assert anchor["resolution"]["state"] == "resolved-unique"
    assert anchor["resolution"]["repository_path"] == "src/worker.py"
    assert (
        anchor["resolution"]["symbol"]["qualname"]
        == "process_output_data"
    )
    assert anchor["source_equivalence"]["state"] == "unknown"


def test_opaque_commit_like_metadata_never_proves_repository_source_identity(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text(
        "VALUE = 1\n", encoding="utf-8"
    )
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
    (tmp_path / "owner.py").write_text(
        "VALUE = 1\n", encoding="utf-8"
    )
    base = _bundle({"anchor_id": "member", "path": "owner.py"})
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        observed = codemap.correlate_evidence(
            base, include_relationships=False
        )
        revision = observed["bundles"][0]["anchors"][0][
            "repository_evidence"
        ]["evidence"][0]["member_revision"]
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

    assert proven["bundles"][0]["anchors"][0][
        "source_equivalence"
    ]["state"] == "proven"
    assert mismatch["bundles"][0]["anchors"][0][
        "source_equivalence"
    ]["state"] == "mismatch"


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
        "def first():\n"
        "    return 1\n"
        "\n"
        "def second():\n"
        "    return 2\n",
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
    assert (
        resolution["reason"]
        == "symbol-does-not-contain-claimed-line"
    )


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
            path_mappings=[
                {"external_prefix": "/app", "repository_prefix": ""}
            ],
            include_relationships=False,
        )

    anchor = packet["bundles"][0]["anchors"][0]
    assert anchor["resolution"]["state"] == "unresolved"
    assert anchor["resolution"]["repository_path"] == "src/missing.py"
    assert anchor["repository_evidence"]["evidence"][0]["state"] == "known-absent"


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
            "anchors": [{"anchor_id": "b:0", "path": "b.py"}],
        },
        {
            "bundle_id": "a",
            "producer": {},
            "completeness": "complete",
            "anchors": [{"anchor_id": "a:0", "path": "a.py"}],
        },
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        first = codemap.correlate_evidence(
            left, include_relationships=False
        )
        second = codemap.correlate_evidence(
            list(reversed(left)), include_relationships=False
        )

    assert first == second
    assert [row["bundle_id"] for row in first["bundles"]] == ["a", "b"]


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
    (tmp_path / "owner.py").write_text(
        "VALUE = 1\n", encoding="utf-8"
    )
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
    assert (
        anchor["resolution"]["reason"]
        == "external-path-mapping-required"
    )
    assert anchor["repository_evidence"]["evidence"] == []


def test_external_paths_and_mapping_prefixes_fail_closed_on_escape(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text(
        "VALUE = 1\n", encoding="utf-8"
    )
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
    (tmp_path / "owner.py").write_text(
        "VALUE = 1\n", encoding="utf-8"
    )
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
    }


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
        before = codemap.correlate_evidence(
            evidence, include_relationships=False
        )
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
    changed = delta["repository_evidence_delta"]["bindings"][
        "changed"
    ][0]
    assert changed["direct_evidence"]["state"] == "changed"
    assert changed["direct_evidence"]["changes"][0]["scope"] == "member"
    assert delta["causation"] == "not-inferred"
    assert delta["interpretation_authority"] == "consumer-owned"


def test_correlation_request_reuses_binding_total_bound(
    tmp_path: Path,
) -> None:
    (tmp_path / "owner.py").write_text(
        "VALUE = 1\n", encoding="utf-8"
    )
    anchors = [
        {"anchor_id": f"a:{index}", "path": "owner.py"}
        for index in range(257)
    ]
    bundles = [
        {
            "bundle_id": "too-many",
            "producer": {},
            "completeness": "complete",
            "anchors": anchors[:256],
        },
        {
            "bundle_id": "one-more",
            "producer": {},
            "completeness": "complete",
            "anchors": anchors[256:],
        },
    ]
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(ValueError, match="256 total anchors"):
            codemap.correlate_evidence(
                bundles, include_relationships=False
            )


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

    owned, external = packet["bundles"][0]["anchors"]
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
        "def process_output_data(value: int) -> int:\n"
        "    return value + 1\n",
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
        packet = codemap.correlate_evidence(
            _bundle(*anchors),
            include_relationships=True,
        )

    emitted = packet["bundles"][0]["anchors"]
    assert len(packet["repository_evidence"]["bindings"]) == 1
    assert len(
        {row["repository_evidence_binding_id"] for row in emitted}
    ) == 1
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
