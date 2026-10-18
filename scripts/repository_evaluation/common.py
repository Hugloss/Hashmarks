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


def evaluator_implementation_identity() -> str:
    """Bind durable evaluation work to the code interpreting its inputs."""
    from pathlib import Path

    root = Path(__file__).parent
    inputs = {path.name: path.read_bytes().hex() for path in sorted(root.glob("*.py"))}
    for relative in (
        "scripts/native_evidence_capture.py",
        "scripts/native_lsp_capture.py",
        "benchmarks/research_receipts.py",
    ):
        inputs[relative] = (root.parents[1] / relative).read_bytes().hex()
    return "sha256:" + canonical_sha256(inputs)
