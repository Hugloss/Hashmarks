"""Regression coverage for direct SCIP semantic evidence on existing CodeMap."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.structural_locality import structural_locality_delta
from hashmarks.evidence_presentation import (
    present_repository_evidence,
    presentation_response,
)

_BASE = "scip-python python demo 0.1.0 `code`/Base#"
_IMPL = "scip-python python demo 0.1.0 `code`/Impl#"


def _repository(root: Path) -> None:
    (root / "code.py").write_text(
        "class Base:\n    pass\n\nclass Impl(Base):\n    pass\n",
        encoding="utf-8",
    )


def _scip(root: Path, relations: list[dict[str, object]]) -> Path:
    path = root.parent / f"{root.name}-index.json"
    path.write_text(
        json.dumps(
            {
                "metadata": {"toolInfo": {"name": "scip-python", "version": "test"}},
                "documents": [
                    {
                        "relativePath": "code.py",
                        "symbols": [
                            {"symbol": _BASE},
                            {"symbol": _IMPL, "relationships": relations},
                        ],
                        "occurrences": [
                            {
                                "range": [0, 5, 9],
                                "symbol": _BASE,
                                "symbolRoles": 1,
                            },
                            {
                                "range": [3, 6, 10],
                                "symbol": _IMPL,
                                "symbolRoles": 1,
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _relations(codemap: CodeMap) -> dict[str, object]:
    packet = codemap.structural_locality("code.py::Impl", refresh=False)
    return packet["native_semantic_relationships"]


def test_scip_relationship_flags_are_direct_and_provenance_bound(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    index = _scip(
        tmp_path,
        [
            {"symbol": _BASE, "isImplementation": True},
            {"symbol": _BASE, "isImplementation": True},
            {
                "symbol": _BASE,
                "is_reference": True,
                "is_type_definition": True,
            },
            {"symbol": "untrusted", "isImplementation": "true"},
        ],
    )
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as cm:
        cm.sync()
        cm.import_scip(index)
        packet = cm.structural_locality("code.py::Impl", refresh=False)
        relations = packet["native_semantic_relationships"]
        assert relations["authority"] == "scip-producer-claim-only"
        assert relations["producer_bindings"] == ["scip-python:test"]
        assert relations["negative_evidence_admissible"] is False
        assert relations["truncated"] is False
        assert relations["observation_coverage"]["state"] == (
            "current-bounded-observation"
        )
        assert (
            relations["observation_coverage"]["negative_evidence_admissible"] is False
        )
        capability = relations["provider_capabilities"][0]
        assert capability["declared_capability_state"] == (
            "not-captured-by-scip-adapter"
        )
        assert capability["observed_relationship_kinds_for_scope"] == [
            "implementation",
            "reference",
            "type_definition",
        ]
        source_revision = relations["source_revision"]
        assert source_revision["observed_at_import"] == [
            source_revision["observed_current"]
        ]
        assert source_revision["producer_claimed_revision"] is None
        assert source_revision["same_as_current_observation"] is True
        assert source_revision["binding_state"] == "unknown"
        assert {
            (row["kind"], row["target_symbol"]) for row in relations["relationships"]
        } == {
            ("implementation", _BASE),
            ("reference", _BASE),
            ("type_definition", _BASE),
        }
        assert all(row["path"] == "code.py" for row in relations["relationships"])
        assert all(row["line"] == 4 for row in relations["relationships"])
        assert all(
            row["source_identity"] == packet["source_identity"]
            for row in relations["relationships"]
        )
        implementation = next(
            row for row in relations["relationships"] if row["kind"] == "implementation"
        )
        assert implementation["source_revision"]["producer_claimed_revision"] is None
        assert implementation["source_revision"]["same_as_current_observation"] is True
        resolution = next(
            row
            for row in relations["target_resolutions"]
            if row["producer"] == "scip-python:test" and row["target_symbol"] == _BASE
        )
        assert resolution["state"] == "unique-candidate"
        assert resolution["candidates"][0]["code_map_symbol_ids"] == ["code.py::Base"]
        # SCIP implements-claims do not turn into proven call edges.
        assert not any(row.get("target_text") == _BASE for row in packet["edges"])

        (tmp_path / "code.py").write_text(
            "class Base:\n    pass\n\nclass Impl(Base):\n    pass\n\n# changed\n",
            encoding="utf-8",
        )
        cm.sync(["code.py"])
        stale = cm.structural_locality("code.py::Impl", refresh=False)
        stale_relations = stale["native_semantic_relationships"]
        assert stale_relations["producer_bindings"] == []
        assert stale_relations["relationships"] == []
        assert stale_relations["observation_coverage"]["state"] == (
            "stale-provider-observation"
        )
        assert stale_relations["provider_capabilities"][0]["freshness"] == "stale"


def test_scip_relationship_truncation_and_reimport_replacement(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    index = _scip(
        tmp_path,
        [{"symbol": f"index-symbol-{i}", "isImplementation": True} for i in range(65)],
    )
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as cm:
        cm.sync()
        cm.import_scip(index)
        observed = _relations(cm)
        assert observed["truncated"] is True
        assert len(observed["relationships"]) == 64
        assert observed["negative_evidence_admissible"] is False

        _scip(tmp_path, [])
        cm.import_scip(index)
        replacement = _relations(cm)
        assert replacement["truncated"] is False
        assert replacement["relationships"] == []
        assert replacement["producer_bindings"] == ["scip-python:test"]
        assert replacement["negative_evidence_admissible"] is False


def test_scip_relationship_target_reports_ambiguous_candidates(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    (tmp_path / "other.py").write_text("class Base:\n    pass\n", encoding="utf-8")
    index = _scip(tmp_path, [{"symbol": _BASE, "isImplementation": True}])
    value = json.loads(index.read_text(encoding="utf-8"))
    value["documents"].append(
        {
            "relativePath": "other.py",
            "symbols": [{"symbol": _BASE}],
            "occurrences": [{"range": [0, 5, 9], "symbol": _BASE, "symbolRoles": 1}],
        }
    )
    index.write_text(json.dumps(value), encoding="utf-8")
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as cm:
        cm.sync()
        cm.import_scip(index)
        packet = cm.structural_locality("code.py::Impl")
    resolution = packet["native_semantic_relationships"]["target_resolutions"][0]
    assert resolution["state"] == "ambiguous-candidates"
    assert {
        symbol_id
        for candidate in resolution["candidates"]
        for symbol_id in candidate["code_map_symbol_ids"]
    } == {"code.py::Base", "other.py::Base"}
    assert resolution["negative_evidence_admissible"] is False


def test_scip_relationship_packet_explains_missing_provider_observation(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as cm:
        cm.sync()
        packet = cm.structural_locality("code.py::Impl")
    relations = packet["native_semantic_relationships"]
    assert relations["observation_coverage"]["state"] == "no-provider-observation"
    assert relations["provider_capabilities"] == []
    assert relations["relationships"] == []
    assert relations["negative_evidence_admissible"] is False


def test_scip_relationship_publication_rolls_back_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repository(tmp_path)
    index = _scip(tmp_path, [{"symbol": _BASE, "isImplementation": True}])
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as cm:
        cm.sync()
        cm.import_scip(index)
        before = _relations(cm)
        _scip(tmp_path, [{"symbol": _BASE, "isDefinition": True}])

        def fail_snapshot(*args: object, **kwargs: object) -> None:
            raise RuntimeError("snapshot failure")

        monkeypatch.setattr(cm, "_record_evidence_snapshot", fail_snapshot)
        with pytest.raises(RuntimeError, match="snapshot failure"):
            cm.import_scip(index)
        assert _relations(cm) == before


def test_scip_relation_claim_delta_requires_same_untruncated_producer(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    index = _scip(tmp_path, [{"symbol": _BASE, "isImplementation": True}])
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as cm:
        cm.sync()
        cm.import_scip(index)
        before = cm.structural_locality("code.py::Impl")

        (tmp_path / "code.py").write_text(
            "class Base:\n    pass\n\nclass Impl(Base):\n    pass\n\n# revision\n",
            encoding="utf-8",
        )
        cm.sync(["code.py"])
        _scip(tmp_path, [{"symbol": _BASE, "isTypeDefinition": True}])
        cm.import_scip(index)
        after = cm.structural_locality("code.py::Impl")
        delta = structural_locality_delta(before, after)
        assert delta["native_relationships_comparable"] is True
        assert any(
            row[2] == "type_definition" for row in delta["native_relationships_added"]
        )
        assert any(
            row[2] == "implementation" for row in delta["native_relationships_removed"]
        )
        projection = present_repository_evidence(delta, format="structured")
        projected_relations = [
            row
            for group in projection["groups"]
            for row in group["findings"]
            if row["kind"]
            in {"scip_relationship_claim_added", "scip_relationship_claim_removed"}
        ]
        assert len(projected_relations) == 2
        assert all(row["assertion"] == "observed_change" for row in projected_relations)
        response = presentation_response(
            "evidence_comparison",
            delta,
            format="structured",
            result_mode="structural",
        )
        assert response["result"] == delta
        unprojected_refs = {
            row["source_ref"]
            for row in response["presentation"]["unprojected_sections"]
        }
        assert not unprojected_refs & {
            "/native_relationships_comparable",
            "/native_relationships_incomparability_reasons",
            "/native_relationships_added",
            "/native_relationships_removed",
        }

        incomplete = dict(after)
        incomplete["native_semantic_relationships"] = {
            **after["native_semantic_relationships"],
            "truncated": True,
        }
        # Recompute packet identity: malformed or incomplete endpoint may not
        # gain a qualified semantic absence claim via the delta projection.
        from hashmarks.codemap.structural_locality import _identity

        incomplete["evidence_identity"] = _identity(
            {k: v for k, v in incomplete.items() if k != "evidence_identity"}
        )
        unavailable = structural_locality_delta(before, incomplete)
        assert unavailable["native_relationships_comparable"] is False
        assert unavailable["native_relationships_removed"] == []


def test_scip_relationship_delta_requires_comparable_exact_endpoints(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    index = _scip(tmp_path, [{"symbol": _BASE, "isImplementation": True}])
    with CodeMap(tmp_path, artifact_db=tmp_path / "artifacts.sqlite3") as cm:
        cm.sync()
        cm.import_scip(index)
        before = cm.structural_locality("code.py::Impl")
        after = dict(before)
        after["target"] = "code.py::Base"
        after["repository_identity"] = "sha256:different-repository-observation"
        from hashmarks.codemap.structural_locality import _identity

        after["evidence_identity"] = _identity(
            {key: value for key, value in after.items() if key != "evidence_identity"}
        )
        delta = structural_locality_delta(before, after)
        assert delta["comparable"] is False
        assert delta["native_relationships_comparable"] is False
        assert (
            "structural-endpoints-incomparable"
            in (delta["native_relationships_incomparability_reasons"])
        )
        assert delta["native_relationships_added"] == []
        assert delta["native_relationships_removed"] == []
