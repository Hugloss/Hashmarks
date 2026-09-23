from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

from hashmarks.codemap import CodeMap
from hashmarks.codemap.python_ast import estimate_tokens

SCHEMA = "hashmarks.agent-metrics.v1"


def _timed(fn):
    started = time.perf_counter()
    value = fn()
    return value, time.perf_counter() - started


def _fixture(root: Path, files: int) -> tuple[str, int]:
    src = root / "src"
    src.mkdir(parents=True)
    total_tokens = 0
    target_symbol = "CriticalAuthFlow"
    for idx in range(files):
        name = f"module_{idx:05d}.py"
        if idx == files // 2:
            body = (
                "from src.module_00000 import helper_00000\n\n"
                "class CriticalAuthFlow:\n"
                "    def validate_expired_token(self, token: str) -> bool:\n"
                "        return helper_00000(token)\n\n"
                "def unrelated_local():\n"
                "    return 1\n"
            )
        else:
            body = (
                f"def helper_{idx:05d}(value=None):\n"
                f"    return value if value is not None else {idx}\n\n"
                f"class Service{idx:05d}:\n"
                "    def run(self):\n"
                f"        return helper_{idx:05d}()\n"
            )
        (src / name).write_text(body, encoding="utf-8")
        total_tokens += estimate_tokens(body)
    return target_symbol, total_tokens


def collect(*, files: int = 1000, budget: int = 1000) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="hashmarks-agent-metrics-") as td:
        root = Path(td)
        target, repo_tokens = _fixture(root, files)
        artifact_db = root / "artifact-cache.sqlite3"
        with CodeMap(root, artifact_db=artifact_db) as codemap:
            syncs = {}
            seconds = {}
            syncs["cold"], seconds["cold_sync"] = _timed(codemap.sync)
            syncs["hot"], seconds["hot_sync"] = _timed(codemap.sync)
            hits, seconds["find"] = _timed(
                lambda: codemap.find("CriticalAuthFlow expired token", limit=10)
            )
            pack, seconds["context"] = _timed(
                lambda: codemap.context(
                    "CriticalAuthFlow expired token", token_budget=budget, limit=10
                )
            )
            target_path = f"src/module_{files // 2:05d}.py"
            target_file = root / target_path
            target_file.write_text(
                target_file.read_text(encoding="utf-8")
                + "\ndef new_branch():\n    return True\n",
                encoding="utf-8",
            )
            syncs["edit"], seconds["one_file_reindex"] = _timed(
                lambda: codemap.sync([target_path])
            )
            stats = codemap.status()

        return {
            "schema": SCHEMA,
            "parameters": {"files": files, "budget": budget},
            "seconds": seconds,
            "index": {
                "cold_parsed": syncs["cold"].parsed_artifacts,
                "hot_parsed": syncs["hot"].parsed_artifacts,
                "hot_reused": syncs["hot"].reused_artifacts,
                "edit_parsed": syncs["edit"].parsed_artifacts,
                "files": stats["files"],
                "symbols": stats["symbols"],
                "edges": stats["edges"],
            },
            "retrieval": {
                "target_symbol": target,
                "target_present_top10": any(hit.qualname == target for hit in hits),
                "first_hit": hits[0].qualname if hits else None,
                "confidence": pack.confidence,
                "abstained": pack.abstained,
            },
            "tokens": {
                "indexed_source_estimate": repo_tokens,
                "context_estimate": pack.estimated_tokens,
                "budget": budget,
                "source_to_context_ratio": None
                if pack.estimated_tokens == 0
                else repo_tokens / pack.estimated_tokens,
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure Hashmarks CodeMap/agent-context efficiency"
    )
    parser.add_argument("--files", type=int, default=1000)
    parser.add_argument("--budget", type=int, default=1000)
    args = parser.parse_args()
    print(  # noqa: T201 - intentional command output
        json.dumps(
            collect(files=args.files, budget=args.budget), indent=2, sort_keys=True
        )
    )


if __name__ == "__main__":
    main()
