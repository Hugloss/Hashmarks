# Imports below follow the standalone script path bootstrap.
# ruff: noqa: E402
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

_S = Path(__file__).resolve().parent
_R = _S.parent.parent
for x in (str(_R), str(_S)):
    if x not in sys.path:
        sys.path.insert(0, x)
from hashmarks.codemap import (
    CodeMap,
)

from .metrics_agent_economics import (
    _file_cost,
)
from .metrics_blind_worker_ab import (
    _load_corpus,
    _sha256_bytes,
    materialize_challenge,
)
from .metrics_worker_inspection_ab import (
    _resolve_after_inspection,
)

SCHEMA = "hashmarks.selective-scout-economics.v1"
FAMILY = "hashmarks-selective-scout-a"
PACKET = "hashmarks.selective-scout-input.v1"


def run_scout(packet: Path, output: Path) -> None:
    p = json.load(open(packet))
    rows = []
    for row in p["tasks"]:
        if set(row) - {"id", "query", "first_path", "ambiguous", "alternatives"}:
            raise ValueError("scout packet contains unsupported/hidden fields")
        alts = [x for x in row.get("alternatives", []) if isinstance(x, dict)]
        res = _resolve_after_inspection(str(row["query"]), alts)
        target = (
            str(res.get("target") or row.get("first_path") or "")
            if res.get("resolved")
            else str(row.get("first_path") or "")
        )
        rows.append(
            {
                "id": row["id"],
                "target": target,
                "resolved": bool(res.get("resolved")),
                "reason": res.get("reason"),
            }
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {"schema": "hashmarks.selective-scout-output.v1", "tasks": rows},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _base_rows(workspace: Path, public: list[dict], limit: int) -> list[dict]:
    rows = []
    with CodeMap(workspace) as codemap:
        codemap.sync()
        for task in public:
            entry = codemap.task_entry_points(task["query"], limit=limit)
            recommended = [
                row for row in entry.get("recommended", []) if isinstance(row, dict)
            ]
            ambiguity = entry.get("ambiguity", {})
            ambiguous = (
                bool(ambiguity.get("ambiguous"))
                if isinstance(ambiguity, dict)
                else False
            )
            rows.append(
                {
                    "id": task["id"],
                    "query": task["query"],
                    "first_path": str(recommended[0].get("path") or "")
                    if recommended
                    else "",
                    "ambiguous": ambiguous,
                    "alternatives": list(ambiguity.get("alternatives", []))
                    if ambiguous and isinstance(ambiguity, dict)
                    else [],
                }
            )
    return rows


def _run_scout_process(
    root: Path, name: str, policy: str, rows: list[dict]
) -> tuple[dict, float]:
    if not rows:
        return {}, 0.0
    packet = root / "packets" / f"{name}-{policy}.json"
    output = root / "outputs" / f"{name}-{policy}.json"
    packet.parent.mkdir(parents=True, exist_ok=True)
    packet.write_text(
        json.dumps({"schema": PACKET, "tasks": rows}, indent=2, sort_keys=True) + "\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = (
        str(_R)
        + os.pathsep
        + str(_S)
        + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    )
    started = time.perf_counter()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.agent_evaluation.metrics_selective_scout",
            "--worker",
            "--packet",
            str(packet),
            "--output",
            str(output),
        ],
        check=True,
        env=env,
    )
    elapsed = (time.perf_counter() - started) * 1000
    return {str(row["id"]): row for row in json.load(open(output))["tasks"]}, elapsed


