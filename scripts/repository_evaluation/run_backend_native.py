"""Acquire/replay explicit genuine backend specimens through native transport QA."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from .backend_corpus import SUITE_PATH, load_corpus
from .backend_native import (
    NativeSpecimenOptions,
    capture_artifact_digests,
    prepare_capture,
    qualify_native_workflow,
)
from .common import canonical_sha256, evaluator_implementation_identity, write_json
from .run_backend import _check_implementation, _observer_identity


def _validate_destinations(
    selected: set[str], output: Path, capture_root: Path
) -> None:
    # A report binds this invocation's observations, never leftovers from an
    # earlier qualification. Validate all destinations before acquiring bytes.
    for workflow_id in selected:
        destination = output / workflow_id
        if destination.exists():
            raise ValueError("native observations require a new output directory")
        capture = capture_root / workflow_id
        if (
            destination.resolve() == capture.resolve()
            or destination.resolve() in capture.resolve().parents
            or capture.resolve() in destination.resolve().parents
        ):
            raise ValueError(
                "native observations and captures must have separate destinations"
            )


def run_native(
    *,
    sources: dict[str, Path],
    output: Path,
    options: NativeSpecimenOptions,
    suite_path: Path = SUITE_PATH,
    workflow_ids: list[str] | None = None,
) -> dict[str, Any]:
    suite, grader = load_corpus(suite_path, sources)
    known = {row["id"] for row in suite["workflows"]}
    selected = known if workflow_ids is None else set(workflow_ids)
    if (
        not selected
        or selected - known
        or workflow_ids is not None
        and len(selected) != len(workflow_ids)
    ):
        raise ValueError(
            "native workflow selection must be nonempty, distinct and declared"
        )
    if len(set(options.transports)) != len(options.transports) or set(
        options.transports
    ) - {"cli", "mcp"}:
        raise ValueError("native transports must be distinct CLI/MCP selections")
    identity = {
        "suite": canonical_sha256(suite),
        "grader": canonical_sha256(grader),
        "observer": _observer_identity(),
        "evaluator": evaluator_implementation_identity(),
        "transports": options.transports,
        "regenerate": options.regenerated,
        "source_identities": {
            name: definition["content_identity"]
            for name, definition in suite["sources"].items()
        },
    }
    outcomes = []
    _validate_destinations(selected, output, options.capture_root)
    for workflow in suite["workflows"]:
        if workflow["id"] not in selected:
            continue
        _check_implementation(identity)
        rule = grader["cases"][workflow["id"]]
        if options.regenerated:
            for stage in ("before", "after"):
                destination = options.capture_root / workflow["id"] / stage
                if destination.exists():
                    raise ValueError(
                        "fresh backend captures require a new output directory"
                    )
                destination.parent.mkdir(parents=True, exist_ok=True)
                prepare_capture(
                    workflow,
                    rule,
                    stage,
                    sources[workflow[stage]],
                    suite["sources"][workflow[stage]],
                    destination,
                )
        outcome = qualify_native_workflow(
            workflow,
            rule,
            sources,
            suite["sources"],
            output / workflow["id"],
            options,
        )
        outcome["artifacts"] = {
            path.relative_to(output / workflow["id"]).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in sorted((output / workflow["id"]).rglob("*.json"))
            if path.name != "report.json"
        }
        outcome["capture_artifacts"] = {
            stage: capture_artifact_digests(
                options.capture_root / workflow["id"] / stage
            )
            for stage in ("before", "after")
        }
        _check_implementation(identity)
        outcomes.append(outcome)
        write_json(output / workflow["id"] / "report.json", outcome)
    status = (
        "FAIL"
        if any(row["status"] == "FAIL" for row in outcomes)
        else "INCOMPLETE"
        if selected != known or any(row["status"] == "INCOMPLETE" for row in outcomes)
        else "PASS"
    )
    report = {
        "schema": "hashmarks.backend-native-specimen-measurement.v3",
        "status": status,
        "identity": identity,
        "outcomes": outcomes,
        "missing_workflows": sorted(known - selected),
        "qualification_scope": "explicit-source-binding-and-native-transport-only",
        "backend_matrix_authority": "not-a-five-of-five-qualification",
    }
    write_json(output / "summary.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources-file", type=Path, required=True)
    parser.add_argument("--suite", type=Path, default=SUITE_PATH)
    parser.add_argument("--capture-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workflow", action="append")
    parser.add_argument("--regenerate", action="store_true")
    parser.add_argument("--transport", action="append", choices=("cli", "mcp"))
    args = parser.parse_args()
    report = run_native(
        sources={
            name: Path(path).resolve()
            for name, path in json.loads(args.sources_file.read_text()).items()
        },
        output=args.output_dir.resolve(),
        suite_path=args.suite.resolve(),
        workflow_ids=args.workflow,
        options=NativeSpecimenOptions(
            args.capture_root.resolve(),
            tuple(args.transport) if args.transport else ("cli", "mcp"),
            args.regenerate,
        ),
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
