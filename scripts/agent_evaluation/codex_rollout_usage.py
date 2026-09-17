from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


def thread_id_from_events(path: Path) -> str | None:
    for line in path.read_text(errors="replace").splitlines():
        try:
            o = json.loads(line)
        except Exception:
            continue
        if (
            isinstance(o, dict)
            and o.get("type") == "thread.started"
            and isinstance(o.get("thread_id"), str)
        ):
            return o["thread_id"]
    return None


def _walk(v: Any):
    if isinstance(v, dict):
        yield v
        for x in v.values():
            yield from _walk(x)
    elif isinstance(v, list):
        for x in v:
            yield from _walk(x)


def usage_from_rollout(path: Path) -> dict[str, int | None]:
    best = dict.fromkeys(FIELDS)
    for line in path.read_text(errors="replace").splitlines():
        try:
            o = json.loads(line)
        except Exception:
            continue
        for d in _walk(o):
            for k in FIELDS:
                v = d.get(k)
                if isinstance(v, int) and v >= 0 and (best[k] is None or v > best[k]):
                    best[k] = v
    return best


def find_rollout(sessions_root: Path, thread_id: str) -> Path | None:
    matches = []
    for p in sessions_root.rglob("*.jsonl"):
        if thread_id in p.name:
            matches.append(p)
            continue
        try:
            head = p.open(errors="replace").read(8192)
            if thread_id in head:
                matches.append(p)
        except OSError:
            pass
    return max(matches, key=lambda p: p.stat().st_mtime) if matches else None


def recover(events: Path, sessions_root: Path) -> dict[str, object]:
    tid = thread_id_from_events(events)
    if not tid:
        return {
            "thread_id": None,
            "rollout": None,
            "usage": dict.fromkeys(FIELDS),
            "recovered": False,
        }
    r = find_rollout(sessions_root, tid)
    return {
        "thread_id": tid,
        "rollout": str(r) if r else None,
        "usage": usage_from_rollout(r) if r else dict.fromkeys(FIELDS),
        "recovered": r is not None,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--events", type=Path, required=True)
    p.add_argument(
        "--sessions-root", type=Path, default=Path.home() / ".codex" / "sessions"
    )
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    v = recover(a.events, a.sessions_root)
    t = json.dumps(v, indent=2, sort_keys=True) + "\n"
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(t)
    print(t, end="")  # noqa: T201 - intentional command output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
