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

from .backend_corpus import confined_file
from .backend_gates import combine_required, presentation_conformance
from .backend_native_witnesses import native_fact_witnesses, native_witness_gate
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
    acquisition_id: str | None = None


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

    language, paths = _capture_inputs(workflow, rule, stage)
    with tempfile.TemporaryDirectory(prefix="hashmarks-native-input-") as scratch:
        root = Path(scratch)
        for relative in paths:
            admitted = confined_file(source, relative)
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(admitted, target)
        if language == "python":
            (root / "environment.json").write_text("[]\n", encoding="utf-8")
            write_json(root / "pyrightconfig.json", {"include": paths, "exclude": []})
        else:
            write_json(
                root / "package.json",
                {"name": "hashmarks-native-specimen", "private": True},
            )
            write_json(root / "tsconfig.json", {"include": paths})
        capture_scip(root, destination, language)
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


def record_capture_acquisition(
    capture: Path, workflow: str, stage: str, acquisition_id: str
) -> None:
    """Record successful QA producer output, never execution/certification state."""
    metadata = json.loads(confined_file(capture, "capture.json").read_bytes())
    products = capture_artifact_digests(capture)
    products.pop("backend-acquisition.json", None)
    write_json(
        capture / "backend-acquisition.json",
        {
            "schema": "hashmarks.backend-native-acquisition.v1",
            "acquisition_id": acquisition_id,
            "workflow": workflow,
            "stage": stage,
            "source_revisions": metadata["source_revisions"],
            "configuration": metadata["configuration"],
            "artifacts": products,
            "authority": "external-qa-capture-caller-claim",
        },
    )


def validate_capture_acquisition(
    capture: Path, workflow: str, stage: str, acquisition_id: str | None
) -> bool | None:
    """Re-prove output binding; a replay or request flag cannot prove acquisition."""
    if acquisition_id is None or not (capture / "backend-acquisition.json").is_file():
        return None
    receipt = json.loads(
        confined_file(capture, "backend-acquisition.json").read_bytes()
    )
    metadata = json.loads(confined_file(capture, "capture.json").read_bytes())
    expected = {
        "schema": "hashmarks.backend-native-acquisition.v1",
        "acquisition_id": acquisition_id,
        "workflow": workflow,
        "stage": stage,
        "source_revisions": metadata["source_revisions"],
        "configuration": metadata["configuration"],
        "authority": "external-qa-capture-caller-claim",
    }
    products = capture_artifact_digests(capture)
    products.pop("backend-acquisition.json", None)
    configuration = metadata["configuration"]
    return (
        all(receipt.get(key) == value for key, value in expected.items())
        and receipt.get("artifacts") == products
        and bool(configuration.get("version"))
        and bool(configuration.get("arguments"))
    )


def _capture_inputs(
    workflow: dict[str, Any], rule: dict[str, Any], stage: str
) -> tuple[str, list[str]]:
    nomination = workflow.get("native_observations", {}).get(stage)
    if nomination is not None:
        paths = nomination["paths"]
        language = nomination["language"]
        if not paths or len(set(paths)) != len(paths):
            raise ValueError("backend native nomination requires distinct source paths")
    else:
        # Legacy specimens remain explicitly oracle-selected. Their capture
        # scope includes every labelled source, not an arbitrary first label.
        paths = sorted(
            {label["path"] for label in rule["source_labels"][stage]}
            | {
                row["value"]
                for row in rule.get(stage, rule)["checks"]
                if row["id"] == "existing-verifier-visible"
            }
        )
        suffixes = {Path(path).suffix for path in paths}
        language = (
            "python"
            if suffixes == {".py"}
            else "typescript"
            if suffixes == {".ts"}
            else None
        )
    suffixes = {Path(path).suffix for path in paths}
    allowed = {"python": {".py"}, "typescript": {".ts"}}
    if not paths or language not in allowed or not suffixes <= allowed[language]:
        raise ValueError("backend native nomination requires one supported language")
    return language, sorted(paths)


def capture_artifact_digests(root: Path) -> dict[str, str]:
    """Hash the declared capture closure, excluding unrelated tool/cache trees."""
    metadata = json.loads(confined_file(root, "capture.json").read_text())
    names = {
        "capture.json",
        "provenance.json",
        "backend-binding.json",
        "index.json",
        "index.scip",
        *metadata["source_revisions"],
        *metadata["configuration"]["configuration"],
    }
    if (root / "backend-acquisition.json").is_file():
        names.add("backend-acquisition.json")
    return {
        name: hashlib.sha256(confined_file(root, name).read_bytes()).hexdigest()
        for name in sorted(names)
    }


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


def _replace_specimens(workspace: Path, source: Path, paths: set[str]) -> None:
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir()
    for relative in sorted(paths):
        # Capture selection is not repository membership. An unchanged file
        # remains present even if the next producer did not select it.
        if not (source / relative).exists():
            continue
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(confined_file(source, relative), target)


