from __future__ import annotations

import argparse
import json
import math
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from hashmarks.codemap import CodeMapService, CodeMapServiceClient

SCHEMA = "hashmarks.codemap-concurrency.v1"


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def _wait(client: CodeMapServiceClient, timeout: float = 10.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return client.status()
        except (OSError, RuntimeError, ConnectionError):
            time.sleep(0.01)
    raise TimeoutError("CodeMap service did not become ready")


def probe(
    workspace: Path,
    *,
    concurrencies: tuple[int, ...] = (1, 2, 4, 8, 16, 32),
    requests_per_worker: int = 2,
) -> dict[str, object]:
    socket_path = workspace / ".hashmarks-concurrency.sock"
    service = CodeMapService(workspace, socket_path=socket_path)
    owner = threading.Thread(target=service.serve_forever, daemon=True)
    owner.start()
    control = CodeMapServiceClient(workspace, socket_path=socket_path, timeout=30.0)
    initial = _wait(control)
    rows: list[dict[str, object]] = []
    try:
        for concurrency in concurrencies:
            barrier = threading.Barrier(concurrency)

            def worker(worker_id: int, barrier=barrier) -> list[dict[str, object]]:
                client = CodeMapServiceClient(
                    workspace, socket_path=socket_path, timeout=30.0
                )
                barrier.wait(timeout=10)
                output = []
                for request_id in range(requests_per_worker):
                    started = time.perf_counter()
                    packet = client.task_decision_packet(
                        "adapter implementation test", token_budget=256
                    )
                    elapsed = (time.perf_counter() - started) * 1000.0
                    output.append(
                        {
                            "worker": worker_id,
                            "request": request_id,
                            "elapsed_ms": elapsed,
                            "generation": packet["canonical_generation"],
                            "decision_generation": packet["identity"][
                                "decision_generation"
                            ],
                            "edit_path": (packet.get("edit") or {}).get("path"),
                            "verify_path": (packet.get("verify") or {}).get("path"),
                        }
                    )
                return output

            started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                nested = list(pool.map(worker, range(concurrency)))
            wall_ms = (time.perf_counter() - started) * 1000.0
            samples = [item for group in nested for item in group]
            latencies = [float(item["elapsed_ms"]) for item in samples]
            generations = {int(item["generation"]) for item in samples}
            decisions = {str(item["decision_generation"]) for item in samples}
            targets = {(item["edit_path"], item["verify_path"]) for item in samples}
            rows.append(
                {
                    "concurrency": concurrency,
                    "requests": len(samples),
                    "wall_ms": wall_ms,
                    "p50_ms": statistics.median(latencies),
                    "p95_ms": _percentile(latencies, 0.95),
                    "p99_ms": _percentile(latencies, 0.99),
                    "generation_count": len(generations),
                    "decision_generation_count": len(decisions),
                    "target_pair_count": len(targets),
                    "generation_consistent": len(generations) == 1,
                    "deterministic": len(decisions) == 1 and len(targets) == 1,
                }
            )
        final = control.status()
    finally:
        try:
            control.stop()
        finally:
            owner.join(timeout=5)
    return {
        "schema": SCHEMA,
        "ownership": initial["ownership"],
        "initial_syncs": initial["syncs"],
        "final_syncs": final["syncs"],
        "one_time_sync": initial["syncs"] == final["syncs"] == 1,
        "all_generations_consistent": all(
            bool(row["generation_consistent"]) for row in rows
        ),
        "all_deterministic": all(bool(row["deterministic"]) for row in rows),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = probe(args.workspace)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text)
    print(text, end="")  # noqa: T201 - intentional command output


if __name__ == "__main__":
    main()
