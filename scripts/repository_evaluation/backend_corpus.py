"""Admission of exact source trees and separate, frozen source oracles."""

from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from hashmarks.codemap.static_python_backend_declarations import (
    StaticPythonBackendDeclarations,
)
from hashmarks.python_ast_cache import read_python_ast
from hashmarks.test_shards import repository_content_identity

from .common import GRADER_SCHEMA, load_json
from .run_cases import _validate_case_membership

SCHEMA = "hashmarks.backend-evidence-workflows.v2"
LEGACY_SCHEMA = "hashmarks.backend-evidence-workflows.v1"
SUITE_PATH = (
    Path(__file__).resolve().parents[2]
    / "benchmarks/repository_evaluation/manifests/backend-v1/suite.json"
)


def confined_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError(
            f"backend source reference is not a repository file: {relative}"
        )
    return path


def confined_file(root: Path, relative: str) -> Path:
    path = confined_path(root, relative)
    if not path.is_file():
        raise ValueError(
            f"backend source reference is not a repository file: {relative}"
        )
    return path


def workflow_transitions(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    """Translate legacy modifications without inferring rename correspondence."""
    transitions = workflow.get("transitions")
    if transitions is None:
        transitions = [
            {"kind": "modify", "before_path": path, "after_path": path}
            for path in workflow.get("changed_paths", [])
        ]
    if not isinstance(transitions, list) or not transitions:
        raise ValueError("backend workflow requires genuine source transitions")
    for transition in transitions:
        _check_transition_shape(transition)
    for stage in ("before_path", "after_path"):
        paths = [row[stage] for row in transitions if row[stage] is not None]
        if len(set(paths)) != len(paths):
            raise ValueError("backend transition endpoints must be distinct per stage")
    return transitions


def _check_transition_shape(transition: object) -> None:
    if not isinstance(transition, dict) or set(transition) != {
        "kind",
        "before_path",
        "after_path",
    }:
        raise ValueError("backend transition requires explicit path endpoints")
    kind = transition["kind"]
    before, after = transition["before_path"], transition["after_path"]
    if any(
        path is not None and (not isinstance(path, str) or not path)
        for path in (before, after)
    ):
        raise ValueError("backend transition endpoints must be nonempty paths or null")
    valid = {
        "modify": before is not None and before == after,
        "add": before is None and after is not None,
        "delete": before is not None and after is None,
        "rename": before is not None and after is not None and before != after,
    }
    if kind not in valid or not valid[kind]:
        raise ValueError("backend transition kind differs from its endpoints")


def workflow_changed_paths(workflow: dict[str, Any]) -> list[str]:
    paths = sorted(
        {
            row[key]
            for row in workflow_transitions(workflow)
            for key in ("before_path", "after_path")
            if row[key] is not None
        }
    )
    declared = workflow.get("changed_paths")
    if declared is not None and sorted(declared) != paths:
        raise ValueError("backend changed paths differ from transition endpoints")
    return paths


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
    declaration = label.get("declaration_line", start)
    if type(declaration) is not int or not start <= declaration <= end:
        raise ValueError(
            "backend oracle declaration line must be inside its source range"
        )
    digest = hashlib.sha256(b"".join(lines[start - 1 : end])).hexdigest()
    if label["sha256"] != digest:
        raise ValueError(f"backend oracle source range changed: {label['path']}")
    if path.suffix == ".py" and "symbol" in label:
        declarations = _python_declaration_ranges(read_python_ast(path).tree)
        exact = declarations.get(label["symbol"], [])
        if not any(
            first <= start <= declaration <= end <= last
            for first, last, declaration in exact
        ):
            raise ValueError(
                f"backend oracle symbol does not match its source declaration: {label['symbol']}"
            )


def _python_declaration_ranges(tree: ast.AST) -> dict[str, list[tuple[int, int, int]]]:
    result: dict[str, list[tuple[int, int, int]]] = {}

    def visit(node: ast.AST, scope: tuple[str, ...]) -> None:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            scope = (*scope, node.name)
            first = min([node.lineno, *(item.lineno for item in node.decorator_list)])
            result.setdefault(".".join(scope), []).append(
                (first, node.end_lineno or node.lineno, node.lineno)
            )
        for child in ast.iter_child_nodes(node):
            visit(child, scope)

    visit(tree, ())
    return result


def _check_workflow_metadata(workflow: dict[str, Any]) -> None:
    identifier = workflow["id"]
    if (
        not isinstance(identifier, str)
        or identifier in {".", ".."}
        or "/" in identifier
        or "\\" in identifier
    ):
        raise ValueError("backend workflow ID must be one confined path component")
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
    workflow_changed_paths(workflow)
    for transition in workflow_transitions(workflow):
        _check_transition(
            transition, sources[workflow["before"]], sources[workflow["after"]]
        )
    _check_boundary_inputs(workflow, rule, sources)
    _check_declaration_inputs(workflow, rule, sources)
    _check_runtime_inputs(workflow, rule, sources)
    _check_native_oracles(rule)


def _check_runtime_inputs(
    workflow: Mapping[str, object],
    rule: Mapping[str, object],
    sources: Mapping[str, Path],
) -> None:
    # Local import keeps source admission and the runtime oracle reader acyclic.
    from .backend_runtime_witnesses import (
        _object,
        _oracle_frames,
        _text,
        validate_runtime_stage,
    )

    inputs, oracles = workflow.get("runtime_observations"), rule.get("runtime_oracles")
    if inputs is None and oracles is None:
        return
    requests, expected = _object(inputs), _object(oracles)
    if set(requests) != {"before", "after"} or set(expected) != set(requests):
        raise ValueError("backend runtime observations require both source stages")
    units = set()
    for stage in ("before", "after"):
        validate_runtime_stage(
            sources[_text(workflow[stage])],
            requests[stage],
            expected[stage],
            repository=_text(workflow["repository"]),
            workflow=_text(workflow["id"]),
            stage=stage,
        )
        units.update(
            stage + ":" + _text(frame["anchor_id"])
            for frame in _oracle_frames(_object(expected[stage]))
        )
    declared = workflow.get("debug_frame_units")
    if (
        not isinstance(declared, list)
        or not units
        or len(declared) != len(units)
        or not all(isinstance(unit, str) and unit in units for unit in declared)
        or len(set(declared)) != len(units)
    ):
        raise ValueError(
            "backend debug frame units differ from complete captured membership"
        )


def _check_native_oracles(rule: dict[str, Any]) -> None:
    if "native_oracles" not in rule:
        return
    oracles = rule["native_oracles"]
    if not isinstance(oracles, dict) or set(oracles) != {"before", "after"}:
        raise ValueError("backend native oracles require both revision stages")
    for stage in ("before", "after"):
        _check_native_stage_oracles(oracles[stage], rule["source_labels"][stage])


def _check_native_stage_oracles(oracles: object, labels: list[dict[str, Any]]) -> None:
    targets = [label["path"] + "::" + label["symbol"] for label in labels]
    if (
        not isinstance(oracles, dict)
        or set(oracles) != set(targets)
        or len(set(targets)) != len(targets)
    ):
        raise ValueError(
            "backend native oracle target membership differs from source labels"
        )
    for oracle in oracles.values():
        if not isinstance(oracle, dict):
            raise ValueError("backend native target oracle must be an object")
        for key in ("checks", "definition_checks"):
            if key != "checks" and key not in oracle:
                continue
            checks = oracle.get(key)
            if not isinstance(checks, list) or not checks:
                raise ValueError("backend native oracle checks must be nonempty")


def _check_transition(
    transition: dict[str, Any], before_root: Path, after_root: Path
) -> None:
    kind = transition["kind"]
    before = (
        confined_file(before_root, transition["before_path"])
        if transition["before_path"] is not None
        else None
    )
    after = (
        confined_file(after_root, transition["after_path"])
        if transition["after_path"] is not None
        else None
    )
    if kind == "modify":
        if before is None or after is None:
            raise ValueError("backend modification requires both source endpoints")
        if before.read_bytes() == after.read_bytes():
            raise ValueError(
                f"backend changed path is unchanged: {transition['before_path']}"
            )
    if kind in {"add", "rename"}:
        _require_absent_endpoint(
            before_root,
            transition["after_path"],
            "backend added/renamed target already exists before transition",
        )
    if kind in {"delete", "rename"}:
        _require_absent_endpoint(
            after_root,
            transition["before_path"],
            "backend deleted/renamed source still exists after transition",
        )


def _require_absent_endpoint(root: Path, path: object, reason: str) -> None:
    if not isinstance(path, str):
        raise ValueError("backend transition requires a nonnull path endpoint")
    if confined_path(root, path).exists():
        raise ValueError(reason)


def _check_declaration_inputs(
    workflow: dict[str, Any], rule: dict[str, Any], sources: dict[str, Path]
) -> None:
    inputs = workflow.get("declaration_observations")
    oracles = rule.get("declaration_oracles")
    if inputs is None and oracles is None:
        return
    if (
        not isinstance(inputs, dict)
        or not isinstance(oracles, dict)
        or set(inputs) != {"before", "after"}
        or set(oracles) != set(inputs)
    ):
        raise ValueError(
            "backend declarations require both revision inputs and oracles"
        )
    for stage in ("before", "after"):
        _check_declaration_revision(
            inputs[stage], oracles[stage], workflow[stage], sources[workflow[stage]]
        )


def _check_declaration_revision(
    request: object, oracle: object, source: str, root: Path
) -> None:
    if not isinstance(request, dict) or not isinstance(oracle, dict):
        raise ValueError("backend declaration inputs and oracles must be objects")
    paths = request.get("python_backend_paths")
    if (
        set(request)
        != {"groups", "result_mode", "python_backend_paths", "include_class_fields"}
        or request["groups"] != []
        or request["result_mode"] != "discovery"
        or not isinstance(paths, list)
    ):
        raise ValueError("backend declaration inputs differ from admitted source scope")
    StaticPythonBackendDeclarations(
        paths=tuple(paths), include_class_fields=request["include_class_fields"]
    )
    if (
        oracle.get("source") != source
        or not oracle.get("checks")
        or not oracle.get("source_labels")
    ):
        raise ValueError("backend declarations require source-bound oracle checks")
    checks = oracle["checks"]
    if (
        not isinstance(checks, list)
        or any(
            not isinstance(check, dict)
            or not isinstance(check.get("id"), str)
            or not check["id"]
            for check in checks
        )
        or len({check["id"] for check in checks}) != len(checks)
    ):
        raise ValueError("backend declaration checks require distinct nonempty IDs")
    if set(paths) != {label["path"] for label in oracle["source_labels"]}:
        raise ValueError("backend declaration paths require independent source labels")
    for label in oracle["source_labels"]:
        _check_label(root, label)


def task_source_labels(rule: dict[str, Any], stage: str) -> list[dict[str, Any]]:
    """Task proof may cover more sources without expanding native nominations."""
    if "task_source_labels" not in rule:
        return rule["source_labels"][stage]
    labels = rule["task_source_labels"]
    if not isinstance(labels, dict) or set(labels) != {"before", "after"}:
        raise ValueError("backend task source labels require both revision stages")
    rows = labels[stage]
    if (
        not isinstance(rows, list)
        or not rows
        or not all(isinstance(label, dict) for label in rows)
    ):
        raise ValueError("backend task source labels must be nonempty label lists")
    return rows


def _check_revision_labels(root: Path, rule: dict[str, Any], stage: str) -> None:
    native_labels = rule["source_labels"][stage]
    labels = task_source_labels(rule, stage)
    for label in native_labels:
        _check_label(root, label)
    if not native_labels or not labels:
        raise ValueError("backend workflow requires source labels for both revisions")
    if "task_source_labels" in rule:
        for label in labels:
            _check_label(root, label)
    stage_rule = {**rule, **rule.get(stage, {})}
    oracle = stage_rule.get("owner_oracle")
    if oracle is not None:
        _check_owner_oracle(root, oracle, labels)
    for check in rule.get(stage, rule).get("checks", []):
        if check.get("id") == "existing-verifier-visible":
            confined_file(root, check["value"])


def _check_owner_oracle(
    root: Path, oracle: dict[str, Any], labels: list[dict[str, Any]]
) -> None:
    scope, resolution = oracle.get("scope"), oracle.get("resolution")
    candidates = oracle.get("candidates")
    if (
        scope not in {"file", "symbol"}
        or resolution not in {"unique", "ambiguous", "unknown"}
        or not isinstance(candidates, list)
    ):
        raise ValueError("backend owner oracle requires explicit scope and resolution")
    valid_count = {
        "unique": len(candidates) == 1,
        "ambiguous": len(candidates) >= 2,
        "unknown": not candidates,
    }
    if not valid_count[resolution]:
        raise ValueError("backend owner oracle resolution differs from candidate count")
    keys = (
        ("path",) if scope == "file" else ("path", "qualname", "start_line", "end_line")
    )
    identities = set()
    for candidate in candidates:
        if not isinstance(candidate, dict) or any(key not in candidate for key in keys):
            raise ValueError("backend owner oracle lacks exact candidate identity")
        confined_file(root, candidate["path"])
        identity = tuple(candidate[key] for key in keys)
        if identity in identities:
            raise ValueError("backend owner oracle contains duplicate candidates")
        identities.add(identity)
        if not any(
            label["path"] == candidate["path"]
            and (
                scope == "file"
                or (
                    label.get("symbol") == candidate["qualname"]
                    and label["start_line"] == candidate["start_line"]
                    and label["end_line"] == candidate["end_line"]
                )
            )
            for label in labels
        ):
            raise ValueError("backend owner oracle lacks independent source label")


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
            or span["path"] not in workflow_changed_paths(workflow)
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
    suite = _load_suite(suite_path)
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


def _load_suite(suite_path: Path) -> dict[str, Any]:
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    if not isinstance(suite, dict) or suite.get("schema") not in {
        SCHEMA,
        LEGACY_SCHEMA,
    }:
        raise ValueError(f"unsupported schema in {suite_path}")
    if suite["schema"] == SCHEMA and any(
        "transitions" not in workflow for workflow in suite.get("workflows", [])
    ):
        raise ValueError("backend v2 workflows require explicit source transitions")
    return suite