def _policy_report(
    root: Path,
    name: str,
    workspace: Path,
    base: list[dict],
    expected: dict[str, set],
    policy: str,
) -> dict:
    selected = [
        {
            **row,
            "spawn": policy == "always-scout"
            or (policy == "selective-scout" and row["ambiguous"]),
        }
        for row in base
    ]
    scout_rows = [
        {
            key: row[key]
            for key in ("id", "query", "first_path", "ambiguous", "alternatives")
        }
        for row in selected
        if row["spawn"]
    ]
    scout_output, elapsed = _run_scout_process(root, name, policy, scout_rows)
    rows = []
    for row in selected:
        target = str(
            scout_output.get(str(row["id"]), {}).get("target") or row["first_path"]
        )
        paths = (
            [str(alternative.get("path") or "") for alternative in row["alternatives"]]
            if row["spawn"]
            else []
        )
        rows.append(
            {
                "id": row["id"],
                "spawned": row["spawn"],
                "ambiguous": row["ambiguous"],
                "initial_target": row["first_path"],
                "final_target": target,
                "correct_final": target in expected[str(row["id"])],
                "scout_evidence": _file_cost(workspace, paths),
            }
        )
    return {
        "summary": {
            "tasks": len(rows),
            "correct_final": sum(row["correct_final"] for row in rows),
            "wrong_final": sum(not row["correct_final"] for row in rows),
            "scout_spawns": sum(row["spawned"] for row in rows),
            "scout_evidence_files": sum(
                int(row["scout_evidence"]["files"]) for row in rows
            ),
            "scout_evidence_bytes": sum(
                int(row["scout_evidence"]["bytes"]) for row in rows
            ),
            "scout_evidence_approx_tokens": sum(
                int(row["scout_evidence"]["approx_tokens"]) for row in rows
            ),
            "scout_subprocess_ms": elapsed,
        },
        "tasks": rows,
    }


def _aggregate_summary(reports: list[dict]) -> dict[str, float]:
    def total(policy, key):
        return sum(
            float(report["policies"][policy]["summary"][key]) for report in reports
        )

    summary: dict[str, float] = {"repositories": len(reports), "tasks": 18}
    for policy, prefix in [
        ("no-scout", "no_scout"),
        ("always-scout", "always_scout"),
        ("selective-scout", "selective_scout"),
    ]:
        for key in (
            "correct_final",
            "wrong_final",
            "scout_spawns",
            "scout_evidence_files",
            "scout_evidence_bytes",
            "scout_evidence_approx_tokens",
            "scout_subprocess_ms",
        ):
            summary[f"{prefix}_{key}"] = total(policy, key)
    summary["selective_spawn_rate"] = summary["selective_scout_scout_spawns"] / 18
    summary["selective_correctness_gain"] = (
        summary["selective_scout_correct_final"] - summary["no_scout_correct_final"]
    )
    summary["always_extra_spawns_vs_selective"] = (
        summary["always_scout_scout_spawns"] - summary["selective_scout_scout_spawns"]
    )
    return summary


def collect(root: Path, limit: int = 20) -> dict[str, object]:
    reports = []
    policies = ("no-scout", "always-scout", "selective-scout")
    for name, ws, corpus, pub in materialize_challenge(root / "challenge"):
        hidden = _load_corpus(corpus)
        public = json.load(open(pub))["tasks"]
        base = _base_rows(ws, public, limit)
        repo = {
            "name": name,
            "public_task_sha256": _sha256_bytes(pub.read_bytes()),
            "hidden_corpus_sha256": _sha256_bytes(corpus.read_bytes()),
            "policies": {},
        }
        expected = {str(t["id"]): set(t.get("expected_files") or ()) for t in hidden}
        for policy in policies:
            repo["policies"][policy] = _policy_report(
                root, name, ws, base, expected, policy
            )
        reports.append(repo)
    summary = _aggregate_summary(reports)
    protocol = {
        "family": FAMILY,
        "public_scout_fields": [
            "id",
            "query",
            "first_path",
            "ambiguous",
            "alternatives",
        ],
        "hidden_fields": ["expected_files", "expected_symbols"],
        "policies": list(policies),
        "selective_trigger": "task_entry_points ambiguity=true",
        "scout_logic": "separate subprocess using public ambiguity resolver only",
        "note": "proxy for cheap retrieval subagent; not an LLM benchmark",
        "limit": limit,
    }
    ident = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(protocol, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    return {
        "schema": SCHEMA,
        "protocol": protocol,
        "protocol_identity": ident,
        "summary": summary,
        "repositories": reports,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--worker", action="store_true")
    p.add_argument("--packet", type=Path)
    p.add_argument("--root", type=Path)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.worker:
        if not a.packet:
            p.error("--packet required")
        run_scout(a.packet, a.output)
        return
    if a.root is None:
        p.error("--root required")
    r = collect(a.root)
    a.output.write_text(json.dumps(r, indent=2, sort_keys=True) + "\n")
    print(json.dumps(r, indent=2, sort_keys=True))  # noqa: T201 - intentional command output


if __name__ == "__main__":
    main()