def _current(packet: dict[str, Any], label: dict[str, Any], revision: str) -> bool:
    return _matching_binding(packet, label, revision) and all(
        row["freshness"] == "current" for row in packet["observations"]
    )


def _matching_binding(
    packet: dict[str, Any], label: dict[str, Any], revision: str
) -> bool:
    rows = packet["observations"]
    target = label["path"] + "::" + label["symbol"]
    return (
        packet["target"] == target
        and bool(rows)
        and all(
            # This accounting field includes incoming producer claim records.
            # Uniqueness of the nominated declaration is checked independently
            # against its exact source token in the untouched native capture.
            row["accounting"]["selected_definitions"] >= 1
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
    unqualified_encoding = False
    for document in index["documents"]:
        if document.get("relative_path", document.get("relativePath")) != path:
            continue
        for row in document["occurrences"]:
            role = row.get("symbol_roles", row.get("symbolRoles", 0))
            location = row.get("range", [])
            if (
                not _definition_role(role)
                or len(location) != 3
                or location[0] != line - 1
            ):
                continue
            if not content[: location[2]].isascii():
                unqualified_encoding = True
                continue
            if content[location[1] : location[2]] == name:
                symbols.add(row["symbol"])
    return {
        "path": path,
        "declaration_line": line,
        "symbol": name,
        "producer_symbols": sorted(symbols),
        "unique_definition_token": None if unqualified_encoding else len(symbols) == 1,
        "token_qualification": "unqualified-non-ascii-prefix"
        if unqualified_encoding
        else "ascii-source-token",
        "basis": "raw-producer-definition-role-and-frozen-source-token",
    }


def _definition_role(value: object) -> bool:
    if type(value) is not int or value < 0:
        raise ValueError("native definition roles must be nonnegative integers")
    return bool(value & 1)


def _transport(
    captures: list[dict[str, Any]], label: dict[str, Any], revision: str
) -> bool | None:
    formats = [row["format"] for row in captures]
    if len(set(formats)) != len(formats) or set(formats) - set(FORMATS):
        raise ValueError(
            "backend native transport formats must be distinct and supported"
        )
    observations = []
    for capture in captures:
        response = capture["response"]
        packet = response.get("result", response)
        valid = _current(packet, label, revision)
        if capture["format"] != "none":
            valid = (
                valid
                and presentation_conformance(packet, response["presentation"])["valid"]
                is True
            )
        observations.append(valid)
    return combine_required(
        [*observations, True if set(formats) == set(FORMATS) else None]
    )


def _stale_native_observation(
    codemap: CodeMap, prior: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    target = prior["path"] + "::" + prior["symbol"]
    try:
        packet = cast(
            "dict[str, Any]",
            codemap.structural_locality(target, result_mode="relationships"),
        )
    except (KeyError, PermissionError) as error:
        # The after specimen may deliberately replace an entire source file.
        # Rejection then proves invalidation, not semantic absence. Failures for
        # a still-present member retain their normal error contract.
        if (codemap.workspace / prior["path"]).is_file():
            raise
        return {
            "target": target,
            "status": "rejected",
            "reason": "selected-source-not-present",
            "error_type": type(error).__name__,
            "negative_evidence_admissible": False,
        }, True
    rows = packet["observations"]
    return packet, bool(rows) and all(
        row["freshness"] != "current" and row["negative_evidence_admissible"] is False
        for row in rows
    )


def _transition_observation(
    codemap: CodeMap, prior: dict[str, Any], provenance: dict[str, Any]
) -> tuple[dict[str, Any], bool | None, dict[str, Any]]:
    previous_revision = provenance["before"]["source_revisions"][prior["path"]]
    member = codemap.workspace / prior["path"]
    unchanged = (
        member.is_file()
        and hash_file(member, domain=FILE_DOMAIN).hash == previous_revision
    )
    try:
        if unchanged:
            packet = codemap.structural_locality(
                prior["path"] + "::" + prior["symbol"], result_mode="relationships"
            )
            valid = _matching_binding(packet, prior, previous_revision)
        else:
            packet, valid = _stale_native_observation(codemap, prior)
    except (KeyError, PermissionError) as error:
        packet = {
            "target": prior["path"] + "::" + prior["symbol"],
            "status": "unresolved",
            "reason": "prior-subject-not-uniquely-observed",
            "error_type": type(error).__name__,
            "negative_evidence_admissible": False,
        }
        valid = None
    return (
        packet,
        valid,
        {
            "path": prior["path"],
            "before_revision": previous_revision,
            "source_transition": "unchanged"
            if unchanged
            else "modified"
            if member.is_file()
            else "deleted",
            "capture_selection": "selected"
            if prior["path"] in provenance["after"]["source_revisions"]
            else "not-selected",
            "negative_evidence_admissible": False,
        },
    )


def _capture_native_transports(
    workspace: Path,
    state: Path,
    subject: tuple[dict[str, Any], str],
    output: Path,
    options: NativeSpecimenOptions,
) -> dict[str, bool | None]:
    label, revision = subject
    case = {
        "operation": "structural_locality",
        "inputs": {
            "target": label["path"] + "::" + label["symbol"],
            "result_mode": "relationships",
        },
    }
    gates = {}
    for transport, capture in (("cli", capture_cli), ("mcp", capture_mcp)):
        rows = (
            capture(workspace, state, case) if transport in options.transports else []
        )
        write_json(output / (transport + ".json"), rows)
        gates[transport] = _transport(rows, label, revision) if rows else None
    return gates


def _observe_native_transitions(
    context: tuple[Path, Path],
    labels: list[dict[str, Any]],
    provenance: dict[str, Any],
    output: Path,
) -> bool | None:
    workspace, state = context
    gates = []
    with CodeMap(workspace, state_dir=state) as codemap:
        for ordinal, prior in enumerate(labels):
            destination = (
                output if ordinal == 0 else output / "transitions" / str(ordinal)
            )
            packet, valid, transition = _transition_observation(
                codemap, prior, provenance
            )
            write_json(destination / "stale-reopened.json", packet)
            write_json(destination / "transition.json", transition)
            gates.append(valid)
    write_json(output / "transition-membership.json", labels)
    return combine_required(gates)


def _observe_native_targets(
    context: tuple[Path, Path],
    capture: Path,
    labels: list[dict[str, Any]],
    output: Path,
    options: NativeSpecimenOptions,
) -> dict[str, bool | None]:
    workspace, state = context
    provenance = json.loads(confined_file(capture, "provenance.json").read_text())
    observations = []
    with CodeMap(workspace, state_dir=state) as codemap:
        for ordinal, label in enumerate(labels):
            destination = output if ordinal == 0 else output / "targets" / str(ordinal)
            packet = codemap.structural_locality(
                label["path"] + "::" + label["symbol"], result_mode="relationships"
            )
            definition = _native_definition(capture, label)
            write_json(destination / "definition-token.json", definition)
            write_json(destination / "api.json", packet)
            observations.append(
                {
                    "definition_token": definition["unique_definition_token"],
                    "binding": _current(
                        packet, label, provenance["source_revisions"][label["path"]]
                    ),
                }
            )
    for ordinal, label in enumerate(labels):
        destination = output if ordinal == 0 else output / "targets" / str(ordinal)
        observations[ordinal].update(
            _capture_native_transports(
                workspace,
                state,
                (label, provenance["source_revisions"][label["path"]]),
                destination,
                options,
            )
        )
    write_json(output / "target-membership.json", labels)
    return {
        name: combine_required(row[name] for row in observations)
        for name in ("definition_token", "binding", "cli", "mcp")
    }


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
    specimen_paths = {
        path
        for observation in provenance.values()
        for path in observation["source_revisions"]
    }
    with tempfile.TemporaryDirectory(prefix="hashmarks-native-backend-") as scratch:
        workspace, state = Path(scratch) / "repo", Path(scratch) / "state"
        for stage in ("before", "after"):
            _replace_specimens(workspace, sources[workflow[stage]], specimen_paths)
            if stage == "after":
                gates["stale_reopened"] = _observe_native_transitions(
                    (workspace, state),
                    rule["source_labels"]["before"],
                    provenance,
                    output,
                )
            with CodeMap(workspace, state_dir=state) as codemap:
                codemap.index.sync()
                write_json(
                    output / stage / "import.json",
                    codemap.import_scip(
                        captures[stage] / "index.json", provenance=provenance[stage]
                    ),
                )
            gates.update(
                {
                    stage + "_" + name: value
                    for name, value in _observe_native_targets(
                        (workspace, state),
                        captures[stage],
                        rule["source_labels"][stage],
                        output / stage,
                        options,
                    ).items()
                }
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
    fresh_acquisition = (
        combine_required(
            validate_capture_acquisition(
                captures[stage], workflow["id"], stage, options.acquisition_id
            )
            for stage in ("before", "after")
        )
        if options.regenerated
        else None
    )
    witnesses = native_fact_witnesses(workflow, rule, sources, output)
    if "native_oracles" in rule:
        gates["reviewed_facts"] = native_witness_gate(witnesses)
    required = [*gates.values(), *([fresh_acquisition] if options.regenerated else [])]
    status = (
        "FAIL" if False in required else "INCOMPLETE" if None in required else "PASS"
    )
    return {
        "id": workflow["id"],
        "status": status,
        "gates": gates,
        "gate_witnesses": witnesses,
        "fresh_acquisition": fresh_acquisition,
        "acquisition_id": options.acquisition_id,
        "capture_mode": "fresh-this-invocation"
        if fresh_acquisition is True
        else "fresh-acquisition-unqualified"
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
