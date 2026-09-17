from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .model import ParsedArtifact

DERIVED_GRAPH_SCHEMA = "hashmarks.codemap-derived-graph.v1"
DERIVED_NODE_SCHEMA = "hashmarks.codemap-derived-node.v1"
PRODUCER = "hashmarks.codemap-derived.v1"


def _identity(domain: str, value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return (
        "sha256:" + hashlib.sha256(domain.encode("utf-8") + b"\0" + payload).hexdigest()
    )


@dataclass(frozen=True)
class DerivedNode:
    path: str
    kind: str
    identity: str
    dependencies: tuple[str, ...]
    input_identities: tuple[str, ...]
    producer: str = PRODUCER

    @property
    def node_id(self) -> str:
        return f"{self.path}::{self.kind}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": DERIVED_NODE_SCHEMA,
            "node_id": self.node_id,
            "path": self.path,
            "kind": self.kind,
            "identity": self.identity,
            "dependencies": list(self.dependencies),
            "input_identities": list(self.input_identities),
            "producer": self.producer,
        }


def derive_file_nodes(path: str, artifact: ParsedArtifact) -> tuple[DerivedNode, ...]:
    """Derive stable semantic surfaces without changing retrieval behavior.

    A node identity represents the *derived value*, while input_identities record
    which upstream values were consumed to compute it.  Keeping those separate
    is intentional: a future invalidation shield can recompute after source-byte
    change and stop propagation when the semantic identity remains unchanged.
    """
    content_id = _identity(
        "hashmarks.codemap-derived.content.v1",
        {
            "file_digest": artifact.file_digest,
            "language": artifact.language,
            "parser": artifact.parser,
        },
    )
    content = DerivedNode(path, "content", content_id, (), ())

    symbol_value = [
        {
            "name": s.name,
            "qualname": s.qualname,
            "kind": s.kind,
            "signature": s.signature,
            "parent": s.parent,
        }
        for s in artifact.symbols
    ]
    symbol_id = _identity("hashmarks.codemap-derived.symbol-surface.v1", symbol_value)
    symbols = DerivedNode(
        path, "symbol_surface", symbol_id, (content.node_id,), (content.identity,)
    )

    relationship_value = [
        {
            "source": e.source,
            "kind": e.kind,
            "target": e.target,
            "confidence": e.confidence,
        }
        for e in artifact.edges
    ]
    relationship_id = _identity(
        "hashmarks.codemap-derived.relationship-surface.v1", relationship_value
    )
    relationships = DerivedNode(
        path,
        "relationship_surface",
        relationship_id,
        (content.node_id, symbols.node_id),
        (content.identity, symbols.identity),
    )

    outline = DerivedNode(
        path,
        "outline_surface",
        _identity("hashmarks.codemap-derived.outline-surface.v1", artifact.outline),
        (symbols.node_id,),
        (symbols.identity,),
    )

    lexical_value = [
        {"token": item.token, "line": item.line} for item in artifact.lexical
    ]
    lexical_id = _identity(
        "hashmarks.codemap-derived.lexical-surface.v1", lexical_value
    )
    lexical = DerivedNode(
        path, "lexical_surface", lexical_id, (content.node_id,), (content.identity,)
    )
    return (content, symbols, relationships, outline, lexical)
