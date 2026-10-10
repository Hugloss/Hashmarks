"""SCIP symbol metadata survives native storage and stays producer-owned."""

from __future__ import annotations

import json
from pathlib import Path

from hashmarks.codemap import CodeMap
from hashmarks.codemap.semantic_relationship_model import (
    validate_relationship_observation,
)

_BASE = "scip-python python demo 0.1.0 `code`/Base#"
_IMPL = "scip-python python demo 0.1.0 `code`/Impl#"


def _write_index(root: Path) -> Path:
    index = root.parent / f"{root.name}-metadata.scip.json"
    index.write_text(
        json.dumps(
            {
                "metadata": {"toolInfo": {"name": "scip-python", "version": "test"}},
                "documents": [
                    {
                        "relativePath": "code.py",
                        "symbols": [
                            {"symbol": _BASE},
                            {
                                "symbol": _IMPL,
                                "displayName": "Impl",
                                "documentation": ["Implementation documentation"],
                                "relationships": [
                                    {"symbol": _BASE, "isImplementation": True}
                                ],
                            },
                        ],
                        "occurrences": [
                            {
                                "range": [0, 6, 10],
                                "symbol": _BASE,
                                "symbolRoles": 1,
                            },
                            {
                                "range": [3, 6, 10],
                                "symbol": _IMPL,
                                "symbolRoles": 1 | 8,
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return index


def _read_source_metadata(cm: CodeMap) -> dict:
    packet = cm.structural_locality(
        "code.py::Impl", result_mode="relationships", refresh=False
    )
    validate_relationship_observation(packet)
    claims = [
        claim
        for producer in packet["observations"]
        for claim in producer["claims"]
        if claim["kind"] == "implementation"
    ]
    assert len(claims) == 1
    return claims[0]["source"]


def test_metadata_survives_native_index_reopen_and_is_not_graph_authority(
    tmp_path: Path,
) -> None:
    (tmp_path / "code.py").write_text(
        "class Base:\n    pass\n\nclass Impl(Base):\n    pass\n",
        encoding="utf-8",
    )
    path = _write_index(tmp_path)
    database = tmp_path / "native.sqlite3"
    with CodeMap(tmp_path, artifact_db=database) as cm:
        cm.sync()
        cm.import_scip(path)
        original = _read_source_metadata(cm)
    with CodeMap(tmp_path, artifact_db=database) as cm:
        cm.sync()
        reopened = _read_source_metadata(cm)
    assert reopened == original
    assert original["declaration"]["documentation"] == ["Implementation documentation"]
    assert original["declaration"]["authority"] == "scip-producer-supplied"
    assert original["occurrence_roles"]["observed_roles"] == [
        "definition",
        "read_access",
    ]
    assert original["occurrence_roles"]["negative_evidence_admissible"] is False
    assert original["resolution"]["state"] in {
        "unique-candidate",
        "unresolved",
    }
