from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, required=True)
    ap.add_argument("--secret", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    secret = json.loads(a.secret.read_text())
    sm = {x["id"]: x for x in secret["tasks"]}
    rows = []
    for p in sorted(a.runs.glob("*.json")):
        r = json.loads(p.read_text())
        assert r.get("sealed") is True
        s = sm[r["task_id"]]
        final = [e for e in r["events"] if e["kind"] == "final_result"][-1]
        m = r["metrics"]
        correct = final["selected_edit"] == s["expected_edit_path"]
        rows.append(
            {
                "id": r["task_id"],
                "lane": r["lane"],
                "category": s["category"],
                "edit_correct": correct,
                "verified": bool(final["verified"]),
                "tool_calls": m["tool_calls"],
                "search_calls": m["search_calls"],
                "read_calls": m["read_calls"],
                "repository_read_bytes": m["repository_read_bytes"],
                "hashmarks_visible_bytes": m["hashmarks_visible_bytes"],
                "verification_attempts": m["verification_attempts"],
                "failed_verifications": m["failed_verifications"],
                "wall_ms": m["wall_ms"],
                "trace_identity": r["identity"],
            }
        )

    def agg(lane):
        xs = [x for x in rows if x["lane"] == lane]
        return {
            "tasks": len(xs),
            "edit_correct": sum(x["edit_correct"] for x in xs),
            "verified": sum(x["verified"] for x in xs),
            "tool_calls": sum(x["tool_calls"] for x in xs),
            "search_calls": sum(x["search_calls"] for x in xs),
            "read_calls": sum(x["read_calls"] for x in xs),
            "repository_read_bytes": sum(x["repository_read_bytes"] for x in xs),
            "hashmarks_visible_bytes": sum(x["hashmarks_visible_bytes"] for x in xs),
            "verification_attempts": sum(x["verification_attempts"] for x in xs),
            "failed_verifications": sum(x["failed_verifications"] for x in xs),
            "median_wall_ms": median(x["wall_ms"] for x in xs) if xs else None,
        }

    out = {
        "schema": "hashmarks.internal-agent-evidence-efficiency.v1",
        "protocol": {
            "worker_answer_blind": True,
            "secret_join_after_trace_seal": True,
            "actual_agent": "current internal ChatGPT/tool environment",
            "claim_scope": "model-in-the-loop spot experiment; exact model token telemetry unavailable",
        },
        "native": agg("native"),
        "hashmarks": agg("hashmarks"),
        "rows": rows,
    }
    a.output.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=2))  # noqa: T201 - intentional command output


if __name__ == "__main__":
    main()
