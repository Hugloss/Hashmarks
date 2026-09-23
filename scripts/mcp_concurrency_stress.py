from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from hashmarks.mcp_surface import (
    HashmarksMcpSurface,
)


@dataclass
class WorkerResult:
    worker: int
    calls: int
    successes: int
    errors: list[str]
    building_payloads: int
    generation_regressions: int
    last_generation: int | None


def _generation(payload: dict[str, Any]) -> int | None:
    value = payload.get("generation")
    if isinstance(value, int):
        return value
    receipt = payload.get("evidence_receipt")
    if isinstance(receipt, dict):
        value = receipt.get("codemap_generation")
        if isinstance(value, int):
            return value
    return None


def _surface_call(surface: HashmarksMcpSurface, lane: int) -> dict[str, Any]:
    if lane == 0:
        return surface.repository_context(max_areas=8)
    if lane == 1:
        return surface.find("flare041", limit=5)
    if lane == 2:
        return surface.task_evidence(
            "change flare041 behavior and verify it",
            limit=12,
            per_role=3,
            token_budget=384,
        )
    return surface.change_impact(
        "change flare041 behavior and verify it",
        ["src/feature.py"],
        max_depth=3,
    )


def _generation_observation(
    payload: dict[str, Any], last_generation: int | None
) -> tuple[int | None, int]:
    generation = _generation(payload)
    if generation is None:
        return last_generation, 0
    regression = int(last_generation is not None and generation < last_generation)
    return max(last_generation or generation, generation), regression


def _worker(
    worker_id: int,
    repo_text: str,
    state_text: str,
    calls: int,
    start: mp.synchronize.Event,
    out: mp.Queue,
) -> None:
    repo = Path(repo_text)
    surface = HashmarksMcpSurface(str(repo), state_dir=state_text)
    errors: list[str] = []
    building_payloads = 0
    generation_regressions = 0
    last_generation: int | None = None
    successes = 0
    try:
        start.wait(timeout=30)
        for index in range(calls):
            try:
                payload = _surface_call(surface, index % 4)
                if "BUILDING" in json.dumps(payload, sort_keys=True):
                    building_payloads += 1
                last_generation, regression = _generation_observation(
                    payload, last_generation
                )
                generation_regressions += regression
                successes += 1
            except Exception as exc:  # qualification receipt needs exact final failures
                errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        surface.close()
        out.put(
            WorkerResult(
                worker=worker_id,
                calls=calls,
                successes=successes,
                errors=errors,
                building_payloads=building_payloads,
                generation_regressions=generation_regressions,
                last_generation=last_generation,
            )
        )


def _writer(repo_text: str, writes: int, start: mp.synchronize.Event) -> None:
    repo = Path(repo_text)
    source = repo / "src" / "feature.py"
    start.wait(timeout=30)
    for index in range(writes):
        body = f"def flare041(value: int) -> int:\n    return value + {index + 2}\n"
        if index % 2:
            temporary = source.with_suffix(".py.tmp")
            temporary.write_text(body, encoding="utf-8")
            os.replace(temporary, source)
        else:
            source.write_text(body, encoding="utf-8")
        time.sleep(0.003)


def _fixture(repo: Path, extra_files: int) -> None:
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src" / "feature.py").write_text(
        "def flare041(value: int) -> int:\n    return value + 1\n",
        encoding="utf-8",
    )
    (repo / "tests" / "test_feature.py").write_text(
        "from src.feature import flare041\n\n"
        "def test_flare041():\n    assert flare041(1) >= 2\n",
        encoding="utf-8",
    )
    for index in range(extra_files):
        (repo / "src" / f"module_{index:04d}.py").write_text(
            f"def helper_{index}(value: int) -> int:\n    return value + {index}\n",
            encoding="utf-8",
        )


