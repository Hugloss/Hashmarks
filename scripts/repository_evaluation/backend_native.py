"""Explicit-target SCIP qualification, separate from answer-blind task retrieval.

These specimens deliberately nominate source files. They prove producer binding,
revision invalidation and transport preservation only; they cannot establish
owner recall, verifier recall, initial sufficiency or whole-repository coverage.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from hashmarks.codemap import CodeMap
from hashmarks.digest import FILE_DOMAIN, hash_file
from hashmarks.evidence_presentation import FORMATS
from hashmarks.evidence_presentation_conformance import validate_evidence_presentation

from .backend_corpus import confined_file
from .backend_transport import capture_cli, capture_mcp
from .common import canonical_sha256, write_json

SCOPE = (
    "explicit selected genuine source files; other repository and external "
    "implementation coverage unobserved"
)


@dataclass(frozen=True)
class NativeSpecimenOptions:
    capture_root: Path
    transports: tuple[str, ...] = ("cli", "mcp")
    regenerated: bool = False


def prepare_capture(
    workflow: dict[str, Any],
    rule: dict[str, Any],
    stage: str,
    source: Path,
    definition: dict[str, Any],
    destination: Path,
) -> None:
    """Invoke the existing opt-in producer capture on explicit QA specimens."""
    from scripts.native_evidence_capture import capture_scip

    label = rule["source_labels"][stage][0]
    checks = rule.get(stage, rule)["checks"]
    verifier = next(
        row["value"] for row in checks if row["id"] == "existing-verifier-visible"
    )
    paths = sorted({label["path"], verifier})
    with tempfile.TemporaryDirectory(prefix="hashmarks-native-input-") as scratch:
        root = Path(scratch)
        for relative in paths:
            admitted = confined_file(source, relative)
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(admitted, target)
        (root / "environment.json").write_text("[]\n", encoding="utf-8")
        write_json(root / "pyrightconfig.json", {"include": paths, "exclude": []})
        capture_scip(root, destination, "python")
    write_json(
        destination / "backend-binding.json",
        {
            "workflow": workflow["id"],
            "stage": stage,
            "source": definition,
            "paths": paths,
            "scope": SCOPE,
        },
    )


def validate_capture(
    capture: Path,
    source: Path,
    *,
    workflow_id: str,
    stage: str,
    definition: dict[str, Any],
) -> dict[str, Any]:
    """Recompute bytes, scope and configuration before importing any evidence."""
    binding = json.loads(confined_file(capture, "backend-binding.json").read_text())
    metadata = json.loads(confined_file(capture, "capture.json").read_text())
    provenance = json.loads(confined_file(capture, "provenance.json").read_text())
    expected_binding = {
        "workflow": workflow_id,
        "stage": stage,
        "source": definition,
        "scope": SCOPE,
    }
    if (
        any(binding.get(key) != value for key, value in expected_binding.items())
        or not binding["paths"]
        or len(set(binding["paths"])) != len(binding["paths"])
        or set(binding["paths"]) != set(metadata["source_revisions"])
        or metadata["source_revisions"] != provenance["source_revisions"]
    ):
        raise ValueError("backend native capture source/scope binding differs")
    for relative, expected in metadata["source_revisions"].items():
        specimen = confined_file(capture, relative)
        admitted = confined_file(source, relative)
        if (
            specimen.read_bytes() != admitted.read_bytes()
            or hash_file(specimen, domain=FILE_DOMAIN).hash != expected
        ):
            raise ValueError(f"backend native source revision differs: {relative}")
    for name, key in (("index.scip", "binary_sha256"), ("index.json", "json_sha256")):
        if (
            hashlib.sha256(confined_file(capture, name).read_bytes()).hexdigest()
            != metadata[key]
        ):
            raise ValueError(f"backend native capture content differs: {name}")
    _validate_configuration(capture, metadata["configuration"], provenance)
    return provenance


def _validate_configuration(
    capture: Path, configuration: dict[str, Any], provenance: dict[str, Any]
) -> None:
    identity = (
        "sha256:"
        + hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
    )
    if identity != provenance["configuration_identity"]:
        raise ValueError("backend native configuration identity differs")
    for name, content in configuration["configuration"].items():
        if confined_file(capture, name).read_text() != content:
            raise ValueError("backend native capture configuration differs")


def _replace_specimens(
    workspace: Path, capture: Path, provenance: dict[str, Any]
) -> None:
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir()
    for relative in provenance["source_revisions"]:
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(confined_file(capture, relative), target)


def _current(packet: dict[str, Any], label: dict[str, Any], revision: str) -> bool:
    rows = packet["observations"]
    target = label["path"] + "::" + label["symbol"]
    return (
        packet["target"] == target
        and bool(rows)
        and all(
            row["freshness"] == "current"
            # This accounting field includes incoming producer claim records.
            # Uniqueness of the nominated declaration is checked independently
            # against its exact source token in the untouched native capture.
            and row["accounting"]["selected_definitions"] >= 1
            and row["scope"]["subject"] == target
            and row["negative_evidence_admissible"] is False
            and any(
                binding["path"] == label["path"]
                and binding["state"] == "matching"
                and binding["claimed_revision"] == revision
                and binding["observed_revision"] == revision
                for binding in row["source_bindings"]
            )
            for row in rows
        )
    )


def _native_definition(capture: Path, label: dict[str, Any]) -> dict[str, Any]:
    """Bind an opaque native symbol to the independently frozen declaration token.

    This checks the producer's literal occurrence range and definition role;
    it does not interpret symbol grammar, relationships, or runtime dispatch.
    """
    path = label["path"]
    line = label.get("declaration_line", label["start_line"])
    content = confined_file(capture, path).read_text().splitlines()[line - 1]
    name = label["symbol"].rsplit(".", 1)[-1]
    index = json.loads(confined_file(capture, "index.json").read_text())
    symbols: set[str] = set()
    for document in index["documents"]:
        if document.get("relative_path", document.get("relativePath")) != path:
            continue
        for row in document["occurrences"]:
            role = row.get("symbol_roles", row.get("symbolRoles", 0))
            location = row.get("range", [])
            if not role & 1 or len(location) != 3 or location[0] != line - 1:
                continue
            if (
                content[: location[2]].isascii()
                and content[location[1] : location[2]] == name
            ):
                symbols.add(row["symbol"])
    return {
        "path": path,
        "declaration_line": line,
        "symbol": name,
        "producer_symbols": sorted(symbols),
        "unique_definition_token": len(symbols) == 1,
        "basis": "raw-producer-definition-role-and-frozen-source-token",
    }


def _transport(
    captures: list[dict[str, Any]], label: dict[str, Any], revision: str
) -> bool:
    if sorted(row["format"] for row in captures) != sorted(FORMATS):
        return False
    for capture in captures:
        response = capture["response"]
        packet = response.get("result", response)
        if not _current(packet, label, revision):
            return False
        if capture["format"] != "none":
            validate_evidence_presentation(packet, response["presentation"])
    return True


def qualify_native_workflow(
    workflow: dict[str, Any],
    rule: dict[str, Any],
    sources: dict[str, Path],
    definitions: dict[str, Any],
    output: Path,
    options: NativeSpecimenOptions,
) -> dict[str, Any]:
    """Observe before/stale/reopened/after specimens through public consumers."""
    captures = {
        stage: (options.capture_root / workflow["id"] / stage).resolve()
        for stage in ("before", "after")
    }
    provenance = {
        stage: validate_capture(
            captures[stage],
            sources[workflow[stage]],
            workflow_id=workflow["id"],
            stage=stage,
            definition=definitions[workflow[stage]],
        )
        for stage in captures
    }
    gates: dict[str, bool | None] = {}
    with tempfile.TemporaryDirectory(prefix="hashmarks-native-backend-") as scratch:
        workspace, state = Path(scratch) / "repo", Path(scratch) / "state"
        for stage in ("before", "after"):
            label = rule["source_labels"][stage][0]
            target = label["path"] + "::" + label["symbol"]
            _replace_specimens(workspace, captures[stage], provenance[stage])
            if stage == "after":
                prior = rule["source_labels"]["before"][0]
                with CodeMap(workspace, state_dir=state) as codemap:
                    stale = cast(
                        "dict[str, Any]",
                        codemap.structural_locality(
                            prior["path"] + "::" + prior["symbol"],
                            result_mode="relationships",
                        ),
                    )
                write_json(output / "stale-reopened.json", stale)
                rows = stale["observations"]
                gates["stale_reopened"] = bool(rows) and all(
                    row["freshness"] != "current"
                    and row["negative_evidence_admissible"] is False
                    for row in rows
                )
            with CodeMap(workspace, state_dir=state) as codemap:
                codemap.sync()
                write_json(
                    output / stage / "import.json",
                    codemap.import_scip(
                        captures[stage] / "index.json", provenance=provenance[stage]
                    ),
                )
                packet = codemap.structural_locality(
                    target, result_mode="relationships"
                )
            revision = provenance[stage]["source_revisions"][label["path"]]
            definition = _native_definition(captures[stage], label)
            gates[stage + "_definition_token"] = definition["unique_definition_token"]
            gates[stage + "_binding"] = _current(packet, label, revision)
            write_json(output / stage / "definition-token.json", definition)
            write_json(output / stage / "api.json", packet)
            case = {
                "operation": "structural_locality",
                "inputs": {"target": target, "result_mode": "relationships"},
            }
            for transport, capture in (("cli", capture_cli), ("mcp", capture_mcp)):
                rows = (
                    capture(workspace, state, case)
                    if transport in options.transports
                    else []
                )
                write_json(output / stage / (transport + ".json"), rows)
                gates[stage + "_" + transport] = (
                    _transport(rows, label, revision) if rows else None
                )
            # Transport observations must not mutate the admitted specimens.
            for relative, expected in provenance[stage]["source_revisions"].items():
                if (
                    hash_file(
                        confined_file(workspace, relative), domain=FILE_DOMAIN
                    ).hash
                    != expected
                ):
                    raise ValueError(
                        "backend native specimen changed during observation"
                    )
    status = (
        "FAIL"
        if False in gates.values()
        else "INCOMPLETE"
        if None in gates.values()
        else "PASS"
    )
    return {
        "id": workflow["id"],
        "status": status,
        "gates": gates,
        "capture_mode": "fresh-this-invocation"
        if options.regenerated
        else "capture-replay",
        "capture_identity": "sha256:"
        + canonical_sha256(
            {
                stage: json.loads((path / "capture.json").read_text())
                for stage, path in captures.items()
            }
        ),
        "scope": SCOPE,
        "retrieval_qualification": "not-measured-explicit-oracle-selected-specimens",
    }
