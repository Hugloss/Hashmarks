"""Real-file corpus materialization and observable evidence assertions for tests."""

from __future__ import annotations

import json
import shutil
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from contract_assertions import (
    assert_array,
    assert_integer,
    assert_object,
    assert_records,
    assert_text,
)

from hashmarks.adapters import (
    maven_dependency_observation,
    uv_lock_dependency_observation,
)
from hashmarks.digest import FILE_DOMAIN, hash_bytes
from hashmarks.evidence_presentation import FORMATS, presentation_response
from hashmarks.evidence_presentation_conformance import validate_evidence_presentation

if TYPE_CHECKING:
    from hashmarks.codemap import CodeMap

CORPUS = Path(__file__).parent / "fixtures" / "dependency_dogfood"
SCIP_CORPUS = Path(__file__).parent / "fixtures" / "native_scip"
LSP_CORPUS = Path(__file__).parent / "fixtures" / "native_lsp"
TASK = "Change normalize_widget in src/engine.py to lowercase the trimmed value and verify its semantics."


def assert_literal_returned_counts(packet: Mapping[str, object]) -> None:
    """Every advertised returned count accounts for the emitted rows only."""
    rows = assert_records(packet["occurrences"])
    members = [
        row
        for row in assert_records(packet["member_observations"])
        if row["availability"] == "observed"
    ]
    by_path = Counter(assert_text(row["path"]) for row in rows)
    by_literal = Counter(assert_text(row["literal"]) for row in rows)
    assert sum(
        assert_integer(row["returned_occurrence_count"]) for row in members
    ) == len(rows)
    assert sum(
        assert_integer(row["returned_occurrence_count"])
        for row in assert_records(packet["literal_observations"])
    ) == len(rows)
    for row in members:
        assert row["returned_occurrence_count"] == by_path[assert_text(row["path"])]
    for row in assert_records(packet["literal_observations"]):
        assert (
            row["returned_occurrence_count"] == by_literal[assert_text(row["literal"])]
        )


def _replace_inputs(root: Path, source: Path, paths: list[str]) -> list[str]:
    """Replace exactly the previous fixture's files, preserving unrelated inputs."""
    ownership = root.parent / (root.name + ".fixture-inputs.json")
    if ownership.exists():
        for name in json.loads(ownership.read_text()):
            (root / name).unlink(missing_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    for name in paths:
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, destination)
    ownership.write_text(json.dumps(paths))
    return paths


def materialize_scip(root: Path, source: Path) -> None:
    paths = [
        path.relative_to(source).as_posix()
        for path in sorted((source / "src").rglob("*"))
        if path.is_file() and path.suffix in (".py", ".ts")
    ]
    for name in (
        "pyproject.toml",
        "pyrightconfig.json",
        "environment.json",
        "package.json",
        "tsconfig.json",
    ):
        if (source / name).exists():
            paths.append(name)
    _replace_inputs(root, source, paths)


def lsp_capture(root: Path, source: Path, name: str) -> dict[str, object]:
    """Rebase only fixture-owned file URIs; raw capture bytes remain untouched."""
    metadata = json.loads((source / "capture.json").read_text())
    original = metadata["original_root_uri"]
    owned = {
        original + "/" + path: (root / path).as_uri()
        for path in metadata["source_revisions"]
    }

    def rebase(value: object) -> object:
        if isinstance(value, str):
            return owned.get(value, value)
        if isinstance(value, list):
            return [rebase(item) for item in value]
        if isinstance(value, dict):
            return {key: rebase(item) for key, item in value.items()}
        return value

    row = next(
        row
        for row in json.loads((source / "captures.json").read_text())
        if row["name"] == name
    )
    return assert_object(rebase(row["capture"]))


def _lsp_document_event(
    source: Path,
    event: dict,
    owned: dict[str, str],
    documents: dict[str, dict],
    lifetimes: Counter[str],
) -> None:
    document = event["params"]["textDocument"]
    path = owned[document["uri"]]
    method = event["method"]
    if method == "textDocument/didOpen":
        assert document["text"] == (source / path).read_text(encoding="utf-8")
        lifetimes[path] += 1
        documents[path] = {
            "text": document["text"],
            "revision_kind": "utf8-document-text",
            "provenance": {
                "producer_session": "fixture-session",
                "document_lifetime": f"open-{lifetimes[path]}",
                "document_version": document["version"],
                "source_kind": "buffer",
                "binding_basis": "producer-snapshot",
            },
        }
    elif method == "textDocument/didChange":
        (change,) = event["params"]["contentChanges"]
        assert set(change) == {"text"}, "this corpus records full document changes"
        documents[path]["text"] = change["text"]
        documents[path]["provenance"]["document_version"] = document["version"]
    else:
        documents[path]["text"] = (source / path).read_text(encoding="utf-8")
        documents[path]["provenance"]["source_kind"] = "disk"


