"""Measure frozen backend workflows; execution and certification stay external."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import hashmarks
from benchmarks.research_receipts import evaluate_with_receipt, work_identity
from hashmarks.producer_identity import native_producer_implementation_identity

from .backend_corpus import SUITE_PATH, confined_file, load_corpus
from .backend_matrix import capability_matrix
from .backend_workflows import execute_workflow
from .common import canonical_sha256, evaluator_implementation_identity, write_json
from .run_heldout import _sources


def _measure(
    workflow: dict[str, Any],
    rule: dict[str, Any],
    sources: dict[str, Path],
    output: Path,
    transports: tuple[str, ...],
    identity: dict[str, Any],
) -> dict[str, Any]:
    _check_implementation(identity)
    result = execute_workflow(
        workflow,
        rule,
        sources,
        output,
        transports=transports,
        source_identities=identity["source_identities"],
    )
    _check_implementation(identity)
    result["artifacts"] = {
        path.relative_to(output).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(output.rglob("*.json"))
    }
    return result


def _observer_identity() -> str:
    return native_producer_implementation_identity(Path(hashmarks.__file__).parent)


def _check_implementation(identity: dict[str, Any]) -> None:
    if (
        identity["observer"] != _observer_identity()
        or identity["evaluator"] != evaluator_implementation_identity()
    ):
        raise ValueError("backend implementation changed during observation")


def _verify_artifacts(output: Path, result: dict[str, Any]) -> None:
    if not result.get("artifacts"):
        raise ValueError("backend outcome lacks retained observations")
    for relative, expected in result["artifacts"].items():
        path = confined_file(output, relative)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(
                f"backend retained observation integrity mismatch: {relative}"
            )


def run_backend(
    *,
    sources: dict[str, Path],
    output_dir: Path,
    suite_path: Path = SUITE_PATH,
    workflow_ids: list[str] | None = None,
    transports: tuple[str, ...] = ("cli", "mcp"),
) -> dict[str, Any]:
    if len(set(transports)) != len(transports) or set(transports) - {"cli", "mcp"}:
        raise ValueError("backend transports must be distinct CLI/MCP selections")
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
            "backend workflow selection must be nonempty, distinct and declared"
        )
    identity = {
        "suite": canonical_sha256(suite),
        "grader": canonical_sha256(grader),
        "observer": _observer_identity(),
        "evaluator": evaluator_implementation_identity(),
        "transports": transports,
        "source_identities": {
            name: definition["content_identity"]
            for name, definition in suite["sources"].items()
        },
    }
    protocol = "sha256:" + canonical_sha256(identity)
    outcomes: list[Mapping[str, Any]] = []
    for workflow in suite["workflows"]:
        if workflow["id"] not in selected:
            continue
        rule = grader["cases"][workflow["id"]]
        output = output_dir / workflow["id"] / "observations"
        result, reused = evaluate_with_receipt(
            receipt_path=output_dir / workflow["id"] / "receipt.json",
            identity=work_identity(
                protocol_identity=protocol,
                work_id=workflow["id"],
                work_payload={"workflow": workflow, "oracle": rule},
                lane="backend-evidence",
            ),
            evaluate=lambda workflow=workflow, rule=rule, output=output: _measure(
                workflow, rule, sources, output, transports, identity
            ),
        )
        _verify_artifacts(output, result)
        outcomes.append({**result, "receipt_reused": reused})
    summary = {
        **capability_matrix(suite["workflows"], outcomes),
        "suite": suite["suite"],
        "identity": identity,
        "protocol_identity": protocol,
        "outcomes": outcomes,
    }
    write_json(output_dir / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--source", action="append")
    source.add_argument("--sources-file", type=Path)
    parser.add_argument("--suite", type=Path, default=SUITE_PATH)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workflow", action="append")
    parser.add_argument(
        "--transport",
        action="append",
        choices=("cli", "mcp"),
        help="Default: both; a partial transport measurement remains incomplete",
    )
    args = parser.parse_args()
    sources = (
        _sources(args.source)
        if args.source
        else {
            name: Path(path).resolve()
            for name, path in json.loads(args.sources_file.read_text()).items()
        }
    )
    summary = run_backend(
        sources=sources,
        output_dir=args.output_dir.resolve(),
        suite_path=args.suite.resolve(),
        workflow_ids=args.workflow,
        transports=tuple(args.transport) if args.transport else ("cli", "mcp"),
    )
    sys.stdout.write(
        json.dumps(
            {
                "status": summary["status"],
                "summary": str(args.output_dir / "summary.json"),
            },
            sort_keys=True,
        )
        + "\n"
    )
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
