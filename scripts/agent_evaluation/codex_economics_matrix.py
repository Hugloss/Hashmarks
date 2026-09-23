# Imports below follow the standalone script path bootstrap.
# ruff: noqa: E402
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_S = Path(__file__).resolve().parent
_R = _S.parent.parent
for x in (str(_R), str(_S)):
    if x not in sys.path:
        sys.path.insert(0, x)
from .codex_agent_economics import (
    CollectionConfig,
    preflight,
)
from .codex_agent_economics import collect as collect_lanes
from .codex_selective_scout_economics import (
    collect as collect_selective,
)

SCHEMA = "hashmarks.codex-economics-matrix.v1"


@dataclass(frozen=True)
class Variant:
    name: str
    model: str
    effort: str
    strategy: str


def parse_variant(s: str) -> Variant:
    parts = s.split(":")
    if len(parts) != 4:
        raise ValueError("variant must be NAME:MODEL:EFFORT:STRATEGY")
    v = Variant(*parts)
    if v.strategy not in {"native", "hashmarks", "selective-real"}:
        raise ValueError("strategy must be native, hashmarks, or selective-real")
    return v


def _joint(result: dict[str, Any], strategy: str) -> tuple[int, int, float, int]:
    verified = 0
    tasks = 0
    elapsed = 0.0
    tokens = 0
    if strategy == "selective-real":
        for repo in result["repositories"]:
            for row in repo["tasks"]:
                tasks += 1
                verified += int(
                    bool(row["correct_first_edit"])
                    and bool(row["correct_verification"])
                )
                elapsed += float(row["main_elapsed_ms"]) + float(
                    row["scout_elapsed_ms"]
                )
            tokens += int(repo["summary"]["total_tokens"])
    else:
        for repo in result["repositories"]:
            lane = repo["lanes"][strategy]
            for row in lane["tasks"]:
                tasks += 1
                verified += int(
                    bool(row["correct_first_edit"])
                    and bool(row["correct_verification"])
                )
                elapsed += float(row["elapsed_ms"])
                tokens += int((row.get("usage") or {}).get("total_tokens") or 0)
    return tasks, verified, elapsed, tokens


def _metric(
    name: str, result: dict[str, Any], strategy: str, model: str, effort: str
) -> dict[str, object]:
    tasks, verified, elapsed, tokens = _joint(result, strategy)
    return {
        "name": name,
        "model": model,
        "reasoning_effort": effort,
        "strategy": strategy,
        "tasks": tasks,
        "verified_solutions": verified,
        "verified_rate": verified / tasks if tasks else 0.0,
        "total_tokens": tokens,
        "token_metrics_available": tokens > 0,
        "tokens_per_verified_solution": tokens / verified
        if tokens > 0 and verified
        else None,
        "wall_ms": elapsed,
        "wall_ms_per_verified_solution": elapsed / verified if verified else None,
    }


def _dominance(rows: list[dict[str, object]]) -> list[dict[str, str]]:
    out = []
    for a in rows:
        for b in rows:
            if (
                a is b
                or not a["token_metrics_available"]
                or not b["token_metrics_available"]
            ):
                continue
            if (
                float(a["verified_rate"]) >= float(b["verified_rate"])
                and int(a["total_tokens"]) <= int(b["total_tokens"])
                and (
                    float(a["verified_rate"]) > float(b["verified_rate"])
                    or int(a["total_tokens"]) < int(b["total_tokens"])
                )
            ):
                out.append({"dominant": str(a["name"]), "dominated": str(b["name"])})
    return out


def plan(
    variants: list[Variant], root: Path, codex_bin: str, max_tasks: int | None
) -> dict[str, object]:
    return {
        "schema": "hashmarks.codex-economics-matrix-plan.v1",
        "preflight": preflight(codex_bin),
        "variants": [v.__dict__ for v in variants],
        "root": str(root),
        "max_tasks": max_tasks,
        "execution_units": sum(
            18 if v.strategy != "selective-real" else 21 for v in variants
        ),
        "note": "selective-real estimate assumes 18 main workers + 3 ambiguity scouts on the retained fixture; actual scout count is evidence-driven.",
    }


def run(
    variants: list[Variant],
    root: Path,
    codex_bin: str,
    max_tasks: int | None,
    timeout: int,
) -> dict[str, object]:
    if not preflight(codex_bin).get("available"):
        raise FileNotFoundError("real Codex CLI preflight failed")
    results = {}
    metrics = []
    for v in variants:
        vr = root / v.name
        if v.strategy == "selective-real":
            r = collect_selective(
                vr,
                CollectionConfig(
                    codex_bin=codex_bin,
                    model=v.model,
                    effort=v.effort,
                    timeout_s=timeout,
                    max_tasks=max_tasks,
                ),
            )
        else:
            r = collect_lanes(
                vr,
                CollectionConfig(
                    codex_bin=codex_bin,
                    model=v.model,
                    effort=v.effort,
                    timeout_s=timeout,
                    lanes=(v.strategy,),
                    max_tasks=max_tasks,
                ),
            )
        results[v.name] = r
        metrics.append(_metric(v.name, r, v.strategy, v.model, v.effort))
    return {
        "schema": SCHEMA,
        "preflight": preflight(codex_bin),
        "variants": metrics,
        "pareto_dominance": _dominance(metrics),
        "raw_results": results,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--variant", action="append", required=True)
    p.add_argument(
        "--root",
        type=Path,
        default=Path(".hashmarks/benchmarks/codex-economics-matrix"),
    )
    p.add_argument("--codex-bin", default="codex")
    p.add_argument("--max-tasks", type=int)
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--plan-only", action="store_true")
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    vs = [parse_variant(x) for x in a.variant]
    v = (
        plan(vs, a.root, a.codex_bin, a.max_tasks)
        if a.plan_only
        else run(vs, a.root, a.codex_bin, a.max_tasks, a.timeout)
    )
    t = json.dumps(v, indent=2, sort_keys=True) + "\n"
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(t)
    print(t, end="")  # noqa: T201 - intentional command output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
