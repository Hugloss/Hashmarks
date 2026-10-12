"""Admission of exact source trees and separate, frozen source oracles."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from hashmarks.test_shards import repository_content_identity

from .common import GRADER_SCHEMA, load_json
from .run_cases import _validate_case_membership

SCHEMA = "hashmarks.backend-evidence-workflows.v1"
SUITE_PATH = (
    Path(__file__).resolve().parents[2]
    / "benchmarks/repository_evaluation/manifests/backend-v1/suite.json"
)


def confined_file(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if (
        Path(relative).is_absolute()
        or not path.is_relative_to(root.resolve())
        or not path.is_file()
    ):
        raise ValueError(
            f"backend source reference is not a repository file: {relative}"
        )
    return path


def _check_label(root: Path, label: dict[str, Any]) -> None:
    path = confined_file(root, label["path"])
    lines = path.read_bytes().splitlines(keepends=True)
    start, end = label["start_line"], label["end_line"]
    if (
        type(start) is not int
        or type(end) is not int
        or not 1 <= start <= end <= len(lines)
    ):
        raise ValueError("backend oracle source range is invalid")
    digest = hashlib.sha256(b"".join(lines[start - 1 : end])).hexdigest()
    if label["sha256"] != digest:
        raise ValueError(f"backend oracle source range changed: {label['path']}")


def _check_workflow_metadata(workflow: dict[str, Any]) -> None:
    capabilities = workflow["capabilities"]
    if (
        not capabilities
        or len(set(capabilities)) != len(capabilities)
        or any(type(value) is not int or not 1 <= value <= 20 for value in capabilities)
    ):
        raise ValueError("backend workflow requires distinct capability IDs in 1..20")
    if (
        not workflow.get("repository")
        or not workflow.get("problem_id")
        or not workflow.get("task")
    ):
        raise ValueError(
            "backend workflow requires repository, genuine problem and task"
        )


def _check_workflow(
    workflow: dict[str, Any], rule: dict[str, Any], sources: dict[str, Path]
) -> None:
    _check_workflow_metadata(workflow)
    for stage in ("before", "after"):
        root = sources[workflow[stage]]
        _check_revision_labels(root, rule, stage)
    if not workflow["changed_paths"]:
        raise ValueError("backend workflow requires a genuine source change")
    for relative in workflow["changed_paths"]:
        before = confined_file(sources[workflow["before"]], relative)
        after = confined_file(sources[workflow["after"]], relative)
        if before.read_bytes() == after.read_bytes():
            raise ValueError(f"backend changed path is unchanged: {relative}")
    _check_boundary_inputs(workflow, rule, sources)


def _check_revision_labels(root: Path, rule: dict[str, Any], stage: str) -> None:
    labels = rule["source_labels"][stage]
    if not labels:
        raise ValueError("backend workflow requires source labels for both revisions")
    for label in labels:
        _check_label(root, label)
    for check in rule.get(stage, rule).get("checks", []):
        if check.get("id") == "existing-verifier-visible":
            confined_file(root, check["value"])


def _check_boundary_inputs(
    workflow: dict[str, Any], rule: dict[str, Any], sources: dict[str, Path]
) -> None:
    inputs = workflow.get("boundary_observations")
    oracles = rule.get("function_boundary_oracles")
    if inputs is None and oracles is None:
        return
    if (
        not isinstance(inputs, dict)
        or not isinstance(oracles, dict)
        or set(inputs) != {"before", "after"}
        or set(oracles) != set(inputs)
    ):
        raise ValueError(
            "backend boundary observations require both revision inputs and oracles"
        )
    for stage in ("before", "after"):
        request, oracle = inputs[stage], oracles[stage]
        root = sources[workflow[stage]]
        span = oracle["reported_span"]
        if (
            request
            != {
                "task": "Inspect caller-reported source lines",
                "changed_paths": [span["path"]],
                "changed_line_spans": [span],
                "max_depth": 1,
            }
            or oracle["source"] != workflow[stage]
            or span["path"] not in workflow["changed_paths"]
        ):
            raise ValueError(
                "backend boundary inputs differ from the admitted source scope"
            )
        _check_boundary_oracle(root, oracle)


def _check_boundary_oracle(root: Path, oracle: dict[str, Any]) -> None:
    span = oracle["reported_span"]
    for key in ("source_label", "site_source_label"):
        if key in oracle:
            _check_label(root, oracle[key])
    lines = confined_file(root, span["path"]).read_bytes().splitlines(keepends=True)
    start, end = span["start_line"], span["end_line"]
    if (
        type(start) is not int
        or type(end) is not int
        or not 1 <= start <= end <= len(lines)
    ):
        raise ValueError("backend boundary source span is invalid")
    if (
        hashlib.sha256(lines[start - 1]).hexdigest()
        != oracle["literal_source_line_sha256"]
    ):
        raise ValueError("backend boundary literal source line changed")
    if not oracle.get("checks"):
        raise ValueError("backend boundary oracle checks must be nonempty")


def load_corpus(
    suite_path: Path, sources: dict[str, Path]
) -> tuple[dict[str, Any], dict[str, Any]]:
    suite = load_json(suite_path, schema=SCHEMA)
    grader = load_json(suite_path.parent / suite["grader_file"], schema=GRADER_SCHEMA)
    workflows = suite["workflows"]
    if not isinstance(workflows, list) or not workflows:
        raise ValueError("backend corpus must contain workflows")
    _validate_case_membership(workflows)
    if set(grader["cases"]) != {row["id"] for row in workflows}:
        raise ValueError("backend workflow and oracle membership differs")
    if set(sources) != set(suite["sources"]):
        raise ValueError("backend corpus requires exactly its declared source trees")
    for name, definition in suite["sources"].items():
        if repository_content_identity(sources[name]) != definition["content_identity"]:
            raise ValueError(f"backend source identity mismatch: {name}")
    for workflow in workflows:
        if any(
            suite["sources"][workflow[stage]]["repository"] != workflow["repository"]
            for stage in ("before", "after")
        ):
            raise ValueError("backend workflow source repository identity differs")
        _check_workflow(workflow, grader["cases"][workflow["id"]], sources)
    return suite, grader
