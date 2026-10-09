"""Compose current SCIP and request-local supplied claims under CodeMap."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from hashmarks.producer_identity import native_producer_implementation_identity

from .lsp_relationship_adapter import lsp_relationship_observation
from .scip_relationship_adapter import scip_relationship_observations
from .semantic_relationship_model import content_identity, finish_observation
from .semantic_relationship_source import RelationshipSourceResolver

if TYPE_CHECKING:
    from .engine import CodeMap


def semantic_relationship_observation(
    codemap: CodeMap,
    target: Mapping[str, Any],
    captures: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    resolver = RelationshipSourceResolver(codemap)
    subject = f"{target['path']}::{target['qualname']}"
    observations = scip_relationship_observations(codemap, target, resolver)
    observations.extend(
        lsp_relationship_observation(capture, subject, resolver) for capture in captures
    )
    freshness = codemap._query_freshness_fields()
    stale = freshness.get("stale")
    repository = {
        "scope_identity": content_identity(str(codemap.workspace)),
        "content_identity": "sha256:" + codemap._workspace_fingerprint_from_store(),
        "generation": codemap.store.generation(),
        "freshness": "current"
        if stale is False
        else "stale"
        if stale is True
        else "unknown",
        "observer_identity": native_producer_implementation_identity(),
    }
    return finish_observation(subject, repository, observations)
