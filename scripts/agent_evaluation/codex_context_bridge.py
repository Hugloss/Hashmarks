# Imports below follow the standalone script path bootstrap.
# ruff: noqa: E402
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_S = Path(__file__).resolve().parent
_R = _S.parent.parent
for x in (str(_R), str(_S)):
    if x not in sys.path:
        sys.path.insert(0, x)
from hashmarks.codemap import (
    CodeMap,
)
from scripts.agent_evaluation.metrics_worker_inspection_ab import (
    _resolve_after_inspection,
)


def packet(
    workspace: Path, query: str, *, mode: str, limit: int = 20
) -> dict[str, object]:
    with CodeMap(workspace) as cm:
        cm.sync()
        entry = cm.task_entry_points(query, limit=limit)
        rec = [r for r in entry.get("recommended", []) if isinstance(r, dict)]
        ambiguity = (
            entry.get("ambiguity", {})
            if isinstance(entry.get("ambiguity"), dict)
            else {}
        )
        alternatives = [
            dict(r) for r in ambiguity.get("alternatives", []) if isinstance(r, dict)
        ]
        chosen = str(rec[0].get("path") or "") if rec else None
        resolution = "canonical-first"
        scout_required = False
        if mode == "selective" and ambiguity.get("ambiguous"):
            scout_required = True
            resolved = _resolve_after_inspection(query, alternatives)
            if resolved.get("resolved") and resolved.get("target"):
                chosen = str(resolved["target"])
                resolution = "selective-scout-" + str(resolved.get("reason"))
        verify_hits = cm.find_task(query + " test verification", limit=limit)
        verify = next(
            (
                h.path
                for h in verify_hits
                if "/tests/" in f"/{h.path.casefold()}"
                or Path(h.path).name.casefold().startswith("test_")
                or ".test." in Path(h.path).name.casefold()
                or ".spec." in Path(h.path).name.casefold()
            ),
            None,
        )
    return {
        "schema": "hashmarks.codex-context-packet.v1",
        "mode": mode,
        "query": query,
        "chosen_edit_target": chosen,
        "verification_target": verify,
        "scout_required": scout_required,
        "resolution": resolution,
        "ambiguity": ambiguity,
        "recommended": rec[:5],
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--query", required=True)
    p.add_argument("--mode", choices=["current", "selective"], default="current")
    p.add_argument("--limit", type=int, default=20)
    a = p.parse_args()
    print(  # noqa: T201 - intentional command output
        json.dumps(
            packet(a.workspace, a.query, mode=a.mode, limit=a.limit), sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
