"""Admission checks for explicit native specimens; no capability rating oracle."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hashmarks.digest import FILE_DOMAIN, hash_file
from scripts.repository_evaluation.backend_native import (
    SCOPE,
    _native_definition,
    validate_capture,
)
from scripts.repository_evaluation.common import write_json


@pytest.fixture
def specimen(tmp_path: Path):
    source, capture = tmp_path / "source", tmp_path / "capture"
    source.mkdir()
    capture.mkdir()
    raw = b"def handle():\n    return 1\n"
    (source / "backend.py").write_bytes(raw)
    (capture / "backend.py").write_bytes(raw)
    (capture / "index.scip").write_bytes(b"controlled binary fixture")
    write_json(capture / "index.json", {"documents": []})
    (capture / "environment.json").write_text("[]\n")
    configuration = {
        "producer": "controlled-fixture",
        "configuration": {"environment.json": "[]\n"},
    }
    revisions = {
        "backend.py": hash_file(source / "backend.py", domain=FILE_DOMAIN).hash
    }
    definition = {"repository": "controlled-fixture", "commit": "fixture"}
    write_json(
        capture / "backend-binding.json",
        {
            "workflow": "handler",
            "stage": "before",
            "source": definition,
            "paths": ["backend.py"],
            "scope": SCOPE,
        },
    )
    write_json(
        capture / "capture.json",
        {
            "configuration": configuration,
            "source_revisions": revisions,
            "binary_sha256": hashlib.sha256(
                (capture / "index.scip").read_bytes()
            ).hexdigest(),
            "json_sha256": hashlib.sha256(
                (capture / "index.json").read_bytes()
            ).hexdigest(),
        },
    )
    write_json(
        capture / "provenance.json",
        {
            "source_revisions": revisions,
            "configuration_identity": "sha256:"
            + hashlib.sha256(
                json.dumps(configuration, sort_keys=True).encode()
            ).hexdigest(),
            "collection_state": "fresh-complete",
        },
    )
    return capture, source, definition


def test_native_specimen_admission_preserves_exact_source_revision(specimen):
    capture, source, definition = specimen
    provenance = validate_capture(
        capture, source, workflow_id="handler", stage="before", definition=definition
    )
    assert (
        provenance["source_revisions"]["backend.py"]
        == hash_file(source / "backend.py", domain=FILE_DOMAIN).hash
    )


@pytest.mark.parametrize(
    "changed", ["backend.py", "index.json", "index.scip", "environment.json"]
)
def test_mutated_native_specimen_is_rejected_before_import(specimen, changed: str):
    capture, source, definition = specimen
    (capture / changed).write_bytes((capture / changed).read_bytes() + b"changed")
    with pytest.raises(ValueError, match="differs"):
        validate_capture(
            capture,
            source,
            workflow_id="handler",
            stage="before",
            definition=definition,
        )


@pytest.mark.parametrize(
    "key,value",
    [
        ("stage", "after"),
        ("scope", "whole-repository"),
        ("paths", ["backend.py", "backend.py"]),
    ],
)
def test_native_scope_or_revision_identity_cannot_be_reinterpreted(
    specimen, key, value
):
    capture, source, definition = specimen
    binding = json.loads((capture / "backend-binding.json").read_text())
    binding[key] = value
    write_json(capture / "backend-binding.json", binding)
    with pytest.raises(ValueError, match="scope binding"):
        validate_capture(
            capture,
            source,
            workflow_id="handler",
            stage="before",
            definition=definition,
        )


@pytest.mark.parametrize(
    "role,location,symbols,unique",
    [
        (1, [0, 4, 10], ["opaque-first"], True),
        (8, [0, 4, 10], ["opaque-first"], False),
        (1, [1, 4, 10], ["opaque-first"], False),
        (1, [0, 0, 6], ["opaque-first"], False),
        (1, [0, 4, 10], ["opaque-first", "opaque-competing"], False),
    ],
)
def test_native_definition_token_preserves_location_and_identity_ambiguity(
    specimen, role, location, symbols, unique
):
    capture, _source, _definition = specimen
    write_json(
        capture / "index.json",
        {
            "documents": [
                {
                    "relative_path": "backend.py",
                    "occurrences": [
                        {"symbol_roles": role, "range": location, "symbol": symbol}
                        for symbol in symbols
                    ],
                }
            ]
        },
    )
    observed = _native_definition(
        capture, {"path": "backend.py", "symbol": "handle", "start_line": 1}
    )
    assert observed["unique_definition_token"] is unique


def test_deleted_native_subject_is_rejected_without_semantic_absence(
    tmp_path: Path,
) -> None:
    from hashmarks.codemap import CodeMap
    from scripts.repository_evaluation.backend_native import _stale_native_observation

    root = tmp_path / "repo"
    root.mkdir()
    with CodeMap(root, state_dir=tmp_path / "state") as codemap:
        packet, invalidated = _stale_native_observation(
            codemap, {"path": "removed.py", "symbol": "Model"}
        )
    assert invalidated is True
    assert packet["status"] == "rejected"
    assert packet["target"] == "removed.py::Model"
    assert packet["negative_evidence_admissible"] is False


def test_present_ambiguous_native_subject_does_not_pass_invalidation(
    tmp_path: Path,
) -> None:
    from hashmarks.codemap import CodeMap
    from scripts.repository_evaluation.backend_native import _stale_native_observation

    (tmp_path / "models.py").write_text(
        "def first():\n    class Model: pass\ndef second():\n    class Model: pass\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        with pytest.raises(KeyError):
            _stale_native_observation(codemap, {"path": "models.py", "symbol": "Model"})
