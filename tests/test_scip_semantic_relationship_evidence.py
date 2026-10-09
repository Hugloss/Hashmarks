"""Regression coverage for direct SCIP semantic evidence on existing CodeMap."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.codemap.structural_locality import structural_locality_delta


_BASE = "scip-python python demo 0.1.0 `code`/Base#"
_IMPL = "scip-python python demo 0.1.0 `code`/Impl#"


def _repository(root: Path) -> None:
    (root / "code.py").write_text(
        "class Base:\n    pass\n\nclass Impl(Base):\n    pass\n",
        encoding="utf-8",
    )


def _scip(root: Path, relations: list[dict[str, object]]) -> Path:
    path = root / "index.json"
    path.write_text(
        json.dumps(
            {
                "metadata": {"toolInfo": {"name": "scip-python", "version": "test"}},
                "documents": [
                    {
                        "relativePath": "code.py",
                        "symbols": [
                            {"symbol": _IMPL, "relationships": relations}
                        ],
                        "occurrences": [
                            {
                                "range": [3, 6, 10],
                                "symbol": _IMPL,
                                "symbolRoles": 1,
                            }
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
        assert {
            (row["kind"], row["target_symbol"])
            for row in relations["relationships"]
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
        # SCIP implements-claims do not turn into proven call edges.
        assert not any(
            row.get("target_text") == _BASE for row in packet["edges"]
        )

        (tmp_path / "code.py").write_text(
            "class Base:\n    pass\n\nclass Impl(Base):\n    pass\n\n# changed\n",
            encoding="utf-8",
        )
        cm.sync(["code.py"])
        stale = cm.structural_locality("code.py::Impl", refresh=False)
        assert "native_semantic_relationships" not in stale


def test_scip_relationship_truncation_and_reimport_replacement(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    index = _scip(
        tmp_path,
        [
            {"symbol": f"index-symbol-{i}", "isImplementation": True}
            for i in range(65)
        ],
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
        before = cm.structural_locality("code.py::Impl", refresh=False)

        (tmp_path / "code.py").write_text(
            "class Base:\n    pass\n\nclass Impl(Base):\n    pass\n\n# revision\n",
            encoding="utf-8",
        )
        cm.sync(["code.py"])
        _scip(tmp_path, [{"symbol": _BASE, "isTypeDefinition": True}])
        cm.import_scip(index)
        after = cm.structural_locality("code.py::Impl", refresh=False)
        delta = structural_locality_delta(before, after)
        assert delta["native_relationships_comparable"] is True
        assert any(
            row[2] == "type_definition" for row in delta["native_relationships_added"]
        )
        assert any(
            row[2] == "implementation" for row in delta["native_relationships_removed"]
        )

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
