from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hashmarks.codemap import CodeMap
from scripts.repository_evaluation.common import write_json

SCHEMA = "hashmarks.retrieval-order-characterization.v2"


def _content_identity(root: Path) -> str:
    digest = hashlib.sha256()
    count = 0
    for path in sorted(path for path in root.rglob("*") if path.is_file()):
        rel = path.relative_to(root).as_posix().encode("utf-8")
        payload = path.read_bytes()
        digest.update(len(rel).to_bytes(8, "big"))
        digest.update(rel)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
        count += 1
    return f"sha256:{digest.hexdigest()}:{count}"


def _build_repository(root: Path, *, files: int) -> dict[str, str]:
    originals: dict[str, str] = {}
    for index in range(files):
        rel = f"module_{index:04d}.py"
        text = f"def broadneedle_{index:04d}():\n    return {index}\n"
        (root / rel).write_text(text, encoding="utf-8")
        originals[rel] = text
    return originals


def _broad_rows(codemap: CodeMap, *, limit: int) -> list[tuple[str, str]]:
    return [
        (str(row.get("path") or ""), str(row.get("qualname") or ""))
        for row in codemap.store.search_candidates("needle", limit=limit)
        if row.get("row_type") == "symbol"
    ]


def _find_rows(codemap: CodeMap, *, limit: int) -> list[tuple[str, str]]:
    return [
        (hit.path, str(hit.qualname or ""))
        for hit in codemap.find("needle", limit=limit)
    ]


def _planner(codemap: CodeMap, *, limit: int) -> dict[str, list[str]]:
    q = "%needle%"
    symbol_sql = """
        EXPLAIN QUERY PLAN
        SELECT s.*, f.evidence_visibility
        FROM symbol s JOIN file_map f ON f.path=s.path
        WHERE lower(s.name) LIKE ? OR lower(s.qualname) LIKE ?
           OR lower(s.signature) LIKE ? OR lower(s.path) LIKE ?
        ORDER BY s.path,s.start_line,s.qualname
        LIMIT ?
    """
    file_sql = """
        EXPLAIN QUERY PLAN
        SELECT path,language,evidence_visibility,full_tokens,outline
        FROM file_map WHERE lower(path) LIKE ? ORDER BY path LIMIT ?
    """
    with codemap.store._lock:  # evaluation-only introspection
        symbol = codemap.store._db.execute(symbol_sql, (q, q, q, q, limit)).fetchall()
        files = codemap.store._db.execute(file_sql, (q, limit)).fetchall()
    return {
        "symbol": [str(row[3]) for row in symbol],
        "file": [str(row[3]) for row in files],
    }


def _cold_run(
    root: Path, state: Path, *, broad_limit: int, find_limit: int
) -> dict[str, Any]:
    with CodeMap(
        root, state_dir=state, artifact_db=state / "artifacts.sqlite3"
    ) as codemap:
        codemap.sync()
        return {
            "content_identity": _content_identity(root),
            "broad_rows": _broad_rows(codemap, limit=broad_limit),
            "find_rows": _find_rows(codemap, limit=find_limit),
            "planner": _planner(codemap, limit=broad_limit),
        }


def characterize_retrieval_order(
    *, files: int = 140, broad_limit: int = 50, find_limit: int = 20
) -> dict[str, Any]:
    if files <= broad_limit or broad_limit < 1 or find_limit < 1:
        raise ValueError("files must exceed broad_limit and limits must be positive")

    with tempfile.TemporaryDirectory(prefix="hashmarks-order-characterization-") as td:
        base = Path(td)
        root = base / "repo"
        root.mkdir()
        originals = _build_repository(root, files=files)
        initial_identity = _content_identity(root)

        cold_a = _cold_run(
            root, base / "state-a", broad_limit=broad_limit, find_limit=find_limit
        )
        cold_b = _cold_run(
            root, base / "state-b", broad_limit=broad_limit, find_limit=find_limit
        )

        state = base / "state-history"
        with CodeMap(
            root, state_dir=state, artifact_db=state / "artifacts.sqlite3"
        ) as codemap:
            codemap.sync()
            before_broad = _broad_rows(codemap, limit=broad_limit)
            before_find = _find_rows(codemap, limit=find_limit)
            if not before_broad:
                raise RuntimeError(
                    "characterization query produced no broad candidates"
                )
            target = before_broad[0][0]
            target_path = root / target
            target_path.write_text(
                "def unrelated_name():\n    return -1\n", encoding="utf-8"
            )
            codemap.sync([target])
            target_path.write_text(originals[target], encoding="utf-8")
            codemap.sync([target])
            restored_identity = _content_identity(root)
            after_broad = _broad_rows(codemap, limit=broad_limit)
            after_find = _find_rows(codemap, limit=find_limit)
            history_planner = _planner(codemap, limit=broad_limit)

        same_content = initial_identity == restored_identity
        broad_changed = before_broad != after_broad
        find_changed = before_find != after_find
        decision = (
            "STABLE_CONTRACT_SATISFIED"
            if same_content and not broad_changed and not find_changed
            else "STABLE_CONTRACT_VIOLATED"
        )
        return {
            "schema": SCHEMA,
            "authority": "retrieval-contract-verification",
            "query": "needle",
            "files": files,
            "broad_limit": broad_limit,
            "find_limit": find_limit,
            "cold_run_stable": cold_a["broad_rows"] == cold_b["broad_rows"]
            and cold_a["find_rows"] == cold_b["find_rows"],
            "same_content_after_aba": same_content,
            "broad_subset_changed_after_aba": broad_changed,
            "find_result_changed_after_aba": find_changed,
            "initial_content_identity": initial_identity,
            "restored_content_identity": restored_identity,
            "before_broad": before_broad,
            "after_broad": after_broad,
            "before_find": before_find,
            "after_find": after_find,
            "cold_planner": cold_a["planner"],
            "history_planner": history_planner,
            "decision": decision,
            "contract_basis": (
                "repository content identity must determine capped fallback retrieval; "
                "SQLite row history must not change the visible subset"
            ),
            "product_contract_enforced": True,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--files", type=int, default=140)
    parser.add_argument("--broad-limit", type=int, default=50)
    parser.add_argument("--find-limit", type=int, default=20)
    args = parser.parse_args()
    write_json(
        args.output,
        characterize_retrieval_order(
            files=args.files,
            broad_limit=args.broad_limit,
            find_limit=args.find_limit,
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
