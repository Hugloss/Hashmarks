from __future__ import annotations

import argparse
import json
import logging
import statistics
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Any
from unittest.mock import patch

from hashmarks import CodeMap
from hashmarks._command_output import log_command_output

logger = logging.getLogger(__name__)


def _json_bytes(value: object) -> int:
    return len(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def _directory_bytes(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def _latency_summary(values_ns: list[int]) -> dict[str, int]:
    ordered = sorted(values_ns)
    p95_index = max(0, (95 * len(ordered) + 99) // 100 - 1)
    return {
        "min_ns": ordered[0],
        "median_ns": int(statistics.median(ordered)),
        "p95_ns": ordered[p95_index],
        "max_ns": ordered[-1],
    }


def _measure_calls(operation, *, iterations: int) -> tuple[dict[str, int], int, object]:
    samples: list[int] = []
    last: object = None
    tracemalloc.start()
    try:
        for _ in range(iterations):
            started = time.perf_counter_ns()
            last = operation()
            samples.append(time.perf_counter_ns() - started)
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return _latency_summary(samples), peak, last


def _dependency_snapshot(scale: int, *, changed: bool) -> dict[str, object]:
    components = [
        {
            "component_id": f"package-{index}",
            "name": f"package-{index}",
            "ecosystem": "fixture",
        }
        for index in range(scale)
    ]
    selections = [
        {
            "node_id": f"package-{index}@1",
            "component_id": f"package-{index}",
            "version": "2" if changed and index == scale - 1 else "1",
            "source": "workspace" if index == 0 else "registry",
            "contexts": ["runtime"],
            "evidence_sources": ["fixture:runtime"],
        }
        for index in range(scale)
    ]
    relationships = [
        {
            "source": f"package-{index - 1}@1",
            "target": f"package-{index}@1",
            "kind": "dependency",
            "context": "runtime",
            "effective_scope": "runtime",
            "evidence_sources": ["fixture:runtime"],
        }
        for index in range(1, scale)
    ]
    return {
        "schema": "hashmarks.dependency-resolution.v3",
        "producer": {
            "kind": "derived-authority-economics-fixture",
            "schema_version": "1",
            "adapter_semantics": "hashmarks.benchmark-dependency-adapter.v1",
        },
        "scope": {"environment": "benchmark"},
        "contexts": ["runtime"],
        "roots": [
            {
                "node_id": "package-0@1",
                "context": "runtime",
                "evidence_sources": ["fixture:runtime"],
            }
        ],
        "evidence_sources": [
            {
                "source_id": "fixture:runtime",
                "kind": "benchmark-resolution-source",
                "authorities": ["resolution-graph", "selection"],
                "context": "runtime",
                "completeness": "complete",
                "truncation": "complete",
            }
        ],
        "components": components,
        "selections": selections,
        "inventory": [],
        "relationships": relationships,
        "coverage": [
            {
                "context": "runtime",
                "kind": "resolution-graph",
                "completeness": "complete",
                "truncation": "complete",
                "evidence_sources": ["fixture:runtime"],
            },
            {
                "context": "runtime",
                "kind": "selection",
                "completeness": "complete",
                "truncation": "complete",
                "evidence_sources": ["fixture:runtime"],
            },
        ],
        "repository_inputs": [{"path": "dependency.lock"}],
        "module_ownership": [],
    }


def _declaration_groups(scale: int) -> list[dict[str, object]]:
    declaration_ids = [f"owner-{index:03d}" for index in range(scale)]
    declarations = [
        {
            "declaration_id": declaration_id,
            "value_state": "resolved",
            "value": "team-a",
            "producer": {"kind": "derived-authority-economics-fixture"},
            "evidence": [
                {
                    "path": "owners.txt",
                    "start_line": index + 1,
                    "end_line": index + 1,
                }
            ],
        }
        for index, declaration_id in enumerate(declaration_ids)
    ]
    return [
        {
            "group_id": "component-ownership",
            "concept": {"kind": "ownership", "identity": "benchmark"},
            "scope": {"environment": "benchmark"},
            "correspondence": {
                "state": "declared",
                "basis": {"provider": "derived-authority-economics-fixture"},
            },
            "declarations": declarations,
            "coverage": {
                "state": "complete",
                "truncation": "complete",
                "expected_declaration_ids": declaration_ids,
                "scope": {"fixture": "owners"},
                "provenance": {"provider": "derived-authority-economics-fixture"},
            },
        }
    ]


def _fixture(root: Path, scale: int) -> tuple[Path, Path]:
    workspace = root / "repo"
    state_dir = root / "state"
    workspace.mkdir()
    (workspace / "dependency.lock").write_text(
        "fixture dependency authority\n",
        encoding="utf-8",
    )
    (workspace / "owners.txt").write_text(
        "".join("team-a\n" for _ in range(scale)),
        encoding="utf-8",
    )
    return workspace, state_dir


def _storage_economics(
    before: dict[str, object],
    after: dict[str, object],
    delta: dict[str, object],
    explanation: dict[str, object],
) -> dict[str, int]:
    before_bytes = _json_bytes(before)
    after_bytes = _json_bytes(after)
    pair_bytes = before_bytes + after_bytes
    delta_bytes = _json_bytes(delta)
    return {
        "before_observation_bytes": before_bytes,
        "after_observation_bytes": after_bytes,
        "caller_endpoint_pair_bytes": pair_bytes,
        "delta_bytes": delta_bytes,
        "delta_saved_vs_pair_bytes": pair_bytes - delta_bytes,
        "explanation_bytes": _json_bytes(explanation),
    }


def measure_derived_authority_economics(
    *,
    iterations: int = 100,
    scale: int = 64,
) -> dict[str, object]:
    if iterations < 1:
        raise ValueError("iterations must be positive")
    if scale < 2 or scale > 128:
        raise ValueError("scale must be between 2 and 128")

    with tempfile.TemporaryDirectory(prefix="hashmarks-derived-authority-") as raw_root:
        workspace, state_dir = _fixture(Path(raw_root), scale)
        with CodeMap(workspace, state_dir=state_dir) as codemap:
            codemap.sync()
            before = codemap.dependency_resolution_evidence(
                _dependency_snapshot(scale, changed=False)
            )
            after = codemap.dependency_resolution_evidence(
                _dependency_snapshot(scale, changed=True)
            )
            declaration = codemap.repository_declarations(_declaration_groups(scale))
            initial_dependency_explain = codemap.dependency_resolution_explain(before)
            initial_dependency_delta = codemap.dependency_resolution_delta(before, after)
            initial_declaration_explain = codemap.repository_declaration_explain(
                declaration
            )

            state_bytes_before = _directory_bytes(state_dir)
            repository_observation_calls = 0
            original_observer = getattr(codemap, "_repository_member_observation")

            def counted_observer(*args: Any, **kwargs: Any):
                nonlocal repository_observation_calls
                repository_observation_calls += 1
                return original_observer(*args, **kwargs)

            with patch.object(
                codemap,
                "_repository_member_observation",
                side_effect=counted_observer,
            ):
                dependency_explain_timing, dependency_explain_peak, last_explain = (
                    _measure_calls(
                        lambda: codemap.dependency_resolution_explain(before),
                        iterations=iterations,
                    )
                )
                dependency_delta_timing, dependency_delta_peak, last_delta = (
                    _measure_calls(
                        lambda: codemap.dependency_resolution_delta(before, after),
                        iterations=iterations,
                    )
                )
                declaration_explain_timing, declaration_explain_peak, last_declaration = (
                    _measure_calls(
                        lambda: codemap.repository_declaration_explain(declaration),
                        iterations=iterations,
                    )
                )

            state_bytes_after = _directory_bytes(state_dir)

    if repository_observation_calls:
        raise RuntimeError(
            "explicit-packet explain/delta unexpectedly re-observed repository members"
        )
    if state_bytes_after != state_bytes_before:
        raise RuntimeError(
            "explicit-packet explain/delta unexpectedly changed persistent state size"
        )
    if last_explain != initial_dependency_explain:
        raise RuntimeError("dependency explanation changed across repeated calls")
    if last_delta != initial_dependency_delta:
        raise RuntimeError("dependency delta changed across repeated calls")
    if last_declaration != initial_declaration_explain:
        raise RuntimeError("declaration explanation changed across repeated calls")

    dependency_storage = _storage_economics(
        before,
        after,
        initial_dependency_delta,
        initial_dependency_explain,
    )
    declaration_bytes = _json_bytes(declaration)
    declaration_explain_bytes = _json_bytes(initial_declaration_explain)
    return {
        "schema": "hashmarks.derived-authority-economics-diagnostic.v1",
        "fixture": {
            "dependency_components": scale,
            "declarations": scale,
            "iterations": iterations,
        },
        "dependency": {
            "storage": dependency_storage,
            "explain_latency": dependency_explain_timing,
            "delta_latency": dependency_delta_timing,
            "explain_peak_tracemalloc_bytes": dependency_explain_peak,
            "delta_peak_tracemalloc_bytes": dependency_delta_peak,
        },
        "declarations": {
            "observation_bytes": declaration_bytes,
            "explanation_bytes": declaration_explain_bytes,
            "explain_latency": declaration_explain_timing,
            "explain_peak_tracemalloc_bytes": declaration_explain_peak,
        },
        "repository_reobservation_calls": repository_observation_calls,
        "persistent_state_bytes": {
            "before": state_bytes_before,
            "after": state_bytes_after,
            "growth": state_bytes_after - state_bytes_before,
        },
        "retention": {
            "required_for_correctness": False,
            "measured_server_history_bytes": 0,
            "recommendation": (
                "do-not-add-retention-unless-real-workload-measurement-shows-material-"
                "latency-or-read-amplification"
            ),
        },
        "measurement": {
            "authority": "runtime-diagnostics-only",
            "storage": "derived-not-persisted",
            "timing": "hardware-dependent-diagnostic",
            "tracemalloc": "process-allocation-diagnostic",
            "persistent_state_check": "exact-state-directory-byte-count",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure explicit-packet derived-authority economics"
    )
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--scale", type=int, default=64)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    receipt = measure_derived_authority_economics(
        iterations=args.iterations,
        scale=args.scale,
    )
    encoded = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    log_command_output(logger, encoded.rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
