"""Read identity-bound backend measurements; never execute selected work."""

from __future__ import annotations

import argparse
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
from .common import canonical_sha256, load_json, write_json
from .run_backend import _check_implementation, _verify_artifacts

CAMPAIGN_SCHEMA = "hashmarks.backend-evidence-campaign.v3"
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
        outcomes.append({**outcome, "id": qualified_id, "gates": gates})
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
    if set(selections) - {entry["id"] for entry in campaign["suites"]}:
        raise ValueError("unexpected backend campaign report selection")
    collected: dict[str, list[dict[str, Any]]] = {
        "workflows": [],
        "outcomes": [],
        "missing": [],
    }
    for entry in campaign["suites"]:
        suite, grader = _load_campaign_suite(campaign_path, entry, sources)
        selection = selections.get(entry["id"], {})
        observed = (
            _workflow_results(
                Path(selection["workflow_report"]).resolve(), suite, grader, sources
            )
            if "workflow_report" in selection
            else {}
        )
        native = (
            _native_results(selection, suite, grader, sources)
            if "native_report" in selection
            else {}
        )
        for key, rows in _merge_suite(
            entry["id"], suite, observed, native, grader
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
    }
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
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


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
