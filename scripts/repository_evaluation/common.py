from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

CASES_SCHEMA = "hashmarks.repository-evaluation-cases.v1"
GRADER_SCHEMA = "hashmarks.repository-evaluation-grader.v1"
RUN_SCHEMA = "hashmarks.repository-evaluation-run.v1"
REPORT_SCHEMA = "hashmarks.repository-evaluation-report.v1"
COMPARISON_SCHEMA = "hashmarks.repository-evaluation-comparison.v1"


def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_json(path: Path, *, schema: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != schema:
        raise ValueError(f"unsupported schema in {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