def _run_round(
    *, round_number: int, workers: int, calls: int, writes: int, extra_files: int
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(
        prefix=f"hashmarks-mcp-concurrency-r{round_number}-"
    ) as tmp_text:
        tmp = Path(tmp_text)
        repo = tmp / "repo"
        repo.mkdir()
        (tmp / "state").mkdir()
        _fixture(repo, extra_files)

        context = mp.get_context("spawn")
        start = context.Event()
        queue: mp.Queue = context.Queue()
        readers = [
            context.Process(
                target=_worker,
                args=(index, str(repo), str(tmp / "state"), calls, start, queue),
                name=f"hashmarks-mcp-reader-{index}",
            )
            for index in range(workers)
        ]
        writer = context.Process(
            target=_writer,
            args=(str(repo), writes, start),
            name="hashmarks-mcp-writer",
        )
        for process in [*readers, writer]:
            process.start()
        start.set()
        writer.join(timeout=120)
        for process in readers:
            process.join(timeout=180)

        process_failures = [
            {"name": process.name, "exitcode": process.exitcode}
            for process in [*readers, writer]
            if process.exitcode != 0
        ]
        results: list[WorkerResult] = []
        for _ in readers:
            try:
                results.append(queue.get(timeout=5))
            except Exception as exc:
                process_failures.append({"name": "result-queue", "error": str(exc)})

        errors = [error for result in results for error in result.errors]
        building_payloads = sum(result.building_payloads for result in results)
        generation_regressions = sum(
            result.generation_regressions for result in results
        )
        expected_calls = workers * calls
        successes = sum(result.successes for result in results)
        status = (
            "PASS"
            if not process_failures
            and not errors
            and successes == expected_calls
            and building_payloads == 0
            and generation_regressions == 0
            else "FAIL"
        )
        return {
            "round": round_number,
            "status": status,
            "expected_calls": expected_calls,
            "successful_calls": successes,
            "errors": errors,
            "building_payloads": building_payloads,
            "generation_regressions": generation_regressions,
            "process_failures": process_failures,
            "workers": [
                asdict(result) for result in sorted(results, key=lambda row: row.worker)
            ],
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Stress independent Hashmarks MCP-style processes against one changing workspace/state."
    )
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument(
        "--calls", type=int, default=80, help="calls per reader per round"
    )
    parser.add_argument("--writes", type=int, default=35)
    parser.add_argument("--extra-files", type=int, default=120)
    parser.add_argument("--receipt", default="dist/mcp-concurrency-stress.json")
    args = parser.parse_args(argv)
    if (
        min(args.rounds, args.workers, args.calls, args.writes) < 1
        or args.extra_files < 0
    ):
        parser.error(
            "rounds/workers/calls/writes must be >= 1 and extra-files must be >= 0"
        )

    started = time.monotonic()
    rounds = [
        _run_round(
            round_number=index + 1,
            workers=args.workers,
            calls=args.calls,
            writes=args.writes,
            extra_files=args.extra_files,
        )
        for index in range(args.rounds)
    ]
    receipt = {
        "schema": "hashmarks.mcp-concurrency-stress.v1",
        "status": "PASS" if all(row["status"] == "PASS" for row in rounds) else "FAIL",
        "configuration": {
            "rounds": args.rounds,
            "workers": args.workers,
            "calls_per_worker": args.calls,
            "writes_per_round": args.writes,
            "extra_files": args.extra_files,
        },
        "totals": {
            "expected_calls": sum(row["expected_calls"] for row in rounds),
            "successful_calls": sum(row["successful_calls"] for row in rounds),
            "errors": sum(len(row["errors"]) for row in rounds),
            "building_payloads": sum(row["building_payloads"] for row in rounds),
            "generation_regressions": sum(
                row["generation_regressions"] for row in rounds
            ),
        },
        "duration_seconds": time.monotonic() - started,
        "round_results": rounds,
    }
    path = Path(args.receipt)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(  # noqa: T201 - intentional command output
        "HASHMARKS MCP CONCURRENCY STRESS: " + receipt["status"] + "\n"
        f"calls: {receipt['totals']['successful_calls']}/{receipt['totals']['expected_calls']}\n"
        f"errors: {receipt['totals']['errors']}\n"
        f"BUILDING payload leaks: {receipt['totals']['building_payloads']}\n"
        f"generation regressions: {receipt['totals']['generation_regressions']}\n"
        f"receipt: {path}"
    )
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
