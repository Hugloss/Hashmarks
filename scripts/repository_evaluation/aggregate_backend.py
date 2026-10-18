"""Read identity-bound backend measurements; never execute selected work."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from benchmarks.research_receipts import read_work_receipt, work_identity

from .backend_corpus import confined_file, load_corpus
from .backend_gates import combine_required
from .backend_grading import validate_transport_capture
from .backend_matrix import SCHEMA as MATRIX_SCHEMA
from .backend_matrix import capability_matrix
from .backend_native import (
    _capture_inputs,
    _current,
    _matching_binding,
    _native_definition,
    _transport,
    capture_artifact_digests,
    validate_capture,
    validate_capture_acquisition,
)
from .backend_native_witnesses import native_fact_witnesses, native_witness_gate
from .common import canonical_sha256, load_json, write_json
from .fact_grading import _json_equal
from .run_backend import _check_implementation, _verify_artifacts

CAMPAIGN_SCHEMA = "hashmarks.backend-evidence-campaign.v4"
NATIVE_SCHEMA = "hashmarks.backend-native-specimen-measurement.v4"
NATIVE_GATES = (
    "before_definition_token",
    "before_binding",
    "before_cli",
    "before_mcp",
    "after_definition_token",
    "after_binding",
    "after_cli",
    "after_mcp",
    "stale_reopened",
)


def _campaign(path: Path) -> dict[str, Any]:
    campaign = load_json(path, schema=CAMPAIGN_SCHEMA)
    if campaign.get("matrix_schema") != MATRIX_SCHEMA or campaign.get(
        "capabilities"
    ) != list(range(1, 21)):
        raise ValueError(
            "backend campaign must retain all twenty current capability contracts"
        )
    suites = campaign.get("suites")
    if not isinstance(suites, list) or not suites:
        raise ValueError("backend campaign requires expected suites")
    ids = [entry["id"] for entry in suites]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate backend campaign suite")
    return campaign


def _report_identity(
    report: dict[str, Any], suite: dict[str, Any], grader: dict[str, Any]
) -> None:
    identity = report["identity"]
    _check_implementation(identity)
    expected = {
        "suite": canonical_sha256(suite),
        "grader": canonical_sha256(grader),
        "source_identities": {
            name: definition["content_identity"]
            for name, definition in suite["sources"].items()
        },
    }
    if any(identity.get(key) != value for key, value in expected.items()):
        raise ValueError("backend aggregate report source/oracle identity mismatch")
    transports = identity["transports"]
    if (
        not isinstance(transports, (list, tuple))
        or len(set(transports)) != len(transports)
        or set(transports) - {"cli", "mcp"}
    ):
        raise ValueError("backend aggregate report has invalid transport selection")


def _outcomes(report: dict[str, Any], suite: dict[str, Any]) -> dict[str, Any]:
    rows = report["outcomes"]
    known = {workflow["id"] for workflow in suite["workflows"]}
    if len({row["id"] for row in rows}) != len(rows):
        raise ValueError("duplicate backend aggregate outcome")
    if any(row["id"] not in known for row in rows):
        raise ValueError("unexpected backend aggregate outcome")
    return {row["id"]: row for row in rows}


def _workflow_results(
    path: Path, suite: dict[str, Any], grader: dict[str, Any], sources: dict[str, Path]
) -> dict[str, Any]:
    report = load_json(path, schema=MATRIX_SCHEMA)
    _report_identity(report, suite, grader)
    protocol = "sha256:" + canonical_sha256(report["identity"])
    if report.get("protocol_identity") != protocol:
        raise ValueError("backend aggregate protocol identity mismatch")
    outcomes = _outcomes(report, suite)
    for workflow in suite["workflows"]:
        if workflow["id"] not in outcomes:
            continue
        work_root = path.parent / workflow["id"]
        retained = read_work_receipt(
            confined_file(path.parent, f"{workflow['id']}/receipt.json"),
            identity=work_identity(
                protocol_identity=protocol,
                work_id=workflow["id"],
                work_payload={
                    "workflow": workflow,
                    "oracle": grader["cases"][workflow["id"]],
                },
                lane="backend-evidence",
            ),
        )
        summary_row = {
            key: value
            for key, value in outcomes[workflow["id"]].items()
            if key != "receipt_reused"
        }
        if retained != summary_row:
            raise ValueError("backend aggregate summary differs from retained receipt")
        _verify_artifacts(work_root / "observations", retained)
        required = {"delta.json", "stale.json"}
        required.update(
            f"{stage}/{profile}{surface}.json"
            for stage in ("before", "after")
            for profile in ("", "initial/")
            for surface in ("api", "cli", "mcp")
        )
        if not required <= set(retained["artifacts"]):
            raise ValueError("backend aggregate lacks required profile artifacts")
        from .backend_regrading import verify_task_summary

        verify_task_summary(
            work_root / "observations",
            workflow,
            grader["cases"][workflow["id"]],
            sources,
            retained,
        )
    return outcomes


def _native_results(
    selection: dict[str, Any],
    suite: dict[str, Any],
    grader: dict[str, Any],
    sources: dict[str, Path],
) -> dict[str, Any]:
    report_path = Path(selection["native_report"]).resolve()
    report = load_json(report_path, schema=NATIVE_SCHEMA)
    _report_identity(report, suite, grader)
    if (
        report.get("qualification_scope")
        != "explicit-source-binding-and-native-transport-only"
    ):
        raise ValueError("backend native report has unsupported semantic scope")
    outcomes = _outcomes(report, suite)
    for workflow in suite["workflows"]:
        if workflow["id"] not in outcomes:
            continue
        _verify_native_outcome(
            workflow,
            grader["cases"][workflow["id"]],
            outcomes[workflow["id"]],
            (report_path.parent, Path(selection["capture_root"]).resolve()),
            (suite["sources"], sources),
            acquisition_id=report["identity"].get("acquisition_id")
            if report["identity"].get("regenerate") is True
            else None,
        )
    return outcomes


def _verify_native_outcome(
    workflow: dict[str, Any],
    rule: dict[str, Any],
    outcome: dict[str, Any],
    roots: tuple[Path, Path],
    inputs: tuple[dict[str, Any], dict[str, Path]],
    *,
    acquisition_id: str | None = None,
) -> None:
    report_root, capture_root = roots
    definitions, sources = inputs
    _verify_artifacts(report_root / workflow["id"], outcome)
    required = {
        "stale-reopened.json",
        "transition.json",
        "transition-membership.json",
    } | {
        f"{stage}/{artifact}.json"
        for stage in ("before", "after")
        for artifact in ("import", "definition-token", "api", "cli", "mcp")
    }
    required.update(
        f"transitions/{ordinal}/{name}.json"
        for ordinal in range(1, len(rule.get("source_labels", {}).get("before", [])))
        for name in ("stale-reopened", "transition")
    )
    for stage in ("before", "after"):
        required.add(stage + "/target-membership.json")
        required.update(
            f"{stage}/targets/{ordinal}/{name}.json"
            for ordinal in range(1, len(rule.get("source_labels", {}).get(stage, [])))
            for name in ("definition-token", "api", "cli", "mcp")
        )
    if not required <= set(outcome["artifacts"]):
        raise ValueError("backend native report is missing required observations")
    metadata = {}
    for stage in ("before", "after"):
        root = capture_root / workflow["id"] / stage
        if capture_artifact_digests(root) != outcome["capture_artifacts"][stage]:
            raise ValueError("backend native capture artifact scope or bytes mismatch")
        _verify_artifacts(root, {"artifacts": outcome["capture_artifacts"][stage]})
        provenance = validate_capture(
            root,
            sources[workflow[stage]],
            workflow_id=workflow["id"],
            stage=stage,
            definition=definitions[workflow[stage]],
        )
        metadata[stage] = json.loads(confined_file(root, "capture.json").read_text())
        _, expected_paths = _capture_inputs(workflow, rule, stage)
        if set(provenance["source_revisions"]) != set(expected_paths):
            raise ValueError("backend native capture differs from nominated scope")
        configuration = metadata[stage]["configuration"]
        if (
            provenance.get("collection_state") != "fresh-complete"
            or not configuration.get("version")
            or not configuration.get("arguments")
        ):
            raise ValueError("backend native acquisition provenance is incomplete")
    if outcome["capture_identity"] != "sha256:" + canonical_sha256(metadata):
        raise ValueError("backend native capture identity mismatch")
    _regrade_native_observations(workflow, rule, outcome, roots, inputs)
    _verify_native_acquisition(outcome, capture_root / workflow["id"], acquisition_id)


def _verify_native_acquisition(
    outcome: dict[str, Any], capture: Path, acquisition_id: str | None
) -> None:
    fresh = (
        combine_required(
            validate_capture_acquisition(
                capture / stage, outcome["id"], stage, acquisition_id
            )
            for stage in ("before", "after")
        )
        if acquisition_id is not None
        else None
    )
    if outcome.get("fresh_acquisition") is not fresh:
        raise ValueError(
            "backend native fresh acquisition differs from invocation proof"
        )
    if outcome.get("acquisition_id") != acquisition_id:
        raise ValueError("backend native acquisition identity differs from report")
    expected_mode = (
        "capture-replay"
        if acquisition_id is None
        else (
            "fresh-this-invocation"
            if fresh is True
            else "fresh-acquisition-unqualified"
        )
    )
    if outcome.get("capture_mode") != expected_mode:
        raise ValueError("backend native capture mode differs from acquisition proof")


def _regrade_native_observations(
    workflow: dict[str, Any],
    rule: dict[str, Any],
    outcome: dict[str, Any],
    roots: tuple[Path, Path],
    inputs: tuple[dict[str, Any], dict[str, Path]],
) -> None:
    """Gate summaries cannot qualify themselves; recompute from admitted bytes."""
    report_root, capture_root = roots
    observed = report_root / workflow["id"]
    gates = {}
    for stage in ("before", "after"):
        gates.update(
            {
                stage + "_" + name: value
                for name, value in _regrade_native_targets(
                    rule["source_labels"][stage],
                    observed / stage,
                    capture_root / workflow["id"] / stage,
                ).items()
            }
        )
    labels = rule["source_labels"]["before"]
    if (
        json.loads(confined_file(observed, "transition-membership.json").read_bytes())
        != labels
    ):
        raise ValueError("backend native transition membership differs from oracle")
    gates["stale_reopened"] = combine_required(
        _regrade_native_transition(
            workflow,
            prior,
            observed if ordinal == 0 else observed / "transitions" / str(ordinal),
            capture_root,
            inputs[1],
        )
        for ordinal, prior in enumerate(labels)
    )
    witnesses = native_fact_witnesses(workflow, rule, inputs[1], observed)
    if "native_oracles" in rule:
        gates["reviewed_facts"] = native_witness_gate(witnesses)
    if not _json_equal(outcome.get("gate_witnesses", []), witnesses):
        raise ValueError("backend native witnesses differ from artifact proof")
    if outcome["gates"].keys() != gates.keys():
        raise ValueError(
            "backend native gate membership differs from observation proof"
        )
    if any(
        type(outcome["gates"].get(name)) is not type(value)
        or outcome["gates"].get(name) != value
        for name, value in gates.items()
    ):
        raise ValueError("backend native gate summary differs from observation proof")


def _regrade_native_targets(
    labels: list[dict[str, Any]], observed: Path, capture: Path
) -> dict[str, bool | None]:
    membership = json.loads(
        confined_file(observed, "target-membership.json").read_text()
    )
    if membership != labels:
        raise ValueError("backend native target membership differs from frozen oracle")
    provenance = json.loads(confined_file(capture, "provenance.json").read_text())
    gates = []
    for ordinal, label in enumerate(labels):
        root = observed if ordinal == 0 else observed / "targets" / str(ordinal)
        revision = provenance["source_revisions"][label["path"]]
        definition = _native_definition(capture, label)
        if definition != json.loads(
            confined_file(root, "definition-token.json").read_text()
        ):
            raise ValueError("backend native definition differs from captured token")
        row = {
            "definition_token": definition["unique_definition_token"],
            "binding": _current(
                json.loads(confined_file(root, "api.json").read_text()), label, revision
            ),
        }
        for transport in ("cli", "mcp"):
            rows = json.loads(confined_file(root, transport + ".json").read_text())
            for capture_row in rows:
                validate_transport_capture(capture_row)
            row[transport] = _transport(rows, label, revision) if rows else None
        gates.append(row)
    return {
        name: combine_required(row[name] for row in gates)
        for name in ("definition_token", "binding", "cli", "mcp")
    }


def _regrade_native_transition(
    workflow: dict[str, Any],
    prior: dict[str, Any],
    observed: Path,
    captures: Path,
    sources: dict[str, Path],
) -> bool | None:
    from hashmarks.digest import FILE_DOMAIN, hash_file

    before = json.loads(
        confined_file(captures, f"{workflow['id']}/before/provenance.json").read_text()
    )
    revision = before["source_revisions"][prior["path"]]
    member = sources[workflow["after"]] / prior["path"]
    unchanged = (
        member.is_file() and hash_file(member, domain=FILE_DOMAIN).hash == revision
    )
    transition = json.loads(confined_file(observed, "transition.json").read_text())
    expected = (
        "unchanged" if unchanged else "modified" if member.is_file() else "deleted"
    )
    if (
        transition.get("source_transition") != expected
        or transition.get("path") != prior["path"]
        or transition.get("before_revision") != revision
    ):
        raise ValueError("backend native transition differs from genuine source change")
    packet = json.loads(confined_file(observed, "stale-reopened.json").read_text())
    if packet.get("status") == "unresolved":
        return (
            None
            if packet.get("target") == prior["path"] + "::" + prior["symbol"]
            and packet.get("negative_evidence_admissible") is False
            else False
        )
    if unchanged:
        return _matching_binding(packet, prior, revision)
    if not member.is_file():
        return (
            packet.get("status") == "rejected"
            and packet.get("negative_evidence_admissible") is False
        )
    rows = packet.get("observations", [])
    return bool(rows) and all(
        row["freshness"] != "current" and row["negative_evidence_admissible"] is False
        for row in rows
    )


def _load_campaign_suite(
    campaign_path: Path, entry: dict[str, Any], sources: dict[str, Path]
) -> tuple[dict[str, Any], dict[str, Any]]:
    suite_path = (campaign_path.parent / entry["suite_file"]).resolve()
    suite_metadata = json.loads(suite_path.read_text())
    suite, grader = load_corpus(
        suite_path, {name: sources[name] for name in suite_metadata["sources"]}
    )
    if (
        canonical_sha256(suite) != entry["suite_sha256"]
        or canonical_sha256(grader) != entry["grader_sha256"]
    ):
        raise ValueError("backend campaign frozen suite/oracle identity mismatch")
    if entry["workflow_ids"] != [row["id"] for row in suite["workflows"]]:
        raise ValueError("backend campaign expected workflow membership mismatch")
    return suite, grader


def _merge_suite(
    suite_id: str,
    suite: dict[str, Any],
    observed: dict[str, Any],
    native: dict[str, Any],
    grader: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    workflows, outcomes, missing = [], [], []
    for workflow in suite["workflows"]:
        qualified_id = f"{suite_id}/{workflow['id']}"
        proofs = (
            grader["cases"][workflow["id"]].get("capability_proofs", {})
            if grader is not None
            else workflow.get("capability_proofs", {})
        )
        workflows.append({**workflow, "id": qualified_id, "capability_proofs": proofs})
        if workflow["id"] not in observed:
            missing.append({"id": qualified_id, "proof": "workflow-report"})
        outcome = observed.get(workflow["id"], {"id": workflow["id"], "gates": {}})
        gates = {**outcome["gates"], "native_binding": None, "fresh_acquisition": None}
        if (
            any(
                workflow.get(flag) is True
                for flag in ("native_required", "native_fresh_required")
            )
            or 18 in workflow["capabilities"]
        ):
            specimen = native.get(workflow["id"])
            if specimen is None:
                missing.append(
                    {"id": qualified_id, "proof": "native-capture-and-binding"}
                )
            else:
                gates["fresh_acquisition"] = specimen.get("fresh_acquisition")
                gates["native_binding"] = combine_required(
                    [
                        *(specimen["gates"].get(name) for name in NATIVE_GATES),
                        *specimen["gates"].values(),
                    ]
                )
        witnesses = [
            {**row, "artifact_scope": scope}
            for scope, rows in (
                ("workflow", outcome.get("gate_witnesses", [])),
                ("native", native.get(workflow["id"], {}).get("gate_witnesses", [])),
            )
            for row in rows
        ]
        outcomes.append(
            {**outcome, "id": qualified_id, "gates": gates, "gate_witnesses": witnesses}
        )
    return {"workflows": workflows, "outcomes": outcomes, "missing": missing}


def aggregate_backend(
    *,
    campaign_path: Path,
    sources: dict[str, Path],
    selections: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    """Validate existing receipts and emit an all-capability QA measurement."""
    campaign = _campaign(campaign_path)
    expected = {entry["id"] for entry in campaign["suites"]}
    inputs: list[dict[str, object]] = [
        {
            "suite": key,
            "proof": "selection",
            "state": "REJECTED",
            "reason": "unexpected backend campaign report selection",
        }
        for key in sorted(set(selections) - expected)
    ]
    collected: dict[str, list[dict[str, Any]]] = {
        "workflows": [],
        "outcomes": [],
        "missing": [],
    }
    for entry in campaign["suites"]:
        suite, grader = _load_campaign_suite(campaign_path, entry, sources)
        selection = selections.get(entry["id"], {})
        if not isinstance(selection, dict):
            inputs.append(
                {
                    "suite": entry["id"],
                    "proof": "selection",
                    "state": "REJECTED",
                    "reason": "backend report selection must be an object",
                }
            )
            selection = {}
        unexpected = set(selection) - {
            "workflow_report",
            "workflow_reports",
            "native_report",
            "native_reports",
            "capture_root",
        }
        if unexpected:
            inputs.append(
                {
                    "suite": entry["id"],
                    "proof": "selection",
                    "state": "REJECTED",
                    "reason": "unsupported backend report selection fields",
                    "fields": sorted(unexpected),
                }
            )
        reports = {}
        for proof in ("workflow", "native"):
            rows, evidence = _admit_report_inputs(
                entry["id"], proof, selection, suite, grader, sources
            )
            reports[proof] = rows
            inputs.extend(evidence)
        for key, rows in _merge_suite(
            entry["id"], suite, reports["workflow"], reports["native"], grader
        ).items():
            collected[key].extend(rows)
    report: dict[str, Any] = {
        **capability_matrix(collected["workflows"], collected["outcomes"]),
        "campaign_identity": "sha256:" + canonical_sha256(campaign),
        "missing_proof": collected["missing"],
        "missing_workflow_reports": [
            row["id"]
            for row in collected["missing"]
            if row["proof"] == "workflow-report"
        ],
        "outcomes": collected["outcomes"],
        "input_reports": inputs,
        "input_integrity": {
            "state": "FAIL"
            if any(row["state"] == "REJECTED" for row in inputs)
            else "INCOMPLETE"
            if any(
                row["state"] == "MISSING" and row.get("required") is True
                for row in inputs
            )
            else "PASS"
        },
    }
    if report["input_integrity"]["state"] == "FAIL":
        report["status"] = "FAIL"
    write_json(output_dir / "summary.json", report)
    lines = [
        "# Backend evidence qualification",
        "",
        f"Status: {report['status']}",
        "",
        "| Capability | Problems | Repositories | Status |",
        "| --- | ---: | ---: | --- |",
    ]
    lines.extend(
        f"| {row['capability']}. {row['name']} | {row['genuine_workflows']} | {len(row['repositories'])} | {row['status']} |"
        for row in report["capabilities"]
    )
    lines.extend(
        ["", "| Suite | Input | State | Reason |", "| --- | --- | --- | --- |"]
    )
    lines.extend(
        f"| {_markdown_cell(row['suite'])} | {row['proof']} | {row['state']} | {_markdown_cell(row.get('reason', ''))} |"
        for row in inputs
    )
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def _markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _report_selections(selection: dict, proof: str) -> list[dict]:
    singular, plural = proof + "_report", proof + "_reports"
    if singular in selection and plural in selection:
        raise ValueError("backend singular and plural reports are mutually exclusive")
    if proof == "native" and "capture_root" in selection and singular not in selection:
        raise ValueError("backend capture_root requires a singular native_report")
    if singular in selection:
        entries = [{singular: selection[singular]}]
        if proof == "native":
            entries[0]["capture_root"] = selection.get("capture_root")
    elif plural in selection:
        raw = selection[plural]
        if not isinstance(raw, list) or not raw:
            raise ValueError("backend report lists must be nonempty")
        entries = [{singular: value} for value in raw] if proof == "workflow" else raw
    else:
        return []
    return _validated_report_references(entries, proof)


def _validated_report_references(entries: list[dict], proof: str) -> list[dict]:
    singular = proof + "_report"
    fields = {singular, "capture_root"} if proof == "native" else {singular}
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or set(entry) != fields
            or any(
                not isinstance(value, str) or not value.strip()
                for value in entry.values()
            )
        ):
            raise ValueError("backend report references require exact nonempty paths")
    return entries


def _admit_report_inputs(
    suite_id: str,
    proof: str,
    selection: dict,
    suite: dict,
    grader: dict,
    sources: dict[str, Path],
) -> tuple[dict, list[dict]]:
    try:
        entries = _report_selections(selection, proof)
    except ValueError as error:
        _, evidence = _admit_report_input(suite_id, proof, {}, suite, grader, sources)
        evidence.update(state="REJECTED", reason=str(error))
        return {}, [evidence]
    if not entries:
        rows, evidence = _admit_report_input(
            suite_id, proof, {}, suite, grader, sources
        )
        return rows, [evidence]
    combined, inputs, overlapping = {}, [], set()
    for entry in entries:
        rows, evidence = _admit_report_input(
            suite_id, proof, entry, suite, grader, sources
        )
        inputs.append(evidence)
        for identifier, outcome in rows.items():
            if identifier in combined or identifier in overlapping:
                overlapping.add(identifier)
                combined.pop(identifier, None)
            else:
                combined[identifier] = _report_bound_outcome(outcome, evidence)
    if overlapping:
        inputs.append(
            {
                "suite": suite_id,
                "proof": proof + "-membership",
                "state": "REJECTED",
                "reason": "overlapping backend workflow outcomes",
                "workflows": sorted(overlapping),
            }
        )
    return combined, inputs


def _report_bound_outcome(outcome: dict, evidence: dict) -> dict:
    namespace = evidence["proof"] + ":sha256:" + evidence["sha256"]
    return {
        **outcome,
        "report_binding": {key: evidence[key] for key in ("proof", "path", "sha256")},
        "gate_witnesses": [
            {**witness, "artifact_namespace": namespace}
            for witness in outcome.get("gate_witnesses", [])
        ],
    }


def _admit_report_input(
    suite_id: str,
    proof: str,
    selection: dict[str, Any],
    suite: dict[str, Any],
    grader: dict[str, Any],
    sources: dict[str, Path],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Retain rejected inputs without weakening their membership into success."""
    key = proof + "_report"
    required = proof == "workflow" or any(
        row.get("native_required") is True
        or row.get("native_fresh_required") is True
        or 18 in row["capabilities"]
        for row in suite["workflows"]
    )
    evidence: dict[str, Any] = {
        "suite": suite_id,
        "proof": proof,
        "required": required,
        "state": "MISSING",
        "reason": "not supplied",
    }
    if key not in selection:
        return {}, evidence
    try:
        path = Path(selection[key]).resolve()
        evidence["path"] = str(path)
        contents = path.read_bytes()
        evidence["sha256"] = hashlib.sha256(contents).hexdigest()
        rows = (
            _workflow_results(path, suite, grader, sources)
            if proof == "workflow"
            else _native_results(selection, suite, grader, sources)
        )
        if path.read_bytes() != contents:
            raise ValueError("backend input report changed during revalidation")
    except (OSError, ValueError, KeyError, TypeError) as error:
        evidence.update(state="REJECTED", reason=str(error))
        return {}, evidence
    evidence.update(
        state="ADMITTED", reason="identity, receipt and artifact revalidation passed"
    )
    return rows, evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--sources-file", type=Path, required=True)
    parser.add_argument("--reports-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = aggregate_backend(
        campaign_path=args.campaign.resolve(),
        sources={
            name: Path(path).resolve()
            for name, path in json.loads(args.sources_file.read_text()).items()
        },
        selections=json.loads(args.reports_file.read_text()),
        output_dir=args.output_dir.resolve(),
    )
    sys.stdout.write(
        json.dumps(
            {
                "status": report["status"],
                "summary": str(args.output_dir / "summary.json"),
            }
        )
        + "\n"
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
