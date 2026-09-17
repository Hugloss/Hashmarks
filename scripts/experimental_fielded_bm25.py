from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_WORD = re.compile(r"[A-Za-z0-9]+")
_SKIP_ROOTS = {".git", ".hashmarks", ".venv", "node_modules"}


def code_terms(value: str) -> list[str]:
    """Code-aware lexical terms for BM25 without external dependencies."""
    out: list[str] = []
    for raw in _WORD.findall(
        value.replace("_", " ").replace("-", " ").replace("/", " ").replace(".", " ")
    ):
        pieces = [p for p in _CAMEL.split(raw) if p]
        normalized = [p.casefold() for p in pieces if len(p) > 1]
        joined = "".join(normalized)
        if len(raw) > 1:
            out.append(raw.casefold())
        out.extend(normalized)
        if joined and joined not in out:
            out.append(joined)
        for left, right in zip(normalized, normalized[1:], strict=False):
            out.append(left + right)
    return out


@dataclass(frozen=True)
class BM25Hit:
    path: str
    score: float
    matched_fields: tuple[str, ...]


class FieldedBM25Index:
    """Small experimental fielded BM25 lane over one synchronized CodeMap.

    It is deliberately additive: no canonical `find_task()` behavior changes.
    The index is built from already-known repository paths/symbols plus current
    source bytes and static edge targets. It exists to measure whether BM25 earns
    enough agent value before becoming persistent runtime infrastructure.
    """

    FIELD_WEIGHTS = {
        "symbol": 5.0,
        "signature": 4.0,
        "path": 3.0,
        "imports": 2.0,
        "body": 1.0,
    }

    def __init__(
        self, workspace: Path, documents: dict[str, dict[str, Counter[str]]]
    ) -> None:
        self.workspace = workspace
        self.documents = documents
        self._field_lengths: dict[str, dict[str, int]] = {}
        self._dfs: dict[str, dict[str, int]] = {}
        for field in self.FIELD_WEIGHTS:
            lengths: dict[str, int] = {}
            df: dict[str, int] = defaultdict(int)
            for path, fields in documents.items():
                counter = fields.get(field, Counter())
                lengths[path] = sum(counter.values())
                for token in counter:
                    df[token] += 1
            self._field_lengths[field] = lengths
            self._dfs[field] = dict(df)

    @classmethod
    def build(cls, codemap) -> FieldedBM25Index:
        workspace = Path(codemap.workspace)
        paths = sorted(codemap.store.paths())
        symbols = codemap.store.symbols_for_paths(
            paths, limit=max(5000, len(paths) * 100)
        )
        symbols_by_path: dict[str, list[dict]] = defaultdict(list)
        for row in symbols:
            symbols_by_path[str(row.get("path") or "")].append(row)
        edges_by_path: dict[str, list[dict]] = defaultdict(list)
        for row in codemap.store.all_edges():
            edges_by_path[str(row.get("path") or "")].append(row)
        documents: dict[str, dict[str, Counter[str]]] = {}
        for rel in paths:
            p = workspace / rel
            if not p.is_file() or any(part in _SKIP_ROOTS for part in Path(rel).parts):
                continue
            try:
                body = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                body = ""
            symbol_text = " ".join(
                str(r.get("name") or "") + " " + str(r.get("qualname") or "")
                for r in symbols_by_path.get(rel, ())
            )
            signature_text = " ".join(
                str(r.get("signature") or "") for r in symbols_by_path.get(rel, ())
            )
            imports_text = " ".join(
                str(r.get("target") or "") for r in edges_by_path.get(rel, ())
            )
            documents[rel] = {
                "path": Counter(code_terms(rel)),
                "symbol": Counter(code_terms(symbol_text)),
                "signature": Counter(code_terms(signature_text)),
                "imports": Counter(code_terms(imports_text)),
                "body": Counter(code_terms(body)),
            }
        return cls(workspace, documents)

    def search(
        self, query: str, *, limit: int = 20, k1: float = 1.2, b: float = 0.75
    ) -> list[BM25Hit]:
        terms = code_terms(query)
        if not terms or not self.documents:
            return []
        n_docs = len(self.documents)
        field_avg = {
            field: (sum(lengths.values()) / n_docs if n_docs else 0.0)
            for field, lengths in self._field_lengths.items()
        }
        scores: dict[str, float] = defaultdict(float)
        matched: dict[str, set[str]] = defaultdict(set)
        for field, weight in self.FIELD_WEIGHTS.items():
            avg_len = field_avg[field] or 1.0
            dfs = self._dfs[field]
            lengths = self._field_lengths[field]
            for term in terms:
                df = dfs.get(term, 0)
                if not df:
                    continue
                idf = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
                for path, fields in self.documents.items():
                    tf = fields[field].get(term, 0)
                    if not tf:
                        continue
                    dl = lengths[path]
                    norm = tf + k1 * (1.0 - b + b * dl / avg_len)
                    scores[path] += weight * idf * (tf * (k1 + 1.0) / norm)
                    matched[path].add(field)
        ranked = sorted(scores, key=lambda path: (-scores[path], path))[:limit]
        return [
            BM25Hit(
                path=path,
                score=scores[path],
                matched_fields=tuple(sorted(matched[path])),
            )
            for path in ranked
        ]
