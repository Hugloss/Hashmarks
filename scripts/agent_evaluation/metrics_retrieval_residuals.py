from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
from typing import TypedDict

from hashmarks._command_output import log_command_output
from hashmarks.codemap import (
    CodeMap,
)

from .metrics_blind_worker_ab import (
    _load_corpus,
    _sha256_bytes,
    materialize_challenge,
)

logger = logging.getLogger(__name__)

SCHEMA = "hashmarks.retrieval-residual-classification.v1"
FAMILY = "hashmarks-residual-classification-a"


class ResidualTaskReport(TypedDict):
    id: object
    query: str
    expected_files: list[str]
    first_edit_target: str | None
    top1_correct: bool
    expected_any_top5: bool
    all_expected_top20: bool
    ambiguous: bool
    residual_class: str


class ResidualRepositoryReport(TypedDict):
    name: str
    public_task_sha256: str
    hidden_corpus_sha256: str
    tasks: list[ResidualTaskReport]


def _task_report(
    cm: CodeMap, task: dict[str, object], secret: dict[str, object], *, limit: int
) -> ResidualTaskReport:
    query = task["query"]
    if not isinstance(query, str):
        raise ValueError("benchmark query must be a string")
    hits = cm.search.find_task(query, limit=limit)
    paths = [hit.path for hit in hits]
    expected_files = secret.get("expected_files") or ()
    if not isinstance(expected_files, (list, tuple, set)) or not all(
        isinstance(path, str) for path in expected_files
    ):
        raise ValueError("expected benchmark paths must be a collection of strings")
    expected = {str(path) for path in expected_files}
    entry = cm.tasks.entry_points(query, limit=limit)
    raw_recommended = entry.get("recommended", [])
    if not isinstance(raw_recommended, list):
        raise ValueError("task entry recommendations must be an array")
    recommended = [row for row in raw_recommended if isinstance(row, dict)]
    first = str(recommended[0].get("path") or "") if recommended else None
    top1 = first in expected
    top5 = bool(expected.intersection(paths[:5]))
    top20 = expected.issubset(set(paths[:20]))
    ambiguity = entry.get("ambiguity", {})
    ambiguous = (
        bool(ambiguity.get("ambiguous")) if isinstance(ambiguity, dict) else False
    )
    if not top20:
        residual = "discovery-miss"
    elif not top5:
        residual = "deep-ranking-miss"
    elif not top1 and ambiguous:
        residual = "role-authority-ambiguity"
    elif not top1:
        residual = "shallow-ranking-miss"
    else:
        residual = "none"
    return {
        "id": task["id"],
        "query": query,
        "expected_files": sorted(expected),
        "first_edit_target": first,
        "top1_correct": top1,
        "expected_any_top5": top5,
        "all_expected_top20": top20,
        "ambiguous": ambiguous,
        "residual_class": residual,
    }


def collect(root: Path, limit: int = 20) -> dict[str, object]:
    reports: list[ResidualRepositoryReport] = []
    for name, ws, corpus, pub in materialize_challenge(root / "challenge"):
        public = json.loads(pub.read_text())["tasks"]
        hidden = _load_corpus(corpus)
        rows = []
        with CodeMap(ws) as cm:
            cm.index.sync()
            for task, secret in zip(public, hidden, strict=False):
                rows.append(_task_report(cm, task, secret, limit=limit))
        reports.append(
            {
                "name": name,
                "public_task_sha256": _sha256_bytes(pub.read_bytes()),
                "hidden_corpus_sha256": _sha256_bytes(corpus.read_bytes()),
                "tasks": rows,
            }
        )
    rows = [x for r in reports for x in r["tasks"]]
    counts = {
        k: sum(r["residual_class"] == k for r in rows)
        for k in [
            "none",
            "role-authority-ambiguity",
            "shallow-ranking-miss",
            "deep-ranking-miss",
            "discovery-miss",
        ]
    }
    summary = {
        "repositories": len(reports),
        "tasks": len(rows),
        "top1_correct": sum(r["top1_correct"] for r in rows),
        "top5_any_expected": sum(r["expected_any_top5"] for r in rows),
        "top20_all_expected": sum(r["all_expected_top20"] for r in rows),
        "residual_counts": counts,
        "ngram_admission": counts["discovery-miss"] > 0,
        "embedding_admission": counts["discovery-miss"] > 0,
        "retrieval_subagent_admission": counts["role-authority-ambiguity"] > 0,
        "recommended_next_lane": "cheap-ambiguity-inspection"
        if counts["role-authority-ambiguity"]
        else "none",
    }
    protocol = {
        "family": FAMILY,
        "classification_order": [
            "discovery-miss",
            "deep-ranking-miss",
            "role-authority-ambiguity",
            "shallow-ranking-miss",
            "none",
        ],
        "admission_rule": "ngram/vector require observed top20 discovery residual; ambiguity-only failures do not admit new recall indexes",
        "hidden_fields": ["expected_files", "expected_symbols"],
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


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    r = collect(a.root)
    text = json.dumps(r, indent=2, sort_keys=True) + "\n"
    if a.output:
        a.output.write_text(text)
    log_command_output(logger, text, end="")


if __name__ == "__main__":
    main()
