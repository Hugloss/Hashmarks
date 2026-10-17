"""Frozen local correspondence vectors and exact-binding read economics.

Benchmark-only fixtures and instrumentation; no runtime diagnostic acquisition.
Run with ``python -m benchmarks.diagnostic_correspondence --output FILE``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from unittest.mock import patch

from hashmarks import CodeMap, Digest, native_producer_implementation_identity
from hashmarks.file_store import FileDigestStore

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "tests/fixtures/diagnostic_correspondence/manifest.json"
)


def fixture_manifest() -> dict[str, Any]:
    return json.loads(FIXTURE.read_bytes())


def materialize_fixture(root: Path) -> dict[str, Any]:
    manifest = fixture_manifest()
    for name, text in manifest["files"].items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    return manifest


def claim_bundle(anchor: Mapping[str, object]) -> list[dict[str, Any]]:
    return [
        {
            "bundle_id": "synthetic-claim",
            "producer": {"kind": "fixture"},
            "scope": {"kind": "supplied-source-location"},
            "completeness": "unknown",
            "truncation": "unknown",
            "anchors": [dict(anchor)],
        }
    ]


def run_vectors(codemap: CodeMap, manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    results = []
    for case in manifest["cases"]:
        try:
            packet: Any = codemap.correlate_evidence(
                claim_bundle(case["anchor"]), include_relationships=False
            )
        except ValueError as exc:
            results.append(
                {
                    "name": case["name"],
                    "passed": case.get("reject") is True,
                    "rejected": str(exc),
                }
            )
            continue
        anchor = packet["bundles"][0]["anchors"][0]
        passed = not case.get("reject") and all(
            (
                anchor["resolution"]["state"] == case["resolution"],
                anchor["source_equivalence"]["state"] == case["source_equivalence"],
                packet["execution_effect"] == "none",
                packet["completeness"]["negative_evidence"] == "not-admissible",
            )
        )
        results.append({"name": case["name"], "passed": bool(passed), "packet": packet})
    return results


def binding_economics(codemap: CodeMap, iterations: int) -> dict[str, Any]:
    request = [
        {
            "binding_id": f"consumer-{n}",
            "evidence": [{"path": "app/service.py", "start_line": 3, "end_line": 4}],
        }
        for n in range(16)
    ]
    original = FileDigestStore.read_bytes_stable
    reads = 0

    def observed(
        store: FileDigestStore, path: str | Path, *, max_attempts: int = 3
    ) -> tuple[bytes, Digest]:
        nonlocal reads
        reads += 1
        return original(store, path, max_attempts=max_attempts)

    elapsed = []
    packets: list[Any] = []
    with patch.object(FileDigestStore, "read_bytes_stable", observed):
        for _ in range(iterations):
            started = time.perf_counter_ns()
            packets.append(
                codemap.repository_evidence_bindings(
                    request, include_relationships=False
                )
            )
            elapsed.append(time.perf_counter_ns() - started)
    facts = [row["evidence"] for row in packets[-1]["bindings"]]
    return {
        "iterations": iterations,
        "bindings_per_request": len(request),
        "stable_byte_reads": reads,
        "median_ns": int(statistics.median(elapsed)),
        "equivalent_binding_facts": all(row == facts[0] for row in facts),
        "repeat_packet_identity": len({row["bindings_identity"] for row in packets})
        == 1,
        "golden_packet": packets[-1],
    }


def correspondence_quality(
    codemap: CodeMap, manifest: Mapping[str, Any]
) -> dict[str, Any]:
    direct: Any = codemap.structural_locality(manifest["locality_target"])
    indirect: Any = codemap.structural_locality(manifest["indirect_target"])
    task: Any = codemap.task_evidence(manifest["task"])
    owner = task["ownership"]["owner"]
    verifier = task["verification"]["selected"]
    return {
        "checks": {
            "direct_targets": {row["symbol_id"] for row in direct["nodes"]}
            == set(manifest["expected_call_targets"]),
            "indirect_targets": {row["symbol_id"] for row in indirect["nodes"]}
            == set(manifest["expected_indirect_call_targets"]),
            "edit_owner": owner is not None
            and owner["path"] == manifest["expected_owner"],
            "verifier": verifier is not None
            and verifier["path"] == manifest["expected_verifier"],
            "verifier_correspondence": manifest["expected_verifier"]
            in direct["verification_paths"],
        },
        "packets": {"direct": direct, "indirect": indirect, "task": task},
    }


def qualify(iterations: int = 5) -> dict[str, Any]:
    if not 1 <= iterations <= 100:
        raise ValueError("iterations must be between 1 and 100")
    with tempfile.TemporaryDirectory(prefix="hashmarks-correspondence-") as directory:
        base = Path(directory)
        manifest = materialize_fixture(base / "repo")
        with CodeMap(
            base / "repo",
            state_dir=base / "state",
            artifact_db=base / "artifacts.sqlite3",
        ) as codemap:
            codemap.index.sync()
            cases = run_vectors(codemap, manifest)
            economics = binding_economics(codemap, iterations)
            quality = correspondence_quality(codemap, manifest)
    return {
        "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        "benchmark_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "producer_identity": native_producer_implementation_identity(),
        "cases": cases,
        "economics": economics,
        "repository_correspondence": quality,
        "passed": all(row["passed"] for row in cases)
        and economics["equivalent_binding_facts"]
        and economics["repeat_packet_identity"]
        and all(quality["checks"].values()),
        "native_runtime_qualification": "not-assessed-not-required",
        "identity_scope": "Raw packets bind this temporary workspace; replay compares the frozen semantic vectors, not identities from another workspace.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=5)
    args = parser.parse_args()
    result = qualify(args.iterations)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