def assert_lsp_transcript(source: Path, metadata: dict, captures: list[dict]) -> None:
    """Bind each retained request, reply and snapshot to the raw protocol events."""
    owned = {
        metadata["original_root_uri"] + "/" + path: path
        for path in metadata["source_revisions"]
    }
    expected = {row["capture"]["request"]["id"]: row["capture"] for row in captures}
    assert len(expected) == len(captures)
    documents: dict[str, dict] = {}
    lifetimes: Counter[str] = Counter()
    requests, responses = set(), set()
    for entry in json.loads((source / "transcript.json").read_text()):
        if "sent" in entry:
            event = entry["sent"]
            method = event.get("method")
            if method in (
                "textDocument/didOpen",
                "textDocument/didChange",
                "textDocument/didClose",
            ):
                _lsp_document_event(source, event, owned, documents, lifetimes)
            elif method and event.get("id") in expected:
                capture = expected[event["id"]]
                assert capture["request"] == event
                assert capture["documents"] == documents
                requests.add(event["id"])
        else:
            event = entry["received"]
            if "method" not in event and event.get("id") in expected:
                assert expected[event["id"]]["response"] == event
                responses.add(event["id"])
    assert requests == responses == set(expected)


def import_native_scip(cm: CodeMap, source: Path) -> None:
    cm.native.import_scip(
        source / "index.json",
        provenance=json.loads((source / "provenance.json").read_text()),
    )


def materialize_dependency(root: Path, source: Path) -> list[str]:
    """Replace admitted inputs; captures remain outside the observed repository."""
    paths = [
        path.relative_to(source).as_posix()
        for path in sorted(source.rglob("*"))
        if path.name in {"pyproject.toml", "uv.lock", "pom.xml"}
    ]
    return _replace_inputs(root, source, paths)


def input_revisions(root: Path, paths: list[str]) -> list[dict[str, str]]:
    return [
        {
            "path": path,
            "member_revision": hash_bytes(
                (root / path).read_bytes(), domain=FILE_DOMAIN
            ).hash,
        }
        for path in paths
    ]


def dependency_capture(
    producer: str, source: Path, inputs: list[dict[str, str]]
) -> dict[str, object]:
    if producer == "uv":
        return uv_lock_dependency_observation(
            lock=(source / "uv.lock").read_bytes(), repository_inputs=inputs
        )
    return maven_dependency_observation(
        trees={"compile": (source / "tree.json").read_bytes()},
        inventories={"compile": (source / "list.txt").read_bytes()},
        complete_tree_contexts=("compile",),
        complete_inventory_contexts=("compile",),
        repository_inputs=inputs,
    )


def assert_projection(native: object, operation: str, mode: str = "default") -> None:
    """Check exact selected evidence and explicit exclusions across all encodings."""
    assert isinstance(native, dict)
    for format in FORMATS:
        response: dict[str, object] = presentation_response(
            operation, native, format=format, result_mode=mode
        )
        if format == "none":
            assert response == native
            continue
        assert response["result"] == native
        projected = assert_object(response["presentation"])
        assert projected["coverage"] == "projection-only"
        for group in assert_records(projected["groups"]):
            assert group["count_observed_in_packet"] == len(
                assert_array(group["findings"])
            ) + assert_integer(group["omitted_from_presentation"])
            for row in assert_records(group["findings"]):
                references = assert_array(row["source_refs"])
                assert len(references) == 1
                value: object = native
                for part in assert_text(references[0]).split("/")[1:]:
                    key = part.replace("~1", "/").replace("~0", "~")
                    value = (
                        value[int(key)]
                        if isinstance(value, list)
                        else assert_object(value)[key]
                    )
                assert row["details"] == value


def assert_hover_capture(
    packet: Mapping[str, object], capture: Mapping[str, object]
) -> dict[str, object]:
    """A genuine hover's exact text remains an attributed, non-relational claim."""
    row = next(
        row
        for row in assert_records(packet["observations"])
        if row["producer"] == capture["producer"]
    )
    result = assert_object(capture["response"])["result"]
    hover = None if result is None else assert_object(result)
    capability = assert_object(row["capability"])
    assert capability["hover_observation"] == {
        "state": "no-hover-returned" if result is None else "hover-returned",
        "contents": None if hover is None else hover["contents"],
        "range": None if hover is None else hover.get("range"),
        "authority": "caller-supplied-producer-claim",
        "semantic_correspondence": "not-established",
        "negative_evidence_admissible": False,
    }
    assert capability["observed_operation"] == "textDocument/hover"
    assert capability["authority"] == "producer-claimed"
    assert row["claims"] == []
    assert (
        assert_object(row["accounting"])["received"]
        == assert_object(row["accounting"])["retained"]
        == 0
    )
    assert row["negative_evidence_admissible"] is False
    assert packet["negative_evidence_admissible"] is False
    return row


def assert_hover_presentation(
    packet: Mapping[str, object],
    presentation: Mapping[str, object],
    capture: Mapping[str, object],
) -> None:
    """Check the transported context, including its independent qualifications."""
    row = assert_hover_capture(packet, capture)
    assert validate_evidence_presentation(packet, presentation)["valid"] is True
    details = [
        assert_object(context["details"])
        for context in assert_records(presentation["source_context"])
    ]
    (context,) = [
        assert_object(item["relationship_observation"])
        for item in details
        if assert_object(item.get("relationship_observation", {})).get("producer")
        == capture["producer"]
    ]
    for field in ("capability", "freshness", "scope", "capture_identity"):
        assert context[field] == row[field]
    if presentation["format"] == "text":
        contents = json.dumps(
            assert_object(assert_object(row["capability"])["hover_observation"])[
                "contents"
            ],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        assert contents in assert_text(presentation["text"])


def semantic_dependency_fields(observation: dict[str, object]) -> dict[str, object]:
    return {
        key: observation[key]
        for key in (
            "definition_identity",
            "resolution_identity",
            "components",
            "selections",
            "inventory",
            "relationships",
            "coverage",
            "repository_inputs",
        )
    }
