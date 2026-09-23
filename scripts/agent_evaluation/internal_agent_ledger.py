from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from hashmarks._command_output import log_command_output

logger = logging.getLogger(__name__)

SCHEMA = "hashmarks.internal-agent-ledger.v1"


def _sha(x):
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(x, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )


def _load(p: Path):
    return json.loads(p.read_text()) if p.exists() else {"schema": SCHEMA, "events": []}


def _save(p: Path, o):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, indent=2, sort_keys=True) + "\n")


def _event(state, kind, **kw):
    state["events"].append(
        {
            "seq": len(state["events"]) + 1,
            "kind": kind,
            "monotonic_ns": time.monotonic_ns(),
            **kw,
        }
    )


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", type=Path, required=True)
    sp = ap.add_subparsers(dest="cmd", required=True)
    i = sp.add_parser("init")
    i.add_argument("--task-id", required=True)
    i.add_argument("--lane", choices=["native", "hashmarks"], required=True)
    i.add_argument("--repo", type=Path, required=True)
    i.add_argument("--query", required=True)
    s = sp.add_parser("search")
    s.add_argument("--pattern", required=True)
    r = sp.add_parser("read")
    r.add_argument("--path", required=True)
    pk = sp.add_parser("packet")
    pk.add_argument("--source", type=Path, required=True)
    pk.add_argument("--budget", type=int, default=512)
    br = sp.add_parser("brief")
    br.add_argument("--source", type=Path, required=True)
    br.add_argument("--budget", type=int, default=512)
    e = sp.add_parser("edit")
    e.add_argument("--path", required=True)
    e.add_argument("--old", required=True)
    e.add_argument("--new", required=True)
    v = sp.add_parser("verify")
    v.add_argument("--path", required=True)
    f = sp.add_parser("finalize")
    f.add_argument("--selected-edit", required=True)
    f.add_argument("--verified", choices=["true", "false"], required=True)
    f.add_argument("--output", type=Path, required=True)
    return ap.parse_args()


