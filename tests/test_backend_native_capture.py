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
    _transport,
    capture_artifact_digests,
    prepare_capture,
    validate_capture,
)
from scripts.repository_evaluation.common import write_json


def test_stage_specimen_preserves_unchanged_files_outside_new_capture(tmp_path):
    from scripts.repository_evaluation.backend_native import _replace_specimens

    before, after, workspace = (
        tmp_path / name for name in ("before", "after", "workspace")
    )
    before.mkdir()
    after.mkdir()
    for root in (before, after):
        (root / "existing.py").write_text("class Existing: pass\n")
    (before / "removed.py").write_text("class Removed: pass\n")
    (after / "added.py").write_text("class Added: pass\n")
    paths = {"existing.py", "removed.py", "added.py"}
    _replace_specimens(workspace, before, paths)
    _replace_specimens(workspace, after, paths)
    assert (workspace / "existing.py").read_bytes() == (
        before / "existing.py"
    ).read_bytes()
    assert (workspace / "added.py").is_file()
    assert not (workspace / "removed.py").exists()


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


@pytest.mark.parametrize("language,suffix", [("python", ".py"), ("typescript", ".ts")])
def test_capture_preparation_preserves_all_sources_without_inventing_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, language: str, suffix: str
):
    from scripts import native_evidence_capture

    source, destination = tmp_path / "source", tmp_path / "capture"
    source.mkdir()
    paths = ["model" + suffix, "provider" + suffix]
    for path in paths:
        (source / path).write_text("# explicitly admitted fixture\n")
    observed = {}

    def capture(root, _destination, selected_language):
        observed["language"] = selected_language
        observed["sources"] = {path: (root / path).read_bytes() for path in paths}

    monkeypatch.setattr(native_evidence_capture, "capture_scip", capture)
    prepare_capture(
        {"id": "annotation-only"},
        {
            "source_labels": {"before": [{"path": path} for path in paths]},
            "checks": [{"id": "source-owner-visible", "value": paths[0]}],
            "verification_oracle_state": "unknown-no-reviewed-direct-test",
        },
        "before",
        source,
        {"repository": "controlled-fixture"},
        destination,
    )
    assert observed["language"] == language
    assert observed["sources"] == {path: (source / path).read_bytes() for path in paths}
    binding = json.loads((destination / "backend-binding.json").read_text())
    assert binding["paths"] == paths
    assert binding["scope"] == SCOPE


def test_native_missing_formats_preserve_known_failure():
    assert (
        _transport([], {"path": "backend.py", "symbol": "handle"}, "revision") is None
    )
    assert (
        _transport(
            [
                {
                    "format": "none",
                    "response": {"target": "backend.py::handle", "observations": []},
                }
            ],
            {"path": "backend.py", "symbol": "handle"},
            "revision",
        )
        is False
    )


def test_native_artifact_scope_does_not_expand_into_tool_caches(specimen):
    capture, _source, _definition = specimen
    extra = capture / "node_modules/ignored.py"
    extra.parent.mkdir()
    extra.write_text("not an admitted producer input\n")
    digests = capture_artifact_digests(capture)
    assert "backend.py" in digests
    assert "index.scip" in digests
    assert not any(name.startswith("node_modules/") for name in digests)


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
