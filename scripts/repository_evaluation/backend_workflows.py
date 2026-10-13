"""Revision workflows in disposable copies of explicitly admitted repositories."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any, cast

from hashmarks.codemap import CodeMap
from hashmarks.digest import FILE_DOMAIN, hash_file
from hashmarks.evidence_presentation import FORMATS
from hashmarks.operation_contract import operation_default_mode, operation_schema
from hashmarks.test_shards import repository_content_identity

from .backend_boundary import observe_boundary
from .backend_corpus import confined_path, workflow_changed_paths
from .backend_declarations import observe_declarations
from .backend_gates import combine_required, fact_state, presentation_conformance
from .backend_matrix import INITIAL_TOKEN_CEILING
from .backend_transport import capture_cli, capture_mcp
from .common import canonical_sha256, write_json
from .fact_grading import grade_facts


def _packet(response: dict[str, Any]) -> dict[str, Any]:
    packet = response.get("result", response)
    if (
        packet.get("schema") == operation_schema("task_evidence", "initial")
        and "encoding" in packet
    ):
        from hashmarks.codemap.task_evidence_initial import decode_initial_packet

        return decode_initial_packet(packet)
    return packet


def _transport_grade(
    captures: list[dict[str, Any]],
    rule: dict[str, Any],
    workspace: Path,
    *,
    initial: bool = False,
    source_identity: str | None = None,
) -> dict[str, Any]:
    grades: list[dict[str, Any]] = []
    for capture in captures:
        response = capture["response"]
        packet = _packet(response)
        checks = rule.get("initial_checks") if initial else rule["checks"]
        graded = (
            grade_facts(capture["format"], {"packet": packet}, {"checks": checks})
            if checks
            else {
                "classification": "INCOMPLETE",
                "checks": [],
                "authority_violations": 0,
            }
        )
        # Initial recall is a separate metric. Projection conformance and exact
        # authority remain hard checks even when an essential fact is missing.
        parity = combine_required(
            [
                True if initial else fact_state(graded["classification"]),
                packet.get("schema")
                == operation_schema("task_evidence", "initial" if initial else None),
            ]
        )
        if capture["format"] != "none":
            parity = combine_required(
                [
                    parity,
                    presentation_conformance(
                        response.get("result", response), response["presentation"]
                    )["valid"]
                    is True,
                ]
            )
        grades.append(
            {
                "format": capture["format"],
                "parity": parity,
                "estimated_tokens": capture["estimated_tokens"],
                "checks": graded["checks"],
                "authority": combine_required(
                    [
                        _authority_safe(packet, rule),
                        graded["authority_violations"] == 0,
                        (
                            packet.get("source_evidence_identity") == source_identity
                            if source_identity is not None
                            else None
                        )
                        if initial
                        else True,
                    ]
                ),
                "revision": _revision_bound(workspace, packet),
                "initial_evidence": (
                    graded["classification"] == "PASS" if checks else None
                ),
                "initial_size": (
                    capture["estimated_tokens"] <= INITIAL_TOKEN_CEILING
                    if initial and capture["format"] in {"compact", "text"}
                    else None
                ),
            }
        )
    by_format = {row["format"]: row for row in grades}
    if len(by_format) != len(grades) or set(by_format) - set(FORMATS):
        raise ValueError("backend transport formats must be distinct and supported")

    def required(name: str, formats: tuple[str, ...] = FORMATS) -> bool | None:
        return combine_required(by_format.get(mode, {}).get(name) for mode in formats)

    return {
        "parity": required("parity"),
        "initial_size": required("initial_size", ("compact", "text")),
        "initial_evidence": required("initial_evidence", ("compact", "text")),
        "grades": grades,
        "authority": required("authority"),
        "revision": required("revision"),
    }


def _authority_safe(packet: dict[str, Any], rule: dict[str, Any]) -> bool | None:
    packet = _packet(packet)
    owner = packet["ownership"]["owner"]
    if owner is None:
        return True  # Unresolved ownership does not assert an exact owner.
    oracle = rule.get("owner_oracle")
    if oracle is None:
        # A legacy path label can disprove a wrong path, but cannot qualify an
        # exact symbol assertion. Preserve that missing proof explicitly.
        return False if owner["path"] != rule["expected_owner_path"] else None
    if oracle["resolution"] != "unique":
        return False
    if oracle["scope"] == "file" and owner.get("qualname"):
        # A reviewed file owner does not establish a more precise symbol.
        return False if owner["path"] != oracle["candidates"][0]["path"] else None
    fields = (
        ("path",)
        if oracle["scope"] == "file"
        else ("path", "qualname", "start_line", "end_line")
    )
    return all(owner.get(key) == oracle["candidates"][0][key] for key in fields)


def _observe_task_profiles(
    workspace: Path,
    state: Path,
    workflow: dict[str, Any],
    rule: dict[str, Any],
    output: Path,
    transports: tuple[str, ...],
) -> dict[str, Any]:
    profiles: dict[str, dict[str, Any]] = {
        "initial": {"result_mode": "initial"},
        "full": {"result_mode": operation_default_mode("task_evidence")},
    }
    captured: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for mode, profile in profiles.items():
        with CodeMap(workspace, state_dir=state) as codemap:
            codemap.sync()
            profile["packet"] = codemap.task_evidence(
                workflow["task"], result_mode=profile["result_mode"]
            )
            profile["revision_bound"] = _revision_bound(
                workspace, _packet(profile["packet"])
            )
        # Close the API writer before transports, and finish every initial
        # surface before requesting the default profile on any surface.
        destination = output / "initial" if mode == "initial" else output
        write_json(destination / "api.json", profile["packet"])
        case = {
            "operation": "task_evidence",
            "inputs": {"task": workflow["task"], "result_mode": profile["result_mode"]},
        }
        captured[mode] = {}
        for name, capture in (("cli", capture_cli), ("mcp", capture_mcp)):
            rows = capture(workspace, state, case) if name in transports else []
            write_json(destination / f"{name}.json", rows)
            captured[mode][name] = rows
    # The full identity is needed for comparison, not for acquiring initial
    # evidence. Grade after both observations have been captured.
    for mode in profiles:
        for name, rows in captured[mode].items():
            profiles[mode][name] = _transport_grade(
                rows,
                rule,
                workspace,
                initial=mode == "initial",
                source_identity=profiles["full"]["packet"].get(
                    "evidence_packet_identity"
                ),
            )
    return profiles


def _observe_stage(
    workspace: Path,
    state: Path,
    workflow: dict[str, Any],
    rule: dict[str, Any],
    output: Path,
    transports: tuple[str, ...],
) -> dict[str, Any]:
    snapshot = repository_content_identity(workspace)
    profiles = _observe_task_profiles(
        workspace, state, workflow, rule, output, transports
    )
    packet = profiles["full"]["packet"]
    boundary_inputs = workflow.get("boundary_observations", {}).get(rule["_stage"])
    boundary_rule = rule.get("function_boundary_oracles", {}).get(rule["_stage"])
    boundary = (
        observe_boundary(
            workspace,
            state,
            boundary_inputs,
            boundary_rule,
            output / "boundary",
            transports,
        )
        if boundary_inputs is not None and boundary_rule is not None
        else None
    )
    declaration_inputs = workflow.get("declaration_observations", {}).get(
        rule["_stage"]
    )
    declaration_rule = rule.get("declaration_oracles", {}).get(rule["_stage"])
    declarations = (
        observe_declarations(
            workspace,
            state,
            declaration_inputs,
            declaration_rule,
            output / "declarations",
            transports,
        )
        if declaration_inputs is not None and declaration_rule is not None
        else None
    )
    # A sequence of public observations must belong to one stable repository
    # snapshot, including producer and transport reads after the writer closes.
    _check_snapshot(workspace, snapshot)
    return {
        **profiles["full"],
        "grade": grade_facts(workflow["id"], {"packet": packet}, rule),
        "revision_bound": _revision_bound(workspace, packet),
        "initial": profiles["initial"],
        "boundary": boundary,
        "declarations": declarations,
    }


def _revision_bound(workspace: Path, packet: dict[str, Any]) -> bool | None:
    packet = _packet(packet)
    candidate = packet["ownership"].get("candidate")
    if not isinstance(candidate, dict) or not candidate.get("path"):
        return None
    path = (workspace / candidate["path"]).resolve()
    if not path.is_relative_to(workspace.resolve()) or not path.is_file():
        return False
    return (
        packet["provenance"].get("revision") == hash_file(path, domain=FILE_DOMAIN).hash
    )


def _freshness(
    codemap: CodeMap, paths: list[str], before_revisions: dict[str, str | None]
) -> dict[str, Any]:
    observations = [
        cast("dict[str, Any]", codemap.source_observation(path)) for path in paths
    ]
    passed = bool(observations) and all(
        _invalidated_member(
            row,
            before_revisions[path],
            confined_path(codemap.workspace, path).is_file(),
        )
        for path, row in zip(paths, observations, strict=True)
    )
    return {"passed": passed, "observations": observations}


def _invalidated_member(
    observation: dict[str, Any], prior_revision: str | None, present: bool
) -> bool:
    if (
        observation["freshness"] == "current"
        or observation["negative_evidence"] != "not-admissible"
    ):
        return False
    member = observation["member"]
    if not present:
        return (
            member["state"] == "known-absent"
            and member["reason"] == "member-not-present"
        )
    if prior_revision is None:
        return (
            member["state"] == "known-present"
            and member.get("index_state") == "unindexed"
        )
    return (
        member["state"] == "unknown"
        and member["reason"] == "member-revision-mismatch"
        and member["member_revision"] == prior_revision
    )


def _gates(
    before: dict[str, Any],
    after: dict[str, Any],
    stale: dict[str, Any],
    rule: dict[str, Any],
    delta_grade: dict[str, Any],
) -> dict[str, bool | None]:
    authority = combine_required(
        [
            *(
                _authority_safe(stage["packet"], {**rule, **rule.get(label, {})})
                for label, stage in (("before", before), ("after", after))
            ),
            *(stage["grade"]["authority_violations"] == 0 for stage in (before, after)),
            *(
                _authority_safe(
                    stage["initial"]["packet"], {**rule, **rule.get(label, {})}
                )
                for label, stage in (("before", before), ("after", after))
            ),
            delta_grade["authority_violations"] == 0,
        ]
    )
    transport_rows = [
        profile[name]
        for stage in (before, after)
        for profile in (stage, stage["initial"])
        for name in ("cli", "mcp")
    ]
    initial_rows = [
        stage["initial"][name] for stage in (before, after) for name in ("cli", "mcp")
    ]

    def transport_gate(name: str) -> bool | None:
        return combine_required(
            profile[name]["parity"]
            for stage in (before, after)
            for profile in (stage, stage["initial"])
        )

    return {
        "facts": combine_required(
            fact_state(grade["classification"])
            for grade in (before["grade"], after["grade"], delta_grade)
        ),
        "authority": combine_required(
            [authority, *(row["authority"] for row in transport_rows)]
        ),
        "revision": combine_required(
            [
                before["revision_bound"],
                after["revision_bound"],
                before["initial"]["revision_bound"],
                after["initial"]["revision_bound"],
                *(row["revision"] for row in transport_rows),
            ]
        ),
        "freshness": stale["passed"],
        "cli": transport_gate("cli"),
        "mcp": transport_gate("mcp"),
        "presentation": combine_required(row["parity"] for row in transport_rows),
        "owner_top_three": combine_required(
            rule.get(label, {}).get("expected_owner_path", rule["expected_owner_path"])
            in {row["path"] for row in stage["packet"]["retrieval"]["results"][:3]}
            for label, stage in (("before", before), ("after", after))
        ),
        "initial_size": combine_required(row["initial_size"] for row in initial_rows),
        "initial_evidence": combine_required(
            row["initial_evidence"] for row in initial_rows
        ),
    }


def execute_workflow(
    workflow: dict[str, Any],
    rule: dict[str, Any],
    sources: dict[str, Path],
    output: Path,
    *,
    transports: tuple[str, ...] = ("cli", "mcp"),
    source_identities: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run one known source transition; no edits to the supplied source trees."""
    paths = workflow_changed_paths(workflow)
    identities = (
        source_identities
        if source_identities is not None
        else {
            workflow[stage]: repository_content_identity(sources[workflow[stage]])
            for stage in ("before", "after")
        }
    )
    with tempfile.TemporaryDirectory(prefix="hashmarks-backend-") as scratch:
        workspace, state = Path(scratch) / "repo", Path(scratch) / "state"
        shutil.copytree(sources[workflow["before"]], workspace, symlinks=True)
        _check_snapshot(workspace, identities[workflow["before"]])
        before_revisions = {
            path: hash_file(confined_path(workspace, path), domain=FILE_DOMAIN).hash
            if confined_path(workspace, path).is_file()
            else None
            for path in paths
        }
        before = _observe_stage(
            workspace,
            state,
            workflow,
            {**rule, **rule.get("before", {}), "_stage": "before"},
            output / "before",
            transports,
        )
        shutil.rmtree(workspace)
        shutil.copytree(sources[workflow["after"]], workspace, symlinks=True)
        _check_snapshot(workspace, identities[workflow["after"]])
        with CodeMap(workspace, state_dir=state) as codemap:
            stale = _freshness(codemap, paths, before_revisions)
            write_json(output / "stale.json", stale)
            delta = codemap.task_post_change_delta(
                workflow["task"],
                paths,
                previous_evidence=before["packet"],
            )
            write_json(output / "delta.json", delta)
            delta_grade = grade_facts(
                workflow["id"], {"packet": delta}, {"checks": rule["delta_checks"]}
            )
        after = _observe_stage(
            workspace,
            state,
            workflow,
            {**rule, **rule.get("after", {}), "_stage": "after"},
            output / "after",
            transports,
        )
    gates = _gates(before, after, stale, rule, delta_grade)
    for stage in (before, after):
        for component in (stage["boundary"], stage["declarations"]):
            if component is None:
                continue
            for key, value in component["gates"].items():
                gates[key] = combine_required([gates[key], value])
            gates["presentation"] = combine_required([gates["cli"], gates["mcp"]])
    return {
        "id": workflow["id"],
        "gates": gates,
        "before": before["grade"],
        "after": after["grade"],
        "delta": delta_grade,
        "boundary_observations": {
            "before": before["boundary"],
            "after": after["boundary"],
        },
        "declaration_observations": {
            "before": before["declarations"],
            "after": after["declarations"],
        },
        "transport_grades": {
            "before": {key: before[key] for key in ("cli", "mcp")},
            "after": {key: after[key] for key in ("cli", "mcp")},
        },
        "initial_transport_grades": {
            stage: {key: observed["initial"][key] for key in ("cli", "mcp")}
            for stage, observed in (("before", before), ("after", after))
        },
        "observation_identity": "sha256:"
        + canonical_sha256(
            {
                "before": before["packet"],
                "after": after["packet"],
                "initial": [before["initial"]["packet"], after["initial"]["packet"]],
                "stale": stale,
                "delta": delta,
                "boundary": [before["boundary"], after["boundary"]],
                "declarations": [before["declarations"], after["declarations"]],
            }
        ),
    }


def _check_snapshot(workspace: Path, expected_identity: str) -> None:
    if repository_content_identity(workspace) != expected_identity:
        raise ValueError(
            "backend source changed while materializing the observation snapshot"
        )