def _record_packet(a: argparse.Namespace, state: dict, repo: Path) -> None:
    method = "task_decision_packet" if a.cmd == "packet" else "task_decision_brief"
    code = """import json,sys,time
from pathlib import Path
from hashmarks.codemap import CodeMap
r=Path(sys.argv[1]); q=sys.argv[2]; b=int(sys.argv[3]); t=time.perf_counter()
with CodeMap(r) as c:
 c.sync(); p=getattr(c,sys.argv[4])(q,token_budget=b)
print(json.dumps({'wall_ms':(time.perf_counter()-t)*1000,'packet':p},sort_keys=True))
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(a.source.resolve())
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(repo),
            state["query"],
            str(a.budget),
            method,
        ],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    observation = json.loads(result.stdout)
    packet = observation["packet"]
    a.state.with_suffix("." + a.cmd + ".json").write_text(
        json.dumps(packet, indent=2, sort_keys=True) + "\n"
    )
    shown = (
        packet
        if a.cmd == "brief"
        else {
            key: packet.get(key)
            for key in (
                "edit",
                "verify",
                "contract",
                "scout",
                "work_context",
                "context_budget",
            )
        }
    )
    _event(
        state,
        "hashmarks_brief" if a.cmd == "brief" else "hashmarks_packet",
        wall_ms=observation["wall_ms"],
        visible_bytes=len(json.dumps(shown, sort_keys=True).encode()),
        packet_identity=(packet.get("identity") or {}).get("decision_generation"),
    )
    _save(a.state, state)
    log_command_output(logger, json.dumps(shown, indent=2, sort_keys=True))


def _metrics(state: dict) -> dict:
    events = state["events"]
    return {
        "tool_calls": sum(
            event["kind"]
            in {"search", "read", "hashmarks_packet", "edit", "verification"}
            for event in events
        ),
        "search_calls": sum(event["kind"] == "search" for event in events),
        "read_calls": sum(event["kind"] == "read" for event in events),
        "repository_read_bytes": sum(
            event.get("bytes", 0) + event.get("result_bytes", 0)
            for event in events
            if event["kind"] in {"search", "read"}
        ),
        "hashmarks_visible_bytes": sum(
            event.get("visible_bytes", 0)
            for event in events
            if event["kind"] in {"hashmarks_packet", "hashmarks_brief"}
        ),
        "verification_attempts": sum(
            event["kind"] == "verification" for event in events
        ),
        "failed_verifications": sum(
            event["kind"] == "verification" and not event.get("passed")
            for event in events
        ),
        "wall_ms": (state["ended_ns"] - state["started_ns"]) / 1e6,
    }


def _finalize(a: argparse.Namespace, state: dict) -> None:
    _event(
        state,
        "final_result",
        selected_edit=a.selected_edit,
        verified=a.verified == "true",
    )
    state["ended_ns"] = time.monotonic_ns()
    state["sealed"] = True
    state["metrics"] = _metrics(state)
    frozen = dict(state)
    frozen.pop("identity", None)
    state["identity"] = _sha(frozen)
    _save(a.state, state)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    log_command_output(logger, state["identity"])


def _normalize_search_output(output: str) -> str:
    lines = []
    for line in output.splitlines():
        lines.append(line[2:] if line.startswith("./") else line)
    return "\n".join(lines) + ("\n" if lines else "")


def _searchable_path(path: Path, repo: Path) -> bool:
    relative = path.relative_to(repo)
    return (
        path.is_file()
        and path.suffix != ".pyc"
        and not any(
            part in {".git", ".hashmarks", "__pycache__"} for part in relative.parts
        )
    )


def _python_search(repo: Path, pattern: str) -> str:
    expression = re.compile(pattern)
    matches: list[str] = []
    for path in sorted(repo.rglob("*"), key=lambda candidate: candidate.as_posix()):
        if not _searchable_path(path, repo):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        relative = path.relative_to(repo).as_posix()
        matches.extend(
            f"{relative}:{line_number}:{line}"
            for line_number, line in enumerate(lines, start=1)
            if expression.search(line)
        )
    return "\n".join(matches) + ("\n" if matches else "")


def _search_output(repo: Path, pattern: str) -> tuple[str, str]:
    rg = shutil.which("rg")
    if rg is None:
        return _python_search(repo, pattern), "python"
    result = subprocess.run(
        [
            rg,
            "-n",
            "--hidden",
            "--no-ignore",
            "--glob",
            "!.git/**",
            "--glob",
            "!.hashmarks/**",
            "--glob",
            "!__pycache__/**",
            "--glob",
            "!*.pyc",
            pattern,
            ".",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
    )
    if result.returncode not in {0, 1}:
        detail = result.stderr.strip()[-1000:]
        raise RuntimeError(f"rg search failed with rc={result.returncode}: {detail}")
    return _normalize_search_output(result.stdout), "rg"


def _search(a: argparse.Namespace, state: dict, repo: Path) -> None:
    started = time.perf_counter()
    output, provider = _search_output(repo, a.pattern)
    elapsed_ms = (time.perf_counter() - started) * 1000
    _event(
        state,
        "search",
        pattern=a.pattern,
        provider=provider,
        wall_ms=elapsed_ms,
        result_bytes=len(output.encode()),
        matches=sum(1 for line in output.splitlines() if line),
    )
    _save(a.state, state)
    log_command_output(logger, output, end="")


def _read(a: argparse.Namespace, state: dict, repo: Path) -> None:
    path = repo / a.path
    started = time.perf_counter()
    data = path.read_text()
    elapsed_ms = (time.perf_counter() - started) * 1000
    _event(state, "read", path=a.path, wall_ms=elapsed_ms, bytes=len(data.encode()))
    _save(a.state, state)
    log_command_output(logger, data, end="")


def _edit(a: argparse.Namespace, state: dict, repo: Path) -> None:
    path = repo / a.path
    text = path.read_text()
    changed = a.old in text
    if changed:
        path.write_text(text.replace(a.old, a.new, 1))
    _event(state, "edit", path=a.path, changed=changed)
    _save(a.state, state)
    log_command_output(logger, "changed" if changed else "unchanged")


def _verify(a: argparse.Namespace, state: dict, repo: Path) -> None:
    started = time.perf_counter()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", a.path],
        cwd=repo,
        text=True,
        capture_output=True,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    _event(
        state,
        "verification",
        path=a.path,
        passed=result.returncode == 0,
        wall_ms=elapsed_ms,
        stdout_bytes=len(result.stdout.encode()),
        stderr_bytes=len(result.stderr.encode()),
    )
    _save(a.state, state)
    log_command_output(logger, result.stdout, end="")
    log_command_output(logger, result.stderr, end="", file=sys.stderr)
    raise SystemExit(result.returncode)


def main():
    a = _parse_args()
    st = _load(a.state)
    if a.cmd == "init":
        st = {
            "schema": SCHEMA,
            "task_id": a.task_id,
            "lane": a.lane,
            "repo": str(a.repo.resolve()),
            "query": a.query,
            "started_ns": time.monotonic_ns(),
            "events": [],
        }
        _event(st, "task_received")
        _save(a.state, st)
        return
    repo = Path(st["repo"])
    if a.cmd in {"packet", "brief"}:
        _record_packet(a, st, repo)
        return
    if a.cmd == "finalize":
        _finalize(a, st)
        return
    {"search": _search, "read": _read, "edit": _edit, "verify": _verify}[a.cmd](
        a, st, repo
    )


if __name__ == "__main__":
    main()
