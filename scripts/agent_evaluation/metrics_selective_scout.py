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
FAMILY = "hashmarks-v0.10.46-selective-scout-a"
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


def collect(root: Path, limit: int = 20) -> dict[str, object]:
    reports = []
    policies = ("no-scout", "always-scout", "selective-scout")
    for name, ws, corpus, pub in materialize_challenge(root / "challenge"):
        hidden = _load_corpus(corpus)
        public = json.load(open(pub))["tasks"]
        base = []
        with CodeMap(ws) as cm:
            cm.sync()
            for task in public:
                entry = cm.task_entry_points(task["query"], limit=limit)
                rec = [r for r in entry.get("recommended", []) if isinstance(r, dict)]
                first = str(rec[0].get("path") or "") if rec else ""
                amb = entry.get("ambiguity", {})
                ambiguous = (
                    bool(amb.get("ambiguous")) if isinstance(amb, dict) else False
                )
                alternatives = (
                    list(amb.get("alternatives", []))
                    if ambiguous and isinstance(amb, dict)
                    else []
                )
                base.append(
                    {
                        "id": task["id"],
                        "query": task["query"],
                        "first_path": first,
                        "ambiguous": ambiguous,
                        "alternatives": alternatives,
                    }
                )
        repo = {
            "name": name,
            "public_task_sha256": _sha256_bytes(pub.read_bytes()),
            "hidden_corpus_sha256": _sha256_bytes(corpus.read_bytes()),
            "policies": {},
        }
        expected = {str(t["id"]): set(t.get("expected_files") or ()) for t in hidden}
        for policy in policies:
            selected = []
            for row in base:
                spawn = policy == "always-scout" or (
                    policy == "selective-scout" and row["ambiguous"]
                )
                selected.append({**row, "spawn": spawn})
            scout_rows = [
                {
                    k: r[k]
                    for k in ("id", "query", "first_path", "ambiguous", "alternatives")
                }
                for r in selected
                if r["spawn"]
            ]
            scout_out = {}
            elapsed = 0.0
            if scout_rows:
                packet = root / "packets" / f"{name}-{policy}.json"
                out = root / "outputs" / f"{name}-{policy}.json"
                packet.parent.mkdir(parents=True, exist_ok=True)
                packet.write_text(
                    json.dumps(
                        {"schema": PACKET, "tasks": scout_rows},
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                )
                t = time.perf_counter()
                env = dict(os.environ)
                env["PYTHONPATH"] = (
                    str(_R)
                    + os.pathsep
                    + str(_S)
                    + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
                )
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "scripts.agent_evaluation.metrics_selective_scout",
                        "--worker",
                        "--packet",
                        str(packet),
                        "--output",
                        str(out),
                    ],
                    check=True,
                    env=env,
                )
                elapsed = (time.perf_counter() - t) * 1000
                scout_out = {str(x["id"]): x for x in json.load(open(out))["tasks"]}
            rows = []
            for r in selected:
                target = str(
                    scout_out.get(str(r["id"]), {}).get("target") or r["first_path"]
                )
                exp = expected[str(r["id"])]
                paths = (
                    [str(a.get("path") or "") for a in r["alternatives"]]
                    if r["spawn"]
                    else []
                )
                cost = _file_cost(ws, paths)
                rows.append(
                    {
                        "id": r["id"],
                        "spawned": r["spawn"],
                        "ambiguous": r["ambiguous"],
                        "initial_target": r["first_path"],
                        "final_target": target,
                        "correct_final": target in exp,
                        "scout_evidence": cost,
                    }
                )
            repo["policies"][policy] = {
                "summary": {
                    "tasks": len(rows),
                    "correct_final": sum(x["correct_final"] for x in rows),
                    "wrong_final": sum(not x["correct_final"] for x in rows),
                    "scout_spawns": sum(x["spawned"] for x in rows),
                    "scout_evidence_files": sum(
                        int(x["scout_evidence"]["files"]) for x in rows
                    ),
                    "scout_evidence_bytes": sum(
                        int(x["scout_evidence"]["bytes"]) for x in rows
                    ),
                    "scout_evidence_approx_tokens": sum(
                        int(x["scout_evidence"]["approx_tokens"]) for x in rows
                    ),
                    "scout_subprocess_ms": elapsed,
                },
                "tasks": rows,
            }
        reports.append(repo)

    def total(policy, key):
        return sum(float(r["policies"][policy]["summary"][key]) for r in reports)

    summary = {"repositories": len(reports), "tasks": 18}
    for pol, prefix in [
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
            summary[f"{prefix}_{key}"] = total(pol, key)
    summary["selective_spawn_rate"] = summary["selective_scout_scout_spawns"] / 18
    summary["selective_correctness_gain"] = (
        summary["selective_scout_correct_final"] - summary["no_scout_correct_final"]
    )
    summary["always_extra_spawns_vs_selective"] = (
        summary["always_scout_scout_spawns"] - summary["selective_scout_scout_spawns"]
    )
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
