from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

CODEMAP_SCHEMA = "hashmarks.codemap.v1"
PYTHON_PARSER = "hashmarks.python-ast.v5"


class EvidenceVisibility(str, Enum):
    DENY = "deny"
    OUTLINE = "outline"
    SOURCE = "source"


class ContextDisclosure(str, Enum):
    ORIENT = "orient"
    OUTLINE = "outline"
    EVIDENCE = "evidence"
    SOURCE = "source"

    @property
    def next(self) -> ContextDisclosure | None:
        order = (self.ORIENT, self.OUTLINE, self.EVIDENCE, self.SOURCE)
        index = order.index(self)
        return None if index + 1 == len(order) else order[index + 1]


@dataclass(frozen=True)
class SymbolRecord:
    name: str
    qualname: str
    kind: str
    signature: str
    start_line: int
    end_line: int
    signature_tokens: int
    body_tokens: int
    parent: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "qualname": self.qualname,
            "kind": self.kind,
            "signature": self.signature,
            "lines": [self.start_line, self.end_line],
            "signature_tokens": self.signature_tokens,
            "body_tokens": self.body_tokens,
            "parent": self.parent,
        }


@dataclass(frozen=True)
class EdgeRecord:
    source: str | None
    kind: str
    target: str
    line: int | None = None
    confidence: str = "static"

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "kind": self.kind,
            "target": self.target,
            "line": self.line,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class LexicalRecord:
    token: str
    line: int

    def as_dict(self) -> dict[str, Any]:
        return {"token": self.token, "line": self.line}


@dataclass(frozen=True)
class ParsedArtifact:
    artifact_key: str
    file_digest: str
    language: str
    parser: str
    full_tokens: int
    outline: str
    symbols: tuple[SymbolRecord, ...] = ()
    edges: tuple[EdgeRecord, ...] = ()
    lexical: tuple[LexicalRecord, ...] = ()
    parse_error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": CODEMAP_SCHEMA,
            "artifact_key": self.artifact_key,
            "file_digest": self.file_digest,
            "language": self.language,
            "parser": self.parser,
            "full_tokens": self.full_tokens,
            "outline": self.outline,
            "symbols": [value.as_dict() for value in self.symbols],
            "edges": [value.as_dict() for value in self.edges],
            "lexical": [value.as_dict() for value in self.lexical],
            "parse_error": self.parse_error,
        }


@dataclass(frozen=True)
class SearchHit:
    path: str
    score: float
    kind: str
    name: str | None = None
    qualname: str | None = None
    signature: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    evidence_visibility: EvidenceVisibility = EvidenceVisibility.SOURCE

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "score": round(self.score, 3),
            "kind": self.kind,
            "name": self.name,
            "qualname": self.qualname,
            "signature": self.signature,
            "lines": None
            if self.start_line is None
            else [self.start_line, self.end_line],
            "evidence_visibility": self.evidence_visibility.value,
        }


@dataclass(frozen=True)
class SyncResult:
    generation: int
    discovered: int
    indexed: int
    reused_artifacts: int
    parsed_artifacts: int
    removed: int
    skipped: int
    parse_errors: int
    seconds: float
    workspace_fingerprint: str
    identity_generation: int | None = None
    derived_surfaces_changed: int = 0
    derived_surfaces_preserved: int = 0
    semantic_invalidation_shields: int = 0
    base_snapshot_reused: int = 0
    base_identity: str | None = None
    overlay_paths: int = 0
    warnings: tuple[str, ...] = ()
    preflight: dict[str, Any] = field(default_factory=dict)
    economics: dict[str, Any] = field(default_factory=dict)
    build_state: str = "COMPLETE"

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": CODEMAP_SCHEMA,
            "generation": self.generation,
            "discovered": self.discovered,
            "indexed": self.indexed,
            "reused_artifacts": self.reused_artifacts,
            "parsed_artifacts": self.parsed_artifacts,
            "removed": self.removed,
            "skipped": self.skipped,
            "parse_errors": self.parse_errors,
            "seconds": self.seconds,
            "workspace_fingerprint": self.workspace_fingerprint,
            "identity_generation": self.identity_generation,
            "derived_surfaces_changed": self.derived_surfaces_changed,
            "derived_surfaces_preserved": self.derived_surfaces_preserved,
            "semantic_invalidation_shields": self.semantic_invalidation_shields,
            "base_snapshot_reused": self.base_snapshot_reused,
            "base_identity": self.base_identity,
            "overlay_paths": self.overlay_paths,
            "warnings": list(self.warnings),
            "preflight": dict(self.preflight),
            "economics": dict(self.economics),
            "build_state": self.build_state,
        }


@dataclass(frozen=True)
class ContextItem:
    path: str
    representation: str
    content: str
    estimated_tokens: int
    symbol: str | None = None
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "representation": self.representation,
            "content": self.content,
            "estimated_tokens": self.estimated_tokens,
            "symbol": self.symbol,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ContextPack:
    query: str
    budget: int
    estimated_tokens: int
    confidence: str
    abstained: bool
    generation: int
    identity_generation: int | None
    stale: bool | None
    disclosure: ContextDisclosure = ContextDisclosure.SOURCE
    cache_hit: bool = False
    shared_flight: bool = False
    context_action_hash: str | None = None
    context_result_digest: str | None = None
    items: tuple[ContextItem, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "hashmarks.context-pack.v2",
            "query": self.query,
            "budget": self.budget,
            "disclosure": self.disclosure.value,
            "next_disclosure": None
            if self.disclosure.next is None
            else self.disclosure.next.value,
            "cache": {
                "hit": self.cache_hit,
                "shared_flight": self.shared_flight,
                "action_hash": self.context_action_hash,
                "result_digest": self.context_result_digest,
            },
            "estimated_tokens": self.estimated_tokens,
            "confidence": self.confidence,
            "abstained": self.abstained,
            "generation": self.generation,
            "identity_generation": self.identity_generation,
            "stale": self.stale,
            "items": [item.as_dict() for item in self.items],
            "warnings": list(self.warnings),
        }
